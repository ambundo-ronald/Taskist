import frappe
from frappe.model.document import Document


class TaskistAccessProfile(Document):
	def validate(self):
		self.name = self.user
		seen = set()
		for row in self.visible_users or []:
			if row.user == self.user:
				frappe.throw("A user already sees their own assigned tasks.")
			if row.user in seen:
				frappe.throw(f"Visible user {row.user} appears more than once.")
			seen.add(row.user)
