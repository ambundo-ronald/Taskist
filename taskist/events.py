import hashlib
import json

import frappe
from frappe.utils import get_datetime, now_datetime

from taskist.access import check_task_view


TERMINAL_EVENTS = {"Completed", "Cancelled"}
ACTIVE_EVENTS = {"Started", "Returned for Correction"}
WAITING_EVENTS = {"Created", "Assigned", "Reassigned", "Review Requested", "Handoff Received"}


def _event_key(task, event_type, dedupe_key):
	if not dedupe_key:
		return None
	value = f"{task}|{event_type}|{dedupe_key}"
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _task_context(task_name):
	return frappe.db.get_value(
		"Task",
		task_name,
		[
			"taskist_reference_doctype",
			"taskist_reference_name",
			"taskist_process_rule",
		],
		as_dict=True,
	) or {}


def record_event(
	task,
	event_type,
	tracker=None,
	actor=None,
	previous_value=None,
	new_value=None,
	notes=None,
	metadata=None,
	event_time=None,
	dedupe_key=None,
):
	"""Append an immutable task/SLA event. Failures never block operational work."""
	try:
		if not task or not frappe.db.exists("Task", task):
			return None
		key = _event_key(task, event_type, dedupe_key)
		if key and frappe.db.exists("Taskist SLA Event", {"event_key": key}):
			return None
		context = _task_context(task)
		process_rule = context.get("taskist_process_rule")
		department = (
			frappe.db.get_value("Taskist Process Rule", process_rule, "department")
			if process_rule
			else None
		)
		event = frappe.new_doc("Taskist SLA Event")
		event.event_type = event_type
		event.event_time = event_time or now_datetime()
		event.task = task
		event.tracker = tracker
		event.reference_doctype = context.get("taskist_reference_doctype")
		event.reference_name = context.get("taskist_reference_name")
		event.process_rule = process_rule
		event.department = department
		event.actor = actor or frappe.session.user
		event.previous_value = str(previous_value)[:1000] if previous_value is not None else None
		event.new_value = str(new_value)[:1000] if new_value is not None else None
		event.notes = str(notes)[:1000] if notes else None
		event.event_key = key
		event.metadata_json = json.dumps(metadata, default=str, sort_keys=True) if metadata else None
		event.insert(ignore_permissions=True)
		return event.name
	except frappe.DuplicateEntryError:
		return None
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Taskist SLA Event")
		return None


def record_task_change(doc, method=None):
	"""Translate native Task lifecycle changes into audit events."""
	if getattr(frappe.flags, "in_taskist_event_log", False):
		return
	previous = doc.get_doc_before_save() if not doc.is_new() else None
	if method == "after_insert" or not previous:
		record_event(
			doc.name,
			"Created",
			new_value=doc.status,
			notes=doc.subject,
			metadata={
				"process_rule": doc.get("taskist_process_rule"),
				"trigger_event": doc.get("taskist_process_trigger_event"),
				"source_doctype": doc.get("taskist_reference_doctype"),
				"source_name": doc.get("taskist_reference_name"),
			},
			event_time=doc.creation,
			dedupe_key=f"created:{doc.name}",
		)
		return
	if previous.status == doc.status:
		return

	if previous.status == "Pending Review" and doc.status == "Completed":
		record_event(
			doc.name,
			"Reviewed",
			previous_value=previous.status,
			new_value=doc.status,
			notes="Work was accepted after review.",
			dedupe_key=f"reviewed:{doc.modified}",
		)
	event_type = {
		"Working": "Started",
		"Pending Review": "Review Requested",
		"Completed": "Completed",
		"Cancelled": "Cancelled",
	}.get(doc.status, "Status Changed")
	if previous.status in ("Completed", "Cancelled") and doc.status not in ("Completed", "Cancelled"):
		event_type = "Reopened"
	record_event(
		doc.name,
		event_type,
		previous_value=previous.status,
		new_value=doc.status,
		dedupe_key=f"status:{doc.modified}:{previous.status}:{doc.status}",
	)


def record_attachment_event(doc, method=None):
	if doc.attached_to_doctype != "Task" or not doc.attached_to_name:
		return
	record_event(
		doc.attached_to_name,
		"Attachment Added",
		new_value=doc.file_name,
		dedupe_key=f"attachment-added:{doc.name}",
	)


def _state_for_event(event, current_state):
	event_type = event.event_type
	new_value = event.new_value
	if event_type in TERMINAL_EVENTS:
		return "closed"
	if event_type == "Paused":
		return "paused"
	if event_type in ("Resumed", "Reopened"):
		return "active" if new_value == "Working" else "waiting"
	if event_type in ACTIVE_EVENTS:
		return "active"
	if event_type in WAITING_EVENTS:
		return "waiting"
	if event_type == "Status Changed":
		if new_value == "Working":
			return "active"
		if new_value in ("Completed", "Cancelled"):
			return "closed"
		if new_value in ("Open", "Pending Review", "Overdue"):
			return "waiting"
	return current_state


def _duration_metrics(events, as_of=None):
	if not events:
		return {"active_minutes": 0, "waiting_minutes": 0, "paused_minutes": 0, "handoff_minutes": 0}

	totals = {"active": 0.0, "waiting": 0.0, "paused": 0.0}
	state = "waiting"
	last_time = get_datetime(events[0].event_time)
	current_time = get_datetime(as_of) if as_of else now_datetime()
	handoff_started = None
	handoff_seconds = 0.0

	for event in events:
		event_time = get_datetime(event.event_time)
		elapsed = max((event_time - last_time).total_seconds(), 0)
		if state in totals:
			totals[state] += elapsed

		if event.event_type in ("Assigned", "Reassigned", "Handoff Received"):
			handoff_started = event_time
		elif event.event_type in ("Acknowledged", "Started") and handoff_started:
			handoff_seconds += max((event_time - handoff_started).total_seconds(), 0)
			handoff_started = None
		elif event.event_type in TERMINAL_EVENTS:
			handoff_started = None

		state = _state_for_event(event, state)
		last_time = event_time

	if state != "closed":
		elapsed = max((current_time - last_time).total_seconds(), 0)
		if state in totals:
			totals[state] += elapsed
		if handoff_started:
			handoff_seconds += max((current_time - handoff_started).total_seconds(), 0)

	return {
		"active_minutes": round(totals["active"] / 60),
		"waiting_minutes": round(totals["waiting"] / 60),
		"paused_minutes": round(totals["paused"] / 60),
		"handoff_minutes": round(handoff_seconds / 60),
	}


@frappe.whitelist()
def get_task_timeline(task_name):
	check_task_view(task_name)
	frappe.has_permission("Task", doc=task_name, throw=True)
	events = frappe.get_all(
		"Taskist SLA Event",
		filters={"task": task_name},
		fields=[
			"name",
			"event_type",
			"event_time",
			"actor",
			"tracker",
			"reference_doctype",
			"reference_name",
			"previous_value",
			"new_value",
			"notes",
			"metadata_json",
		],
		order_by="event_time asc, creation asc",
		limit_page_length=2000,
	)
	for event in events:
		event.event_time = str(event.event_time)
		if event.metadata_json:
			try:
				event.metadata = json.loads(event.metadata_json)
			except (json.JSONDecodeError, TypeError):
				event.metadata = {}
		else:
			event.metadata = {}
		event.pop("metadata_json", None)
	return {"events": events, "metrics": _duration_metrics(events)}
