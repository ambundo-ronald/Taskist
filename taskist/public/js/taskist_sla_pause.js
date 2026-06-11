frappe.ui.form.on("Taskist SLA Pause", {
	refresh(frm) {
		if (frm.doc.status === "Requested") {
			frm.add_custom_button(__("Approve"), () => decide(frm, true), __("Decision"));
			frm.add_custom_button(__("Reject"), () => decide(frm, false), __("Decision"));
		}
		if (frm.doc.status === "Active") {
			frm.add_custom_button(__("Resume SLA"), () => {
				frappe.call({
					method: "taskist.delay.resume_sla",
					args: { task_name: frm.doc.task },
					freeze: true,
				}).then(() => frm.reload_doc());
			});
		}
	},
});

function decide(frm, approve) {
	frappe.prompt(
		[{ fieldname: "notes", fieldtype: "Small Text", label: __("Decision Notes") }],
		(values) => {
			frappe.call({
				method: "taskist.delay.decide_sla_pause",
				args: {
					pause_name: frm.doc.name,
					approve: approve ? 1 : 0,
					decision_notes: values.notes,
				},
				freeze: true,
			}).then(() => frm.reload_doc());
		},
		approve ? __("Approve SLA Pause") : __("Reject SLA Pause"),
		approve ? __("Approve") : __("Reject"),
	);
}
