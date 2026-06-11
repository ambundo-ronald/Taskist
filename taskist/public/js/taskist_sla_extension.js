frappe.ui.form.on("Taskist SLA Extension", {
	refresh(frm) {
		if (frm.doc.status !== "Requested") {
			return;
		}
		frm.add_custom_button(__("Approve"), () => decide(frm, true), __("Decision"));
		frm.add_custom_button(__("Reject"), () => decide(frm, false), __("Decision"));
	},
});

function decide(frm, approve) {
	frappe.prompt(
		[{ fieldname: "notes", fieldtype: "Small Text", label: __("Decision Notes") }],
		(values) => {
			frappe.call({
				method: "taskist.delay.decide_sla_extension",
				args: {
					extension_name: frm.doc.name,
					approve: approve ? 1 : 0,
					decision_notes: values.notes,
				},
				freeze: true,
			}).then(() => frm.reload_doc());
		},
		approve ? __("Approve SLA Extension") : __("Reject SLA Extension"),
		approve ? __("Approve") : __("Reject"),
	);
}
