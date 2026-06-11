import frappe
from frappe.utils import add_days


def _columns():
	return [
		{"fieldname": "event_time", "label": "Time", "fieldtype": "Datetime", "width": 160},
		{"fieldname": "event_type", "label": "Event", "fieldtype": "Data", "width": 150},
		{"fieldname": "task", "label": "Task", "fieldtype": "Link", "options": "Task", "width": 180},
		{"fieldname": "process_rule", "label": "Process", "fieldtype": "Link", "options": "Taskist Process Rule", "width": 170},
		{"fieldname": "department", "label": "Department", "fieldtype": "Data", "width": 130},
		{"fieldname": "reference_name", "label": "Source", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 170},
		{"fieldname": "reference_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType", "width": 140},
		{"fieldname": "actor", "label": "Actor", "fieldtype": "Link", "options": "User", "width": 170},
		{"fieldname": "previous_value", "label": "Previous", "fieldtype": "Data", "width": 130},
		{"fieldname": "new_value", "label": "New", "fieldtype": "Data", "width": 130},
		{"fieldname": "notes", "label": "Notes", "fieldtype": "Data", "width": 300},
		{"fieldname": "tracker", "label": "SLA Tracker", "fieldtype": "Link", "options": "Taskist SLA Tracker", "width": 180},
	]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	query_filters = {}
	if filters.task:
		query_filters["task"] = filters.task
	if filters.process_rule:
		query_filters["process_rule"] = filters.process_rule
	if filters.department:
		query_filters["department"] = filters.department
	if filters.reference_doctype:
		query_filters["reference_doctype"] = filters.reference_doctype
	if filters.reference_name:
		query_filters["reference_name"] = filters.reference_name
	if filters.event_type:
		query_filters["event_type"] = filters.event_type
	if filters.actor:
		query_filters["actor"] = filters.actor
	if filters.from_date and filters.to_date:
		query_filters["event_time"] = ["between", [filters.from_date, add_days(filters.to_date, 1)]]
	elif filters.from_date:
		query_filters["event_time"] = [">=", filters.from_date]
	elif filters.to_date:
		query_filters["event_time"] = ["<", add_days(filters.to_date, 1)]

	data = frappe.get_all(
		"Taskist SLA Event",
		filters=query_filters,
		fields=[
			"event_time",
			"event_type",
			"task",
			"process_rule",
			"department",
			"reference_doctype",
			"reference_name",
			"actor",
			"previous_value",
			"new_value",
			"notes",
			"tracker",
		],
		order_by="event_time desc",
		limit_page_length=10000,
	)
	return _columns(), data
