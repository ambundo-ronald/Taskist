import frappe
from frappe.model.document import Document


class TaskistRuleRevision(Document):
	def before_save(self):
		if not self.is_new():
			frappe.throw("Rule revisions are immutable.", frappe.PermissionError)

	def on_trash(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw("Only a System Manager may delete rule revisions.", frappe.PermissionError)
