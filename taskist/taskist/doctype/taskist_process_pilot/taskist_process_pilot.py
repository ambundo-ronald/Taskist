import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, nowdate


ACTIVE_STATUSES = ("Shadow", "Operational")


class TaskistProcessPilot(Document):
	def validate(self):
		self._validate_dates()
		self._validate_rules()
		self._validate_active_membership()
		self._set_phase_timestamps()
		self._set_signoff()

	def _validate_dates(self):
		if self.start_date and self.end_date and getdate(self.start_date) > getdate(self.end_date):
			frappe.throw("Pilot Start Date cannot be after Pilot End Date.")

	def _validate_rules(self):
		if not self.rules:
			frappe.throw("Add at least one Process Rule to the pilot.")
		if len(self.rules) > 5:
			frappe.throw("A department pilot may contain no more than five Process Rules.")
		seen = set()
		for row in self.rules:
			if row.process_rule in seen:
				frappe.throw(f"Process Rule {row.process_rule} is listed more than once.")
			seen.add(row.process_rule)
			rule = frappe.db.get_value(
				"Taskist Process Rule",
				row.process_rule,
				["department", "enabled"],
				as_dict=True,
			)
			if not rule:
				frappe.throw(f"Process Rule {row.process_rule} does not exist.")
			if not rule.enabled:
				frappe.throw(f"Enable Process Rule {row.process_rule} before adding it to a pilot.")
			if self.department and rule.department != self.department:
				frappe.throw(
					f"Process Rule {row.process_rule} belongs to {rule.department or 'no department'}, "
					f"not {self.department}."
				)

	def _validate_active_membership(self):
		if self.status not in ACTIVE_STATUSES:
			return
		for row in self.rules:
			conflict = frappe.db.sql(
				"""
				select child.parent
				from `tabTaskist Pilot Rule` child
				inner join `tabTaskist Process Pilot` pilot on pilot.name = child.parent
				where child.process_rule = %s
					and child.parent != %s
					and pilot.status in ('Shadow', 'Operational')
				limit 1
				""",
				(row.process_rule, self.name or ""),
			)
			if conflict:
				frappe.throw(
					f"Process Rule {row.process_rule} is already active in pilot {conflict[0][0]}."
				)

	def _set_signoff(self):
		if self.status != "Completed":
			return
		if not self.signed_off_by:
			self.signed_off_by = frappe.session.user
		if not self.signed_off_on:
			self.signed_off_on = nowdate()
		if not self.signoff_notes:
			frappe.throw("Sign-off Notes are required when completing a pilot.")

	def _set_phase_timestamps(self):
		previous = self.get_doc_before_save() if not self.is_new() else None
		if self.status == "Shadow" and not self.shadow_started_on:
			self.shadow_started_on = now_datetime()
		if self.status == "Operational" and not self.operational_started_on:
			if not self.shadow_started_on:
				frappe.throw("Run the pilot in Shadow mode before moving it to Operational.")
			self.operational_started_on = now_datetime()
		if previous and previous.status == "Completed" and self.status != "Completed":
			frappe.throw("A completed pilot cannot be reopened.")
