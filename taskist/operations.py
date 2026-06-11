import json

import frappe
from frappe.utils import get_datetime, now_datetime

from taskist.access import can_manage_all_tasks, check_task_update


def _task_names(value):
	if isinstance(value, str):
		value = json.loads(value)
	if not isinstance(value, list):
		frappe.throw("Task names must be a list.")
	return list(dict.fromkeys(filter(None, value)))


@frappe.whitelist()
def get_daily_review():
	"""Return the visible open queue, ordered for a daily SLA control meeting."""
	from taskist.api import get_tasks

	tasks = get_tasks(include_completed=0, page_length=500)
	now = now_datetime()
	for task in tasks:
		due_at = get_datetime(task.get("_sla_due_at")) if task.get("_sla_due_at") else None
		if int(task.get("_sla_escalation_level") or 0) > 0 or task.get("_manual_escalated"):
			task["_review_band"] = "Escalated"
		elif task.get("_sla_status") == "Breached":
			task["_review_band"] = "Red"
		elif task.get("_sla_status") == "Warning":
			task["_review_band"] = "Amber"
		else:
			task["_review_band"] = "Green"
		task["_age_hours"] = round((now - get_datetime(task.creation)).total_seconds() / 3600, 1)
		task["_overdue_hours"] = (
			round((now - due_at).total_seconds() / 3600, 1)
			if due_at and now > due_at
			else 0
		)
	tasks.sort(
		key=lambda row: (
			0 if row["_review_band"] == "Escalated" else
			1 if row["_review_band"] == "Red" else
			2 if row["_review_band"] == "Amber" else 3,
			-row["_overdue_hours"],
			row.get("_sla_due_at") or "9999-12-31",
		)
	)
	return {
		"tasks": tasks,
		"can_manage": can_manage_all_tasks(),
		"counts": {
			band: sum(1 for task in tasks if task["_review_band"] == band)
			for band in ("Green", "Amber", "Red", "Escalated")
		},
	}


@frappe.whitelist()
def bulk_reassign_tasks(task_names, user):
	if not can_manage_all_tasks():
		frappe.throw("Only Taskist Managers can bulk reassign tasks.", frappe.PermissionError)
	if not frappe.db.exists("User", {"name": user, "enabled": 1}):
		frappe.throw("Select an enabled user.")

	from frappe.desk.form.assign_to import add as assign_add
	from frappe.desk.form.assign_to import remove as assign_remove
	from taskist.events import record_event

	updated = []
	for task_name in _task_names(task_names):
		check_task_update(task_name)
		task = frappe.get_doc("Task", task_name)
		try:
			current = set(json.loads(task._assign or "[]"))
		except (json.JSONDecodeError, TypeError):
			current = set()
		for assignee in sorted(current - {user}):
			assign_remove("Task", task.name, assignee)
		if user not in current:
			assign_add({
				"doctype": "Task",
				"name": task.name,
				"assign_to": [user],
				"description": task.subject,
			})
		record_event(
			task.name,
			"Reassigned",
			previous_value=", ".join(sorted(current)) or None,
			new_value=user,
			notes="Bulk reassigned during daily SLA review.",
			dedupe_key=f"daily-review-reassign:{task.name}:{user}:{now_datetime()}",
		)
		updated.append(task.name)
	return {"updated": updated}


@frappe.whitelist()
def bulk_escalate_tasks(task_names, recipient, notes=None):
	if not can_manage_all_tasks():
		frappe.throw("Only Taskist Managers can escalate tasks.", frappe.PermissionError)
	if not frappe.db.exists("User", {"name": recipient, "enabled": 1}):
		frappe.throw("Select an enabled escalation recipient.")

	from taskist.events import record_event
	from taskist.sla import _send_in_app

	updated = []
	for task_name in _task_names(task_names):
		check_task_update(task_name)
		subject = frappe.db.get_value("Task", task_name, "subject") or task_name
		_send_in_app(
			recipient,
			"Taskist manual escalation",
			notes or f"{task_name}: {subject} requires attention.",
			task_name,
		)
		record_event(
			task_name,
			"Manual Escalation",
			new_value=recipient,
			notes=notes or "Manually escalated during daily SLA review.",
			metadata={"manual": True, "recipient": recipient},
			dedupe_key=f"daily-review-escalation:{task_name}:{recipient}:{now_datetime()}",
		)
		tracker = frappe.db.get_value("Taskist SLA Tracker", {"task": task_name}, "name")
		if tracker:
			current_level = int(
				frappe.db.get_value("Taskist SLA Tracker", tracker, "current_escalation_level") or 0
			)
			frappe.db.set_value(
				"Taskist SLA Tracker",
				tracker,
				"current_escalation_level",
				max(current_level, 1),
				update_modified=False,
			)
		updated.append(task_name)
	return {"updated": updated}
