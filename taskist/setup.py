import frappe


TASKIST_ROLES = {
	"Taskist User": {"read": 1, "write": 1, "create": 1},
	"Taskist Manager": {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
	"Taskist Auditor": {"read": 1, "report": 1, "export": 1},
}


def ensure_roles_and_permissions():
	for role, permissions in TASKIST_ROLES.items():
		if not frappe.db.exists("Role", role):
			doc = frappe.new_doc("Role")
			doc.role_name = role
			doc.desk_access = 1
			doc.insert(ignore_permissions=True)

		if not frappe.db.exists("Custom DocPerm", {"parent": "Task", "role": role, "permlevel": 0}):
			docperm = frappe.new_doc("Custom DocPerm")
			docperm.parent = "Task"
			docperm.parenttype = "DocType"
			docperm.parentfield = "permissions"
			docperm.role = role
			docperm.permlevel = 0
			for field, value in permissions.items():
				setattr(docperm, field, value)
			docperm.insert(ignore_permissions=True)


def before_migrate():
	ensure_roles_and_permissions()


def after_install():
	ensure_roles_and_permissions()
