import frappe

from taskist.access import can_update_task, can_view_all_tasks, can_view_task, runs_all_tasks, visible_users


def task_query_conditions(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or can_view_all_tasks(user) or runs_all_tasks(user):
		return ""
	users = visible_users(user) or set()
	conditions = []
	for email in sorted(users):
		pattern = f'%"{email}"%'
		conditions.append(f"`tabTask`.`_assign` like {frappe.db.escape(pattern)}")
	conditions.append(
		"("
		f"`tabTask`.`owner` = {frappe.db.escape(user)} and "
		"(`tabTask`.`_assign` is null or `tabTask`.`_assign` = '' or `tabTask`.`_assign` = '[]')"
		")"
	)
	return "(" + " or ".join(conditions) + ")" if conditions else "1=0"


UPDATE_TYPES = ("write", "delete", "submit", "cancel", "amend")


def task_has_permission(doc, ptype=None, user=None, debug=False, permission_type=None):
	"""has_permission hook for Task: narrows what roles allow to the tasks a person may see or update.

	Frappe passes the action as `ptype` (and drops arguments a hook does not name), so it must be named `ptype`.
	Returning None leaves the decision to role permissions; False refuses.
	"""
	user = user or frappe.session.user
	ptype = ptype or permission_type or "read"
	# Creating a task is up to role permissions (Projects User, Taskist User, ...): Taskist only narrows existing
	# tasks. A task being created has no name yet, so the checks below cannot apply to it.
	if ptype == "create":
		return None
	task_name = doc.name if hasattr(doc, "name") else str(doc)
	if not task_name or (callable(getattr(doc, "is_new", None)) and doc.is_new()):
		return None
	if ptype in UPDATE_TYPES:
		return can_update_task(task_name, user)
	return can_view_task(task_name, user)
