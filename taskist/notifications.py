"""Taskist activity notification helpers."""

import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime


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


def _notification_url(row):
	if row.document_type == "Task" and row.document_name:
		return f"/taskist?task={row.document_name}"
	if row.document_type and row.document_name:
		return f"/app/{frappe.scrub(row.document_type)}/{row.document_name}"
	return "/taskist"


@frappe.whitelist()
def get_recent_notifications(limit=20):
	"""Return durable Taskist notifications for the current user."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login is required to view notifications"), frappe.PermissionError)

	limit = min(max(int(limit or 20), 1), 100)
	rows = frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user},
		fields=[
			"name",
			"subject",
			"email_content",
			"document_type",
			"document_name",
			"read",
			"creation",
		],
		order_by="creation desc",
		limit_page_length=limit,
	)
	unread_count = frappe.db.count(
		"Notification Log",
		{"for_user": frappe.session.user, "read": 0},
	)
	return {
		"unread_count": unread_count,
		"notifications": [
			{
				"name": row.name,
				"subject": row.subject,
				"body": plain_text(row.email_content, 240),
				"document_type": row.document_type,
				"document_name": row.document_name,
				"read": bool(row.read),
				"creation": str(row.creation),
				"url": _notification_url(row),
			}
			for row in rows
		],
	}


@frappe.whitelist()
def mark_notification_read(notification_name=None, mark_all=False):
	"""Mark one or all current-user notifications as read."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login is required to update notifications"), frappe.PermissionError)

	if mark_all:
		frappe.db.set_value(
			"Notification Log",
			{"for_user": frappe.session.user, "read": 0},
			"read",
			1,
			update_modified=False,
		)
		return {"success": True}

	if not notification_name:
		frappe.throw(_("Notification is required"))
	doc = frappe.get_doc("Notification Log", notification_name)
	if doc.for_user != frappe.session.user:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	doc.read = 1
	if hasattr(doc, "read_by"):
		doc.read_by = frappe.session.user
	if hasattr(doc, "read_on"):
		doc.read_on = now_datetime()
	doc.save(ignore_permissions=True)
	return {"success": True}
