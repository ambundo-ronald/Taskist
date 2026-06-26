function approve_taskist_rule(frm) {
	frappe.prompt(
		[
			{
				fieldname: "effective_from",
				fieldtype: "Datetime",
				label: __("Effective From"),
				default: frm.doc.effective_from || frappe.datetime.now_datetime(),
				reqd: 1,
			},
			{
				fieldname: "effective_to",
				fieldtype: "Datetime",
				label: __("Effective To"),
				default: frm.doc.effective_to,
			},
			{
				fieldname: "change_reason",
				fieldtype: "Small Text",
				label: __("Approval / Change Reason"),
				default: frm.doc.change_reason,
				reqd: 1,
			},
		],
		(values) => {
			frappe.call({
				method: "taskist.governance.approve_rule",
				args: {
					rule_doctype: frm.doctype,
					rule_name: frm.doc.name,
					effective_from: values.effective_from,
					effective_to: values.effective_to,
					change_reason: values.change_reason,
				},
				freeze: true,
				freeze_message: __("Approving rule"),
			}).then(() => {
				frappe.show_alert({ message: __("Rule approved"), indicator: "green" });
				frm.reload_doc();
			});
		},
		__("Approve Rule"),
		__("Approve"),
	);
}

function retire_taskist_rule(frm) {
	frappe.prompt(
		[
			{
				fieldname: "change_reason",
				fieldtype: "Small Text",
				label: __("Retirement Reason"),
				reqd: 1,
			},
		],
		(values) => {
			frappe.call({
				method: "taskist.governance.retire_rule",
				args: {
					rule_doctype: frm.doctype,
					rule_name: frm.doc.name,
					change_reason: values.change_reason,
				},
				freeze: true,
				freeze_message: __("Retiring rule"),
			}).then(() => {
				frappe.show_alert({ message: __("Rule retired"), indicator: "orange" });
				frm.reload_doc();
			});
		},
		__("Retire Rule"),
		__("Retire"),
	);
}

function clone_taskist_rule(frm) {
	const fields = [
		{
			fieldname: "new_rule_name",
			fieldtype: "Data",
			label: __("New Rule Name"),
			default: `${frm.doc.rule_name || frm.doc.name} Copy`,
			reqd: 1,
		},
	];
	if (frm.doctype === "Taskist Process Rule") {
		fields.push({
			fieldname: "new_process_code",
			fieldtype: "Data",
			label: __("New Process Code"),
			default: `${frm.doc.process_code || frappe.scrub(frm.doc.name).toUpperCase()}_COPY`,
			reqd: 1,
		});
	}

	frappe.prompt(
		fields,
		(values) => {
			frappe.call({
				method: "taskist.governance.clone_rule",
				args: {
					rule_doctype: frm.doctype,
					rule_name: frm.doc.name,
					new_rule_name: values.new_rule_name,
					new_process_code: values.new_process_code,
				},
				freeze: true,
				freeze_message: __("Cloning rule"),
			}).then(({ message }) => {
				frappe.show_alert({ message: __("Rule cloned as draft"), indicator: "blue" });
				frappe.set_route("Form", message.doctype, message.name);
			});
		},
		__("Clone Rule"),
		__("Clone"),
	);
}

function add_taskist_governance_buttons(frm) {
	if (frm.is_new()) {
		return;
	}

	frm.add_custom_button(__("Clone Rule"), () => clone_taskist_rule(frm), __("Governance"));

	if (frm.doc.approval_status !== "Approved") {
		frm.add_custom_button(__("Approve Rule"), () => approve_taskist_rule(frm), __("Governance"));
	}

	if (frm.doc.approval_status === "Approved") {
		frm.add_custom_button(__("Retire Rule"), () => retire_taskist_rule(frm), __("Governance"));
	}
}
