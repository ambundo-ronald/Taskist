<template>
	<div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
		<header class="px-3 md:px-6 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
			<div class="flex flex-wrap items-center gap-3">
				<div>
					<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">System Health</h2>
					<p class="text-xs text-gray-500 dark:text-gray-400">Scheduler, SLA, process, and notification diagnostics</p>
				</div>
				<div class="ml-auto flex items-center gap-2">
					<Button v-if="dashboard.can_manage" @click="runCycle" label="Run SLA Cycle" size="sm" theme="blue" :loading="running" />
					<button @click="loadDashboard" class="icon-button" title="Refresh health">
						<FeatherIcon name="refresh-cw" class="w-4 h-4" />
					</button>
				</div>
			</div>
		</header>
		<div v-if="loading" class="flex-1 flex items-center justify-center"><LoadingIndicator class="w-6 h-6" /></div>
		<div v-else-if="error" class="flex-1 flex items-center justify-center px-6 text-sm text-red-600">{{ error }}</div>
		<main v-else class="flex-1 overflow-auto">
			<section class="grid grid-cols-2 md:grid-cols-5 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
				<div v-for="item in metrics" :key="item.label" class="metric-cell">
					<div class="text-[11px] text-gray-500">{{ item.label }}</div>
					<div class="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{{ item.value }}</div>
					<div class="text-[10px] text-gray-400">{{ item.detail }}</div>
				</div>
			</section>
			<section class="p-4 md:p-6 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
				<div class="section-heading">
					<div><h3>Operational Checks</h3><p>Heartbeat is healthy when seen within twelve minutes</p></div>
					<span class="text-xs text-gray-500">Updated {{ dateTime(dashboard.generated_at) }}</span>
				</div>
				<div class="grid md:grid-cols-2 xl:grid-cols-3 gap-px bg-gray-200 dark:bg-gray-700 border border-gray-200 dark:border-gray-700">
					<div v-for="check in dashboard.checks || []" :key="check.key" class="bg-white dark:bg-gray-800 p-3 flex gap-3">
						<FeatherIcon :name="checkIcon(check.status)" class="w-4 h-4 mt-0.5" :class="checkColor(check.status)" />
						<div><div class="text-sm font-medium text-gray-800 dark:text-gray-100">{{ check.label }}</div><div class="text-xs text-gray-500 mt-1">{{ check.detail }}</div></div>
					</div>
				</div>
			</section>
			<section class="panel">
				<div class="section-heading">
					<div><h3>Delivery Recovery</h3><p>Pending and failed notification attempts</p></div>
					<a href="/app/taskist-notification-delivery" class="text-xs text-blue-600 hover:underline">Open delivery ledger</a>
				</div>
				<div class="overflow-auto">
					<table class="data-table min-w-[900px]">
						<thead><tr><th>Modified</th><th>Status</th><th>Task</th><th>Recipient</th><th>Channel</th><th>Attempts</th><th>Error</th><th></th></tr></thead>
						<tbody>
							<tr v-for="row in dashboard.deliveries || []" :key="row.name">
								<td>{{ dateTime(row.modified) }}</td>
								<td><span :class="row.status === 'Failed' ? 'status status-bad' : 'status status-waiting'">{{ row.status }}</span></td>
								<td><a :href="`/taskist?task=${encodeURIComponent(row.task)}`" class="text-blue-600 hover:underline">{{ row.task }}</a></td>
								<td>{{ row.recipient }}</td><td>{{ row.channel }}</td><td>{{ row.attempts }}/5</td>
								<td class="max-w-xs truncate" :title="row.last_error">{{ row.last_error || '-' }}</td>
								<td><Button v-if="dashboard.can_manage && row.status === 'Failed' && row.attempts < 5" @click="retry(row)" label="Retry" size="sm" variant="subtle" /></td>
							</tr>
							<tr v-if="!dashboard.deliveries?.length"><td colspan="8" class="empty-cell">No pending or failed deliveries</td></tr>
						</tbody>
					</table>
				</div>
			</section>
			<section class="panel">
				<div class="section-heading">
					<div><h3>Process Errors</h3><p>Recent rule failures captured by department pilots</p></div>
					<a href="/app/taskist-pilot-observation" class="text-xs text-blue-600 hover:underline">Open observation ledger</a>
				</div>
				<div class="overflow-auto">
					<table class="data-table min-w-[760px]">
						<thead><tr><th>Observed</th><th>Rule</th><th>Source</th><th>Error</th></tr></thead>
						<tbody>
							<tr v-for="row in dashboard.process_errors || []" :key="row.name">
								<td>{{ dateTime(row.observed_on) }}</td><td class="font-medium">{{ row.process_rule }}</td>
								<td><a :href="sourceLink(row)" target="_blank" class="text-blue-600 hover:underline">{{ row.reference_doctype }} {{ row.reference_name }}</a></td>
								<td class="max-w-xl truncate" :title="row.error_message">{{ row.error_message }}</td>
							</tr>
							<tr v-if="!dashboard.process_errors?.length"><td colspan="4" class="empty-cell">No captured process errors</td></tr>
						</tbody>
					</table>
				</div>
			</section>
		</main>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { call } from '@/data/api'

const loading = ref(false)
const running = ref(false)
const error = ref('')
const dashboard = ref<any>({ summary: {}, checks: [], deliveries: [], process_errors: [], can_manage: false })
const metrics = computed(() => {
	const row = dashboard.value.summary || {}
	return [
		{ label: 'Healthy checks', value: row.healthy || 0, detail: `${row.warning || 0} warning, ${row.critical || 0} critical` },
		{ label: 'Open trackers', value: row.open_trackers || 0, detail: 'actively monitored' },
		{ label: 'Breached', value: row.breached_trackers || 0, detail: 'require attention' },
		{ label: 'Push devices', value: row.active_subscriptions || 0, detail: 'active subscriptions' },
		{ label: 'Failed delivery', value: row.failed_deliveries || 0, detail: 'retry queue' },
	]
})
async function loadDashboard() {
	loading.value = true
	error.value = ''
	try { dashboard.value = await call('taskist.health.get_system_health') }
	catch (value: any) { error.value = value?.message || 'Unable to load system health' }
	finally { loading.value = false }
}
async function runCycle() {
	running.value = true
	error.value = ''
	try { dashboard.value = await call('taskist.health.run_sla_cycle') }
	catch (value: any) { error.value = value?.message || 'Unable to run the SLA cycle' }
	finally { running.value = false }
}
async function retry(row: any) {
	try { await call('taskist.health.retry_delivery', { delivery_name: row.name }); await loadDashboard() }
	catch (value: any) { error.value = value?.message || 'Unable to retry delivery' }
}
function dateTime(value: string) { return value ? dayjs(value).format('MMM D, YYYY h:mm A') : '-' }
function checkIcon(status: string) { return status === 'Healthy' ? 'check-circle' : status === 'Critical' ? 'x-circle' : 'alert-triangle' }
function checkColor(status: string) { return status === 'Healthy' ? 'text-green-500' : status === 'Critical' ? 'text-red-500' : 'text-amber-500' }
function sourceLink(row: any) {
	const route = String(row.reference_doctype || '').toLowerCase().replace(/[\s_]+/g, '-')
	return `/app/${route}/${encodeURIComponent(row.reference_name)}`
}
onMounted(loadDashboard)
</script>

<style scoped>
.icon-button { @apply h-8 w-8 flex items-center justify-center rounded text-gray-500 hover:text-blue-600 hover:bg-gray-100 dark:hover:bg-gray-700; }
.metric-cell { @apply px-4 py-3 border-r border-gray-100 dark:border-gray-700; }
.panel { @apply p-4 md:p-6 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700; }
.section-heading { @apply flex items-center justify-between gap-4 mb-4; }
.section-heading h3 { @apply text-sm font-semibold text-gray-900 dark:text-gray-100; }
.section-heading p { @apply text-xs text-gray-500 mt-0.5; }
.data-table { @apply w-full text-xs text-left text-gray-600 dark:text-gray-300; }
.data-table th { @apply py-2 pr-3 text-[10px] font-medium uppercase text-gray-400 border-b border-gray-200 dark:border-gray-700; }
.data-table td { @apply py-2 pr-3 border-b border-gray-100 dark:border-gray-700; }
.empty-cell { @apply py-8 text-center text-gray-400; }
.status { @apply inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium; }
.status-bad { @apply bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300; }
.status-waiting { @apply bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300; }
</style>
