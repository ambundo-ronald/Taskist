import frappe
from frappe.utils import get_datetime, now_datetime


def _columns():
	return [
		{"fieldname": "exception_type", "label": "Exception", "fieldtype": "Data", "width": 180},
		{"fieldname": "task", "label": "Task", "fieldtype": "Link", "options": "Task", "width": 180},
		{"fieldname": "tracker", "label": "SLA Tracker", "fieldtype": "Link", "options": "Taskist SLA Tracker", "width": 180},
		{"fieldname": "reference", "label": "Reference", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 170},
		{"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Link", "options": "DocType", "width": 150},
		{"fieldname": "owner", "label": "Responsible User", "fieldtype": "Link", "options": "User", "width": 180},
		{"fieldname": "reason", "label": "Reason", "fieldtype": "Link", "options": "Taskist Delay Reason", "width": 180},
		{"fieldname": "age_hours", "label": "Age Hours", "fieldtype": "Float", "width": 100},
		{"fieldname": "details", "label": "Details", "fieldtype": "Data", "width": 300},
	]


def _age_hours(value):
	if not value:
		return 0
	return round((now_datetime() - get_datetime(value)).total_seconds() / 3600, 1)


def _tracker_context(tracker_name):
	return frappe.db.get_value(
		"Taskist SLA Tracker",
		tracker_name,
		["reference_doctype", "reference_name", "user"],
		as_dict=True,
	) or {}


def _approval_exceptions():
	rows = []
	for pause in frappe.get_all(
		"Taskist SLA Pause",
		filters={"status": "Requested"},
		fields=["name", "tracker", "task", "delay_reason", "requested_by", "requested_on", "notes"],
		limit_page_length=1000,
	):
		context = _tracker_context(pause.tracker)
		rows.append({
			"exception_type": "Pending Pause Approval",
			"task": pause.task,
			"tracker": pause.tracker,
			"reference": context.get("reference_name"),
			"reference_doctype": context.get("reference_doctype"),
			"owner": pause.requested_by,
			"reason": pause.delay_reason,
			"age_hours": _age_hours(pause.requested_on),
			"details": pause.notes,
		})
	for extension in frappe.get_all(
		"Taskist SLA Extension",
		filters={"status": "Requested"},
		fields=["name", "tracker", "task", "delay_reason", "requested_by", "requested_on", "requested_due_at", "notes"],
		limit_page_length=1000,
	):
		context = _tracker_context(extension.tracker)
		rows.append({
			"exception_type": "Pending Extension Approval",
			"task": extension.task,
			"tracker": extension.tracker,
			"reference": context.get("reference_name"),
			"reference_doctype": context.get("reference_doctype"),
			"owner": extension.requested_by,
			"reason": extension.delay_reason,
			"age_hours": _age_hours(extension.requested_on),
			"details": f"Requested due {extension.requested_due_at}: {extension.notes}",
		})
	return rows


def _stale_pause_exceptions():
	rows = []
	for pause in frappe.get_all(
		"Taskist SLA Pause",
		filters={"status": "Active"},
		fields=["tracker", "task", "delay_reason", "requested_by", "pause_started_on", "notes"],
		limit_page_length=1000,
	):
		age = _age_hours(pause.pause_started_on)
		if age < 24:
			continue
		context = _tracker_context(pause.tracker)
		rows.append({
			"exception_type": "Active Pause Over 24h",
			"task": pause.task,
			"tracker": pause.tracker,
			"reference": context.get("reference_name"),
			"reference_doctype": context.get("reference_doctype"),
			"owner": pause.requested_by,
			"reason": pause.delay_reason,
			"age_hours": age,
			"details": pause.notes,
		})
	return rows


def _missing_explanation_exceptions():
	rows = []
	trackers = frappe.get_all(
		"Taskist SLA Tracker",
		filters={"status": "Completed", "breached_on": ["is", "set"]},
		fields=["name", "task", "reference_doctype", "reference_name", "user", "completed_on"],
		limit_page_length=2000,
	)
	for tracker in trackers:
		if frappe.db.exists(
			"Taskist Delay Log",
			{"tracker": tracker.name, "action": "Breached Completion"},
		):
			continue
		rows.append({
			"exception_type": "Missing Breach Explanation",
			"task": tracker.task,
			"tracker": tracker.name,
			"reference": tracker.reference_name,
			"reference_doctype": tracker.reference_doctype,
			"owner": tracker.user,
			"age_hours": _age_hours(tracker.completed_on),
			"details": "Completed after breach without a Taskist Delay Log.",
		})
	return rows


def _missing_evidence_exceptions():
	rows = []
	reasons = frappe.get_all(
		"Taskist Delay Reason",
		filters={"evidence_required": 1},
		pluck="name",
		limit_page_length=500,
	)
	if not reasons:
		return rows
	logs = frappe.get_all(
		"Taskist Delay Log",
		filters={"delay_reason": ["in", reasons]},
		fields=["task", "tracker", "delay_reason", "logged_by", "logged_on", "notes"],
		limit_page_length=2000,
	)
	for log in logs:
		if frappe.db.count("File", {"attached_to_doctype": "Task", "attached_to_name": log.task}):
			continue
		context = _tracker_context(log.tracker)
		rows.append({
			"exception_type": "Missing Required Evidence",
			"task": log.task,
			"tracker": log.tracker,
			"reference": context.get("reference_name"),
			"reference_doctype": context.get("reference_doctype"),
			"owner": log.logged_by,
			"reason": log.delay_reason,
			"age_hours": _age_hours(log.logged_on),
			"details": log.notes,
		})
	return rows


def get_data():
	rows = []
	rows.extend(_approval_exceptions())
	rows.extend(_stale_pause_exceptions())
	rows.extend(_missing_explanation_exceptions())
	rows.extend(_missing_evidence_exceptions())
	return sorted(rows, key=lambda row: row.get("age_hours") or 0, reverse=True)


def execute(filters=None):
	return _columns(), get_data()
