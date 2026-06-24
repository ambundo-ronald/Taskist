import hashlib
import json
from datetime import datetime, timedelta

import frappe
from frappe.utils import add_to_date, get_datetime, get_time, now_datetime


DONE_TASK_STATUSES = ["Completed", "Cancelled"]
RESPONDED_TASK_STATUSES = ["Working", "Pending Review", "Completed"]


def _loads_filters(value):
	if not value:
		return {}
	if isinstance(value, (dict, list)):
		return value
	return json.loads(value)


def _task_users(task):
	if not task.get("_assign"):
		return []
	try:
		assignees = json.loads(task._assign)
	except (json.JSONDecodeError, TypeError):
		return []
	return assignees or []


def _task_user(task):
	users = _task_users(task)
	return users[0] if users else None


def _tracker_name(rule_name, task_name):
	return f"{rule_name}-{task_name}"[:140]


def _source_document(rule, task):
	try:
		return frappe.get_doc(rule.reference_doctype, task.taskist_reference_name)
	except frappe.DoesNotExistError:
		return None


def _priority_for_task(rule, task, source_doc):
	priority = None
	if source_doc and rule.priority_field:
		priority = source_doc.get(rule.priority_field)
	return str(priority or task.get("priority") or rule.default_priority or "Medium")


def _priority_target(rule, priority):
	for row in rule.sla_priorities or []:
		if (row.priority or "").lower() == priority.lower():
			return row
	return None


def _holiday_dates(rule):
	if not rule.holiday_list:
		return set()
	return {
		row.holiday_date
		for row in frappe.get_all(
			"Holiday",
			filters={"parent": rule.holiday_list},
			fields=["holiday_date"],
			limit_page_length=1000,
		)
	}


def _next_working_day(value, holidays, start_time):
	current = value
	while current.date() in holidays or current.weekday() >= 5:
		current = datetime.combine(current.date() + timedelta(days=1), start_time)
	return current


def _add_service_minutes(rule, start, minutes):
	if not rule.apply_working_hours:
		return add_to_date(start, minutes=minutes, as_datetime=True)

	work_start = get_time(rule.working_hours_start or "08:00:00")
	work_end = get_time(rule.working_hours_end or "17:00:00")
	if work_end <= work_start:
		frappe.throw(f"Working Hours End must be after Working Hours Start on SLA {rule.name}")

	holidays = _holiday_dates(rule)
	current = _next_working_day(get_datetime(start), holidays, work_start)
	if current.time() < work_start:
		current = datetime.combine(current.date(), work_start)
	elif current.time() >= work_end:
		current = _next_working_day(
			datetime.combine(current.date() + timedelta(days=1), work_start),
			holidays,
			work_start,
		)

	remaining = max(int(minutes or 0), 0)
	while remaining:
		end_of_day = datetime.combine(current.date(), work_end)
		available = max(int((end_of_day - current).total_seconds() // 60), 0)
		if remaining <= available:
			return current + timedelta(minutes=remaining)
		remaining -= available
		current = _next_working_day(
			datetime.combine(current.date() + timedelta(days=1), work_start),
			holidays,
			work_start,
		)
	return current


def _deadline_values(rule, task, source_doc):
	priority = _priority_for_task(rule, task, source_doc)
	target = _priority_target(rule, priority)
	if not target and rule.default_priority:
		priority = rule.default_priority
		target = _priority_target(rule, priority)
	response_minutes = int(target.first_response_minutes or 0) if target else 0
	resolution_minutes = int(target.resolution_minutes or 0) if target else int(rule.target_minutes or 0)
	warning_minutes = (
		int(target.warning_minutes_before_due or 0)
		if target
		else int(rule.warning_minutes_before_due or 0)
	)
	start_time = get_datetime(task.creation)
	response_due_at = _add_service_minutes(rule, start_time, response_minutes) if response_minutes else None
	due_at = _add_service_minutes(rule, start_time, resolution_minutes)
	warning_at = (
		_add_service_minutes(rule, start_time, max(resolution_minutes - warning_minutes, 0))
		if warning_minutes
		else None
	)
	return priority, start_time, response_due_at, warning_at, due_at


def _send_push(user, title, body, task_name, tag):
	if not user:
		return False
	from taskist.push import send_push_to_user

	result = send_push_to_user(
		user,
		title,
		body,
		f"/taskist?task={task_name}",
		data={"task": task_name},
		tag=tag,
	)
	if not result.get("sent"):
		raise RuntimeError(result.get("skipped") or "No active push subscription")
	return True


def _send_in_app(user, title, body, task_name):
	if not user:
		return False
	notification = frappe.new_doc("Notification Log")
	notification.subject = title
	notification.email_content = body
	notification.for_user = user
	notification.type = "Alert"
	notification.document_type = "Task"
	notification.document_name = task_name
	notification.from_user = "Administrator"
	notification.insert(ignore_permissions=True)
	frappe.publish_realtime(
		"taskist_notification",
		{"title": title, "body": body, "task": task_name, "url": f"/taskist?task={task_name}"},
		user=user,
		after_commit=True,
	)
	return True


def _send_email(user, title, body, task_name):
	if not user:
		return False
	frappe.sendmail(
		recipients=[user],
		subject=title,
		message=f"{body}<br><br><a href=\"{frappe.utils.get_url('/taskist?task=' + task_name)}\">Open Taskist</a>",
	)
	return True


def _delivery_channels(channel):
	channels = []
	if channel in ("Push", "Push and Email", "All"):
		channels.append("Push")
	if channel in ("In App", "All"):
		channels.append("In App")
	if channel in ("Email", "Push and Email", "All"):
		channels.append("Email")
	return channels


def _delivery_name(event_key, user, channel):
	value = f"{event_key}|{user}|{channel}"
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _attempt_delivery(event_key, tracker_name, user, channel, title, body, task_name):
	name = _delivery_name(event_key, user, channel)
	if frappe.db.exists("Taskist Notification Delivery", name):
		delivery = frappe.get_doc("Taskist Notification Delivery", name)
	else:
		delivery = frappe.new_doc("Taskist Notification Delivery")
		delivery.name = name
		delivery.event_key = event_key
		delivery.tracker = tracker_name
		delivery.task = task_name
		delivery.recipient = user
		delivery.channel = channel
		delivery.title = title
		delivery.body = body

	if delivery.status in ("Sent", "Cancelled") or int(delivery.attempts or 0) >= 5:
		return True

	delivery.attempts = int(delivery.attempts or 0) + 1
	try:
		if channel == "Push":
			_send_push(user, title, body, task_name, event_key)
		elif channel == "In App":
			_send_in_app(user, title, body, task_name)
		elif channel == "Email":
			_send_email(user, title, body, task_name)
		delivery.status = "Sent"
		delivery.sent_on = now_datetime()
		delivery.last_error = None
	except Exception as exc:
		delivery.status = "Failed"
		delivery.last_error = str(exc)[:500]
		frappe.log_error(frappe.get_traceback(), "Taskist SLA Notification Delivery")
	delivery.save(ignore_permissions=True)
	from taskist.events import record_event

	record_event(
		task_name,
		"Notification Sent" if delivery.status == "Sent" else "Notification Failed",
		tracker=tracker_name,
		new_value=f"{channel}: {user}",
		notes=title if delivery.status == "Sent" else delivery.last_error,
		metadata={
			"recipient": user,
			"channel": channel,
			"title": title,
			"attempt": delivery.attempts,
			"delivery": delivery.name,
		},
		dedupe_key=f"delivery:{delivery.name}:{delivery.attempts}:{delivery.status}",
	)
	return delivery.status == "Sent" or int(delivery.attempts or 0) >= 5


def _deliver(users, channel, title, body, task_name, event_key, tracker_name=None):
	results = []
	for user in set(filter(None, users)):
		for delivery_channel in _delivery_channels(channel):
			results.append(
				_attempt_delivery(
					event_key,
					tracker_name,
					user,
					delivery_channel,
					title,
					body,
					task_name,
				)
			)
	return bool(results) and all(results)


def _deliver_alert(users, title, body, task_name, event_key, tracker_name=None):
	push_ok = _deliver(users, "Push", title, body, task_name, f"{event_key}:push", tracker_name)
	in_app_ok = _deliver(users, "In App", title, body, task_name, f"{event_key}:in-app", tracker_name)
	return push_ok or in_app_ok


def retry_failed_deliveries():
	"""Retry failed notification channels unless their SLA was cancelled."""
	retry_before = add_to_date(now_datetime(), minutes=-4, as_datetime=True)
	names = frappe.get_all(
		"Taskist Notification Delivery",
		filters={
			"status": "Failed",
			"attempts": ["<", 5],
			"modified": ["<=", retry_before],
		},
		pluck="name",
		limit_page_length=200,
	)
	for name in names:
		delivery = frappe.get_doc("Taskist Notification Delivery", name)
		if delivery.tracker:
			tracker_status = frappe.db.get_value("Taskist SLA Tracker", delivery.tracker, "status")
			if tracker_status == "Cancelled":
				delivery.status = "Cancelled"
				delivery.last_error = None
				delivery.save(ignore_permissions=True)
				continue
		_attempt_delivery(
			delivery.event_key,
			delivery.tracker,
			delivery.recipient,
			delivery.channel,
			delivery.title,
			delivery.body,
			delivery.task,
		)


def _escalation_recipients(row, tracker):
	if row.recipient_type == "Assignee":
		assign_value = frappe.db.get_value("Task", tracker.task, "_assign")
		return _task_users({"_assign": assign_value})
	if row.recipient_type == "User":
		return [row.recipient]
	if row.recipient_type == "Role":
		users = frappe.get_all(
			"Has Role",
			filters={"role": row.recipient, "parenttype": "User"},
			pluck="parent",
			limit_page_length=500,
		)
		if not users:
			return []
		return frappe.get_all(
			"User",
			filters={"name": ["in", users], "enabled": 1},
			pluck="name",
			limit_page_length=500,
		)
	if row.recipient_type == "Document Owner":
		return [
			frappe.db.get_value(
				tracker.reference_doctype,
				tracker.reference_name,
				"owner",
			)
		]
	return []


def ensure_tracker(rule, task):
	from taskist.governance import is_rule_effective

	if not is_rule_effective(rule):
		return None
	tracker_name = _tracker_name(rule.name, task.name)
	is_new = not frappe.db.exists("Taskist SLA Tracker", tracker_name)
	tracker = frappe.new_doc("Taskist SLA Tracker") if is_new else frappe.get_doc("Taskist SLA Tracker", tracker_name)

	if is_new:
		from taskist.governance import current_revision

		tracker.name = tracker_name
		tracker.rule = rule.name
		tracker.rule_revision = current_revision(rule)
		tracker.policy_snapshot_json = frappe.db.get_value(
			"Taskist Rule Revision",
			tracker.rule_revision,
			"configuration_json",
		)
		tracker.task = task.name
		tracker.reference_doctype = task.taskist_reference_doctype
		tracker.reference_name = task.taskist_reference_name

	source_doc = _source_document(rule, task)
	priority, start_time, response_due_at, warning_at, due_at = _deadline_values(rule, task, source_doc)
	tracker.user = _task_user(task)
	tracker.priority = priority
	tracker.start_time = start_time
	tracker.response_due_at = response_due_at
	tracker.warning_at = warning_at
	tracker.due_at = due_at
	if task.status in DONE_TASK_STATUSES:
		tracker.status = task.status
		tracker.completed_on = tracker.completed_on or now_datetime()
	elif getattr(tracker, "status", None) in DONE_TASK_STATUSES:
		tracker.status = "Open"
		tracker.completed_on = None
	else:
		tracker.status = getattr(tracker, "status", None) or "Open"
	tracker.response_status = getattr(tracker, "response_status", None) or "Pending"
	tracker.save(ignore_permissions=True)
	if is_new:
		from taskist.events import record_event

		record_event(
			task.name,
			"SLA Started",
			tracker=tracker.name,
			new_value=str(tracker.due_at),
			notes=f"SLA {rule.name} started with {priority} priority.",
			metadata={
				"rule": rule.name,
				"response_due_at": tracker.response_due_at,
				"warning_at": tracker.warning_at,
				"due_at": tracker.due_at,
			},
			event_time=start_time,
			dedupe_key=f"sla-started:{tracker.name}",
		)
	return tracker


def mark_response_for_task(task):
	if task.status not in RESPONDED_TASK_STATUSES:
		return
	trackers = frappe.get_all(
		"Taskist SLA Tracker",
		filters={"task": task.name, "response_status": ["in", ["Pending", "Breached"]]},
		pluck="name",
		limit_page_length=100,
	)
	now = now_datetime()
	for name in trackers:
		tracker = frappe.get_doc("Taskist SLA Tracker", name)
		previous_status = tracker.response_status
		tracker.responded_on = now
		if tracker.response_status != "Breached":
			tracker.response_status = (
				"Met"
				if not tracker.response_due_at or now <= get_datetime(tracker.response_due_at)
				else "Breached"
			)
		tracker.save(ignore_permissions=True)
		from taskist.events import record_event

		record_event(
			task.name,
			"Acknowledged",
			tracker=tracker.name,
			previous_value=previous_status,
			new_value=tracker.response_status,
			notes="First SLA response recorded.",
			event_time=now,
			dedupe_key=f"acknowledged:{tracker.name}",
		)


def complete_trackers_for_task(task):
	mark_response_for_task(task)
	trackers = frappe.get_all(
		"Taskist SLA Tracker",
		filters={"task": task.name, "status": ["not in", ["Completed", "Cancelled"]]},
		pluck="name",
		limit_page_length=100,
	)
	for name in trackers:
		tracker = frappe.get_doc("Taskist SLA Tracker", name)
		tracker.status = "Completed" if task.status == "Completed" else "Cancelled"
		tracker.completed_on = now_datetime()
		if tracker.active_pause and frappe.db.exists("Taskist SLA Pause", tracker.active_pause):
			frappe.db.set_value(
				"Taskist SLA Pause",
				tracker.active_pause,
				{"status": "Cancelled", "resumed_on": now_datetime()},
				update_modified=False,
			)
		tracker.pause_status = "Not Paused"
		tracker.active_pause = None
		tracker.save(ignore_permissions=True)
		extension_names = frappe.get_all(
			"Taskist SLA Extension",
			filters={"task": task.name, "status": "Requested"},
			pluck="name",
			limit_page_length=100,
		)
		for extension_name in extension_names:
			frappe.db.set_value(
				"Taskist SLA Extension",
				extension_name,
				{"status": "Cancelled", "decided_on": now_datetime()},
				update_modified=False,
			)
		if tracker.status == "Cancelled":
			delivery_names = frappe.get_all(
				"Taskist Notification Delivery",
				filters={
					"tracker": tracker.name,
					"status": ["in", ["Pending", "Failed"]],
				},
				pluck="name",
				limit_page_length=500,
			)
			for delivery_name in delivery_names:
				frappe.db.set_value(
					"Taskist Notification Delivery",
					delivery_name,
					{"status": "Cancelled", "last_error": None},
					update_modified=False,
				)


def _task_matches_rule(rule, task):
	try:
		filters = _loads_filters(rule.conditions_json)
	except Exception:
		frappe.log_error(f"Invalid SLA filters on {rule.name}", "Taskist SLA")
		return False
	if not filters:
		return True
	filters = list(filters) if isinstance(filters, list) else dict(filters)
	if isinstance(filters, dict):
		filters["name"] = task.taskist_reference_name
	else:
		filters.append(["name", "=", task.taskist_reference_name])
	return bool(frappe.get_all(rule.reference_doctype, filters=filters, pluck="name", limit_page_length=1))


def evaluate_task_against_sla_rules(task):
	if not task.get("taskist_reference_doctype") or not task.get("taskist_reference_name"):
		return
	rules = frappe.get_all(
		"Taskist SLA Rule",
		filters={"enabled": 1, "reference_doctype": task.taskist_reference_doctype},
		pluck="name",
		limit_page_length=100,
	)
	for rule_name in rules:
		rule = frappe.get_doc("Taskist SLA Rule", rule_name)
		from taskist.governance import is_rule_effective

		if not is_rule_effective(rule):
			continue
		if _task_matches_rule(rule, task):
			ensure_tracker(rule, task)


def _evaluate_escalations(rule, tracker, now):
	sent = set(json.loads(tracker.escalations_sent_json or "[]"))
	changed = False
	for row in rule.escalation_matrix or []:
		if row.trigger == "Warning" and tracker.status == "Breached":
			continue
		base_time = {
			"Response Breach": tracker.response_due_at,
			"Warning": tracker.warning_at,
			"Breach": tracker.due_at,
		}.get(row.trigger)
		if not base_time:
			continue
		trigger_at = add_to_date(base_time, minutes=int(row.after_minutes or 0), as_datetime=True)
		key = f"{row.trigger}:{row.level}:{row.idx}"
		if now < get_datetime(trigger_at) or key in sent:
			continue
		title = f"SLA {row.trigger.lower()} escalation"
		body = f"{tracker.task} reached SLA {row.trigger.lower()} level {row.level}."
		delivered = _deliver(
			_escalation_recipients(row, tracker),
			row.channel,
			title,
			body,
			tracker.task,
			f"taskist-sla-{key}-{tracker.name}-{trigger_at}",
			tracker.name,
		)
		if not delivered:
			continue
		sent.add(key)
		tracker.current_escalation_level = max(int(tracker.current_escalation_level or 0), int(row.level or 0))
		from taskist.events import record_event

		record_event(
			tracker.task,
			"Escalated",
			tracker=tracker.name,
			new_value=f"Level {row.level}",
			notes=f"{row.trigger} escalation sent through {row.channel}.",
			metadata={
				"trigger": row.trigger,
				"level": row.level,
				"recipient_type": row.recipient_type,
				"recipient": row.recipient,
				"channel": row.channel,
			},
			dedupe_key=f"escalation:{tracker.name}:{key}",
		)
		changed = True
	if changed:
		tracker.escalations_sent_json = json.dumps(sorted(sent))


def evaluate_sla_rules():
	"""Create/update trackers, then evaluate response, resolution, and escalation deadlines."""
	rules = frappe.get_all(
		"Taskist SLA Rule",
		filters={"enabled": 1},
		pluck="name",
		limit_page_length=100,
	)
	for rule_name in rules:
		rule = frappe.get_doc("Taskist SLA Rule", rule_name)
		from taskist.governance import is_rule_effective

		if not is_rule_effective(rule):
			continue
		try:
			filters = _loads_filters(rule.conditions_json)
		except Exception:
			frappe.log_error(f"Invalid SLA filters on {rule.name}", "Taskist SLA")
			continue
		source_names = frappe.get_all(
			rule.reference_doctype,
			filters=filters,
			pluck="name",
			limit_page_length=500,
		)
		if not source_names:
			continue
		tasks = frappe.get_all(
			"Task",
			filters={
				"taskist_reference_doctype": rule.reference_doctype,
				"taskist_reference_name": ["in", source_names],
				"is_template": 0,
			},
			fields=[
				"name", "status", "priority", "creation", "_assign",
				"taskist_reference_doctype", "taskist_reference_name",
			],
			limit_page_length=500,
		)
		for task in tasks:
			if task.status in DONE_TASK_STATUSES:
				complete_trackers_for_task(task)
			else:
				ensure_tracker(rule, task)
				mark_response_for_task(task)
	evaluate_open_trackers()


def evaluate_open_trackers():
	now = now_datetime()
	names = frappe.get_all(
		"Taskist SLA Tracker",
		filters={"status": ["in", ["Open", "Warning", "Breached"]]},
		pluck="name",
		limit_page_length=500,
	)
	for name in names:
		tracker = frappe.get_doc("Taskist SLA Tracker", name)
		rule = frappe.get_doc("Taskist SLA Rule", tracker.rule)
		assign_value = frappe.db.get_value("Task", tracker.task, "_assign")
		assignees = _task_users({"_assign": assign_value}) or [tracker.user]

		if tracker.response_status == "Pending" and tracker.response_due_at:
			if get_datetime(tracker.response_due_at) <= now:
				tracker.response_status = "Breached"
				from taskist.events import record_event

				record_event(
					tracker.task,
					"Response Breached",
					tracker=tracker.name,
					previous_value="Pending",
					new_value="Breached",
					notes="First response target was exceeded.",
					event_time=now,
					dedupe_key=f"response-breached:{tracker.name}:{tracker.response_due_at}",
				)
		if tracker.response_status == "Breached" and rule.notify_on_breach and not tracker.response_breach_sent_on:
			delivered = _deliver_alert(
				assignees,
				"First response SLA breached",
				f"{tracker.task} has passed its first response target.",
				tracker.task,
				f"taskist-sla-response-breach-{tracker.name}-{tracker.response_due_at}",
				tracker.name,
			)
			if delivered:
				tracker.response_breach_sent_on = now

		if tracker.due_at and get_datetime(tracker.due_at) <= now:
			if tracker.status != "Breached":
				previous_status = tracker.status
				tracker.status = "Breached"
				tracker.breached_on = now
				from taskist.events import record_event

				record_event(
					tracker.task,
					"Breached",
					tracker=tracker.name,
					previous_value=previous_status,
					new_value="Breached",
					notes="Resolution target was exceeded.",
					event_time=now,
					dedupe_key=f"resolution-breached:{tracker.name}:{tracker.due_at}",
				)
			if rule.notify_on_breach and not tracker.breach_sent_on:
				delivered = _deliver_alert(
					assignees,
					"SLA breached",
					f"{tracker.task} has passed its resolution target.",
					tracker.task,
					f"taskist-sla-breach-{tracker.name}-{tracker.due_at}",
					tracker.name,
				)
				if delivered:
					tracker.breach_sent_on = now
		elif tracker.warning_at and get_datetime(tracker.warning_at) <= now:
			if tracker.status == "Open":
				tracker.status = "Warning"
				from taskist.events import record_event

				record_event(
					tracker.task,
					"Warning",
					tracker=tracker.name,
					previous_value="Open",
					new_value="Warning",
					notes="SLA warning threshold reached.",
					event_time=now,
					dedupe_key=f"warning:{tracker.name}:{tracker.warning_at}",
				)
			if rule.notify_on_warning and not tracker.warning_sent_on:
				delivered = _deliver_alert(
					assignees,
					"SLA warning",
					f"{tracker.task} is approaching its resolution target.",
					tracker.task,
					f"taskist-sla-warning-{tracker.name}-{tracker.warning_at}",
					tracker.name,
				)
				if delivered:
					tracker.warning_sent_on = now

		_evaluate_escalations(rule, tracker, now)
		tracker.save(ignore_permissions=True)
