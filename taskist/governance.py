import hashlib
import json

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from taskist.access import can_manage_all_tasks, can_view_all_tasks


RULE_DOCTYPES = ("Taskist Process Rule", "Taskist SLA Rule")
GOVERNANCE_FIELDS = {
	"enabled", "approval_status", "business_owner", "effective_from", "effective_to",
	"approved_by", "approved_on", "change_reason", "current_version",
}


def _configuration(doc):
	data = doc.as_dict(no_nulls=False)
	def scrub(value):
		if isinstance(value, dict):
			return {
				key: scrub(item)
				for key, item in value.items()
				if key not in {
					"name", "owner", "creation", "modified", "modified_by", "docstatus",
					"doctype", "idx", "parent", "parentfield", "parenttype",
					"_user_tags", "_comments", "_assign", "_liked_by",
				}
			}
		if isinstance(value, list):
			return [scrub(item) for item in value]
		return value
	data = scrub(data)
	data.pop("current_version", None)
	for field in (
		"name", "owner", "creation", "modified", "modified_by", "docstatus",
		"doctype", "idx", "_user_tags", "_comments", "_assign", "_liked_by",
	):
		data.pop(field, None)
	return data


def _configuration_hash(data):
	value = json.dumps(data, default=str, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(value.encode("utf-8")).hexdigest(), value


def is_rule_effective(rule, at_time=None):
	at_time = get_datetime(at_time or now_datetime())
	if not rule.enabled or rule.approval_status != "Approved":
		return False
	if rule.effective_from and at_time < get_datetime(rule.effective_from):
		return False
	if rule.effective_to and at_time > get_datetime(rule.effective_to):
		return False
	return True


def validate_rule_governance(doc):
	if doc.enabled:
		if not doc.business_owner:
			frappe.throw("Business Owner is required before enabling a rule.")
		if doc.approval_status != "Approved":
			frappe.throw("Only an approved rule can be enabled.")
		if not doc.effective_from:
			frappe.throw("Effective From is required before enabling a rule.")
	if doc.effective_from and doc.effective_to:
		if get_datetime(doc.effective_from) >= get_datetime(doc.effective_to):
			frappe.throw("Effective To must be after Effective From.")


def mark_material_change_draft(doc):
	if doc.is_new():
		return
	previous = doc.get_doc_before_save()
	if not previous or previous.approval_status != "Approved":
		return
	before = _configuration(previous)
	after = _configuration(doc)
	for field in GOVERNANCE_FIELDS:
		before.pop(field, None)
		after.pop(field, None)
	if _configuration_hash(before)[0] != _configuration_hash(after)[0]:
		doc.approval_status = "Draft"
		doc.enabled = 0
		doc.approved_by = None
		doc.approved_on = None


def record_rule_revision(doc, method=None):
	if doc.doctype not in RULE_DOCTYPES:
		return
	data = _configuration(doc)
	config_hash, config_json = _configuration_hash(data)
	existing = frappe.db.get_value(
		"Taskist Rule Revision",
		{"rule_doctype": doc.doctype, "rule_name": doc.name, "configuration_hash": config_hash},
		"name",
	)
	if existing:
		return existing
	version = frappe.db.count(
		"Taskist Rule Revision",
		{"rule_doctype": doc.doctype, "rule_name": doc.name},
	) + 1
	revision = frappe.new_doc("Taskist Rule Revision")
	revision.revision_key = f"{doc.doctype}:{doc.name}:v{version}:{config_hash[:12]}"
	revision.rule_doctype = doc.doctype
	revision.rule_name = doc.name
	revision.version = version
	revision.status = doc.approval_status
	revision.effective_from = doc.effective_from
	revision.effective_to = doc.effective_to
	revision.approved_by = doc.approved_by
	revision.approved_on = doc.approved_on
	revision.change_reason = doc.change_reason
	revision.configuration_hash = config_hash
	revision.configuration_json = config_json
	revision.insert(ignore_permissions=True)
	frappe.db.set_value(doc.doctype, doc.name, "current_version", version, update_modified=False)
	return revision.name


def current_revision(rule):
	name = frappe.db.get_value(
		"Taskist Rule Revision",
		{
			"rule_doctype": rule.doctype,
			"rule_name": rule.name,
			"version": int(rule.current_version or 0),
		},
		"name",
	)
	return name or record_rule_revision(rule)


@frappe.whitelist()
def approve_rule(rule_doctype, rule_name, effective_from=None, effective_to=None, change_reason=None):
	if not can_manage_all_tasks():
		frappe.throw(_("Only Taskist Managers can approve rules."), frappe.PermissionError)
	if rule_doctype not in RULE_DOCTYPES:
		frappe.throw(_("Unsupported rule type."))
	if not change_reason:
		frappe.throw(_("An approval reason is required."))
	doc = frappe.get_doc(rule_doctype, rule_name)
	doc.business_owner = doc.business_owner or frappe.session.user
	doc.approval_status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.effective_from = effective_from or doc.effective_from or now_datetime()
	doc.effective_to = effective_to or doc.effective_to
	doc.change_reason = change_reason or doc.change_reason
	doc.enabled = 1
	doc.save(ignore_permissions=True)
	doc.reload()
	return {"name": doc.name, "version": doc.current_version, "status": doc.approval_status}


@frappe.whitelist()
def clone_rule(rule_doctype, rule_name, new_rule_name, new_process_code=None):
	if not can_manage_all_tasks():
		frappe.throw(_("Only Taskist Managers can clone rules."), frappe.PermissionError)
	if rule_doctype not in RULE_DOCTYPES:
		frappe.throw(_("Unsupported rule type."))
	if not new_rule_name:
		frappe.throw(_("New rule name is required."))
	if frappe.db.exists(rule_doctype, new_rule_name):
		frappe.throw(_("A rule with this name already exists."))

	from frappe.model.copy_doc import copy_doc

	source = frappe.get_doc(rule_doctype, rule_name)
	doc = copy_doc(source)
	doc.rule_name = new_rule_name
	doc.enabled = 0
	doc.approval_status = "Draft"
	doc.approved_by = None
	doc.approved_on = None
	doc.current_version = 0
	doc.change_reason = _("Cloned from {0}").format(rule_name)
	if rule_doctype == "Taskist Process Rule":
		doc.process_code = new_process_code or frappe.scrub(new_rule_name).upper()
		if frappe.db.exists(rule_doctype, {"process_code": doc.process_code}):
			frappe.throw(_("A process rule with this process code already exists."))
	doc.insert(ignore_permissions=False)
	return {"doctype": doc.doctype, "name": doc.name}


@frappe.whitelist()
def retire_rule(rule_doctype, rule_name, change_reason):
	if not can_manage_all_tasks():
		frappe.throw(_("Only Taskist Managers can retire rules."), frappe.PermissionError)
	if rule_doctype not in RULE_DOCTYPES:
		frappe.throw(_("Unsupported rule type."))
	if not change_reason:
		frappe.throw(_("A retirement reason is required."))
	doc = frappe.get_doc(rule_doctype, rule_name)
	doc.enabled = 0
	doc.approval_status = "Retired"
	doc.effective_to = now_datetime()
	doc.change_reason = change_reason
	doc.save(ignore_permissions=True)
	doc.reload()
	return {"name": doc.name, "version": doc.current_version, "status": doc.approval_status}


@frappe.whitelist()
def get_governance_dashboard():
	if not can_view_all_tasks():
		frappe.throw(_("You do not have access to governance results."), frappe.PermissionError)
	rows = []
	for doctype in RULE_DOCTYPES:
		for row in frappe.get_all(
			doctype,
			fields=[
				"name", "enabled", "approval_status", "business_owner", "effective_from",
				"effective_to", "approved_by", "approved_on", "current_version", "modified",
			],
			limit_page_length=100000,
		):
			issues = []
			if not row.business_owner:
				issues.append("Missing owner")
			if row.approval_status != "Approved":
				issues.append("Not approved")
			if not row.effective_from:
				issues.append("No effective date")
			if not row.current_version:
				issues.append("No revision")
			rows.append({
				**row,
				"rule_doctype": doctype,
				"effective": is_rule_effective(row),
				"issues": issues,
			})
	ready = sum(1 for row in rows if not row["issues"])
	return {
		"summary": {
			"total": len(rows),
			"ready": ready,
			"draft": sum(1 for row in rows if row["approval_status"] == "Draft"),
			"effective": sum(1 for row in rows if row["effective"]),
			"missing_owner": sum(1 for row in rows if not row["business_owner"]),
		},
		"rules": sorted(rows, key=lambda row: (len(row["issues"]), row["rule_doctype"], row["name"])),
		"can_manage": can_manage_all_tasks(),
	}
