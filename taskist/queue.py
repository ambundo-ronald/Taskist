import json

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from taskist.access import can_view_all_tasks, visible_users


ACTIVE_STATUSES = ["Open", "Working", "Pending Review", "Overdue"]


def _task_users(task):
	if not task.get("_assign"):
		return []
	try:
		return json.loads(task._assign) or []
	except (json.JSONDecodeError, TypeError):
		return []


def _can_view_user(user):
	if can_view_all_tasks():
		return True
	users = visible_users() or set()
	return user in users


def _deadline_for_task(task, tracker=None):
	if tracker and tracker.due_at:
		return get_datetime(tracker.due_at)
	if task.exp_end_date:
		return get_datetime(task.exp_end_date)
	start = get_datetime(task.exp_start_date or task.creation or now_datetime())
	minutes = max(int(float(task.expected_time or 1) * 60), 30)
	return add_to_date(start, minutes=minutes, as_datetime=True)


def _start_for_task(task, tracker=None):
	now = now_datetime()
	start = get_datetime(
		task.exp_start_date
		or (tracker.start_time if tracker and tracker.start_time else None)
		or task.creation
		or now
	)
	if task.status in ACTIVE_STATUSES and start < now:
		return now
	return start


def _intervals_for_user(user, exclude_task=None):
	tasks = frappe.get_all(
		"Task",
		filters={
			"is_template": 0,
			"status": ["in", ACTIVE_STATUSES],
			"_assign": ["like", f'%"{user}"%'],
		},
		fields=[
			"name", "subject", "status", "priority", "exp_start_date", "exp_end_date",
			"expected_time", "creation", "_assign",
		],
		order_by="exp_start_date asc, creation asc",
		limit_page_length=200,
	)
	if exclude_task:
		tasks = [task for task in tasks if task.name != exclude_task]
	if not tasks:
		return []
	trackers = frappe.get_all(
		"Taskist SLA Tracker",
		filters={
			"task": ["in", [task.name for task in tasks]],
			"status": ["in", ["Open", "Warning", "Breached", "Paused"]],
		},
		fields=["task", "start_time", "due_at", "status", "rule"],
		order_by="due_at asc",
		limit_page_length=200,
	)
	tracker_by_task = {}
	for tracker in trackers:
		if tracker.task not in tracker_by_task:
			tracker_by_task[tracker.task] = tracker
	intervals = []
	for task in tasks:
		tracker = tracker_by_task.get(task.name)
		start = _start_for_task(task, tracker)
		end = _deadline_for_task(task, tracker)
		if end <= start:
			end = add_to_date(start, minutes=30, as_datetime=True)
		intervals.append({
			"task": task.name,
			"subject": task.subject,
			"status": task.status,
			"priority": task.priority,
			"start": start,
			"end": end,
			"sla_status": tracker.status if tracker else None,
			"sla_rule": tracker.rule if tracker else None,
		})
	return sorted(intervals, key=lambda row: (row["start"], row["end"]))


def _overlaps(start, end, interval):
	return start < interval["end"] and end > interval["start"]


def _availability(user, proposed_start=None, proposed_end=None, duration_minutes=None, exclude_task=None):
	proposed_start = get_datetime(proposed_start or now_datetime())
	if proposed_end:
		proposed_end = get_datetime(proposed_end)
	else:
		proposed_end = add_to_date(
			proposed_start,
			minutes=max(int(duration_minutes or 60), 30),
			as_datetime=True,
		)
	if proposed_end <= proposed_start:
		proposed_end = add_to_date(proposed_start, minutes=30, as_datetime=True)

	intervals = _intervals_for_user(user, exclude_task=exclude_task)
	next_start = proposed_start
	next_end = proposed_end
	while True:
		blockers = [row for row in intervals if _overlaps(next_start, next_end, row)]
		if not blockers:
			break
		next_start = max(row["end"] for row in blockers)
		duration = int((proposed_end - proposed_start).total_seconds() // 60)
		next_end = add_to_date(next_start, minutes=max(duration, 30), as_datetime=True)

	overlaps = [row for row in intervals if _overlaps(proposed_start, proposed_end, row)]
	return {
		"user": user,
		"proposed_start": str(proposed_start),
		"proposed_end": str(proposed_end),
		"available": not overlaps,
		"overlap_count": len(overlaps),
		"next_available_from": str(next_start) if overlaps else str(proposed_start),
		"intervals": [
			{
				**row,
				"start": str(row["start"]),
				"end": str(row["end"]),
			}
			for row in intervals[:25]
		],
		"overlapping_tasks": [
			{
				**row,
				"start": str(row["start"]),
				"end": str(row["end"]),
			}
			for row in overlaps[:10]
		],
	}


@frappe.whitelist()
def get_queue_advisory(user=None, proposed_start=None, proposed_end=None, duration_minutes=None, exclude_task=None):
	user = user or frappe.session.user
	if not _can_view_user(user):
		frappe.throw(_("You cannot view this user's task queue."), frappe.PermissionError)
	return _availability(
		user,
		proposed_start=proposed_start,
		proposed_end=proposed_end,
		duration_minutes=duration_minutes,
		exclude_task=exclude_task,
	)


def notify_assignment_queue_conflict(todo, task):
	assigner = getattr(todo, "owner", None)
	assignee = getattr(todo, "allocated_to", None)
	if not assigner or not assignee or assigner == "Administrator":
		return
	advisory = _availability(
		assignee,
		proposed_start=task.exp_start_date or now_datetime(),
		proposed_end=task.exp_end_date,
		exclude_task=task.name,
	)
	if advisory["available"]:
		return
	title = "Taskist queue conflict"
	body = (
		f"{assignee} already has {advisory['overlap_count']} active task(s) in that window. "
		f"Suggested start: {advisory['next_available_from']}."
	)
	notification = frappe.new_doc("Notification Log")
	notification.subject = title
	notification.email_content = body
	notification.for_user = assigner
	notification.type = "Alert"
	notification.document_type = "Task"
	notification.document_name = task.name
	notification.from_user = "Administrator"
	notification.insert(ignore_permissions=True)
	frappe.publish_realtime(
		"taskist_notification",
		{"title": title, "body": body, "task": task.name, "url": f"/taskist?task={task.name}"},
		user=assigner,
		after_commit=True,
	)
