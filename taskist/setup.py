import frappe
from frappe.utils import now_datetime
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


TASKIST_ROLES = {
	"Taskist User": {"read": 1, "write": 1, "create": 1},
	"Taskist Manager": {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
	"Taskist Auditor": {"read": 1, "report": 1, "export": 1},
}

DEFAULT_DELAY_REASONS = [
	("Awaiting Internal Approval", "Internal", "Department", 0, 0),
	("Incomplete Documentation", "Internal", "Employee", 0, 1),
	("Customer Delay", "Customer", "Customer", 1, 0),
	("Supplier Delay", "Supplier", "Supplier", 1, 0),
	("Stock Unavailable", "Stock", "Department", 1, 0),
	("Finance Hold", "Finance", "Department", 1, 0),
	("Technical Clarification Required", "Technical", "Shared", 1, 0),
	("System Issue", "System", "System", 1, 1),
	("Staff Non-Compliance", "Internal", "Employee", 0, 0),
	("Source Assignment Closed", "Internal", "Shared", 0, 0),
	("Other", "Other", "Shared", 0, 0),
]


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


def ensure_task_custom_fields():
	create_custom_fields(
		{
			"Task": [
				{
					"fieldname": "taskist_process_rule",
					"label": "Taskist Process Rule",
					"fieldtype": "Link",
					"options": "Taskist Process Rule",
					"insert_after": "taskist_reference_todo",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_process_event_key",
					"label": "Taskist Process Event Key",
					"fieldtype": "Data",
					"insert_after": "taskist_process_rule",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
					"unique": 1,
				},
				{
					"fieldname": "taskist_process_trigger_event",
					"label": "Taskist Process Trigger Event",
					"fieldtype": "Data",
					"insert_after": "taskist_process_event_key",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_process_chain_id",
					"label": "Taskist Process Chain ID",
					"fieldtype": "Data",
					"insert_after": "taskist_process_trigger_event",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_process_sequence",
					"label": "Taskist Process Sequence",
					"fieldtype": "Int",
					"insert_after": "taskist_process_chain_id",
					"default": "1",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_previous_process_task",
					"label": "Previous Process Task",
					"fieldtype": "Link",
					"options": "Task",
					"insert_after": "taskist_process_sequence",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_next_process_task",
					"label": "Next Process Task",
					"fieldtype": "Link",
					"options": "Task",
					"insert_after": "taskist_previous_process_task",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_manager_approved_by",
					"label": "Taskist Manager Approved By",
					"fieldtype": "Link",
					"options": "User",
					"insert_after": "taskist_next_process_task",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_manager_approved_on",
					"label": "Taskist Manager Approved On",
					"fieldtype": "Datetime",
					"insert_after": "taskist_manager_approved_by",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "taskist_checklist_json",
					"label": "Taskist Completion Checklist JSON",
					"fieldtype": "Long Text",
					"insert_after": "taskist_manager_approved_on",
					"hidden": 1,
					"no_copy": 1,
				},
			]
		},
		update=True,
	)


def ensure_delay_reasons():
	if not frappe.db.exists("DocType", "Taskist Delay Reason"):
		return
	for name, category, party, pause_eligible, evidence_required in DEFAULT_DELAY_REASONS:
		if frappe.db.exists("Taskist Delay Reason", name):
			continue
		reason = frappe.new_doc("Taskist Delay Reason")
		reason.reason_name = name
		reason.enabled = 1
		reason.category = category
		reason.responsible_party = party
		reason.pause_eligible = pause_eligible
		reason.evidence_required = evidence_required
		reason.insert(ignore_permissions=True)


def ensure_rule_governance():
	from taskist.governance import RULE_DOCTYPES, record_rule_revision

	for doctype in RULE_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, pluck="name", limit_page_length=100000):
			doc = frappe.get_doc(doctype, name)
			updates = {}
			if not doc.business_owner:
				updates["business_owner"] = doc.owner or "Administrator"
			if not doc.approval_status or doc.approval_status == "Draft":
				updates["approval_status"] = "Approved"
			if not doc.effective_from:
				updates["effective_from"] = doc.creation or now_datetime()
			if not doc.approved_by:
				updates["approved_by"] = "Administrator"
			if not doc.approved_on:
				updates["approved_on"] = doc.creation or now_datetime()
			if not doc.change_reason:
				updates["change_reason"] = "Existing rule approved during Taskist governance migration."
			if updates:
				frappe.db.set_value(doctype, name, updates, update_modified=False)
				doc.reload()
			record_rule_revision(doc)


def before_migrate():
	ensure_roles_and_permissions()


def after_migrate():
	ensure_roles_and_permissions()
	ensure_task_custom_fields()
	ensure_delay_reasons()
	ensure_rule_governance()


def after_install():
	ensure_roles_and_permissions()
	ensure_task_custom_fields()
	ensure_delay_reasons()
	ensure_rule_governance()
