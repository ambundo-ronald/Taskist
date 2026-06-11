import re
from html import escape
from urllib.parse import quote

import frappe
from frappe.utils import nowdate


def _strip_html(value):
	return re.sub(r"<[^>]+>", "", value or "").strip()


def _task_subject(todo):
	description = _strip_html(todo.description)
	if description:
		return description[:140]
	return f"{todo.reference_type}: {todo.reference_name}"


def _find_task_for_todo(todo):
	if getattr(todo, "taskist_task", None):
		if frappe.db.exists("Task", todo.taskist_task):
			return todo.taskist_task

	tasks = frappe.get_all(
		"Task",
		filters={
			"taskist_reference_doctype": todo.reference_type,
			"taskist_reference_name": todo.reference_name,
			"taskist_reference_todo": todo.name,
			"is_template": 0,
		},
		pluck="name",
		limit_page_length=1,
	)
	return tasks[0] if tasks else None


def sync_todo_assignment(doc, method=None):
	"""Create/update a Taskist task when a user is assigned to any non-Task document."""
	if getattr(frappe.flags, "in_taskist_assignment_sync", False):
		return
	if not doc.reference_type or not doc.reference_name or not doc.allocated_to:
		return
	if doc.reference_type == "Task":
		from taskist.events import record_event

		previous = doc.get_doc_before_save() if method == "on_update" else None
		if method == "after_insert":
			record_event(
				doc.reference_name,
				"Assigned",
				actor=doc.owner,
				new_value=doc.allocated_to,
				notes="Assigned through Frappe.",
				dedupe_key=f"task-todo-assigned:{doc.name}",
			)
		elif method == "on_trash" or (previous and previous.status != doc.status and doc.status in ("Closed", "Cancelled")):
			record_event(
				doc.reference_name,
				"Unassigned",
				previous_value=doc.allocated_to,
				notes=f"Frappe assignment {doc.status.lower() if method != 'on_trash' else 'removed'}.",
				dedupe_key=f"task-todo-unassigned:{doc.name}:{doc.status}:{method}",
			)
		return

	frappe.flags.in_taskist_assignment_sync = True
	try:
		task_name = _find_task_for_todo(doc)
		status_map = {
			"Closed": "Completed",
			"Cancelled": "Cancelled",
		}
		status = status_map.get(doc.status, "Open")

		if task_name:
			task = frappe.get_doc("Task", task_name)
		else:
			task = frappe.new_doc("Task")
			task.status = status
			task.exp_start_date = nowdate()

		task.subject = _task_subject(doc)
		task.status = status
		task.description = (
			f"Taskist assignment from {escape(doc.reference_type)} "
			f"<a href=\"/app/{frappe.scrub(doc.reference_type).replace('_', '-')}/{quote(doc.reference_name, safe='')}\">"
			f"{escape(doc.reference_name)}</a>"
		)
		task.taskist_reference_doctype = doc.reference_type
		task.taskist_reference_name = doc.reference_name
		task.taskist_reference_todo = doc.name
		task.save(ignore_permissions=True)
		try:
			from taskist.sla import evaluate_task_against_sla_rules

			evaluate_task_against_sla_rules(task)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Taskist SLA Assignment Sync")

		if not task_name:
			from frappe.desk.form.assign_to import add as assign_add
			from taskist.events import record_event

			assign_add({
				"doctype": "Task",
				"name": task.name,
				"assign_to": [doc.allocated_to],
				"description": task.subject,
			})
			record_event(
				task.name,
				"Assigned",
				actor=doc.owner,
				new_value=doc.allocated_to,
				notes=f"Assigned from {doc.reference_type} {doc.reference_name}.",
				dedupe_key=f"todo-assignment:{doc.name}:{doc.allocated_to}",
			)
			try:
				from taskist.push import send_push_to_user

				send_push_to_user(
					doc.allocated_to,
					"New Taskist assignment",
					task.subject,
					f"/taskist?task={task.name}",
					data={"task": task.name, "source_doctype": doc.reference_type, "source_name": doc.reference_name},
					tag=f"taskist-assignment-{task.name}",
				)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "Taskist Assignment Push")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Taskist Assignment Sync")
	finally:
		frappe.flags.in_taskist_assignment_sync = False


def set_source_todo_status_for_task(task, status):
	if not getattr(task, "taskist_reference_todo", None):
		return
	if not frappe.db.exists("ToDo", task.taskist_reference_todo):
		return

	todo = frappe.get_doc("ToDo", task.taskist_reference_todo)
	if todo.status == status:
		return

	previous_sync_flag = getattr(frappe.flags, "in_taskist_assignment_sync", False)
	frappe.flags.in_taskist_assignment_sync = True
	try:
		todo.status = status
		todo.save(ignore_permissions=True)
	finally:
		frappe.flags.in_taskist_assignment_sync = previous_sync_flag


def close_source_todo_for_task(task):
	set_source_todo_status_for_task(task, "Closed")


def cancel_source_todo_for_task(task):
	set_source_todo_status_for_task(task, "Cancelled")
