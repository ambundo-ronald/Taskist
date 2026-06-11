frappe.ui.form.on("Taskist Process Rule", {
	refresh(frm) {
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
