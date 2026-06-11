from collections import defaultdict

import frappe
from frappe import _
from taskist.access import can_manage_all_tasks, can_view_all_tasks
from taskist.analytics import _analytics_data


def _require_view():
	if not can_view_all_tasks():
		frappe.throw(_("You do not have access to department pilot results."), frappe.PermissionError)


def _require_manage():
	if not can_manage_all_tasks():
		frappe.throw(_("Only Taskist Managers can change a department pilot."), frappe.PermissionError)


def _pct(numerator, denominator):
	return round(numerator * 100 / denominator, 1) if denominator else None


def _pilot_doc(pilot_name=None):
	if pilot_name:
		return frappe.get_doc("Taskist Process Pilot", pilot_name)
	name = frappe.db.get_value(
		"Taskist Process Pilot",
		{"status": ["in", ["Shadow", "Operational"]]},
		"name",
		order_by="start_date desc",
	)
	if not name:
		name = frappe.db.get_value(
			"Taskist Process Pilot",
			{},
			"name",
			order_by="start_date desc",
		)
	return frappe.get_doc("Taskist Process Pilot", name) if name else None


def _rule_result(rule, observations):
	counts = defaultdict(int)
	for row in observations:
		if row.process_rule == rule:
			counts[row.outcome] += 1
	operational = sum(
		1 for row in observations
		if row.process_rule == rule and row.mode == "Operational"
	)
	success = counts["Task Created"] + counts["Existing Task"]
	return {
		"rule": rule,
		"eligible": sum(counts.values()),
		"shadow_matches": counts["Shadow Match"],
		"operational_events": operational,
		"tasks_created": counts["Task Created"],
		"duplicates_prevented": counts["Existing Task"],
		"no_assignee": counts["No Assignee"],
		"errors": counts["Error"],
		"automation_success_pct": _pct(success, operational),
	}


@frappe.whitelist()
def get_pilot_dashboard(pilot_name=None):
	_require_view()
	pilots = frappe.get_all(
		"Taskist Process Pilot",
		fields=["name", "pilot_name", "department", "status", "start_date", "end_date"],
		order_by="start_date desc",
		limit_page_length=100,
	)
	pilot = _pilot_doc(pilot_name)
	if not pilot:
		return {"pilots": pilots, "pilot": None}

	rules = [row.process_rule for row in pilot.rules]
	observations = frappe.get_all(
		"Taskist Pilot Observation",
		filters={"pilot": pilot.name},
		fields=[
			"name", "process_rule", "mode", "outcome", "reference_doctype",
			"reference_name", "task", "observed_on", "error_message",
		],
		order_by="observed_on desc",
		limit_page_length=100000,
	)
	counts = defaultdict(int)
	for row in observations:
		counts[row.outcome] += 1
		for field in ("observed_on",):
			if row.get(field):
				row[field] = str(row[field])

	operational_events = sum(1 for row in observations if row.mode == "Operational")
	success = counts["Task Created"] + counts["Existing Task"]
	duplicate_rows = frappe.db.sql(
		"""
		select taskist_process_event_key, count(*) as task_count
		from `tabTask`
		where taskist_process_rule in %(rules)s
			and taskist_process_event_key is not null
			and creation >= %(start)s
			and (%(end)s is null or creation < date_add(%(end)s, interval 1 day))
		group by taskist_process_event_key
		having count(*) > 1
		""",
		{"rules": tuple(rules or [""]), "start": pilot.start_date, "end": pilot.end_date},
		as_dict=True,
	) if rules else []
	actual_duplicate_tasks = sum(int(row.task_count) - 1 for row in duplicate_rows)
	duplicate_rate = _pct(actual_duplicate_tasks, operational_events) or 0

	analytics = _analytics_data(
		pilot.start_date,
		pilot.end_date,
		department=pilot.department,
	)
	process_metrics = {
		row["label"]: row for row in analytics.get("by_process", [])
		if row["label"] in rules
	}
	rule_results = []
	for rule in rules:
		result = _rule_result(rule, observations)
		result["metrics"] = process_metrics.get(rule, {})
		rule_results.append(result)

	shadow_matches = counts["Shadow Match"]
	errors = counts["Error"]
	no_assignee = counts["No Assignee"]
	automation_success = _pct(success, operational_events)
	criteria = [
		{
			"label": "Shadow evidence collected",
			"passed": shadow_matches > 0,
			"value": f"{shadow_matches} matched events",
		},
		{
			"label": "Eligible events automated",
			"passed": automation_success is not None and automation_success >= 95,
			"value": f"{automation_success or 0}% success",
		},
		{
			"label": "Duplicate task rate",
			"passed": duplicate_rate <= 1,
			"value": f"{duplicate_rate}% duplicates",
		},
		{
			"label": "Assignment resolution",
			"passed": no_assignee == 0,
			"value": f"{no_assignee} unresolved",
		},
		{
			"label": "Runtime errors",
			"passed": errors == 0,
			"value": f"{errors} errors",
		},
	]

	return {
		"pilots": pilots,
		"pilot": {
			"name": pilot.name,
			"pilot_name": pilot.pilot_name,
			"department": pilot.department,
			"status": pilot.status,
			"pilot_owner": pilot.pilot_owner,
			"start_date": str(pilot.start_date),
			"end_date": str(pilot.end_date) if pilot.end_date else None,
			"shadow_started_on": str(pilot.shadow_started_on) if pilot.shadow_started_on else None,
			"operational_started_on": (
				str(pilot.operational_started_on) if pilot.operational_started_on else None
			),
			"signed_off_by": pilot.signed_off_by,
			"signed_off_on": str(pilot.signed_off_on) if pilot.signed_off_on else None,
			"signoff_notes": pilot.signoff_notes,
			"baseline": {
				"lead_time_minutes": pilot.baseline_lead_time_minutes or 0,
				"waiting_time_minutes": pilot.baseline_waiting_time_minutes or 0,
				"rework_rate": pilot.baseline_rework_rate or 0,
				"breach_rate": pilot.baseline_breach_rate or 0,
			},
		},
		"summary": {
			"eligible_events": len(observations),
			"shadow_matches": shadow_matches,
			"operational_events": operational_events,
			"tasks_created": counts["Task Created"],
			"duplicates_prevented": counts["Existing Task"],
			"actual_duplicate_tasks": actual_duplicate_tasks,
			"automation_success_pct": automation_success,
			"duplicate_rate_pct": duplicate_rate,
			"no_assignee": no_assignee,
			"errors": errors,
		},
		"criteria": criteria,
		"ready_for_signoff": all(row["passed"] for row in criteria),
		"rules": rule_results,
		"observations": observations[:200],
		"can_manage": can_manage_all_tasks(),
	}


@frappe.whitelist()
def update_pilot_status(pilot_name, status, notes=None):
	_require_manage()
	allowed = {
		"Draft": {"Shadow", "Cancelled"},
		"Shadow": {"Operational", "Cancelled"},
		"Operational": {"Completed", "Cancelled"},
	}
	pilot = frappe.get_doc("Taskist Process Pilot", pilot_name)
	if status not in allowed.get(pilot.status, set()):
		frappe.throw(f"Pilot cannot move from {pilot.status} to {status}.")
	if status == "Completed":
		dashboard = get_pilot_dashboard(pilot_name)
		if not dashboard.get("ready_for_signoff"):
			frappe.throw("Resolve the failed readiness checks before completing this pilot.")
		if not notes:
			frappe.throw("Sign-off Notes are required to complete the pilot.")
		pilot.signoff_notes = notes
	pilot.status = status
	pilot.save(ignore_permissions=True)
	return get_pilot_dashboard(pilot_name)
