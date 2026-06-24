"""Taskist activity notification helpers."""

import json
import re

import frappe


def _task_assignees(task):
	assign_value = task.get("_assign") if hasattr(task, "get") else None
	if not assign_value:
		return []
	try:
		return json.loads(assign_value) or []
	except (json.JSONDecodeError, TypeError):
		return []


def task_recipients(task, include_owner=True):
	recipients = set(_task_assignees(task))
	if include_owner and task.get("owner"):
		recipients.add(task.owner)
	return recipients


def plain_text(value, limit=180):
	text = re.sub(r"<[^>]+>", "", value or "").strip()
	return text[:limit]


def notify_task_activity(task, title, body, event_key, recipients=None, exclude_user=None):
	"""Notify task stakeholders through audited push and in-app channels."""
	try:
		if isinstance(task, str):
			task = frappe.get_doc("Task", task)
		users = set(recipients or task_recipients(task))
		if exclude_user:
			users.discard(exclude_user)
		users.discard("Administrator")
		if not users:
			return False

		from taskist.sla import _deliver

		push_ok = _deliver(
			users,
			"Push",
			title,
			body,
			task.name,
			f"taskist-activity-push-{event_key}",
		)
		in_app_ok = _deliver(
			users,
			"In App",
			title,
			body,
			task.name,
			f"taskist-activity-in-app-{event_key}",
		)
		return push_ok or in_app_ok
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Taskist Activity Notification")
		return False
