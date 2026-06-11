import json
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime, nowdate

from taskist.access import can_view_all_tasks
from taskist.events import _duration_metrics, _state_for_event


def _require_analytics_access():
	if not can_view_all_tasks():
		frappe.throw(
			_("You need Taskist Manager, Taskist Auditor, System Manager, or view-all access to use analytics."),
			frappe.PermissionError,
		)


def _period(from_date=None, to_date=None):
	to_value = getdate(to_date or nowdate())
	from_value = getdate(from_date or add_days(to_value, -29))
	if from_value > to_value:
		frappe.throw(_("From Date cannot be after To Date."))
	return from_value, to_value, get_datetime(f"{to_value + timedelta(days=1)} 00:00:00")


def _chunks(values, size=500):
	for index in range(0, len(values), size):
		yield values[index:index + size]


def _all_for_names(doctype, field, names, fields, order_by=None):
	rows = []
	for names_chunk in _chunks(names):
		rows.extend(
			frappe.get_all(
				doctype,
				filters={field: ["in", names_chunk]},
				fields=fields,
				order_by=order_by,
				limit_page_length=100000,
			)
		)
	return rows


def _minutes_between(start, end):
	if not start or not end:
		return None
	return max(round((get_datetime(end) - get_datetime(start)).total_seconds() / 60), 0)


def _rework_minutes(events, as_of=None):
	started = None
	total = 0
	current_time = get_datetime(as_of) if as_of else now_datetime()
	for event in events:
		if event.event_type in ("Rework Requested", "Returned for Correction"):
			started = get_datetime(event.event_time)
		elif started and event.event_type in ("Review Requested", "Reviewed", "Completed", "Cancelled"):
			total += max((get_datetime(event.event_time) - started).total_seconds(), 0)
			started = None
	if started:
		total += max((current_time - started).total_seconds(), 0)
	return round(total / 60)


def _breach_minutes(tracker, period_end):
	if not tracker.due_at:
		return 0
	if tracker.completed_on and get_datetime(tracker.completed_on) <= get_datetime(tracker.due_at):
		return 0
	if not tracker.breached_on and get_datetime(tracker.due_at) >= period_end:
		return 0
	end = min(
		get_datetime(tracker.completed_on) if tracker.completed_on else now_datetime(),
		now_datetime(),
		period_end,
	)
	return max(round((end - get_datetime(tracker.due_at)).total_seconds() / 60), 0)


def _new_group(label):
	return {
		"label": label or "Unspecified",
		"measured": 0,
		"volume": 0,
		"completed": 0,
		"backlog": 0,
		"tracked": 0,
		"compliant": 0,
		"response_tracked": 0,
		"response_met": 0,
		"breaches": 0,
		"breach_minutes": 0,
		"active_minutes": 0,
		"waiting_minutes": 0,
		"paused_minutes": 0,
		"handoff_minutes": 0,
		"rework_minutes": 0,
		"acknowledged": 0,
		"assigned": 0,
	}


def _finalize_group(group):
	total_flow = group["active_minutes"] + group["waiting_minutes"]
	return {
		**group,
		"sla_compliance_pct": round(group["compliant"] * 100 / group["tracked"], 1) if group["tracked"] else None,
		"response_compliance_pct": (
			round(group["response_met"] * 100 / group["response_tracked"], 1)
			if group["response_tracked"]
			else None
		),
		"flow_efficiency_pct": round(group["active_minutes"] * 100 / total_flow, 1) if total_flow else None,
		"acknowledgement_pct": round(group["acknowledged"] * 100 / group["assigned"], 1) if group["assigned"] else None,
		"avg_active_minutes": round(group["active_minutes"] / group["measured"]) if group["measured"] else 0,
		"avg_waiting_minutes": round(group["waiting_minutes"] / group["measured"]) if group["measured"] else 0,
		"avg_pause_minutes": round(group["paused_minutes"] / group["measured"]) if group["measured"] else 0,
		"avg_handoff_minutes": round(group["handoff_minutes"] / group["measured"]) if group["measured"] else 0,
		"avg_rework_minutes": round(group["rework_minutes"] / group["measured"]) if group["measured"] else 0,
		"avg_breach_minutes": round(group["breach_minutes"] / group["breaches"]) if group["breaches"] else 0,
	}


def _add_task_to_group(group, metric):
	for field in (
		"measured", "volume", "completed", "backlog", "tracked", "compliant", "response_tracked",
		"response_met", "breaches", "breach_minutes", "active_minutes", "waiting_minutes",
		"paused_minutes", "handoff_minutes", "rework_minutes", "acknowledged", "assigned",
	):
		group[field] += metric[field]


def _analytics_data(from_date=None, to_date=None, department=None, process_rule=None, priority=None):
	from_value, to_value, period_end = _period(from_date, to_date)
	task_filters = {"creation": ["<", period_end]}
	if process_rule:
		task_filters["taskist_process_rule"] = process_rule
	if priority:
		task_filters["priority"] = priority

	rule_rows = frappe.get_all(
		"Taskist Process Rule",
		fields=["name", "department"],
		limit_page_length=100000,
	)
	rule_departments = {row.name: row.department or "Unspecified" for row in rule_rows}
	if department:
		rules = [name for name, value in rule_departments.items() if value == department]
		if not rules:
			return _empty_dashboard(from_value, to_value)
		if process_rule and process_rule not in rules:
			return _empty_dashboard(from_value, to_value)
		if not process_rule:
			task_filters["taskist_process_rule"] = ["in", rules]

	tasks = frappe.get_all(
		"Task",
		filters=task_filters,
		fields=[
			"name", "subject", "status", "priority", "creation", "completed_on",
			"taskist_process_rule", "taskist_process_trigger_event",
		],
		order_by="creation asc",
		limit_page_length=100000,
	)
	if not tasks:
		return _empty_dashboard(from_value, to_value)

	task_names = [task.name for task in tasks]
	trackers = _all_for_names(
		"Taskist SLA Tracker",
		"task",
		task_names,
		[
			"name", "task", "status", "start_time", "response_due_at", "responded_on",
			"response_status", "due_at", "breached_on", "completed_on", "priority",
		],
	)
	events = _all_for_names(
		"Taskist SLA Event",
		"task",
		task_names,
		["task", "event_type", "event_time", "new_value"],
		order_by="event_time asc, creation asc",
	)
	trackers_by_task = defaultdict(list)
	events_by_task = defaultdict(list)
	for tracker in trackers:
		trackers_by_task[tracker.task].append(tracker)
	for event in events:
		events_by_task[event.task].append(event)

	period_start = get_datetime(f"{from_value} 00:00:00")
	task_metrics = []
	trend = {
		str(day): {"date": str(day), "created": 0, "completed": 0, "breached": 0}
		for day in (from_value + timedelta(days=offset) for offset in range((to_value - from_value).days + 1))
	}

	for task in tasks:
		created = get_datetime(task.creation)
		task_events = [
			event for event in events_by_task[task.name]
			if get_datetime(event.event_time) < period_end
		]
		task_trackers = trackers_by_task[task.name]
		completed_on = get_datetime(task.completed_on) if task.completed_on else None
		created_in_period = period_start <= created < period_end
		completed_in_period = bool(completed_on and period_start <= completed_on < period_end)
		event_state = "waiting"
		for event in task_events:
			event_state = _state_for_event(event, event_state)
		closed_by_period_end = event_state == "closed" if task_events else bool(
			completed_on and completed_on < period_end
		)
		backlog_at_period_end = created < period_end and not closed_by_period_end
		relevant = created_in_period or completed_in_period or backlog_at_period_end
		if not relevant:
			continue

		as_of = min(now_datetime(), period_end)
		durations = _duration_metrics(task_events, as_of=as_of)
		rework_minutes = _rework_minutes(task_events, as_of=as_of)
		assigned = int(any(event.event_type in ("Assigned", "Reassigned", "Handoff Received") for event in task_events))
		acknowledged = int(any(event.event_type in ("Acknowledged", "Started") for event in task_events))
		tracked = 0
		compliant = 0
		response_tracked = 0
		response_met = 0
		breaches = 0
		breach_minutes = 0
		response_minutes = []
		resolution_minutes = []

		for tracker in task_trackers:
			if tracker.start_time and get_datetime(tracker.start_time) >= period_end:
				continue
			metric_cutoff = min(now_datetime(), period_end)
			responded_by_period_end = bool(
				tracker.responded_on and get_datetime(tracker.responded_on) < period_end
			)
			breached_by_period_end = bool(
				tracker.breached_on and get_datetime(tracker.breached_on) < period_end
			)
			completed_by_period_end = bool(
				tracker.completed_on and get_datetime(tracker.completed_on) < period_end
			)
			response_overdue = bool(
				not responded_by_period_end
				and tracker.response_due_at
				and get_datetime(tracker.response_due_at) < metric_cutoff
			)
			resolution_overdue = bool(
				not completed_by_period_end
				and tracker.due_at
				and get_datetime(tracker.due_at) < metric_cutoff
			)
			response_evaluated = responded_by_period_end or (
				tracker.response_status == "Breached"
				and tracker.response_due_at
				and get_datetime(tracker.response_due_at) < period_end
			) or response_overdue
			if tracker.response_due_at and response_evaluated:
				response_tracked += 1
				if responded_by_period_end and get_datetime(tracker.responded_on) <= get_datetime(tracker.response_due_at):
					response_met += 1
			if responded_by_period_end:
				value = _minutes_between(tracker.start_time, tracker.responded_on)
				if value is not None:
					response_minutes.append(value)
			if completed_by_period_end:
				value = _minutes_between(tracker.start_time, tracker.completed_on)
				if value is not None:
					resolution_minutes.append(value)
			resolution_evaluated = completed_by_period_end or breached_by_period_end or resolution_overdue
			if resolution_evaluated:
				tracked += 1
				is_compliant = bool(
					completed_by_period_end
					and tracker.due_at
					and get_datetime(tracker.completed_on) <= get_datetime(tracker.due_at)
				)
				compliant += int(is_compliant)
			current_breach_minutes = _breach_minutes(tracker, period_end)
			if current_breach_minutes or breached_by_period_end:
				breaches += 1
				breach_minutes += current_breach_minutes
				breach_date = getdate(tracker.breached_on if breached_by_period_end else tracker.due_at)
				if str(breach_date) in trend:
					trend[str(breach_date)]["breached"] += 1

		if created_in_period:
			trend[str(getdate(created))]["created"] += 1
		if completed_in_period:
			trend[str(getdate(completed_on))]["completed"] += 1

		task_metrics.append({
			"task": task.name,
			"process": task.taskist_process_rule or "General Tasks",
			"department": rule_departments.get(task.taskist_process_rule, "Unspecified"),
			"priority": task.priority or "Unspecified",
			"workflow_state": task.taskist_process_trigger_event or "Direct Assignment",
			"measured": 1,
			"volume": int(created_in_period),
			"completed": int(completed_in_period),
			"backlog": int(backlog_at_period_end),
			"tracked": tracked,
			"compliant": compliant,
			"response_tracked": response_tracked,
			"response_met": response_met,
			"breaches": breaches,
			"breach_minutes": breach_minutes,
			"active_minutes": durations["active_minutes"],
			"waiting_minutes": durations["waiting_minutes"],
			"paused_minutes": durations["paused_minutes"],
			"handoff_minutes": durations["handoff_minutes"],
			"rework_minutes": rework_minutes,
			"assigned": assigned,
			"acknowledged": acknowledged,
			"response_minutes": response_minutes,
			"resolution_minutes": resolution_minutes,
			"age_minutes": max(round((min(now_datetime(), period_end) - created).total_seconds() / 60), 0),
		})

	groups = {
		"process": defaultdict(lambda: None),
		"department": defaultdict(lambda: None),
		"priority": defaultdict(lambda: None),
		"workflow": defaultdict(lambda: None),
	}
	total = _new_group("All Work")
	all_response_minutes = []
	all_resolution_minutes = []
	for metric in task_metrics:
		_add_task_to_group(total, metric)
		all_response_minutes.extend(metric["response_minutes"])
		all_resolution_minutes.extend(metric["resolution_minutes"])
		for dimension, key in (
			("process", metric["process"]),
			("department", metric["department"]),
			("priority", metric["priority"]),
			("workflow", metric["workflow_state"]),
		):
			if groups[dimension][key] is None:
				groups[dimension][key] = _new_group(key)
			_add_task_to_group(groups[dimension][key], metric)

	summary = _finalize_group(total)
	summary.update({
		"avg_response_minutes": round(sum(all_response_minutes) / len(all_response_minutes)) if all_response_minutes else 0,
		"avg_resolution_minutes": (
			round(sum(all_resolution_minutes) / len(all_resolution_minutes)) if all_resolution_minutes else 0
		),
		"avg_backlog_age_minutes": (
			round(sum(item["age_minutes"] for item in task_metrics if item["backlog"]) / summary["backlog"])
			if summary["backlog"]
			else 0
		),
	})

	final_groups = {
		key: sorted((_finalize_group(value) for value in values.values()), key=lambda row: row["volume"], reverse=True)
		for key, values in groups.items()
	}
	delays = _delay_metrics(task_names, period_start, period_end)
	notifications = _notification_metrics(task_names, period_start, period_end)
	heatmap = _heatmap(task_metrics)

	return {
		"period": {"from_date": str(from_value), "to_date": str(to_value)},
		"summary": summary,
		"by_process": final_groups["process"],
		"by_department": final_groups["department"],
		"by_priority": final_groups["priority"],
		"by_workflow": final_groups["workflow"],
		"bottlenecks": sorted(
			final_groups["workflow"],
			key=lambda row: (row["avg_waiting_minutes"], row["breaches"], row["rework_minutes"]),
			reverse=True,
		)[:10],
		"heatmap": heatmap,
		"delays": delays,
		"notifications": notifications,
		"trend": list(trend.values()),
		"filters": {
			"departments": sorted({row["label"] for row in final_groups["department"]}),
			"processes": sorted({row["label"] for row in final_groups["process"]}),
			"priorities": ["Urgent", "High", "Medium", "Low"],
		},
	}


def _delay_metrics(task_names, period_start, period_end):
	logs = _all_for_names(
		"Taskist Delay Log",
		"task",
		task_names,
		["delay_reason", "action", "logged_on"],
	)
	logs = [row for row in logs if row.logged_on and period_start <= get_datetime(row.logged_on) < period_end]
	reason_names = list({row.delay_reason for row in logs if row.delay_reason})
	reasons = {}
	if reason_names:
		for row in frappe.get_all(
			"Taskist Delay Reason",
			filters={"name": ["in", reason_names]},
			fields=["name", "category", "responsible_party"],
			limit_page_length=100000,
		):
			reasons[row.name] = row
	by_reason = defaultdict(int)
	by_owner = defaultdict(int)
	by_action = defaultdict(int)
	for log in logs:
		context = reasons.get(log.delay_reason)
		by_reason[log.delay_reason or "Unspecified"] += 1
		by_owner[(context.responsible_party if context else None) or "Unspecified"] += 1
		by_action[log.action or "Unspecified"] += 1
	return {
		"total": len(logs),
		"by_reason": [{"label": key, "count": value} for key, value in sorted(by_reason.items(), key=lambda row: row[1], reverse=True)],
		"by_responsible_party": [
			{"label": key, "count": value} for key, value in sorted(by_owner.items(), key=lambda row: row[1], reverse=True)
		],
		"by_action": [{"label": key, "count": value} for key, value in sorted(by_action.items(), key=lambda row: row[1], reverse=True)],
	}


def _notification_metrics(task_names, period_start, period_end):
	deliveries = _all_for_names(
		"Taskist Notification Delivery",
		"task",
		task_names,
		["status", "channel", "attempts", "creation", "sent_on"],
	)
	deliveries = [row for row in deliveries if period_start <= get_datetime(row.creation) < period_end]
	by_status = defaultdict(int)
	by_channel = defaultdict(lambda: {"total": 0, "sent": 0, "failed": 0, "pending": 0})
	for delivery in deliveries:
		by_status[delivery.status] += 1
		channel = by_channel[delivery.channel or "Unspecified"]
		channel["total"] += 1
		channel[delivery.status.lower()] = channel.get(delivery.status.lower(), 0) + 1
	total = len(deliveries)
	sent = by_status["Sent"]
	return {
		"total": total,
		"sent": sent,
		"failed": by_status["Failed"],
		"pending": by_status["Pending"],
		"cancelled": by_status["Cancelled"],
		"success_rate_pct": round(sent * 100 / total, 1) if total else None,
		"channels": [{"label": key, **value} for key, value in sorted(by_channel.items())],
	}


def _heatmap(task_metrics):
	cells = {}
	for metric in task_metrics:
		key = (metric["department"], metric["process"])
		if key not in cells:
			cells[key] = _new_group(metric["process"])
		_add_task_to_group(cells[key], metric)
	departments = sorted({key[0] for key in cells})
	processes = sorted({key[1] for key in cells})
	rows = []
	for process in processes:
		values = []
		for department in departments:
			group = cells.get((department, process))
			values.append(_finalize_group(group) if group else None)
		rows.append({"process": process, "values": values})
	return {"departments": departments, "rows": rows}


def _empty_dashboard(from_date, to_date):
	summary = _finalize_group(_new_group("All Work"))
	summary.update({
		"avg_response_minutes": 0,
		"avg_resolution_minutes": 0,
		"avg_backlog_age_minutes": 0,
	})
	return {
		"period": {"from_date": str(from_date), "to_date": str(to_date)},
		"summary": summary,
		"by_process": [],
		"by_department": [],
		"by_priority": [],
		"by_workflow": [],
		"bottlenecks": [],
		"heatmap": {"departments": [], "rows": []},
		"delays": {"total": 0, "by_reason": [], "by_responsible_party": [], "by_action": []},
		"notifications": {
			"total": 0, "sent": 0, "failed": 0, "pending": 0, "cancelled": 0,
			"success_rate_pct": None, "channels": [],
		},
		"trend": [],
		"filters": {"departments": [], "processes": [], "priorities": ["Urgent", "High", "Medium", "Low"]},
	}


@frappe.whitelist()
def get_kpi_dashboard(from_date=None, to_date=None, department=None, process_rule=None, priority=None):
	_require_analytics_access()
	return _analytics_data(from_date, to_date, department, process_rule, priority)


@frappe.whitelist()
def get_kpi_snapshots(limit=12):
	_require_analytics_access()
	rows = frappe.get_all(
		"Taskist KPI Snapshot",
		fields=["name", "month_start", "period_end", "generated_on", "generated_by", "metrics_json"],
		order_by="month_start desc",
		limit_page_length=min(max(int(limit or 12), 1), 60),
	)
	for row in rows:
		try:
			row.metrics = json.loads(row.metrics_json)
		except (TypeError, json.JSONDecodeError):
			row.metrics = {}
		row.pop("metrics_json", None)
		for field in ("month_start", "period_end", "generated_on"):
			if row.get(field):
				row[field] = str(row[field])
	return rows


def create_monthly_kpi_snapshot():
	today = getdate(nowdate())
	current_month = today.replace(day=1)
	period_end = current_month - timedelta(days=1)
	month_start = period_end.replace(day=1)
	snapshot_key = month_start.strftime("%Y-%m")
	if frappe.db.exists("Taskist KPI Snapshot", snapshot_key):
		return snapshot_key

	data = _analytics_data(month_start, period_end)
	doc = frappe.new_doc("Taskist KPI Snapshot")
	doc.snapshot_key = snapshot_key
	doc.month_start = month_start
	doc.period_end = period_end
	doc.generated_on = now_datetime()
	doc.generated_by = frappe.session.user
	doc.metrics_json = json.dumps(data, default=str, sort_keys=True)
	doc.insert(ignore_permissions=True)
	return doc.name
