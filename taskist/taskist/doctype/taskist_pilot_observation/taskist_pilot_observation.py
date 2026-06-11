import frappe
from frappe.model.document import Document


class TaskistPilotObservation(Document):
	def before_save(self):
		if not self.is_new():
			frappe.throw(
				"Pilot observations are immutable. Record a new source event instead of editing history.",
				frappe.PermissionError,
			)

	def on_trash(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw(
				"Only a System Manager may delete pilot observations during controlled maintenance.",
				frappe.PermissionError,
			)
