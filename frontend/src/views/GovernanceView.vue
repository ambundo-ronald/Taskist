<template>
	<div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
		<header class="px-3 md:px-6 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
			<div class="flex items-center gap-3">
				<div>
					<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">Rule Governance</h2>
					<p class="text-xs text-gray-500 dark:text-gray-400">Ownership, approvals, effective dates, and immutable revisions</p>
				</div>
				<button @click="loadDashboard" class="icon-button ml-auto" title="Refresh governance">
					<FeatherIcon name="refresh-cw" class="w-4 h-4" />
				</button>
			</div>
		</header>
		<div v-if="loading" class="flex-1 flex items-center justify-center"><LoadingIndicator class="w-6 h-6" /></div>
		<div v-else-if="error" class="flex-1 flex items-center justify-center text-sm text-red-600">{{ error }}</div>
		<main v-else class="flex-1 overflow-auto">
			<section class="grid grid-cols-2 md:grid-cols-5 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
				<div v-for="item in metrics" :key="item.label" class="metric-cell">
					<div class="text-[11px] text-gray-500">{{ item.label }}</div>
					<div class="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{{ item.value }}</div>
					<div class="text-[10px] text-gray-400">{{ item.detail }}</div>
				</div>
			</section>
			<section class="p-4 md:p-6 bg-white dark:bg-gray-800">
				<div class="flex flex-wrap items-center gap-2 mb-4">
					<button v-for="item in filters" :key="item.value" @click="activeFilter = item.value" :class="activeFilter === item.value ? 'filter-active' : 'filter-button'">
						{{ item.label }}
					</button>
					<a href="/app/taskist-rule-revision" class="ml-auto text-xs text-blue-600 hover:underline">Open revision ledger</a>
				</div>
				<div class="overflow-auto">
					<table class="data-table min-w-[1000px]">
						<thead><tr><th>Rule</th><th>Type</th><th>Owner</th><th>Status</th><th>Version</th><th>Effective</th><th>Approved by</th><th>Readiness</th><th></th></tr></thead>
						<tbody>
							<tr v-for="row in visibleRules" :key="`${row.rule_doctype}:${row.name}`">
								<td class="font-medium"><a :href="ruleLink(row)" target="_blank" class="text-blue-600 hover:underline">{{ row.name }}</a></td>
								<td>{{ row.rule_doctype === 'Taskist SLA Rule' ? 'SLA' : 'Process' }}</td>
								<td>{{ row.business_owner || '-' }}</td>
								<td><span :class="statusClass(row)">{{ row.approval_status || 'Draft' }}</span></td>
								<td>v{{ row.current_version || 0 }}</td>
								<td>{{ dateTime(row.effective_from) }}</td>
								<td>{{ row.approved_by || '-' }}</td>
								<td>
									<span v-if="!row.issues.length" class="status status-good">Ready</span>
									<span v-else class="text-xs text-red-600">{{ row.issues.join(', ') }}</span>
								</td>
								<td>
									<Button v-if="dashboard.can_manage && row.approval_status !== 'Approved' && row.business_owner" @click="openApproval(row)" label="Approve" size="sm" theme="green" />
								</td>
							</tr>
							<tr v-if="!visibleRules.length"><td colspan="9" class="empty-cell">No rules match this filter</td></tr>
						</tbody>
					</table>
				</div>
			</section>
		</main>
		<div v-if="approvalRule" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="approvalRule = null">
			<div class="w-full max-w-md rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-xl p-4">
				<h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Approve {{ approvalRule.name }}</h3>
				<label class="field-label">Effective from</label>
				<input v-model="effectiveFrom" type="datetime-local" class="control-input w-full" />
				<label class="field-label">Change reason</label>
				<textarea v-model="changeReason" rows="3" class="control-input w-full h-auto py-2"></textarea>
				<div class="mt-4 flex justify-end gap-2">
					<Button @click="approvalRule = null" label="Cancel" size="sm" variant="subtle" />
					<Button @click="approve" :disabled="!changeReason.trim()" label="Approve Rule" size="sm" theme="green" />
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { call } from '@/data/api'

const loading = ref(false)
const error = ref('')
const dashboard = ref<any>({ summary: {}, rules: [], can_manage: false })
const activeFilter = ref('all')
const approvalRule = ref<any>(null)
const effectiveFrom = ref('')
const changeReason = ref('')
const filters = [
	{ label: 'All', value: 'all' }, { label: 'Needs attention', value: 'issues' },
	{ label: 'Draft', value: 'draft' }, { label: 'Effective', value: 'effective' },
]
const metrics = computed(() => {
	const row = dashboard.value.summary || {}
	return [
		{ label: 'Total rules', value: row.total || 0, detail: 'process and SLA' },
		{ label: 'Governance ready', value: row.ready || 0, detail: 'complete metadata' },
		{ label: 'Effective now', value: row.effective || 0, detail: 'approved and active' },
		{ label: 'Draft changes', value: row.draft || 0, detail: 'awaiting approval' },
		{ label: 'Missing owner', value: row.missing_owner || 0, detail: 'must be assigned' },
	]
})
const visibleRules = computed(() => (dashboard.value.rules || []).filter((row: any) => {
	if (activeFilter.value === 'issues') return row.issues.length
	if (activeFilter.value === 'draft') return row.approval_status === 'Draft'
	if (activeFilter.value === 'effective') return row.effective
	return true
}))
async function loadDashboard() {
	loading.value = true
	error.value = ''
	try { dashboard.value = await call('taskist.governance.get_governance_dashboard') }
	catch (value: any) { error.value = value?.message || 'Unable to load governance' }
	finally { loading.value = false }
}
function openApproval(row: any) {
	approvalRule.value = row
	effectiveFrom.value = dayjs().format('YYYY-MM-DDTHH:mm')
	changeReason.value = ''
}
async function approve() {
	await call('taskist.governance.approve_rule', {
		rule_doctype: approvalRule.value.rule_doctype,
		rule_name: approvalRule.value.name,
		effective_from: dayjs(effectiveFrom.value).format('YYYY-MM-DD HH:mm:ss'),
		change_reason: changeReason.value.trim(),
	})
	approvalRule.value = null
	await loadDashboard()
}
function ruleLink(row: any) {
	const route = row.rule_doctype.toLowerCase().replace(/[\s_]+/g, '-')
	return `/app/${route}/${encodeURIComponent(row.name)}`
}
function dateTime(value: string) { return value ? dayjs(value).format('MMM D, YYYY h:mm A') : '-' }
function statusClass(row: any) {
	if (row.approval_status === 'Approved') return row.effective ? 'status status-good' : 'status status-waiting'
	if (row.approval_status === 'Retired') return 'status status-neutral'
	return 'status status-draft'
}
onMounted(loadDashboard)
</script>

<style scoped>
.icon-button { @apply h-8 w-8 flex items-center justify-center rounded text-gray-500 hover:text-blue-600 hover:bg-gray-100 dark:hover:bg-gray-700; }
.metric-cell { @apply px-4 py-3 border-r border-gray-100 dark:border-gray-700; }
.filter-button, .filter-active { @apply px-2.5 py-1.5 rounded text-xs; }
.filter-button { @apply text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700; }
.filter-active { @apply bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300; }
.data-table { @apply w-full text-xs text-left text-gray-600 dark:text-gray-300; }
.data-table th { @apply py-2 pr-3 text-[10px] font-medium uppercase text-gray-400 border-b border-gray-200 dark:border-gray-700; }
.data-table td { @apply py-2 pr-3 border-b border-gray-100 dark:border-gray-700; }
.empty-cell { @apply py-8 text-center text-gray-400; }
.status { @apply inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium; }
.status-good { @apply bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300; }
.status-waiting { @apply bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300; }
.status-draft { @apply bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300; }
.status-neutral { @apply bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300; }
.field-label { @apply block mt-3 mb-1 text-xs text-gray-500; }
.control-input { @apply h-8 border border-gray-200 dark:border-gray-600 rounded px-2 text-xs bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200; }
</style>
