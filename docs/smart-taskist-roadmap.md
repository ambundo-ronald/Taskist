# Smart Taskist Roadmap

Taskist can become an activity layer over ERPNext documents, not only a Project Task UI.

## Implementation Backlog

Implement the operational flow-control system in small releases. Each phase should be deployed,
tested with real users, and signed off before the next phase becomes operational.

### Phase 0: Stabilize the Task and SLA Foundation

Status: Mostly complete. Deploy and verify before starting Phase 1.

- [x] Use ERPNext `Task` as the single work item.
- [x] Create tasks from Frappe document assignments.
- [x] Link generated tasks to the exact source document.
- [x] Synchronize completion and cancellation with the linked assignment.
- [x] Apply assignment-based RBAC and delegated access profiles.
- [x] Define SLA priority targets, working hours, holidays, and escalation matrices.
- [x] Support push, email, and in-app SLA notifications.
- [x] Audit notification delivery and retry temporary failures.
- [ ] Deploy the latest changes and run `bench migrate`.
- [ ] Verify the scheduler runs every five minutes.
- [ ] Test assignment, completion, cancellation, RBAC, SLA breach, and notification delivery with
      two ordinary users and one manager.
- [ ] Document the production roles, access profiles, VAPID settings, and scheduler owner.

Acceptance criteria:

- An assigned document appears in the assignee's Taskist list and opens the correct source document.
- Completion or cancellation is reflected immediately on the linked assignment and SLA tracker.
- Ordinary users cannot read or update another user's private tasks.
- A short test SLA produces one warning, one breach, and the configured escalation notifications.

### Phase 1: Process Rule Engine

Goal: Create tasks from business events without requiring someone to assign the source document
manually.

Status: Engine implemented locally. Deployment, migration, and pilot rules remain.

Create a `Taskist Process Rule` DocType with:

- [x] Rule name, enabled flag, department, process code, and description.
- [x] Trigger DocType and trigger event.
- [x] Optional workflow-state transition and conditions.
- [x] Task subject template, description template, priority, and project mapping.
- [x] Assignment strategy: fixed user, role, source field, document owner, or round robin.
- [x] Linked `Taskist SLA Rule`.
- [x] Required output description and completion condition.
- [x] Duplicate policy and idempotency key.

Build the runtime:

- [x] Add generic document hooks that evaluate enabled process rules.
- [x] Create one source-linked Task when a rule matches.
- [x] Prevent duplicate tasks when the same event is received more than once.
- [x] Store the matched process rule and trigger event on the Task.
- [x] Re-evaluate assignment when the configured source field changes.
- [x] Add a rule simulator that shows whether a document would match before enabling a rule.
- [x] Log rule evaluation errors without blocking the source transaction.

Pilot rules:

- [ ] Material Request approved -> RFQ Issuance.
- [ ] Sales Order confirmed -> Job Opening.
- [ ] Issue created -> Ticket Acknowledgement.
- [ ] Purchase Receipt submitted -> GRN Posting.
- [ ] Expense Claim submitted -> Expense Approval.

Acceptance criteria:

- Each pilot event creates exactly one correctly assigned Task.
- The Task receives the configured SLA and opens the triggering document.
- Re-saving the document does not create a duplicate Task.

### Phase 2: Delay, Pause, and Exception Management

Goal: Explain delays fairly and distinguish controllable waiting from approved external waiting.

Status: Phase 2 is implemented locally. Production migration and multi-user verification remain.

Create:

- [x] `Taskist Delay Reason` master with category, responsible party, pause eligibility, and evidence
      requirement.
- [x] `Taskist SLA Pause` runtime record with task, tracker, reason, start, end, requester, approver,
      notes, and evidence through Task attachments.
- [x] Delay categories for internal, customer, supplier, stock, finance, technical, and system delays.

Implement:

- [x] Require a delay reason when completing a breached task.
- [x] Require a reason when extending a due date or returning work for correction.
- [x] Allow SLA pauses only for approved reason categories.
- [x] Require manager approval for SLA pauses.
- [x] Require manager approval for deadline extensions.
- [x] Recalculate response, warning, and resolution deadlines after an approved pause.
- [x] Prevent cancelled tasks from reopening notification retries.
- [x] Display pause state and delay ownership in Taskist.
- [x] Enforce Task attachments for delay reasons configured as evidence-required.
- [x] Report pending approvals, stale pauses, missing delay reasons, and missing evidence as
      compliance exceptions.

Acceptance criteria:

- A breached task cannot be closed silently.
- Approved external delays pause the clock and preserve the original target.
- Internal waiting remains part of SLA performance unless an authorized exception is approved.

### Phase 3: SLA Event and Audit Timeline

Goal: Make every important task and SLA transition measurable and explainable.

Status: Phase 3 is implemented locally. Production migration and operational verification remain.

Create `Taskist SLA Event` with:

- [x] Event type, task, tracker, source document, timestamp, actor, previous value, new value, and notes.
- [x] Event types for created, assigned, acknowledged, started, paused, resumed, reassigned, warned,
      breached, escalated, reviewed, completed, reopened, and cancelled.
- [x] Immutable records after insertion, except by System Manager during controlled maintenance.

Implement:

- [x] Record events from Task, ToDo, workflow, SLA, escalation, and notification handlers.
- [x] Add a unified timeline to the Task detail view.
- [x] Calculate active work time, waiting time, paused time, and handoff time.
- [x] Expose an exportable audit report by process, department, task, and source document.

Acceptance criteria:

- A manager can reconstruct who owned the work, what changed, why it was delayed, and who was
  notified without reading server logs.

### Phase 4: Process Handoffs and Output Validation

Goal: Move work between departments automatically without informal follow-up.

Status: Phase 4 engine is implemented locally. Process configuration, migration, and an end-to-end
department pilot remain.

Extend `Taskist Process Rule` with:

- [x] Completion output type: document created, workflow state reached, field populated, checklist
      completed, attachment uploaded, or manager approval.
- [x] Next process rule or next task template.
- [x] Handoff assignee strategy and SLA.
- [x] Rejection and rework route.

Implement:

- [x] Validate the required output before a task can be completed.
- [x] Create the next task only after successful completion.
- [x] Carry source-document context through the process chain.
- [x] Record handoff start and acceptance times.
- [x] Return incomplete work to the previous owner with a reason and rework SLA.
- [x] Show the complete process chain from the current Task.

First end-to-end flow:

- [ ] Sales Order confirmed.
- [ ] Job Opening.
- [ ] BOM or BOQ confirmation.
- [ ] Material Request.
- [ ] Procurement and material issuance.
- [ ] Assembly and QA.
- [ ] Dispatch and site execution.
- [ ] Commissioning and handover.
- [ ] Job costing and invoicing.
- [ ] Project closure.

Acceptance criteria:

- Completing one stage creates the correct next responsibility automatically.
- Work cannot advance without its configured output evidence.
- Rework is visible and measured separately from normal processing.

### Phase 5: Operational Views and Daily Control

Goal: Give employees and managers actionable queues rather than passive reports.

Status: Phase 5 operational controls are implemented locally. Department-specific saved views and
production user testing remain.

- [x] Add My Tasks, Shared Tasks, Team Tasks, Escalated Tasks, and Waiting on Others views.
- [x] Add Green, Amber, Red, and Escalated SLA filters.
- [x] Add department, process, priority, delay owner, and ageing filters.
- [x] Build a daily SLA review view showing overdue work, blockers, owners, and next actions.
- [x] Add bulk reassignment and approved escalation actions for managers.
- [x] Add user-defined saved operational views; Finance, Procurement, Service, Operations, and
      Stores presets remain to be configured in production.
- [x] Add mobile-friendly acknowledgement, delay reason, evidence upload, and completion actions.

Acceptance criteria:

- The daily SLA meeting can be run entirely from Taskist in 15 minutes.
- Every reviewed item has an owner, next action, deadline, and visible escalation state.

### Phase 6: KPI and MUDA Analytics

Goal: Measure flow efficiency and expose recurring waste rather than merely counting overdue tasks.

Status: Phase 6 analytics are implemented locally. Production migration, the first monthly
snapshot, and KPI validation against real department data remain.

Build metrics for:

- [x] SLA compliance rate by process, department, priority, and period.
- [x] First response and resolution performance.
- [x] Average processing, waiting, pause, rework, and handoff times.
- [x] Breach count and breach duration.
- [x] Delay reasons and responsible-party trends.
- [x] Repeat breaches by process and workflow state.
- [x] Volume, backlog ageing, throughput, and completion trend.
- [x] Notification delivery health and acknowledgement rate.

Build dashboards:

- [x] Employee operational queue.
- [x] Department manager scorecard.
- [x] Executive SLA dashboard.
- [x] Process bottleneck and department heatmap.
- [x] Value Stream Mapping report comparing processing time with waiting time.
- [x] Monthly KPI snapshot so historical results do not change after rule updates.

Acceptance criteria:

- Managers can identify the workflow state causing the most waiting and quantify its impact.
- KPI calculations separate employee-controlled delay from approved external delay.

### Phase 7: Department Pilot

Goal: Validate the operating model before organization-wide rollout.

Status: Pilot controls are implemented locally. Department selection, real process mapping, the
live shadow and operational periods, user feedback, and department-owner sign-off remain.

- [x] Add a department pilot record with owner, dates, baseline measures, and no more than five
      process rules.
- [x] Add controlled Draft, Shadow, Operational, Completed, and Cancelled pilot states.
- [x] Make Shadow mode evaluate triggers and assignees without creating Tasks or notifications.
- [x] Record immutable eligible-event outcomes for shadow matches, created Tasks, prevented
      duplicates, missing assignees, and runtime errors.
- [x] Add a pilot scorecard with automation success, duplicate rate, per-rule flow metrics, and
      readiness gates.
- [x] Require all readiness gates and sign-off notes before a pilot can be completed.
- [ ] Select one department with high volume and clear triggers; Procurement or Service is preferred.
- [ ] Map the real current process with users before configuring rules.
- [ ] Record baseline lead time, waiting time, rework, and breach rate.
- [ ] Configure no more than five pilot process rules.
- [ ] Run shadow mode for one week without consequences.
- [ ] Correct trigger, assignment, duration, and escalation errors.
- [ ] Run operational mode for two weeks.
- [ ] Review user feedback, false escalations, missed tasks, and notification fatigue.
- [ ] Obtain department-owner sign-off.

Acceptance criteria:

- At least 95% of eligible source events create the expected task.
- No duplicate task rate above 1%.
- Managers agree the SLA and delay attribution are fair enough for operational use.

### Phase 8: Governance and Organization Rollout

Goal: Scale the system without encouraging gaming or unfair performance decisions.

Status: Governance controls are implemented locally. Production role decisions, operating
procedures, training, staged department rollout, and two monthly KPI review cycles remain.

- [x] Assign an owner for each process rule and SLA rule.
- [x] Add approval and effective dates for rule changes.
- [x] Version process and SLA rules with immutable configuration revisions.
- [x] Snapshot the approved SLA revision and complete policy JSON onto each new tracker.
- [x] Return materially changed approved rules to Draft and disable them until re-approved.
- [x] Prevent live execution of draft, retired, future, or expired rules.
- [x] Validate that approved process rules use approved SLA, handoff, and rework rules.
- [x] Add manager approval, retirement, readiness, and revision-ledger controls.
- [ ] Define escalation etiquette and notification limits.
- [ ] Define who may pause, extend, reassign, cancel, or override an SLA.
- [ ] Publish department-specific operating procedures.
- [ ] Train users on acknowledgement, evidence, delay reasons, and handoffs.
- [ ] Roll out Finance, Procurement, Service, Operations, and Stores incrementally.
- [ ] Review KPI quality for at least two monthly cycles before linking results to formal performance
      management.

Acceptance criteria:

- Every enabled rule has a business owner, tested trigger, assignee strategy, SLA, escalation path,
  output standard, and reporting category.
- Performance decisions use reviewed SLA evidence rather than raw breach counts alone.

### Recommended Execution Order

1. Complete production verification for Phase 0.
2. Build Phase 1 and pilot five automatic process rules.
3. Add Phase 2 before SLA results are used for employee accountability.
4. Add Phase 3 before building executive analytics.
5. Implement one complete Phase 4 handoff chain.
6. Build operational views and dashboards from real event data.
7. Pilot one department, recalibrate, then roll out gradually.

### Phase 9: Production Hardening

Goal: Make failures visible, recovery deliberate, and every change continuously verifiable.

Status: Initial hardening controls are implemented locally. Live Frappe tests, load testing, and
production operating procedures remain.

- [x] Add static repository validation for Python syntax and DocType JSON.
- [x] Add GitHub Actions checks for backend validation, frontend type checking, and production build.
- [x] Record a five-minute scheduler heartbeat.
- [x] Add a manager System Health view for scheduler, VAPID, push library, notification delivery,
      stale trackers, and process errors.
- [x] Add controlled recovery actions for one notification delivery and a full SLA evaluation cycle.
- [x] Add an idempotent administrator API for replaying a source-document process event.
- [x] Add database indexes for scheduler, delivery, audit, pilot, and governance query fields.
- [ ] Add Frappe integration tests for assignment sync, RBAC, cancellation, SLA, escalation,
      process deduplication, handoff, governance, and recovery.
- [ ] Move high-volume SLA evaluation and notifications to bounded background jobs.
- [ ] Replace large in-memory analytics reads with paginated or SQL-level aggregation.
- [ ] Run load tests with production-like task, event, tracker, and delivery volumes.
- [ ] Configure alert ownership and a recovery runbook for critical health checks.
- [ ] Validate backup restoration and disaster recovery on a staging site.

Acceptance criteria:

- Every pull request fails automatically on invalid Python, DocType JSON, frontend types, or build output.
- Managers can prove the scheduler is running and identify failed notifications or rule errors from Taskist.
- Recovery actions remain permission-controlled and idempotent.
- Production-volume SLA cycles finish within the five-minute scheduler interval.

### Phase 10: Queue and Capacity Scheduling

Goal: Prevent accidental overload by showing live task countdowns and warning assigners when an
assignee is already occupied during the proposed working window.

Status: Initial queue advisory is implemented locally. Enforcement policies and department tuning
remain.

- [x] Show live countdowns on task cards, list rows, and task details using SLA due time first, then
      task due date.
- [x] Build a queue advisory API that calculates active assigned task windows from SLA deadlines,
      task due dates, and estimated duration.
- [x] Warn Taskist assigners when a selected assignee already has active work in the proposed window.
- [x] Notify ERP document assigners when a generated assignment task collides with the assignee's
      active queue.
- [ ] Add role-controlled hard blocking for teams that want assignment conflicts to require approval.
- [ ] Add department-level queue capacity rules such as maximum concurrent tasks, buffer time, and
      priority override.
- [ ] Add a visual queue timeline by user, department, and day.

Acceptance criteria:

- A user can see how much time remains before an active task breaches its SLA.
- When assigning into an occupied window, the assigner sees how many active tasks conflict and the
  next suggested start time.
- Queue warnings do not override RBAC or reveal task details outside the viewer's Taskist scope.

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
- Inherit the assignment instructions and source document title, priority, description, project,
  and due date where those fields are available.
- Mark the Task complete when the related `ToDo` is closed.
- Let users complete the Task from Taskist, then close/update the linked `ToDo`.
- Synchronize cancellation in both directions and immediately cancel any active SLA tracker.

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
- SLA setup can start from templates for Internal Approval, Quotation / Sales, Procurement,
  Finance, and Support Desk instead of manually filling every priority row.
- Process rules can use a simple setup prompt for the common "source document creates task"
  pattern, then advanced handoff/output fields can be configured only when needed.

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
- Activity sent for pending review.
- Comment or attachment added on an assigned activity.
- Queue conflict detected during assignment.

The initial push implementation stores browser subscriptions and exposes a reusable backend sender.
SLA and activity events use audited delivery records for push and in-app notifications.
Taskist also exposes a persistent in-app notification drawer backed by Frappe Notification Log, so
refreshing the PWA does not lose alerts.

For multi-site or multi-ERPNext deployments, browser push subscriptions are site-specific. Configure
VAPID on each ERPNext site/domain and have users enable notifications on each site they use. If two
ERPNext sites share users but run on different domains, each domain owns its own service worker,
subscription records, and notification history.

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
- Failed deliveries retry independently after completion, but are suppressed when the Task or SLA
  tracker is cancelled.
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
