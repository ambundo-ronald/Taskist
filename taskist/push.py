import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime


def _get_vapid_config():
	public_key = frappe.conf.get("taskist_vapid_public_key")
	private_key = frappe.conf.get("taskist_vapid_private_key")
	subject = frappe.conf.get("taskist_vapid_subject") or f"mailto:{frappe.conf.get('admin_email', 'admin@example.com')}"
	return public_key, private_key, subject


@frappe.whitelist()
def get_push_config():
	"""Return browser push configuration for the current site."""
	public_key, private_key, _subject = _get_vapid_config()
	return {
		"enabled": bool(public_key and private_key),
		"public_key": public_key,
	}


def _subscription_name(endpoint):
	return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


@frappe.whitelist()
def save_push_subscription(subscription):
	"""Store or refresh the current user's browser push subscription."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login is required to enable push notifications"), frappe.PermissionError)

	if isinstance(subscription, str):
		subscription = json.loads(subscription)

	endpoint = subscription.get("endpoint")
	keys = subscription.get("keys") or {}
	p256dh = keys.get("p256dh")
	auth = keys.get("auth")
	if not endpoint or not p256dh or not auth:
		frappe.throw(_("Invalid push subscription"))

	name = _subscription_name(endpoint)
	if frappe.db.exists("Taskist Push Subscription", name):
		doc = frappe.get_doc("Taskist Push Subscription", name)
	else:
		doc = frappe.new_doc("Taskist Push Subscription")
		doc.name = name

	doc.user = frappe.session.user
	doc.endpoint = endpoint
	doc.p256dh = p256dh
	doc.auth = auth
	doc.enabled = 1
	doc.user_agent = frappe.get_request_header("User-Agent") or ""
	doc.last_seen = now_datetime()
	doc.save(ignore_permissions=True)
	return {"enabled": True}


@frappe.whitelist()
def remove_push_subscription(endpoint):
	"""Disable a browser push subscription for the current user."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login is required to disable push notifications"), frappe.PermissionError)

	name = _subscription_name(endpoint)
	if frappe.db.exists("Taskist Push Subscription", name):
		doc = frappe.get_doc("Taskist Push Subscription", name)
		if doc.user != frappe.session.user and "System Manager" not in frappe.get_roles():
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		doc.enabled = 0
		doc.save(ignore_permissions=True)
	return {"enabled": False}


def send_push_to_user(user, title, body, url="/taskist", data=None, tag=None):
	"""Send a Web Push notification to all active subscriptions for a user."""
	public_key, private_key, subject = _get_vapid_config()
	if not public_key or not private_key:
		return {"sent": 0, "skipped": "missing_vapid_keys"}

	try:
		from pywebpush import WebPushException, webpush
	except ImportError:
		frappe.log_error("Install pywebpush to send Taskist push notifications", "Taskist Push")
		return {"sent": 0, "skipped": "missing_pywebpush"}

	payload = {
		"title": title,
		"body": body,
		"url": url,
		"tag": tag or "taskist",
		"data": data or {},
	}

	subscriptions = frappe.get_all(
		"Taskist Push Subscription",
		filters={"user": user, "enabled": 1},
		fields=["name", "endpoint", "p256dh", "auth"],
		limit_page_length=100,
	)

	sent = 0
	failed = 0
	for sub in subscriptions:
		try:
			webpush(
				subscription_info={
					"endpoint": sub.endpoint,
					"keys": {"p256dh": sub.p256dh, "auth": sub.auth},
				},
				data=json.dumps(payload),
				vapid_private_key=private_key,
				vapid_claims={"sub": subject},
			)
			sent += 1
		except WebPushException as exc:
			status_code = getattr(getattr(exc, "response", None), "status_code", None)
			if status_code in (404, 410):
				frappe.db.set_value("Taskist Push Subscription", sub.name, "enabled", 0)
			else:
				frappe.log_error(frappe.get_traceback(), "Taskist Push")
			failed += 1

	return {"sent": sent, "failed": failed, "subscriptions": len(subscriptions)}


@frappe.whitelist()
def send_test_push():
	"""Send a test push notification to the current user."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login is required to test push notifications"), frappe.PermissionError)

	result = send_push_to_user(
		frappe.session.user,
		"Taskist notifications are on",
		"You will receive task and SLA alerts here.",
		"/taskist",
		tag="taskist-test",
	)
	if not result.get("sent"):
		frappe.throw(_("Test push was not delivered: {0}").format(result.get("skipped") or "no active subscription"))
	return result


@frappe.whitelist()
def get_notification_health():
	"""Return push and SLA delivery diagnostics for Taskist administrators."""
	roles = set(frappe.get_roles())
	if not roles.intersection({"System Manager", "Taskist Manager"}):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	public_key, private_key, _subject = _get_vapid_config()
	try:
		import pywebpush  # noqa: F401

		pywebpush_installed = True
	except ImportError:
		pywebpush_installed = False

	return {
		"vapid_configured": bool(public_key and private_key),
		"pywebpush_installed": pywebpush_installed,
		"active_subscriptions": frappe.db.count("Taskist Push Subscription", {"enabled": 1}),
		"failed_deliveries": frappe.db.count("Taskist Notification Delivery", {"status": "Failed"}),
		"pending_deliveries": frappe.db.count("Taskist Notification Delivery", {"status": "Pending"}),
		"sent_deliveries": frappe.db.count("Taskist Notification Delivery", {"status": "Sent"}),
	}
