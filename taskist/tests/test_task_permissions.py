"""Task permissions (taskist.permissions, taskist.access) against a stub frappe.

Run from the repo root: python -m unittest discover -s taskist/tests -t .
"""
import importlib
import inspect
import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock


def frappe_call(fn, **kwargs):
	"""Call a hook the way frappe.call does: arguments the function does not name are dropped."""
	params = inspect.signature(fn).parameters
	if any(p.kind == p.VAR_KEYWORD for p in params.values()):
		return fn(**kwargs)
	return fn(**{k: v for k, v in kwargs.items() if k in params})


class TaskPermissionTests(unittest.TestCase):
	def setUp(self):
		self.roles = {"alice@example.com": ["Employee"], "boss@example.com": ["Projects Manager"],
			"field@example.com": ["Maintenance Manager"], "tl@example.com": ["Taskist Manager"]}
		# TASK-1: Bob's, assigned to Carol. TASK-2: Alice's, nobody assigned. TASK-3: assigned to Alice.
		self.tasks = {"TASK-1": {"owner": "bob@example.com", "_assign": json.dumps(["carol@example.com"])},
			"TASK-2": {"owner": "alice@example.com", "_assign": None},
			"TASK-3": {"owner": "bob@example.com", "_assign": json.dumps(["alice@example.com"])}}
		frappe = ModuleType("frappe")
		frappe._ = lambda text: text
		frappe.session = SimpleNamespace(user="alice@example.com")
		frappe.get_roles = lambda user=None: self.roles.get(user or frappe.session.user, [])
		frappe.get_all = MagicMock(return_value=[])
		frappe.db = MagicMock()
		frappe.db.exists = MagicMock(return_value=False)  # no Taskist Access Profiles

		def get_value(doctype, name, fields=None, as_dict=False):
			if doctype == "Task":
				row = self.tasks.get(name)
				return SimpleNamespace(get=row.get, **row) if row else None
			return None
		frappe.db.get_value = MagicMock(side_effect=get_value)
		frappe.db.escape = lambda value: f"'{value}'"
		self.frappe = frappe
		sys.modules["frappe"] = frappe
		for name in ("taskist.access", "taskist.permissions"):
			sys.modules.pop(name, None)
		self.addCleanup(sys.modules.pop, "frappe", None)
		self.perm = importlib.import_module("taskist.permissions")

	def check(self, task, ptype, user="alice@example.com", new=False):
		doc = SimpleNamespace(name=task, is_new=lambda: new)
		return frappe_call(self.perm.task_has_permission, doc=doc, ptype=ptype, user=user, debug=False)

	# 1. Frappe's ptype reaches the hook -------------------------------------------------------------------------
	def test_the_action_frappe_passes_is_used(self):
		self.assertTrue(self.check("TASK-3", "read"))  # assigned to Alice: she may read it
		self.assertTrue(self.check("TASK-3", "write"))  # and update it
		self.assertFalse(self.check("TASK-1", "read"))  # Bob's task for Carol: hidden from Alice
		self.assertFalse(self.check("TASK-1", "write"))

	def test_old_permission_type_argument_still_works(self):
		doc = SimpleNamespace(name="TASK-1", is_new=lambda: False)
		self.assertFalse(self.perm.task_has_permission(doc, user="alice@example.com", permission_type="write"))

	# 2. Creating is left to role permissions -------------------------------------------------------------------
	def test_creating_a_task_is_left_to_roles(self):
		for user in ("alice@example.com", "boss@example.com"):
			with self.subTest(user=user):
				self.assertIsNone(self.check(None, "create", user=user, new=True))

	def test_a_task_being_saved_for_the_first_time_is_left_to_roles(self):
		self.assertIsNone(self.check(None, "read", new=True))
		self.assertIsNone(self.check("TASK-NEW", "write", new=True))

	# 3. Projects and field-work managers see and manage every task ---------------------------------------------
	def test_projects_and_maintenance_managers_see_and_update_every_task(self):
		for user in ("boss@example.com", "field@example.com", "tl@example.com"):
			for ptype in ("read", "write", "delete"):
				with self.subTest(user=user, ptype=ptype):
					self.assertTrue(self.check("TASK-1", ptype, user=user))

	def test_list_conditions_open_up_for_managers_only(self):
		self.assertEqual(self.perm.task_query_conditions("boss@example.com"), "")
		self.assertIn("alice@example.com", self.perm.task_query_conditions("alice@example.com"))

	def test_taskist_dashboards_and_approvals_still_need_taskist_roles(self):
		access = importlib.import_module("taskist.access")
		for user in ("boss@example.com", "field@example.com"):
			with self.subTest(user=user):
				self.assertFalse(access.can_manage_all_tasks(user))  # SLA extensions, rules, bulk reassign
				self.assertFalse(access.can_view_all_tasks(user))  # analytics, health, pilots
		self.assertTrue(access.can_manage_all_tasks("tl@example.com"))

if __name__ == "__main__":
	unittest.main()
