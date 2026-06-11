import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from taskist.access import can_manage_all_tasks, can_view_all_tasks


HEARTBEAT_NAME = "Taskist System Health"


def _require_view():
	if not can_view_all_tasks():
		frappe.throw(_("You do not have access to system health."), frappe.PermissionError)


def _require_manage():
	if not can_manage_all_tasks():
		frappe.throw(_("Only Taskist Managers can run recovery actions."), frappe.PermissionError)


def record_scheduler_heartbeat():
	"""Record proof that the five-minute Taskist scheduler is executing."""
	if not frappe.db.exists("DocType", HEARTBEAT_NAME):
		return
	doc = frappe.get_single(HEARTBEAT_NAME)
	doc.last_scheduler_run = now_datetime()
	doc.save(ignore_permissions=True)


def _recent_deliveries():
	rows = frappe.get_all(
		"Taskist Notification Delivery",
		filters={"status": ["in", ["Failed", "Pending"]]},
		fields=[
			"name", "status", "task", "tracker", "recipient", "channel", "attempts",
			"last_error", "modified",
		],
		order_by="modified desc",
		limit_page_length=50,
	)
	for row in rows:
		row.modified = str(row.modified) if row.modified else None
	return rows


def _recent_process_errors():
	rows = frappe.get_all(
		"Taskist Pilot Observation",
		filters={"outcome": "Error"},
		fields=[
			"name", "process_rule", "reference_doctype", "reference_name",
			"error_message", "observed_on",
		],
		order_by="observed_on desc",
		limit_page_length=25,
	)
	for row in rows:
		row.observed_on = str(row.observed_on) if row.observed_on else None
	return rows


@frappe.whitelist()
def get_system_health():
	_require_view()
	from taskist.push import get_notification_health

	heartbeat = frappe.get_single(HEARTBEAT_NAME)
	last_run = heartbeat.last_scheduler_run
	stale_before = add_to_date(now_datetime(), minutes=-12, as_datetime=True)
	scheduler_healthy = bool(last_run and last_run >= stale_before)
	open_statuses = ["Open", "Warning", "Breached"]
	stale_trackers = frappe.db.count(
		"Taskist SLA Tracker",
		{"status": ["in", open_statuses], "modified": ["<=", add_to_date(now_datetime(), hours=-1)]},
	)
	notification = get_notification_health()
	checks = [
		{
			"key": "scheduler",
			"label": "Five-minute scheduler",
			"status": "Healthy" if scheduler_healthy else "Critical",
			"detail": (
				f"Last heartbeat {last_run}"
				if last_run else "No scheduler heartbeat has been recorded"
			),
		},
		{
			"key": "vapid",
			"label": "Web Push configuration",
			"status": "Healthy" if notification["vapid_configured"] else "Warning",
			"detail": "VAPID keys configured" if notification["vapid_configured"] else "VAPID keys are missing",
		},
		{
			"key": "pywebpush",
			"label": "Push library",
			"status": "Healthy" if notification["pywebpush_installed"] else "Critical",
			"detail": "pywebpush is installed" if notification["pywebpush_installed"] else "pywebpush is not installed",
		},
		{
			"key": "deliveries",
			"label": "Notification delivery",
			"status": "Healthy" if not notification["failed_deliveries"] else "Warning",
			"detail": f'{notification["failed_deliveries"]} failed deliveries',
		},
		{
			"key": "trackers",
			"label": "SLA tracker freshness",
			"status": "Healthy" if not stale_trackers else "Warning",
			"detail": f"{stale_trackers} open trackers unchanged for over one hour",
		},
	]
	return {
		"generated_at": str(now_datetime()),
		"last_scheduler_run": str(last_run) if last_run else None,
		"checks": checks,
		"summary": {
			"healthy": sum(row["status"] == "Healthy" for row in checks),
			"warning": sum(row["status"] == "Warning" for row in checks),
			"critical": sum(row["status"] == "Critical" for row in checks),
			"open_trackers": frappe.db.count("Taskist SLA Tracker", {"status": ["in", open_statuses]}),
			"breached_trackers": frappe.db.count("Taskist SLA Tracker", {"status": "Breached"}),
			"active_subscriptions": notification["active_subscriptions"],
			"failed_deliveries": notification["failed_deliveries"],
		},
		"deliveries": _recent_deliveries(),
		"process_errors": _recent_process_errors(),
		"can_manage": can_manage_all_tasks(),
	}


@frappe.whitelist()
def retry_delivery(delivery_name):
	_require_manage()
	delivery = frappe.get_doc("Taskist Notification Delivery", delivery_name)
	if delivery.status == "Sent":
		return {"name": delivery.name, "status": delivery.status}
	if delivery.status == "Cancelled":
		frappe.throw(_("Cancelled deliveries cannot be retried."))
	if int(delivery.attempts or 0) >= 5:
		frappe.throw(_("This delivery reached the maximum number of attempts."))
	from taskist.sla import _attempt_delivery

	_attempt_delivery(
		delivery.event_key,
		delivery.tracker,
		delivery.recipient,
		delivery.channel,
		delivery.title,
		delivery.body,
		delivery.task,
	)
	delivery.reload()
	return {"name": delivery.name, "status": delivery.status, "attempts": delivery.attempts}


@frappe.whitelist()
def run_sla_cycle():
	_require_manage()
	from taskist.sla import evaluate_sla_rules, retry_failed_deliveries

	record_scheduler_heartbeat()
	evaluate_sla_rules()
	retry_failed_deliveries()
	return get_system_health()


@frappe.whitelist()
def replay_document_event(reference_doctype, reference_name, event="on_update"):
	_require_manage()
	if event not in {"after_insert", "on_update", "on_submit", "on_cancel"}:
		frappe.throw(_("Unsupported document event."))
	doc = frappe.get_doc(reference_doctype, reference_name)
	from taskist.process import process_document_event

	process_document_event(doc, event)
	return {"doctype": reference_doctype, "name": reference_name, "event": event}
