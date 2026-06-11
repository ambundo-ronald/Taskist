import frappe
from frappe.model.document import Document


class TaskistKPISnapshot(Document):
	def before_save(self):
		if not self.is_new():
			frappe.throw(
				"Taskist KPI Snapshots are immutable. Create a new snapshot for a new reporting period.",
				frappe.PermissionError,
			)

	def on_trash(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw(
				"Only a System Manager may delete KPI snapshots during controlled maintenance.",
				frappe.PermissionError,
			)
