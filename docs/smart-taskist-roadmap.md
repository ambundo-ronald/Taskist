# Smart Taskist Roadmap

Taskist can become an activity layer over ERPNext documents, not only a Project Task UI.

## Source-Linked Tasks

Taskist should use ERPNext `Task` as the single work item, whether or not it belongs to a Project.

- Source document: any DocType, such as Purchase Order, Sales Order, Issue, Lead, Payment Entry, or Issue.
- Assigned user: the user responsible for the next action, copied from the source document assignment.
- Task state: Open, Working, Pending Review, Completed, Cancelled.
- Deep link: every source-linked Task opens the originating document.
- Project remains optional.

## Document Assignment Automation

When a supported document is assigned through Frappe assignment, Taskist should create or update a normal ERPNext Task.

Suggested first slice:

- Listen to `ToDo` creation/update events where `reference_type` and `reference_name` point to a business document.
- Create a source-linked Task for the assigned user.
- Mark the Task complete when the related `ToDo` is closed.
- Let users complete the Task from Taskist, then close/update the linked `ToDo`.

## SLA Engine

Create a `Taskist SLA Rule` DocType that defines how long a document or activity should take.

Recommended fields:

- Rule name and enabled flag.
- Reference DocType.
- Conditions JSON, using Frappe filter syntax.
- Start event: document creation, assignment, status change, submitted, or custom field transition.
- Stop event: completed activity, document status, workflow state, submitted/cancelled, or custom field transition.
- Duration target in minutes/hours/days.
- Business calendar, holiday list, and working hours.
- Escalation recipients and notification channels.

Runtime records should be stored separately in `Taskist SLA Tracker`, one per matched document or source-linked Task.

Initial implementation:

- SLA rules target a source DocType.
- Conditions are stored as optional JSON filters.
- Source-linked Tasks get a tracker when they match an enabled rule.
- Trackers compute start time, warning time, and due time.
- The hourly scheduler evaluates open trackers.
- Warning and breach events can send push notifications.

### SLA Priority Targets

Each SLA Rule contains a Priority Targets child table. The source document field configured in
`Priority Field` is checked first, then Task priority, then the rule's default priority.

| Priority | First Response | Resolution | Warning Before Due |
|---|---:|---:|---:|
| Urgent | 10 minutes | 2 hours | 30 minutes |
| High | 30 minutes | 4 hours | 60 minutes |
| Medium | 2 hours | 1 working day | 2 hours |
| Low | 4 hours | 3 working days | 1 working day |

First response is recorded when the Task moves to Working, Pending Review, or Completed.
Resolution is recorded when the Task is completed.

### Escalation Matrix

Each SLA Rule also contains an Escalation Matrix child table.

| Level | Trigger | After | Recipient Type | Recipient | Channel |
|---:|---|---:|---|---|---|
| 1 | Response Breach | 0 minutes | Assignee | | Push |
| 2 | Warning | 0 minutes | Assignee | | Push |
| 3 | Breach | 0 minutes | Role | Projects Manager | Push and Email |
| 4 | Breach | 60 minutes | User | operations@example.com | All |

Supported recipients are Assignee, Document Owner, User, and Role. Supported channels are Push,
In App, Email, Push and Email, and All. Each escalation row is sent only once per tracker.

### Service Calendar

Rules can optionally calculate deadlines within working hours. Configure a start time, end time,
and Holiday List. Saturdays, Sundays, and Holiday List dates are skipped.

## Notifications

Push notifications should be one delivery channel beside email and in-app realtime updates.

Useful notification events:

- New assignment.
- SLA warning threshold reached.
- SLA breached.
- Activity completed.
- Activity sent back for review.
- Comment or attachment added on an assigned activity.

The initial push implementation stores browser subscriptions and exposes a reusable backend sender. SLA and activity events can call `taskist.push.send_push_to_user`.

## Task Visibility and RBAC

Taskist applies assignment-based permissions to the native ERPNext Task DocType.

Roles:

- `Taskist User`: sees and updates tasks assigned to themselves.
- `Taskist Manager`: sees and manages all tasks.
- `Taskist Auditor`: sees all tasks but does not receive broad update permission.
- `System Manager`: sees and manages all tasks.

Tasks assigned to multiple users are shared between those users. An unassigned task is visible only
to its owner until it is assigned.

For delegated or team visibility, create a `Taskist Access Profile` for the viewer:

| Field | Purpose |
|---|---|
| User | Person receiving additional visibility |
| View All Tasks | Grants visibility across all assignees |
| Can View Tasks Assigned To | Selected users whose assigned tasks are visible |
| Can Update | Allows updates to that selected user's tasks |

The access policy applies in Taskist APIs and through Frappe Task permission hooks, including Desk
lists and REST reads.

Administrators can inspect the current user's effective scope through:

```text
/api/method/taskist.api.get_access_scope
```

## Notification Reliability

Every SLA notification channel attempt is recorded in `Taskist Notification Delivery`.

- Successful recipient/channel combinations are not duplicated.
- Failed deliveries retry every five minutes.
- Failed deliveries retry independently even if the Task or SLA tracker is later completed.
- Retries stop after five failed attempts.
- Push subscriptions returning HTTP 404 or 410 are disabled automatically.
- In-app notifications create Frappe Notification Log records.
- SLA evaluation runs every five minutes through the scheduler.

Administrators can inspect notification health through:

```text
/api/method/taskist.push.get_notification_health
```

The response confirms VAPID configuration, `pywebpush` availability, active subscriptions, and
sent/failed/pending delivery counts.

### Deployment Verification

1. Run the site migration and ensure the scheduler is enabled.
2. Assign `Taskist User`, `Taskist Manager`, or `Taskist Auditor` roles as appropriate.
3. Log in as two ordinary users and verify each sees only their assignments.
4. Assign one Task to both users and verify both can see it.
5. Add a Taskist Access Profile and verify delegated visibility and update access independently.
6. Enable push from each user's installed PWA.
7. Call `taskist.push.send_test_push` while logged in as each user.
8. Create a short SLA target and confirm response breach, warning, resolution breach, and escalation records.
9. Inspect `Taskist Notification Delivery`, Notification Log, and Error Log for the delivery audit trail.
