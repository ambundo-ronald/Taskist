const TASKIST_SLA_TEMPLATES = {
	"Internal Approval": {
		apply_working_hours: 1,
		working_hours_start: "08:00:00",
		working_hours_end: "17:00:00",
		priorities: [
			["Urgent", 10, 120, 30],
			["High", 30, 240, 60],
			["Medium", 120, 480, 120],
			["Low", 240, 1440, 240],
		],
	},
	"Quotation / Sales": {
		apply_working_hours: 1,
		working_hours_start: "08:00:00",
		working_hours_end: "17:00:00",
		priorities: [
			["Urgent", 10, 120, 30],
			["High", 30, 240, 60],
			["Medium", 60, 480, 120],
			["Low", 120, 960, 240],
		],
	},
	"Procurement": {
		apply_working_hours: 1,
		working_hours_start: "08:00:00",
		working_hours_end: "17:00:00",
		priorities: [
			["Urgent", 15, 240, 60],
			["High", 60, 480, 120],
			["Medium", 240, 1440, 240],
			["Low", 480, 2880, 480],
		],
	},
	"Finance": {
		apply_working_hours: 1,
		working_hours_start: "08:00:00",
		working_hours_end: "17:00:00",
		priorities: [
			["Urgent", 30, 240, 60],
			["High", 120, 480, 120],
			["Medium", 240, 1440, 240],
			["Low", 480, 2880, 480],
		],
	},
	"Support Desk": {
		apply_working_hours: 1,
		working_hours_start: "08:00:00",
		working_hours_end: "17:00:00",
		priorities: [
			["Urgent", 10, 120, 30],
			["High", 30, 240, 60],
			["Medium", 120, 1440, 120],
			["Low", 240, 2880, 480],
		],
	},
};

function set_sla_priorities(frm, priorities) {
	frm.clear_table("sla_priorities");
	for (const [priority, first_response_minutes, resolution_minutes, warning_minutes_before_due] of priorities) {
		const row = frm.add_child("sla_priorities");
		row.priority = priority;
		row.first_response_minutes = first_response_minutes;
		row.resolution_minutes = resolution_minutes;
		row.warning_minutes_before_due = warning_minutes_before_due;
	}
	frm.refresh_field("sla_priorities");
}

function set_default_escalations(frm) {
	frm.clear_table("escalation_matrix");

	const rows = [
		{
			level: 1,
			trigger: "Response Breach",
			after_minutes: 0,
			recipient_type: "Assignee",
			channel: "All",
		},
		{
			level: 2,
			trigger: "Warning",
			after_minutes: 0,
			recipient_type: "Assignee",
			channel: "In App",
		},
		{
			level: 3,
			trigger: "Breach",
			after_minutes: 0,
			recipient_type: "Role",
			recipient: "Taskist Manager",
			channel: "All",
		},
		{
			level: 4,
			trigger: "Breach",
			after_minutes: 60,
			recipient_type: "Document Owner",
			channel: "Email",
		},
	];

	for (const values of rows) {
		Object.assign(frm.add_child("escalation_matrix"), values);
	}
	frm.refresh_field("escalation_matrix");
}

function apply_sla_template(frm) {
	frappe.prompt(
		[
			{
				fieldname: "template",
				fieldtype: "Select",
				label: __("Template"),
				options: Object.keys(TASKIST_SLA_TEMPLATES).join("\n"),
				default: "Internal Approval",
				reqd: 1,
			},
			{
				fieldname: "replace_escalations",
				fieldtype: "Check",
				label: __("Replace Escalation Matrix"),
				default: 1,
			},
		],
		(values) => {
			const template = TASKIST_SLA_TEMPLATES[values.template];
			frm.set_value("default_priority", "Medium");
			frm.set_value("priority_field", frm.doc.priority_field || "priority");
			frm.set_value("apply_working_hours", template.apply_working_hours);
			frm.set_value("working_hours_start", template.working_hours_start);
			frm.set_value("working_hours_end", template.working_hours_end);
			frm.set_value("notify_on_warning", 1);
			frm.set_value("notify_on_breach", 1);
			frm.set_value("target_minutes", template.priorities.find((row) => row[0] === "Medium")[2]);
			frm.set_value("warning_minutes_before_due", template.priorities.find((row) => row[0] === "Medium")[3]);
			set_sla_priorities(frm, template.priorities);
			if (values.replace_escalations) {
				set_default_escalations(frm);
			}
			frm.dirty();
			frappe.show_alert({ message: __("SLA template applied"), indicator: "green" });
		},
		__("Apply SLA Template"),
		__("Apply"),
	);
}

frappe.ui.form.on("Taskist SLA Rule", {
	refresh(frm) {
		add_taskist_governance_buttons(frm);
		frm.add_custom_button(__("Apply SLA Template"), () => apply_sla_template(frm), __("Setup"));
		frm.add_custom_button(__("Add Default Escalation Matrix"), () => {
			set_default_escalations(frm);
			frm.dirty();
			frappe.show_alert({ message: __("Default escalation matrix added"), indicator: "green" });
		}, __("Setup"));
	},
});
