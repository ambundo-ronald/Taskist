frappe.query_reports["Taskist SLA Audit Timeline"] = {
	filters: [
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date"},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date"},
		{fieldname: "task", label: __("Task"), fieldtype: "Link", options: "Task"},
		{fieldname: "process_rule", label: __("Process"), fieldtype: "Link", options: "Taskist Process Rule"},
		{fieldname: "department", label: __("Department"), fieldtype: "Data"},
		{fieldname: "reference_doctype", label: __("Source DocType"), fieldtype: "Link", options: "DocType"},
		{
			fieldname: "reference_name",
			label: __("Source"),
			fieldtype: "Dynamic Link",
			options: "reference_doctype",
		},
		{
			fieldname: "event_type",
			label: __("Event"),
			fieldtype: "Select",
			options: "\nCreated\nAssigned\nUnassigned\nReassigned\nAcknowledged\nStarted\nStatus Changed\nReview Requested\nReviewed\nReturned for Correction\nWarning\nResponse Breached\nBreached\nEscalated\nManual Escalation\nNotification Sent\nNotification Failed\nPause Requested\nPaused\nPause Rejected\nResumed\nExtension Requested\nExtension Approved\nExtension Rejected\nCompleted\nReopened\nCancelled\nComment Added\nAttachment Added\nAttachment Removed\nSLA Started\nChecklist Updated\nOutput Approved\nHandoff Started\nHandoff Received\nRework Requested",
		},
		{fieldname: "actor", label: __("Actor"), fieldtype: "Link", options: "User"},
	],
};
