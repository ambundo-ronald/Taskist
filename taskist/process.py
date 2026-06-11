import hashlib
import json
from html import escape
from urllib.parse import quote

import frappe
from frappe.utils import getdate, now_datetime, nowdate

from taskist.access import can_manage_all_tasks, can_view_task, check_task_update, check_task_view
from taskist.governance import is_rule_effective


IGNORED_DOCTYPES = {"Task", "ToDo"}
TERMINAL_TASK_STATUSES = ["Completed", "Cancelled", "Template"]


def _loads_filters(value):
	if not value:
		return {}
	if isinstance(value, (dict, list)):
		return value
	return json.loads(value)


def _matches_conditions(rule, doc):
	filters = _loads_filters(rule.conditions_json)
	if not filters:
		return True
	filters = list(filters) if isinstance(filters, list) else dict(filters)
	if isinstance(filters, dict):
		filters["name"] = doc.name
	else:
		filters.append(["name", "=", doc.name])
	return bool(
		frappe.get_all(
			doc.doctype,
			filters=filters,
			pluck="name",
			limit_page_length=1,
		)
	)


def _workflow_transition(rule, doc, previous_state=None):
	fieldname = rule.workflow_state_field or "workflow_state"
	current_state = doc.get(fieldname)
	if previous_state is None:
		previous_doc = doc.get_doc_before_save()
		previous_state = previous_doc.get(fieldname) if previous_doc else None
	if rule.workflow_to_state and current_state != rule.workflow_to_state:
		return False
	if rule.workflow_from_state and previous_state != rule.workflow_from_state:
		return False
	return current_state != previous_state


def _matches_event(rule, doc, method, previous_state=None):
	event_methods = {
		"After Insert": "after_insert",
		"On Update": "on_update",
		"On Submit": "on_submit",
		"On Cancel": "on_cancel",
	}
	if rule.trigger_event == "Workflow State Change":
		return method == "on_update" and _workflow_transition(rule, doc, previous_state)
	return event_methods.get(rule.trigger_event) == method


def _event_key(rule, doc):
	parts = [rule.name, doc.doctype, doc.name]
	if rule.duplicate_policy == "Once Per Workflow State":
		fieldname = rule.workflow_state_field or "workflow_state"
		parts.append(str(doc.get(fieldname) or rule.trigger_event))
	value = "|".join(parts)
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _active_pilot(process_rule):
	rows = frappe.db.sql(
		"""
		select pilot.name, pilot.status, pilot.department
		from `tabTaskist Pilot Rule` child
		inner join `tabTaskist Process Pilot` pilot on pilot.name = child.parent
		where child.process_rule = %s
			and pilot.status in ('Shadow', 'Operational')
			and pilot.start_date <= %s
			and (pilot.end_date is null or pilot.end_date >= %s)
		order by pilot.start_date desc
		limit 1
		""",
		(process_rule, getdate(nowdate()), getdate(nowdate())),
		as_dict=True,
	)
	return rows[0] if rows else None


def _pilot_observation_key(pilot, source_event_key):
	value = f"{pilot}|{source_event_key}"
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_pilot_observation(
	pilot,
	rule,
	doc,
	source_event_key,
	outcome,
	task=None,
	assignees=None,
	error_message=None,
):
	"""Record one immutable result for each eligible source event."""
	if not pilot:
		return None
	event_key = _pilot_observation_key(pilot.name, source_event_key)
	if frappe.db.exists("Taskist Pilot Observation", event_key):
		return event_key
	try:
		observation = frappe.new_doc("Taskist Pilot Observation")
		observation.event_key = event_key
		observation.pilot = pilot.name
		observation.process_rule = rule.name
		observation.department = pilot.department or rule.department
		observation.mode = pilot.status
		observation.outcome = outcome
		observation.reference_doctype = doc.doctype
		observation.reference_name = doc.name
		observation.trigger_event = rule.trigger_event
		observation.task = task.name if task else None
		observation.assignees_json = json.dumps(assignees or [])
		observation.observed_on = now_datetime()
		observation.error_message = str(error_message)[:1000] if error_message else None
		observation.insert(ignore_permissions=True)
		return observation.name
	except frappe.DuplicateEntryError:
		return event_key
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Taskist Pilot Observation")
		return None


def _render(template, doc):
	if not template:
		return ""
	return frappe.render_template(template, {"doc": doc.as_dict()}).strip()


def _enabled_users_for_role(role):
	users = frappe.get_all(
		"Has Role",
		filters={"role": role, "parenttype": "User"},
		pluck="parent",
		limit_page_length=500,
	)
	if not users:
		return []
	return sorted(
		frappe.get_all(
			"User",
			filters={"name": ["in", users], "enabled": 1, "user_type": "System User"},
			pluck="name",
			limit_page_length=500,
		)
	)


def _normalize_users(value):
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			try:
				value = json.loads(value)
			except json.JSONDecodeError:
				value = [value]
		elif "," in value:
			value = [item.strip() for item in value.split(",")]
		else:
			value = [value]
	if not isinstance(value, (list, tuple, set)):
		value = [value]
	users = []
	for user in value:
		if user and frappe.db.exists("User", {"name": user, "enabled": 1}):
			users.append(user)
	return sorted(set(users))


def _least_loaded_user(users):
	load = []
	for user in users:
		count = frappe.db.count(
			"Task",
			{
				"status": ["not in", TERMINAL_TASK_STATUSES],
				"_assign": ["like", f'%"{user}"%'],
			},
		)
		load.append((count, user))
	return min(load)[1] if load else None


def resolve_assignees(rule, doc):
	return _resolve_assignees(
		rule.assignment_strategy,
		doc,
		rule.assigned_user,
		rule.assigned_role,
		rule.assignee_field,
	)


def _resolve_assignees(strategy, doc, assigned_user=None, assigned_role=None, assignee_field=None):
	if strategy == "Fixed User":
		return _normalize_users(assigned_user)
	if strategy == "Role":
		return _enabled_users_for_role(assigned_role)
	if strategy == "Source Field":
		return _normalize_users(doc.get(assignee_field))
	if strategy == "Document Owner":
		return _normalize_users(doc.owner)
	if strategy == "Round Robin Role":
		user = _least_loaded_user(_enabled_users_for_role(assigned_role))
		return [user] if user else []
	return []


def _handoff_assignees(rule, next_rule, doc):
	strategy = rule.handoff_assignment_strategy or "Use Next Rule"
	if strategy == "Use Next Rule":
		return resolve_assignees(next_rule, doc)
	return _resolve_assignees(
		strategy,
		doc,
		rule.handoff_assigned_user,
		rule.handoff_assigned_role,
		rule.handoff_assignee_field,
	)


def _source_link(doc):
	route = frappe.scrub(doc.doctype).replace("_", "-")
	return f"/app/{route}/{quote(doc.name, safe='')}"


def _task_description(rule, doc):
	description = _render(rule.description_template, doc)
	if not description:
		description = (
			f"Task generated by process rule {escape(rule.name)} from "
			f"<a href=\"{_source_link(doc)}\">{escape(doc.doctype)} {escape(doc.name)}</a>."
		)
	if rule.output_standard:
		description += f"<br><br><strong>Required output:</strong> {escape(rule.output_standard)}"
	return description


def _existing_task(event_key):
	return frappe.db.get_value("Task", {"taskist_process_event_key": event_key}, "name")


def _current_assignees(task):
	try:
		return set(json.loads(task._assign or "[]"))
	except (json.JSONDecodeError, TypeError):
		return set()


def _notify_assignment(rule, task, doc, user, event_key):
	try:
		from taskist.push import send_push_to_user

		send_push_to_user(
			user,
			f"New {rule.process_code} task",
			task.subject,
			f"/taskist?task={task.name}",
			data={
				"task": task.name,
				"process_rule": rule.name,
				"source_doctype": doc.doctype,
				"source_name": doc.name,
			},
			tag=f"taskist-process-{event_key}-{user}",
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Taskist Process Assignment Push")


def _sync_task_assignees(rule, task, doc, assignees, event_key):
	from frappe.desk.form.assign_to import add as assign_add
	from frappe.desk.form.assign_to import remove as assign_remove
	from taskist.events import record_event

	current = _current_assignees(task)
	desired = set(assignees)
	for user in sorted(current - desired):
		assign_remove("Task", task.name, user)
		record_event(
			task.name,
			"Unassigned",
			previous_value=user,
			notes=f"Assignment recalculated by process rule {rule.name}.",
			dedupe_key=f"{event_key}:unassigned:{user}:{task.modified}",
		)
	for user in sorted(desired - current):
		assign_add(
			{
				"doctype": "Task",
				"name": task.name,
				"assign_to": [user],
				"description": task.subject,
			}
		)
		record_event(
			task.name,
			"Reassigned" if current else "Assigned",
			previous_value=", ".join(sorted(current)) if current else None,
			new_value=user,
			notes=f"Assigned by process rule {rule.name}.",
			dedupe_key=f"{event_key}:assigned:{user}:{task.modified}",
		)
		_notify_assignment(rule, task, doc, user, event_key)


def build_rule_preview(rule, doc, previous_state=None):
	event_key = _event_key(rule, doc)
	assignees = resolve_assignees(rule, doc)
	return {
		"rule": rule.name,
		"process_code": rule.process_code,
		"trigger_event": rule.trigger_event,
		"reference_doctype": doc.doctype,
		"reference_name": doc.name,
		"event_key": event_key,
		"existing_task": _existing_task(event_key),
		"subject": _render(rule.subject_template, doc)[:140],
		"description": _task_description(rule, doc),
		"priority": rule.priority,
		"project": doc.get(rule.project_field) if rule.project_field else None,
		"assignees": assignees,
		"sla_rule": rule.sla_rule,
		"completion_output_type": rule.completion_output_type,
		"output_standard": rule.output_standard,
		"next_process_rule": rule.next_process_rule,
		"rework_process_rule": rule.rework_process_rule,
		"conditions_match": _matches_conditions(rule, doc),
		"workflow_transition_matches": (
			_workflow_transition(rule, doc, previous_state)
			if rule.trigger_event == "Workflow State Change"
			else None
		),
	}


def create_task_from_rule(
	rule,
	doc,
	event_key=None,
	assignees=None,
	sla_rule=None,
	previous_task=None,
	trigger_event=None,
):
	event_key = event_key or _event_key(rule, doc)
	existing = _existing_task(event_key)
	assignees = assignees if assignees is not None else resolve_assignees(rule, doc)
	if not assignees:
		raise frappe.ValidationError(f"Process rule {rule.name} resolved no enabled assignees.")
	if existing:
		task = frappe.get_doc("Task", existing)
		if task.status not in TERMINAL_TASK_STATUSES:
			_sync_task_assignees(rule, task, doc, assignees, event_key)
		return task

	task = frappe.new_doc("Task")
	task.subject = _render(rule.subject_template, doc)[:140]
	task.description = _task_description(rule, doc)
	task.status = "Open"
	task.priority = rule.priority or "Medium"
	task.taskist_reference_doctype = doc.doctype
	task.taskist_reference_name = doc.name
	task.taskist_process_rule = rule.name
	task.taskist_process_event_key = event_key
	task.taskist_process_trigger_event = trigger_event or rule.trigger_event
	task.taskist_process_chain_id = (
		previous_task.taskist_process_chain_id
		if previous_task and previous_task.taskist_process_chain_id
		else event_key
	)
	task.taskist_process_sequence = (
		int(previous_task.taskist_process_sequence or 1) + 1
		if previous_task
		else 1
	)
	task.taskist_previous_process_task = previous_task.name if previous_task else None
	if rule.completion_output_type == "Checklist Completed" and rule.completion_checklist_json:
		task.taskist_checklist_json = json.dumps(
			[
				{"label": str(label).strip(), "completed": 0}
				for label in json.loads(rule.completion_checklist_json)
			]
		)
	if rule.project_field and doc.get(rule.project_field):
		task.project = doc.get(rule.project_field)
	try:
		task.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		existing = _existing_task(event_key)
		if existing:
			return frappe.get_doc("Task", existing)
		raise

	_sync_task_assignees(rule, task, doc, assignees, event_key)

	effective_sla_rule = sla_rule or rule.sla_rule
	if effective_sla_rule:
		from taskist.sla import ensure_tracker

		ensure_tracker(frappe.get_doc("Taskist SLA Rule", effective_sla_rule), task)
	else:
		from taskist.sla import evaluate_task_against_sla_rules

		evaluate_task_against_sla_rules(task)
	return task


def _completion_filters(rule, source_doc):
	if not rule.completion_condition_json:
		return {}
	rendered = frappe.render_template(
		rule.completion_condition_json,
		{"doc": source_doc.as_dict()},
	)
	return _loads_filters(rendered)


def _document_matches(doctype, filters, document_name=None):
	filters = list(filters) if isinstance(filters, list) else dict(filters or {})
	if document_name:
		if isinstance(filters, dict):
			filters["name"] = document_name
		else:
			filters.append(["name", "=", document_name])
	return bool(frappe.get_all(doctype, filters=filters, pluck="name", limit_page_length=1))


def _validate_completion_output(task, rule, source_doc):
	output_type = rule.completion_output_type or "None"
	conditions = _completion_filters(rule, source_doc)

	if output_type == "Document Created":
		filters = list(conditions) if isinstance(conditions, list) else dict(conditions)
		if rule.output_link_field:
			if isinstance(filters, dict):
				filters[rule.output_link_field] = source_doc.name
			else:
				filters.append([rule.output_link_field, "=", source_doc.name])
		if not _document_matches(rule.output_doctype, filters):
			frappe.throw(
				f"Create the required {rule.output_doctype} before completing this task."
			)
		return

	if output_type == "Workflow State Reached":
		if str(source_doc.get(rule.output_field) or "") != str(rule.output_expected_value or ""):
			frappe.throw(
				f"{source_doc.doctype} {source_doc.name} must reach "
				f"{rule.output_field} = {rule.output_expected_value} before completion."
			)
	elif output_type == "Field Populated":
		if not source_doc.get(rule.output_field):
			frappe.throw(
				f"Populate {rule.output_field} on {source_doc.doctype} {source_doc.name} before completion."
			)
	elif output_type == "Checklist Completed":
		try:
			items = json.loads(task.taskist_checklist_json or "[]")
		except (json.JSONDecodeError, TypeError):
			items = []
		if not items or any(not int(item.get("completed") or 0) for item in items):
			frappe.throw("Complete every required checklist item before completing this task.")
	elif output_type == "Attachment Uploaded":
		files = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Task", "attached_to_name": task.name},
			fields=["file_name"],
			limit_page_length=500,
		)
		extension = (rule.required_attachment_extension or "").lower().lstrip(".")
		if extension:
			files = [
				file for file in files
				if (file.file_name or "").lower().endswith(f".{extension}")
			]
		if not files:
			requirement = f"a .{extension} attachment" if extension else "an attachment"
			frappe.throw(f"Upload {requirement} before completing this task.")
	elif output_type == "Manager Approval":
		if not task.taskist_manager_approved_by:
			frappe.throw("A Taskist Manager must approve this task before it can be completed.")

	if conditions and not _document_matches(source_doc.doctype, conditions, source_doc.name):
		frappe.throw("The configured completion conditions are not yet satisfied.")


def _handoff_key(task, rule, route="next"):
	value = f"taskist-handoff|{route}|{task.name}|{rule.name}"
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_task_completion(doc, method=None):
	if doc.is_new() or doc.status != "Completed":
		return
	previous = doc.get_doc_before_save()
	if previous and previous.status == "Completed":
		return
	if not doc.taskist_process_rule:
		return
	rule = frappe.get_doc("Taskist Process Rule", doc.taskist_process_rule)
	if not doc.taskist_reference_doctype or not doc.taskist_reference_name:
		frappe.throw("This process task is missing its source-document context.")
	source_doc = frappe.get_doc(doc.taskist_reference_doctype, doc.taskist_reference_name)
	_validate_completion_output(doc, rule, source_doc)
	if rule.next_process_rule:
		next_rule = frappe.get_doc("Taskist Process Rule", rule.next_process_rule)
		if not is_rule_effective(next_rule):
			frappe.throw(f"Next Process Rule {next_rule.name} is not approved and effective.")
		if next_rule.reference_doctype != source_doc.doctype:
			frappe.throw(
				f"Next Process Rule {next_rule.name} targets {next_rule.reference_doctype}, "
				f"not {source_doc.doctype}."
			)
		if not _handoff_assignees(rule, next_rule, source_doc):
			frappe.throw(f"Next Process Rule {next_rule.name} resolved no enabled assignees.")


def handle_task_handoff(doc, method=None):
	if doc.status != "Completed" or not doc.taskist_process_rule:
		return None
	previous = doc.get_doc_before_save()
	if previous and previous.status == "Completed":
		return None
	rule = frappe.get_doc("Taskist Process Rule", doc.taskist_process_rule)
	if not rule.next_process_rule:
		return None
	source_doc = frappe.get_doc(doc.taskist_reference_doctype, doc.taskist_reference_name)
	next_rule = frappe.get_doc("Taskist Process Rule", rule.next_process_rule)
	event_key = _handoff_key(doc, next_rule)
	next_task = create_task_from_rule(
		next_rule,
		source_doc,
		event_key=event_key,
		assignees=_handoff_assignees(rule, next_rule, source_doc),
		sla_rule=rule.handoff_sla_rule,
		previous_task=doc,
		trigger_event=f"Handoff from {rule.name}",
	)
	if doc.taskist_next_process_task != next_task.name:
		frappe.db.set_value(
			"Task",
			doc.name,
			"taskist_next_process_task",
			next_task.name,
			update_modified=False,
		)
	from taskist.events import record_event

	record_event(
		doc.name,
		"Handoff Started",
		new_value=next_task.name,
		notes=f"Work handed to {next_rule.name}.",
		metadata={"next_task": next_task.name, "next_rule": next_rule.name},
		dedupe_key=f"handoff-started:{event_key}",
	)
	record_event(
		next_task.name,
		"Handoff Received",
		previous_value=doc.name,
		notes=f"Work received from {rule.name}.",
		metadata={"previous_task": doc.name, "previous_rule": rule.name},
		dedupe_key=f"handoff-received:{event_key}",
	)
	return next_task


@frappe.whitelist()
def request_process_rework(task_name, delay_reason, notes):
	check_task_update(task_name)
	task = frappe.get_doc("Task", task_name)
	if task.status != "Pending Review":
		frappe.throw("Only a task pending review can be returned through the rework route.")
	if not task.taskist_process_rule:
		frappe.throw("This Task is not linked to a Process Rule.")
	if not notes:
		frappe.throw("Explain why the work is being returned.")

	current_rule = frappe.get_doc("Taskist Process Rule", task.taskist_process_rule)
	rework_rule_name = current_rule.rework_process_rule
	rework_assignees = None
	if not rework_rule_name and task.taskist_previous_process_task:
		previous_task = frappe.get_doc("Task", task.taskist_previous_process_task)
		rework_rule_name = previous_task.taskist_process_rule
		rework_assignees = sorted(_current_assignees(previous_task))
	if not rework_rule_name:
		frappe.throw("Configure a Rework Process Rule or link this Task to a previous process stage.")
	rework_rule = frappe.get_doc("Taskist Process Rule", rework_rule_name)
	if not is_rule_effective(rework_rule):
		frappe.throw(f"Rework Process Rule {rework_rule.name} is not approved and effective.")

	from taskist.delay import _log_delay, _validate_reason_and_evidence

	_validate_reason_and_evidence(task.name, delay_reason)
	source_doc = frappe.get_doc(task.taskist_reference_doctype, task.taskist_reference_name)
	if rework_rule.reference_doctype != source_doc.doctype:
		frappe.throw(
			f"Rework Process Rule {rework_rule.name} targets {rework_rule.reference_doctype}, "
			f"not {source_doc.doctype}."
		)
	rework_number = frappe.db.count(
		"Taskist SLA Event",
		{"task": task.name, "event_type": "Rework Requested"},
	) + 1
	event_key = _handoff_key(task, rework_rule, route=f"rework-{rework_number}")
	rework_task = create_task_from_rule(
		rework_rule,
		source_doc,
		event_key=event_key,
		assignees=rework_assignees,
		sla_rule=current_rule.rework_sla_rule,
		previous_task=task,
		trigger_event=f"Rework from {current_rule.name}",
	)
	frappe.db.set_value(
		"Task",
		task.name,
		"taskist_next_process_task",
		rework_task.name,
		update_modified=False,
	)
	task.taskist_next_process_task = rework_task.name
	_log_delay(
		task.name,
		frappe.db.get_value("Taskist SLA Tracker", {"task": task.name}, "name"),
		"Returned for Correction",
		delay_reason,
		notes,
	)
	from taskist.events import record_event

	record_event(
		task.name,
		"Rework Requested",
		new_value=rework_task.name,
		notes=notes,
		metadata={
			"rework_task": rework_task.name,
			"rework_rule": rework_rule.name,
			"delay_reason": delay_reason,
		},
		dedupe_key=f"rework-requested:{event_key}",
	)
	record_event(
		rework_task.name,
		"Handoff Received",
		previous_value=task.name,
		notes=f"Rework requested from {current_rule.name}: {notes}",
		metadata={"rejected_task": task.name, "delay_reason": delay_reason},
		dedupe_key=f"rework-received:{event_key}",
	)

	task.status = "Cancelled"
	task.save(ignore_permissions=True)
	return {"rework_task": rework_task.name, "chain": get_process_chain(rework_task.name)}


@frappe.whitelist()
def approve_task_output(task_name, notes=None):
	if not can_manage_all_tasks():
		frappe.throw("Only Taskist Managers can approve process output.", frappe.PermissionError)
	check_task_view(task_name)
	task = frappe.get_doc("Task", task_name)
	if not task.taskist_process_rule:
		frappe.throw("This Task is not linked to a Process Rule.")
	rule = frappe.get_doc("Taskist Process Rule", task.taskist_process_rule)
	if rule.completion_output_type != "Manager Approval":
		frappe.throw("This Process Rule does not require manager approval.")
	frappe.db.set_value(
		"Task",
		task.name,
		{
			"taskist_manager_approved_by": frappe.session.user,
			"taskist_manager_approved_on": now_datetime(),
		},
		update_modified=True,
	)
	from taskist.events import record_event

	record_event(
		task.name,
		"Output Approved",
		new_value=frappe.session.user,
		notes=notes or "Process output approved.",
		dedupe_key=f"output-approved:{task.name}:{frappe.session.user}",
	)
	return get_process_chain(task.name)


@frappe.whitelist()
def update_task_checklist(task_name, items):
	check_task_update(task_name)
	if isinstance(items, str):
		items = json.loads(items)
	if not isinstance(items, list):
		frappe.throw("Checklist items must be a list.")
	task = frappe.get_doc("Task", task_name)
	try:
		configured = json.loads(task.taskist_checklist_json or "[]")
	except (json.JSONDecodeError, TypeError):
		configured = []
	labels = [str(item.get("label") or "").strip() for item in configured]
	incoming = {
		str(item.get("label") or "").strip(): 1 if int(item.get("completed") or 0) else 0
		for item in items
	}
	updated = [{"label": label, "completed": incoming.get(label, 0)} for label in labels if label]
	frappe.db.set_value("Task", task.name, "taskist_checklist_json", json.dumps(updated), update_modified=True)
	from taskist.events import record_event

	record_event(
		task.name,
		"Checklist Updated",
		new_value=f"{sum(item['completed'] for item in updated)}/{len(updated)}",
		notes="Completion checklist updated.",
		dedupe_key=f"checklist:{task.name}:{frappe.generate_hash(length=10)}",
	)
	return updated


@frappe.whitelist()
def get_process_chain(task_name):
	check_task_view(task_name)
	task = frappe.get_doc("Task", task_name)
	chain_id = task.taskist_process_chain_id
	fields = [
		"name",
		"subject",
		"status",
		"taskist_process_rule",
		"taskist_process_sequence",
		"taskist_previous_process_task",
		"taskist_next_process_task",
		"taskist_manager_approved_by",
		"taskist_manager_approved_on",
		"taskist_checklist_json",
	]
	if chain_id:
		tasks = frappe.get_all(
			"Task",
			filters={"taskist_process_chain_id": chain_id},
			fields=fields,
			order_by="taskist_process_sequence asc, creation asc",
			limit_page_length=500,
		)
	else:
		tasks = [frappe.db.get_value("Task", task.name, fields, as_dict=True)]
	for chain_task in tasks:
		chain_task.can_open = can_view_task(chain_task.name)
	rule = frappe.get_doc("Taskist Process Rule", task.taskist_process_rule) if task.taskist_process_rule else None
	return {
		"tasks": tasks,
		"current": task.name,
		"approval_required": bool(rule and rule.completion_output_type == "Manager Approval"),
		"can_approve": can_manage_all_tasks(),
		"output_type": rule.completion_output_type if rule else "None",
		"output_standard": rule.output_standard if rule else None,
		"rework_available": bool(
			rule and (rule.rework_process_rule or task.taskist_previous_process_task)
		),
	}


def process_document_event(doc, method=None):
	"""Evaluate enabled process rules for a source document event."""
	if (
		not method
		or doc.doctype in IGNORED_DOCTYPES
		or doc.doctype.startswith("Taskist ")
		or getattr(frappe.flags, "in_taskist_process_rule", False)
	):
		return

	rule_names = frappe.get_all(
		"Taskist Process Rule",
		filters={"enabled": 1, "reference_doctype": doc.doctype},
		pluck="name",
		limit_page_length=200,
	)
	if not rule_names:
		return

	previous_flag = getattr(frappe.flags, "in_taskist_process_rule", False)
	frappe.flags.in_taskist_process_rule = True
	try:
		for rule_name in rule_names:
			pilot = None
			rule = None
			source_event_key = None
			try:
				rule = frappe.get_doc("Taskist Process Rule", rule_name)
				if not is_rule_effective(rule):
					continue
				if not _matches_event(rule, doc, method):
					continue
				if not _matches_conditions(rule, doc):
					continue
				pilot = _active_pilot(rule.name)
				source_event_key = _event_key(rule, doc)
				assignees = resolve_assignees(rule, doc)
				if not assignees:
					_record_pilot_observation(
						pilot,
						rule,
						doc,
						source_event_key,
						"No Assignee",
						error_message=f"Process rule {rule.name} resolved no enabled assignees.",
					)
					raise frappe.ValidationError(
						f"Process rule {rule.name} resolved no enabled assignees."
					)
				if pilot and pilot.status == "Shadow":
					_record_pilot_observation(
						pilot,
						rule,
						doc,
						source_event_key,
						"Shadow Match",
						assignees=assignees,
					)
					continue
				existing = _existing_task(source_event_key)
				task = create_task_from_rule(
					rule,
					doc,
					event_key=source_event_key,
					assignees=assignees,
				)
				_record_pilot_observation(
					pilot,
					rule,
					doc,
					source_event_key,
					"Existing Task" if existing else "Task Created",
					task=task,
					assignees=assignees,
				)
			except Exception:
				if pilot and rule and source_event_key:
					_record_pilot_observation(
						pilot,
						rule,
						doc,
						source_event_key,
						"Error",
						error_message=frappe.get_traceback(),
					)
				frappe.log_error(
					frappe.get_traceback(),
					f"Taskist Process Rule {rule_name} on {doc.doctype} {doc.name}",
				)
	finally:
		frappe.flags.in_taskist_process_rule = previous_flag


@frappe.whitelist()
def simulate_process_rule(rule_name, reference_name, previous_state=None):
	"""Preview matching, assignment, and task output without creating a Task."""
	if not ({"System Manager", "Taskist Manager"} & set(frappe.get_roles())):
		frappe.throw("Only Taskist Managers can simulate process rules.", frappe.PermissionError)
	rule = frappe.get_doc("Taskist Process Rule", rule_name)
	rule.check_permission("read")
	doc = frappe.get_doc(rule.reference_doctype, reference_name)
	if not frappe.has_permission(rule.reference_doctype, "read", doc=doc):
		frappe.throw("You cannot read the source document.", frappe.PermissionError)
	return build_rule_preview(rule, doc, previous_state)
