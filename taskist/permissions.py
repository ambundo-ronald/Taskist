import frappe

from taskist.access import can_update_task, can_view_all_tasks, can_view_task, visible_users


def task_query_conditions(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or can_view_all_tasks(user):
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


def task_has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if permission_type == "create":
		return bool(
			set(frappe.get_roles(user))
			& {"System Manager", "Taskist User", "Taskist Manager"}
		)
	task_name = doc.name if hasattr(doc, "name") else str(doc)
	if permission_type in ("write", "delete", "submit", "cancel"):
		return can_update_task(task_name, user)
	return can_view_task(task_name, user)
