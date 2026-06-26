function setup_simple_process_rule(frm) {
	frappe.prompt(
		[
			{
				fieldname: "reference_doctype",
				fieldtype: "Link",
				label: __("Trigger DocType"),
				options: "DocType",
				default: frm.doc.reference_doctype,
				reqd: 1,
			},
			{
				fieldname: "trigger_event",
				fieldtype: "Select",
				label: __("When Should Task Be Created?"),
				options: "After Insert\nOn Update\nOn Submit\nOn Cancel\nWorkflow State Change",
				default: frm.doc.trigger_event || "On Submit",
				reqd: 1,
			},
			{
				fieldname: "task_action",
				fieldtype: "Data",
				label: __("Task Action"),
				description: __("Example: Review, Approve, Prepare quotation, Follow up"),
				default: "Review",
				reqd: 1,
			},
			{
				fieldname: "assignment_strategy",
				fieldtype: "Select",
				label: __("Assign To"),
				options: "Document Owner\nFixed User\nRole\nSource Field\nRound Robin Role",
				default: frm.doc.assignment_strategy || "Document Owner",
				reqd: 1,
			},
			{
				fieldname: "assigned_user",
				fieldtype: "Link",
				label: __("Assigned User"),
				options: "User",
				depends_on: "eval:doc.assignment_strategy == 'Fixed User'",
			},
			{
				fieldname: "assigned_role",
				fieldtype: "Link",
				label: __("Assigned Role"),
				options: "Role",
				depends_on: "eval:in_list(['Role', 'Round Robin Role'], doc.assignment_strategy)",
			},
			{
				fieldname: "assignee_field",
				fieldtype: "Data",
				label: __("Assignee Field"),
				description: __("Field on the source document that contains a User email."),
				depends_on: "eval:doc.assignment_strategy == 'Source Field'",
			},
			{
				fieldname: "sla_rule",
				fieldtype: "Link",
				label: __("SLA Rule"),
				options: "Taskist SLA Rule",
				default: frm.doc.sla_rule,
			},
		],
		(values) => {
			const action = values.task_action.trim();
			const doctype = values.reference_doctype;
			const code = frappe.scrub(`${doctype} ${action}`).toUpperCase();
			frm.set_value("reference_doctype", doctype);
			frm.set_value("trigger_event", values.trigger_event);
			frm.set_value("process_code", frm.doc.process_code || code);
			frm.set_value("description", frm.doc.description || `${action} task created from ${doctype}.`);
			frm.set_value("subject_template", `${action} {{ doc.name }}`);
			frm.set_value("description_template", `<p>${action} {{ doc.doctype }} {{ doc.name }}.</p>`);
			frm.set_value("priority", frm.doc.priority || "Medium");
			frm.set_value("assignment_strategy", values.assignment_strategy);
			frm.set_value("assigned_user", values.assigned_user || "");
			frm.set_value("assigned_role", values.assigned_role || "");
			frm.set_value("assignee_field", values.assignee_field || "");
			frm.set_value("sla_rule", values.sla_rule || "");
			frm.set_value("duplicate_policy", "Once Per Document");
			frm.set_value("completion_output_type", "None");
			frm.set_value("output_standard", frm.doc.output_standard || `${action} completed.`);
			frm.dirty();
			frappe.show_alert({ message: __("Simple process setup applied"), indicator: "green" });
		},
		__("Simple Auto Task Setup"),
		__("Apply"),
	);
}

frappe.ui.form.on("Taskist Process Rule", {
	refresh(frm) {
		add_taskist_governance_buttons(frm);
		frm.add_custom_button(__("Simple Auto Task Setup"), () => setup_simple_process_rule(frm), __("Setup"));

		if (frm.is_new() || !frm.doc.reference_doctype) {
			return;
		}

		frm.add_custom_button(__("Simulate Rule"), () => {
			const fields = [
				{
					fieldname: "reference_name",
					fieldtype: "Dynamic Link",
					label: __("Source Document"),
					options: "reference_doctype",
					reqd: 1,
				},
				{
					fieldname: "reference_doctype",
					fieldtype: "Data",
					default: frm.doc.reference_doctype,
					hidden: 1,
				},
			];
			if (frm.doc.trigger_event === "Workflow State Change") {
				fields.push({
					fieldname: "previous_state",
					fieldtype: "Data",
					label: __("Previous Workflow State"),
					description: __("Optional. Use this to test a specific workflow transition."),
				});
			}

			frappe.prompt(
				fields,
				(values) => {
					frappe.call({
						method: "taskist.process.simulate_process_rule",
						args: {
							rule_name: frm.doc.name,
							reference_name: values.reference_name,
							previous_state: values.previous_state,
						},
						freeze: true,
						freeze_message: __("Simulating process rule"),
					}).then(({ message }) => {
						const escaped = frappe.utils.escape_html(JSON.stringify(message, null, 2));
						frappe.msgprint({
							title: __("Process Rule Simulation"),
							message: `<pre style="max-height: 60vh; overflow: auto;">${escaped}</pre>`,
							wide: true,
						});
					});
				},
				__("Simulate Process Rule"),
				__("Simulate"),
			);
		});
	},
});
