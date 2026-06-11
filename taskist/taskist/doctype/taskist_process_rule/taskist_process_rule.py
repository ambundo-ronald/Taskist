import json

import frappe
from frappe.model.document import Document
from taskist.governance import mark_material_change_draft, record_rule_revision, validate_rule_governance


class TaskistProcessRule(Document):
	def validate(self):
		mark_material_change_draft(self)
		self._validate_reference_doctype()
		self._validate_conditions()
		self._validate_completion_condition()
		self._validate_workflow_trigger()
		self._validate_assignment()
		self._validate_sla_rule()
		self._validate_output()
		self._validate_handoff()
		validate_rule_governance(self)

	def on_update(self):
		record_rule_revision(self)

	def _validate_reference_doctype(self):
		reference_doctype = self.reference_doctype or ""
		if reference_doctype in ("Task", "ToDo") or reference_doctype.startswith("Taskist "):
			frappe.throw("Process rules cannot target Task, ToDo, or Taskist internal DocTypes.")

	def _validate_conditions(self):
		if not self.conditions_json:
			return
		try:
			filters = json.loads(self.conditions_json)
		except (json.JSONDecodeError, TypeError):
			frappe.throw("Conditions JSON must be valid JSON.")
		if not isinstance(filters, (dict, list)):
			frappe.throw("Conditions JSON must be a JSON object or filter list.")

	def _validate_completion_condition(self):
		if not self.completion_condition_json:
			return
		try:
			filters = json.loads(self.completion_condition_json)
		except (json.JSONDecodeError, TypeError):
			frappe.throw("Completion Condition JSON must be valid JSON.")
		if not isinstance(filters, (dict, list)):
			frappe.throw("Completion Condition JSON must be a JSON object or filter list.")

	def _validate_workflow_trigger(self):
		if self.trigger_event != "Workflow State Change":
			return
		if not self.workflow_state_field:
			frappe.throw("Workflow State Field is required for workflow-state triggers.")
		if not self.workflow_to_state:
			frappe.throw("To State is required for workflow-state triggers.")

	def _validate_assignment(self):
		if self.assignment_strategy == "Fixed User" and not self.assigned_user:
			frappe.throw("Assigned User is required for Fixed User assignment.")
		if self.assignment_strategy in ("Role", "Round Robin Role") and not self.assigned_role:
			frappe.throw("Assigned Role is required for role assignment.")
		if self.assignment_strategy == "Source Field" and not self.assignee_field:
			frappe.throw("Assignee Field is required for Source Field assignment.")

	def _validate_sla_rule(self):
		if not self.sla_rule:
			return
		sla = frappe.db.get_value(
			"Taskist SLA Rule",
			self.sla_rule,
			["reference_doctype", "approval_status"],
			as_dict=True,
		)
		reference_doctype = sla.reference_doctype if sla else None
		if reference_doctype and reference_doctype != self.reference_doctype:
			frappe.throw(
				f"SLA Rule {self.sla_rule} targets {reference_doctype}, not {self.reference_doctype}."
			)
		if self.approval_status == "Approved" and sla and sla.approval_status != "Approved":
			frappe.throw(f"SLA Rule {self.sla_rule} must be approved first.")

	def _validate_output(self):
		output_type = self.completion_output_type or "None"
		if output_type == "Document Created" and not self.output_doctype:
			frappe.throw("Output DocType is required when completion requires a created document.")
		if (
			output_type == "Document Created"
			and not self.output_link_field
			and not self.completion_condition_json
		):
			frappe.throw(
				"Document Created validation requires an Output Link Field or Completion Condition JSON."
			)
		if output_type in ("Workflow State Reached", "Field Populated") and not self.output_field:
			frappe.throw("Output Field is required for the selected completion output type.")
		if output_type == "Workflow State Reached" and not self.output_expected_value:
			frappe.throw("Expected Value is required for a workflow-state output.")
		if output_type == "Checklist Completed":
			if not self.completion_checklist_json:
				frappe.throw("Completion Checklist JSON is required for checklist validation.")
			try:
				items = json.loads(self.completion_checklist_json)
			except (json.JSONDecodeError, TypeError):
				frappe.throw("Completion Checklist JSON must be valid JSON.")
			if not isinstance(items, list) or not items or not all(
				isinstance(item, str) and item.strip() for item in items
			):
				frappe.throw("Completion Checklist JSON must be a non-empty JSON array of labels.")

	def _validate_handoff(self):
		for linked_rule in (self.next_process_rule, self.rework_process_rule):
			if linked_rule and linked_rule == self.name:
				frappe.throw("A Process Rule cannot hand work back to itself.")
			if linked_rule:
				linked = frappe.db.get_value(
					"Taskist Process Rule",
					linked_rule,
					["reference_doctype", "approval_status"],
					as_dict=True,
				)
				reference_doctype = linked.reference_doctype if linked else None
				if reference_doctype and reference_doctype != self.reference_doctype:
					frappe.throw(
						f"Process Rule {linked_rule} targets {reference_doctype}, "
						f"not {self.reference_doctype}."
					)
				if self.approval_status == "Approved" and linked and linked.approval_status != "Approved":
					frappe.throw(f"Linked Process Rule {linked_rule} must be approved first.")
		strategy = self.handoff_assignment_strategy or "Use Next Rule"
		if strategy == "Fixed User" and not self.handoff_assigned_user:
			frappe.throw("Handoff User is required for Fixed User handoff assignment.")
		if strategy in ("Role", "Round Robin Role") and not self.handoff_assigned_role:
			frappe.throw("Handoff Role is required for role-based handoff assignment.")
		if strategy == "Source Field" and not self.handoff_assignee_field:
			frappe.throw("Handoff Assignee Field is required for Source Field handoff assignment.")
		for fieldname in ("handoff_sla_rule", "rework_sla_rule"):
			sla_rule = self.get(fieldname)
			if not sla_rule:
				continue
			sla = frappe.db.get_value(
				"Taskist SLA Rule",
				sla_rule,
				["reference_doctype", "approval_status"],
				as_dict=True,
			)
			reference_doctype = sla.reference_doctype if sla else None
			if reference_doctype and reference_doctype != self.reference_doctype:
				frappe.throw(
					f"SLA Rule {sla_rule} targets {reference_doctype}, not {self.reference_doctype}."
				)
			if self.approval_status == "Approved" and sla and sla.approval_status != "Approved":
				frappe.throw(f"SLA Rule {sla_rule} must be approved first.")
