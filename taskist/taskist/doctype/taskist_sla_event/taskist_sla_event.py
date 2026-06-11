import frappe
from frappe.model.document import Document


class TaskistSLAEvent(Document):
	def before_save(self):
		if not self.is_new() and "System Manager" not in frappe.get_roles():
			frappe.throw(
				"Taskist SLA Events are immutable. Only a System Manager may edit them during controlled maintenance.",
				frappe.PermissionError,
			)

	def on_trash(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw(
				"Only a System Manager may delete Taskist SLA Events during controlled maintenance.",
				frappe.PermissionError,
			)
