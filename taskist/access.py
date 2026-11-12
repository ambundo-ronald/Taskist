import json

import frappe
from frappe import _


VIEW_ALL_ROLES = {"System Manager", "Taskist Manager", "Taskist Auditor"}
MANAGE_ALL_ROLES = {"System Manager", "Taskist Manager"}
# The people who run projects and field work (ERPNext Projects Manager, and Maintenance Manager, which Techy Ops
# uses) may see and update every task. This is only about tasks: Taskist's dashboards and approvals (SLA
# extensions, rules, bulk reassign, escalation) still need the Taskist roles above.
TASK_MANAGER_ROLES = {"Projects Manager", "Maintenance Manager"}


def _roles(user=None):
	return set(frappe.get_roles(user or frappe.session.user))


def can_view_all_tasks(user=None):
	user = user or frappe.session.user
	if _roles(user) & VIEW_ALL_ROLES:
		return True
	return bool(frappe.db.get_value("Taskist Access Profile", user, "view_all_tasks"))


def can_manage_all_tasks(user=None):
	return bool(_roles(user) & MANAGE_ALL_ROLES)


def runs_all_tasks(user=None):
	"""A projects or field-work manager: sees and updates every task (see TASK_MANAGER_ROLES)."""
	return bool(_roles(user) & TASK_MANAGER_ROLES)


def visible_users(user=None):
	user = user or frappe.session.user
	if can_view_all_tasks(user):
		return None

	users = {user}
	if frappe.db.exists("Taskist Access Profile", user):
		users.update(
			frappe.get_all(
				"Taskist Visible User",
				filters={"parent": user, "parenttype": "Taskist Access Profile"},
				pluck="user",
				limit_page_length=500,
			)
		)
	return users


def manageable_users(user=None):
	user = user or frappe.session.user
	if can_manage_all_tasks(user):
		return None
	users = {user}
	if frappe.db.exists("Taskist Access Profile", user):
		users.update(
			frappe.get_all(
				"Taskist Visible User",
				filters={
					"parent": user,
					"parenttype": "Taskist Access Profile",
					"can_update": 1,
				},
				pluck="user",
				limit_page_length=500,
			)
		)
	return users


def task_assignees(task):
	assign_value = task.get("_assign") if hasattr(task, "get") else None
	if not assign_value:
		return set()
	try:
		return set(json.loads(assign_value))
	except (json.JSONDecodeError, TypeError):
		return set()


def can_view_task(task_name, user=None):
	user = user or frappe.session.user
	if can_view_all_tasks(user) or runs_all_tasks(user):
		return True

	task = frappe.db.get_value("Task", task_name, ["_assign", "owner"], as_dict=True)
	if not task:
		return False
	assignees = task_assignees(task)
	if not assignees and task.owner == user:
		return True
	return bool(assignees & visible_users(user))


def check_task_view(task_name, user=None):
	if not can_view_task(task_name, user):
		frappe.throw(_("You do not have access to this Taskist task."), frappe.PermissionError)


def can_update_task(task_name, user=None):
	user = user or frappe.session.user
	if can_manage_all_tasks(user) or runs_all_tasks(user):
		return True
	task = frappe.db.get_value("Task", task_name, ["_assign", "owner"], as_dict=True)
	if not task:
		return False
	assignees = task_assignees(task)
	if not assignees and task.owner == user:
		return True
	return bool(assignees & manageable_users(user))


def check_task_update(task_name, user=None):
	if not can_update_task(task_name, user):
		frappe.throw(_("You do not have permission to update this Taskist task."), frappe.PermissionError)

