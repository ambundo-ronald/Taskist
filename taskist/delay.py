from datetime import datetime, timedelta

import frappe
from frappe.utils import add_to_date, get_datetime, get_time, now_datetime

from taskist.access import can_manage_all_tasks, check_task_update, check_task_view


def _active_tracker(task_name):
	name = frappe.db.get_value(
		"Taskist SLA Tracker",
		{"task": task_name, "status": ["in", ["Open", "Warning", "Breached", "Paused"]]},
		"name",
		order_by="due_at asc",
	)
	return frappe.get_doc("Taskist SLA Tracker", name) if name else None


def _service_minutes_between(rule, start, end):
	start = get_datetime(start)
	end = get_datetime(end)
	if end <= start:
		return 0
	if not rule.apply_working_hours:
		return max(int((end - start).total_seconds() // 60), 0)

	work_start = get_time(rule.working_hours_start or "08:00:00")
	work_end = get_time(rule.working_hours_end or "17:00:00")
	holidays = {
		row.holiday_date
		for row in frappe.get_all(
			"Holiday",
			filters={"parent": rule.holiday_list},
			fields=["holiday_date"],
			limit_page_length=1000,
		)
	} if rule.holiday_list else set()

	total = 0
	current_date = start.date()
	while current_date <= end.date():
		if current_date.weekday() < 5 and current_date not in holidays:
			day_start = datetime.combine(current_date, work_start)
			day_end = datetime.combine(current_date, work_end)
			overlap_start = max(start, day_start)
			overlap_end = min(end, day_end)
			if overlap_end > overlap_start:
				total += int((overlap_end - overlap_start).total_seconds() // 60)
		current_date += timedelta(days=1)
	return total


def _shift_datetime(rule, value, minutes):
	if not value or not minutes:
		return value
	from taskist.sla import _add_service_minutes

	return _add_service_minutes(rule, get_datetime(value), minutes)


def _log_delay(task, tracker, action, delay_reason, notes):
	log = frappe.new_doc("Taskist Delay Log")
	log.task = task
	log.tracker = tracker
	log.action = action
	log.delay_reason = delay_reason
	log.notes = notes
	log.logged_by = frappe.session.user
	log.logged_on = now_datetime()
	log.insert(ignore_permissions=True)
	from taskist.events import record_event

	event_type = {
		"Breached Completion": "Status Changed",
		"Returned for Correction": "Returned for Correction",
		"Extension Requested": "Extension Requested",
		"Extension Approved": "Extension Approved",
		"Extension Rejected": "Extension Rejected",
		"Pause Request": "Pause Requested",
		"Pause Rejected": "Pause Rejected",
		"Pause Resumed": None,
	}.get(action, "Status Changed")
	if event_type:
		record_event(
			task,
			event_type,
			tracker=tracker,
			new_value=delay_reason,
			notes=notes,
			metadata={"delay_log": log.name, "delay_action": action, "delay_reason": delay_reason},
			event_time=log.logged_on,
			dedupe_key=f"delay-log:{log.name}",
		)
	return log


def _validate_reason_and_evidence(task_name, delay_reason):
	if not delay_reason:
		frappe.throw("Select a delay reason.")
	reason = frappe.get_doc("Taskist Delay Reason", delay_reason)
	if not reason.enabled:
		frappe.throw("Select an enabled Taskist Delay Reason.")
	if reason.evidence_required and not frappe.db.count(
		"File",
		{"attached_to_doctype": "Task", "attached_to_name": task_name},
	):
		frappe.throw(
			f"{reason.name} requires supporting evidence. Attach a file to the Task before continuing."
		)
	return reason


def require_breach_explanation(task_name, delay_reason=None, notes=None):
	tracker = frappe.db.get_value(
		"Taskist SLA Tracker",
		{"task": task_name, "status": "Breached"},
		"name",
		order_by="due_at asc",
	)
	if not tracker:
		return None
	if not delay_reason or not notes:
		frappe.throw("A delay reason and explanation are required to complete a breached task.")
	_validate_reason_and_evidence(task_name, delay_reason)
	return _log_delay(task_name, tracker, "Breached Completion", delay_reason, notes)


def validate_task_sla_transition(doc, method=None):
	"""Govern deadline extensions, rework, and breached completion."""
	if doc.is_new():
		return
	previous = doc.get_doc_before_save()
	approved_extensions = getattr(frappe.flags, "taskist_approved_extensions", set()) or set()
	if (
		previous
		and previous.exp_end_date
		and doc.exp_end_date
		and get_datetime(doc.exp_end_date) > get_datetime(previous.exp_end_date)
		and doc.name not in approved_extensions
		and _active_tracker(doc.name)
	):
		frappe.throw("Request an SLA deadline extension instead of changing the Task end date directly.")
	explanations = getattr(frappe.flags, "taskist_delay_explanations", {}) or {}
	explanation = explanations.get(doc.name, {})
	if previous and previous.status == "Pending Review" and doc.status in ("Open", "Working"):
		if not explanation.get("delay_reason") or not explanation.get("notes"):
			frappe.throw("A reason and explanation are required when returning work for correction.")
		_validate_reason_and_evidence(doc.name, explanation.get("delay_reason"))
		tracker = _active_tracker(doc.name)
		_log_delay(
			doc.name,
			tracker.name if tracker else None,
			"Returned for Correction",
			explanation.get("delay_reason"),
			explanation.get("notes"),
		)
		return
	if doc.status != "Completed" or (previous and previous.status == "Completed"):
		return
	if not explanation and getattr(frappe.flags, "in_taskist_assignment_sync", False):
		explanation = {
			"delay_reason": "Source Assignment Closed",
			"notes": "The linked Frappe assignment was closed.",
		}
	require_breach_explanation(
		doc.name,
		explanation.get("delay_reason"),
		explanation.get("notes"),
	)


def save_with_delay_explanation(task, delay_reason=None, notes=None):
	explanations = getattr(frappe.flags, "taskist_delay_explanations", {}) or {}
	previous = explanations.get(task.name)
	explanations[task.name] = {"delay_reason": delay_reason, "notes": notes}
	frappe.flags.taskist_delay_explanations = explanations
	try:
		task.save(ignore_permissions=False)
	finally:
		if previous is None:
			explanations.pop(task.name, None)
		else:
			explanations[task.name] = previous


@frappe.whitelist()
def get_delay_reasons(pause_eligible=None):
	filters = {"enabled": 1}
	if pause_eligible is not None:
		filters["pause_eligible"] = int(pause_eligible)
	return frappe.get_all(
		"Taskist Delay Reason",
		filters=filters,
		fields=["name", "category", "responsible_party", "pause_eligible", "evidence_required"],
		order_by="reason_name asc",
		limit_page_length=200,
	)


@frappe.whitelist()
def get_task_pause_state(task_name):
	check_task_view(task_name)
	tracker = _active_tracker(task_name)
	if not tracker:
		return {"tracker": None, "pause": None}
	pause = None
	if tracker.active_pause and frappe.db.exists("Taskist SLA Pause", tracker.active_pause):
		pause = frappe.get_doc("Taskist SLA Pause", tracker.active_pause).as_dict()
	return {
		"tracker": {
			"name": tracker.name,
			"status": tracker.status,
			"pause_status": tracker.pause_status,
			"total_paused_minutes": tracker.total_paused_minutes,
		},
		"pause": pause,
		"can_approve": can_manage_all_tasks(),
	}


@frappe.whitelist()
def request_sla_pause(task_name, delay_reason, notes):
	check_task_update(task_name)
	tracker = _active_tracker(task_name)
	if not tracker:
		frappe.throw("This task has no active SLA tracker.")
	if tracker.pause_status in ("Requested", "Paused"):
		frappe.throw("This SLA already has a pending or active pause.")
	reason = _validate_reason_and_evidence(task_name, delay_reason)
	if not reason.enabled or not reason.pause_eligible:
		frappe.throw("This delay reason is not eligible to pause an SLA.")
	if not notes:
		frappe.throw("Explain why the SLA should be paused.")

	pause = frappe.new_doc("Taskist SLA Pause")
	pause.tracker = tracker.name
	pause.task = task_name
	pause.delay_reason = reason.name
	pause.status = "Requested"
	pause.notes = notes
	pause.requested_by = frappe.session.user
	pause.requested_on = now_datetime()
	pause.insert(ignore_permissions=True)

	tracker.pause_status = "Requested"
	tracker.active_pause = pause.name
	tracker.save(ignore_permissions=True)
	_log_delay(task_name, tracker.name, "Pause Request", reason.name, notes)
	return get_task_pause_state(task_name)


def _pending_extension(task_name):
	return frappe.db.get_value(
		"Taskist SLA Extension",
		{"task": task_name, "status": "Requested"},
		"name",
	)


@frappe.whitelist()
def get_task_extension_state(task_name):
	check_task_view(task_name)
	tracker = _active_tracker(task_name)
	pending = _pending_extension(task_name)
	return {
		"tracker": tracker.name if tracker else None,
		"current_due_at": str(tracker.due_at) if tracker and tracker.due_at else None,
		"extension": frappe.get_doc("Taskist SLA Extension", pending).as_dict() if pending else None,
		"can_approve": can_manage_all_tasks(),
	}


@frappe.whitelist()
def get_compliance_exceptions():
	if not can_manage_all_tasks():
		frappe.throw("Only Taskist Managers can view compliance exceptions.", frappe.PermissionError)
	from taskist.taskist.report.taskist_compliance_exceptions.taskist_compliance_exceptions import get_data

	return get_data()


@frappe.whitelist()
def request_sla_extension(task_name, requested_due_at, delay_reason, notes):
	check_task_update(task_name)
	tracker = _active_tracker(task_name)
	if not tracker:
		frappe.throw("This task has no active SLA tracker.")
	if tracker.pause_status == "Paused":
		frappe.throw("Resume the paused SLA before requesting a deadline extension.")
	if _pending_extension(task_name):
		frappe.throw("This task already has a pending deadline extension.")
	requested_due_at = get_datetime(requested_due_at)
	if requested_due_at <= get_datetime(tracker.due_at):
		frappe.throw("The requested deadline must be later than the current SLA deadline.")
	reason = _validate_reason_and_evidence(task_name, delay_reason)
	if not notes:
		frappe.throw("Explain why the deadline should be extended.")

	extension = frappe.new_doc("Taskist SLA Extension")
	extension.tracker = tracker.name
	extension.task = task_name
	extension.delay_reason = reason.name
	extension.status = "Requested"
	extension.current_due_at = tracker.due_at
	extension.requested_due_at = requested_due_at
	extension.notes = notes
	extension.requested_by = frappe.session.user
	extension.requested_on = now_datetime()
	extension.insert(ignore_permissions=True)
	_log_delay(task_name, tracker.name, "Extension Requested", reason.name, notes)
	return get_task_extension_state(task_name)


@frappe.whitelist()
def decide_sla_extension(extension_name, approve, decision_notes=None):
	if not can_manage_all_tasks():
		frappe.throw("Only Taskist Managers can approve SLA extensions.", frappe.PermissionError)
	extension = frappe.get_doc("Taskist SLA Extension", extension_name)
	if extension.status != "Requested":
		frappe.throw("Only requested extensions can be approved or rejected.")
	tracker = frappe.get_doc("Taskist SLA Tracker", extension.tracker)
	now = now_datetime()
	extension.decided_by = frappe.session.user
	extension.decided_on = now
	extension.decision_notes = decision_notes

	if int(approve):
		rule = frappe.get_doc("Taskist SLA Rule", tracker.rule)
		minutes = _service_minutes_between(rule, tracker.due_at, extension.requested_due_at)
		tracker.warning_at = _shift_datetime(rule, tracker.warning_at, minutes)
		tracker.due_at = extension.requested_due_at
		tracker.warning_sent_on = None
		tracker.breach_sent_on = None
		tracker.current_escalation_level = 0
		tracker.escalations_sent_json = None
		if tracker.status == "Breached" and get_datetime(tracker.due_at) > now:
			tracker.status = "Warning" if tracker.warning_at and get_datetime(tracker.warning_at) <= now else "Open"
			tracker.breached_on = None
		stale_deliveries = frappe.get_all(
			"Taskist Notification Delivery",
			filters={
				"tracker": tracker.name,
				"status": ["in", ["Pending", "Failed"]],
			},
			pluck="name",
			limit_page_length=500,
		)
		for delivery_name in stale_deliveries:
			frappe.db.set_value(
				"Taskist Notification Delivery",
				delivery_name,
				{"status": "Cancelled", "last_error": None},
				update_modified=False,
			)
		extension.status = "Approved"
		extension.approved_due_at = extension.requested_due_at

		approved_extensions = getattr(frappe.flags, "taskist_approved_extensions", set()) or set()
		approved_extensions.add(extension.task)
		frappe.flags.taskist_approved_extensions = approved_extensions
		try:
			task = frappe.get_doc("Task", extension.task)
			task.exp_end_date = extension.requested_due_at
			task.save(ignore_permissions=True)
		finally:
			approved_extensions.discard(extension.task)
		_log_delay(
			extension.task,
			tracker.name,
			"Extension Approved",
			extension.delay_reason,
			decision_notes or f"Deadline extended to {extension.requested_due_at}",
		)
		tracker.save(ignore_permissions=True)
	else:
		extension.status = "Rejected"
		_log_delay(
			extension.task,
			tracker.name,
			"Extension Rejected",
			extension.delay_reason,
			decision_notes or "Deadline extension rejected",
		)
	extension.save(ignore_permissions=True)
	return get_task_extension_state(extension.task)


@frappe.whitelist()
def decide_sla_pause(pause_name, approve, decision_notes=None):
	if not can_manage_all_tasks():
		frappe.throw("Only Taskist Managers can approve SLA pauses.", frappe.PermissionError)
	pause = frappe.get_doc("Taskist SLA Pause", pause_name)
	if pause.status != "Requested":
		frappe.throw("Only requested pauses can be approved or rejected.")
	tracker = frappe.get_doc("Taskist SLA Tracker", pause.tracker)
	if int(approve):
		pause.status = "Active"
		pause.status_before_pause = tracker.status
		pause.approved_by = frappe.session.user
		pause.approved_on = now_datetime()
		pause.pause_started_on = pause.requested_on
		tracker.status = "Paused"
		tracker.pause_status = "Paused"
		from taskist.events import record_event

		record_event(
			pause.task,
			"Paused",
			tracker=tracker.name,
			previous_value=pause.status_before_pause,
			new_value="Paused",
			notes=decision_notes or pause.notes,
			metadata={"pause": pause.name, "delay_reason": pause.delay_reason},
			dedupe_key=f"pause-approved:{pause.name}",
		)
	else:
		pause.status = "Rejected"
		tracker.pause_status = "Not Paused"
		tracker.active_pause = None
		_log_delay(pause.task, tracker.name, "Pause Rejected", pause.delay_reason, decision_notes or "Rejected")
	pause.decision_notes = decision_notes
	pause.save(ignore_permissions=True)
	tracker.save(ignore_permissions=True)
	return get_task_pause_state(pause.task)


@frappe.whitelist()
def resume_sla(task_name, notes=None):
	check_task_update(task_name)
	tracker = _active_tracker(task_name)
	if not tracker or tracker.pause_status != "Paused" or not tracker.active_pause:
		frappe.throw("This task does not have an active SLA pause.")
	pause = frappe.get_doc("Taskist SLA Pause", tracker.active_pause)
	if pause.status != "Active":
		frappe.throw("The linked SLA pause is not active.")

	now = now_datetime()
	rule = frappe.get_doc("Taskist SLA Rule", tracker.rule)
	minutes = _service_minutes_between(rule, pause.pause_started_on, now)
	tracker.response_due_at = _shift_datetime(rule, tracker.response_due_at, minutes)
	tracker.warning_at = _shift_datetime(rule, tracker.warning_at, minutes)
	tracker.due_at = _shift_datetime(rule, tracker.due_at, minutes)
	tracker.total_paused_minutes = int(tracker.total_paused_minutes or 0) + minutes
	tracker.pause_status = "Not Paused"
	tracker.active_pause = None
	tracker.status = pause.status_before_pause or "Open"

	pause.status = "Resumed"
	pause.resumed_on = now
	pause.paused_minutes = minutes
	pause.decision_notes = notes
	pause.save(ignore_permissions=True)
	tracker.save(ignore_permissions=True)
	log = _log_delay(task_name, tracker.name, "Pause Resumed", pause.delay_reason, notes or "SLA resumed")
	from taskist.events import record_event

	record_event(
		task_name,
		"Resumed",
		tracker=tracker.name,
		previous_value="Paused",
		new_value=tracker.status,
		notes=notes or "SLA resumed",
		metadata={
			"pause": pause.name,
			"delay_log": log.name,
			"delay_reason": pause.delay_reason,
			"paused_minutes": minutes,
		},
		dedupe_key=f"pause-resumed:{pause.name}",
	)
	return get_task_pause_state(task_name)
