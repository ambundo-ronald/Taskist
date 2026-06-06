import json

import frappe
from frappe.model.document import Document
from frappe.utils import get_time


class TaskistSLARule(Document):
	def validate(self):
		self._validate_conditions()
		self._validate_priorities()
		self._validate_working_hours()
		self._validate_escalations()

	def _validate_conditions(self):
		if not self.conditions_json:
			return
		try:
			filters = json.loads(self.conditions_json)
		except (json.JSONDecodeError, TypeError):
			frappe.throw("Conditions JSON must be valid JSON.")
		if not isinstance(filters, (dict, list)):
			frappe.throw("Conditions JSON must be a JSON object or filter list.")

	def _validate_priorities(self):
		seen = set()
		for row in self.sla_priorities or []:
			key = (row.priority or "").strip().lower()
			if key in seen:
				frappe.throw(f"Priority {row.priority} appears more than once.")
			seen.add(key)
			if int(row.resolution_minutes or 0) <= 0:
				frappe.throw(f"Resolution minutes must be greater than zero for {row.priority}.")
			if int(row.warning_minutes_before_due or 0) > int(row.resolution_minutes or 0):
				frappe.throw(f"Warning time cannot exceed resolution time for {row.priority}.")
		if not self.sla_priorities:
			if int(self.target_minutes or 0) <= 0:
				frappe.throw("Add at least one Priority Target or set legacy Target Minutes.")
			if int(self.warning_minutes_before_due or 0) > int(self.target_minutes or 0):
				frappe.throw("Legacy warning time cannot exceed legacy target time.")

	def _validate_working_hours(self):
		if not self.apply_working_hours:
			return
		if get_time(self.working_hours_end) <= get_time(self.working_hours_start):
			frappe.throw("Working Hours End must be after Working Hours Start.")

	def _validate_escalations(self):
		seen = set()
		for row in self.escalation_matrix or []:
			key = (row.trigger, int(row.level or 0))
			if key in seen:
				frappe.throw(f"{row.trigger} escalation level {row.level} appears more than once.")
			seen.add(key)
			if row.recipient_type in ("User", "Role") and not row.recipient:
				frappe.throw(f"Recipient is required for {row.recipient_type} escalation level {row.level}.")
