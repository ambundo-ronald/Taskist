<template>
	<div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
		<header class="px-3 md:px-6 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
			<div class="flex flex-wrap items-center gap-3">
				<div>
					<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">Department Pilot</h2>
					<p class="text-xs text-gray-500 dark:text-gray-400">Shadow evidence, automation quality, and operational sign-off</p>
				</div>
				<div class="ml-auto flex items-center gap-2">
					<select v-model="selectedPilot" @change="loadDashboard" class="control-input" aria-label="Pilot">
						<option value="">Latest pilot</option>
						<option v-for="item in dashboard.pilots || []" :key="item.name" :value="item.name">
							{{ item.pilot_name }} | {{ item.status }}
						</option>
					</select>
					<a href="/app/taskist-process-pilot/new-taskist-process-pilot" class="icon-button" title="Create pilot">
						<FeatherIcon name="plus" class="w-4 h-4" />
					</a>
					<button @click="loadDashboard" class="icon-button" title="Refresh pilot">
						<FeatherIcon name="refresh-cw" class="w-4 h-4" />
					</button>
				</div>
			</div>
		</header>

		<div v-if="loading" class="flex-1 flex items-center justify-center">
			<LoadingIndicator class="w-6 h-6" />
		</div>
		<div v-else-if="error" class="flex-1 flex items-center justify-center px-6 text-sm text-red-600">{{ error }}</div>
		<div v-else-if="!dashboard.pilot" class="flex-1 flex flex-col items-center justify-center gap-3 text-sm text-gray-500">
			<span>No department pilot has been configured.</span>
			<a href="/app/taskist-process-pilot/new-taskist-process-pilot" class="text-blue-600 hover:underline">Create the first pilot</a>
		</div>
		<main v-else class="flex-1 overflow-auto">
			<section class="px-4 md:px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
				<div class="flex flex-wrap items-center gap-3">
					<div>
						<div class="flex items-center gap-2">
							<h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">{{ dashboard.pilot.pilot_name }}</h3>
							<span :class="statusClass(dashboard.pilot.status)">{{ dashboard.pilot.status }}</span>
						</div>
						<p class="text-xs text-gray-500 mt-1">
							{{ dashboard.pilot.department }} | {{ dashboard.pilot.pilot_owner }} |
							{{ dateLabel(dashboard.pilot.start_date) }} to {{ dateLabel(dashboard.pilot.end_date) }}
						</p>
					</div>
					<div v-if="dashboard.can_manage" class="ml-auto flex items-center gap-2">
						<Button
							v-if="dashboard.pilot.status === 'Draft'"
							@click="changeStatus('Shadow')"
							label="Start Shadow"
							size="sm"
							theme="blue"
						/>
						<Button
							v-if="dashboard.pilot.status === 'Shadow'"
							@click="changeStatus('Operational')"
							label="Go Operational"
							size="sm"
							theme="orange"
						/>
						<Button
							v-if="dashboard.pilot.status === 'Operational'"
							@click="openSignoff"
							:disabled="!dashboard.ready_for_signoff"
							label="Complete Pilot"
							size="sm"
							theme="green"
						/>
						<button
							v-if="['Draft', 'Shadow', 'Operational'].includes(dashboard.pilot.status)"
							@click="changeStatus('Cancelled')"
							class="icon-button text-red-500"
							title="Cancel pilot"
						>
							<FeatherIcon name="x-circle" class="w-4 h-4" />
						</button>
					</div>
				</div>
			</section>

			<section class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
				<div v-for="metric in summaryMetrics" :key="metric.label" class="metric-cell">
					<div class="text-[11px] text-gray-500 dark:text-gray-400">{{ metric.label }}</div>
					<div class="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{{ metric.value }}</div>
					<div class="text-[10px] text-gray-400">{{ metric.detail }}</div>
				</div>
			</section>

			<div class="grid xl:grid-cols-2">
				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Readiness Gates</h3>
							<p>Every check must pass before operational sign-off</p>
						</div>
						<span :class="dashboard.ready_for_signoff ? 'ready-badge' : 'hold-badge'">
							{{ dashboard.ready_for_signoff ? 'Ready' : 'Hold' }}
						</span>
					</div>
					<div class="divide-y divide-gray-100 dark:divide-gray-700">
						<div v-for="row in dashboard.criteria || []" :key="row.label" class="flex items-center gap-3 py-3">
							<FeatherIcon :name="row.passed ? 'check-circle' : 'x-circle'" class="w-4 h-4" :class="row.passed ? 'text-green-500' : 'text-red-500'" />
							<span class="flex-1 text-sm text-gray-700 dark:text-gray-200">{{ row.label }}</span>
							<span class="text-xs text-gray-500">{{ row.value }}</span>
						</div>
					</div>
				</section>

				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Baseline Comparison</h3>
							<p>Starting measures captured before automation</p>
						</div>
						<FeatherIcon name="git-compare" class="w-4 h-4 text-gray-400" />
					</div>
					<div class="grid grid-cols-2 gap-x-6 gap-y-4">
						<div class="baseline-row"><span>Lead time</span><strong>{{ duration(dashboard.pilot.baseline.lead_time_minutes) }}</strong></div>
						<div class="baseline-row"><span>Waiting time</span><strong>{{ duration(dashboard.pilot.baseline.waiting_time_minutes) }}</strong></div>
						<div class="baseline-row"><span>Rework rate</span><strong>{{ percent(dashboard.pilot.baseline.rework_rate) }}</strong></div>
						<div class="baseline-row"><span>Breach rate</span><strong>{{ percent(dashboard.pilot.baseline.breach_rate) }}</strong></div>
					</div>
					<div v-if="dashboard.pilot.signed_off_by" class="mt-5 pt-4 border-t border-gray-100 dark:border-gray-700 text-xs text-gray-500">
						Signed off by {{ dashboard.pilot.signed_off_by }} on {{ dateLabel(dashboard.pilot.signed_off_on) }}
						<p class="mt-1 text-gray-700 dark:text-gray-300">{{ dashboard.pilot.signoff_notes }}</p>
					</div>
				</section>

				<section class="panel xl:col-span-2">
					<div class="section-heading">
						<div>
							<h3>Rule Performance</h3>
							<p>Eligible events, task creation, deduplication, and live flow measures</p>
						</div>
						<span class="text-xs text-gray-500">{{ dashboard.rules?.length || 0 }} of 5 rules</span>
					</div>
					<div class="overflow-auto">
						<table class="data-table min-w-[940px]">
							<thead>
								<tr><th>Process rule</th><th>Shadow</th><th>Live events</th><th>Created</th><th>Deduplicated</th><th>Success</th><th>SLA</th><th>Waiting</th><th>Errors</th></tr>
							</thead>
							<tbody>
								<tr v-for="row in dashboard.rules || []" :key="row.rule">
									<td class="font-medium">{{ row.rule }}</td>
									<td>{{ row.shadow_matches }}</td>
									<td>{{ row.operational_events }}</td>
									<td>{{ row.tasks_created }}</td>
									<td>{{ row.duplicates_prevented }}</td>
									<td><span :class="scoreClass(row.automation_success_pct)">{{ percent(row.automation_success_pct) }}</span></td>
									<td>{{ percent(row.metrics?.sla_compliance_pct) }}</td>
									<td>{{ duration(row.metrics?.avg_waiting_minutes) }}</td>
									<td>{{ row.errors + row.no_assignee }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>

				<section class="panel xl:col-span-2">
					<div class="section-heading">
						<div>
							<h3>Trigger Observations</h3>
							<p>Immutable evidence from source-document events</p>
						</div>
						<a href="/app/taskist-pilot-observation" class="text-xs text-blue-600 hover:underline">Open full ledger</a>
					</div>
					<div class="overflow-auto">
						<table class="data-table min-w-[900px]">
							<thead><tr><th>Observed</th><th>Rule</th><th>Mode</th><th>Outcome</th><th>Source</th><th>Task</th><th>Error</th></tr></thead>
							<tbody>
								<tr v-for="row in dashboard.observations || []" :key="row.name">
									<td>{{ dateTime(row.observed_on) }}</td>
									<td class="font-medium">{{ row.process_rule }}</td>
									<td>{{ row.mode }}</td>
									<td><span :class="outcomeClass(row.outcome)">{{ row.outcome }}</span></td>
									<td>
										<a :href="sourceLink(row)" target="_blank" class="text-blue-600 hover:underline">{{ row.reference_doctype }} {{ row.reference_name }}</a>
									</td>
									<td>
										<a v-if="row.task" :href="`/app/task/${encodeURIComponent(row.task)}`" target="_blank" class="text-blue-600 hover:underline">{{ row.task }}</a>
										<span v-else>-</span>
									</td>
									<td class="max-w-56 truncate text-red-500" :title="row.error_message">{{ row.error_message || '-' }}</td>
								</tr>
								<tr v-if="!dashboard.observations?.length"><td colspan="7" class="empty-cell">No eligible source events observed yet</td></tr>
							</tbody>
						</table>
					</div>
				</section>
			</div>
		</main>

		<div v-if="showSignoff" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showSignoff = false">
			<div class="w-full max-w-md rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-xl p-4">
				<h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Complete Department Pilot</h3>
				<textarea v-model="signoffNotes" rows="4" class="mt-3 w-full control-input h-auto py-2" placeholder="Record the department owner's decision and rollout conditions"></textarea>
				<div class="mt-3 flex justify-end gap-2">
					<Button @click="showSignoff = false" label="Cancel" size="sm" variant="subtle" />
					<Button @click="completePilot" :disabled="!signoffNotes.trim()" label="Sign Off" size="sm" theme="green" />
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
const selectedPilot = ref('')
const dashboard = ref<any>({ pilots: [], pilot: null })
const showSignoff = ref(false)
const signoffNotes = ref('')

const summaryMetrics = computed(() => {
	const row = dashboard.value.summary || {}
	return [
		{ label: 'Eligible events', value: row.eligible_events || 0, detail: `${row.shadow_matches || 0} shadow matches` },
		{ label: 'Live events', value: row.operational_events || 0, detail: 'operational triggers' },
		{ label: 'Tasks created', value: row.tasks_created || 0, detail: `${row.duplicates_prevented || 0} deduplicated` },
		{ label: 'Automation', value: percent(row.automation_success_pct), detail: 'target at least 95%' },
		{ label: 'Duplicates', value: percent(row.duplicate_rate_pct), detail: `${row.actual_duplicate_tasks || 0} extra tasks` },
		{ label: 'No assignee', value: row.no_assignee || 0, detail: 'must be zero' },
		{ label: 'Runtime errors', value: row.errors || 0, detail: 'must be zero' },
		{ label: 'Readiness', value: dashboard.value.ready_for_signoff ? 'Ready' : 'Hold', detail: 'department sign-off' },
	]
})

async function loadDashboard() {
	loading.value = true
	error.value = ''
	try {
		dashboard.value = await call('taskist.pilot.get_pilot_dashboard', {
			pilot_name: selectedPilot.value || undefined,
		})
		if (!selectedPilot.value && dashboard.value.pilot) selectedPilot.value = dashboard.value.pilot.name
	} catch (value: any) {
		error.value = value?.message || 'Unable to load department pilot'
	} finally {
		loading.value = false
	}
}

async function changeStatus(status: string, notes?: string) {
	loading.value = true
	try {
		dashboard.value = await call('taskist.pilot.update_pilot_status', {
			pilot_name: dashboard.value.pilot.name,
			status,
			notes,
		})
	} catch (value: any) {
		error.value = value?.message || 'Unable to update pilot'
	} finally {
		loading.value = false
	}
}

function openSignoff() {
	signoffNotes.value = ''
	showSignoff.value = true
}

async function completePilot() {
	await changeStatus('Completed', signoffNotes.value.trim())
	showSignoff.value = false
}

function percent(value: number | null | undefined) {
	return value == null ? '-' : `${Number(value).toFixed(1).replace('.0', '')}%`
}

function duration(value: number | null | undefined) {
	const minutes = Math.max(Number(value || 0), 0)
	if (minutes < 60) return `${Math.round(minutes)}m`
	if (minutes < 1440) return `${(minutes / 60).toFixed(1)}h`
	return `${(minutes / 1440).toFixed(1)}d`
}

function dateLabel(value: string | null) {
	return value ? dayjs(value).format('MMM D, YYYY') : 'open'
}

function dateTime(value: string) {
	return dayjs(value).format('MMM D, h:mm A')
}

function sourceLink(row: any) {
	const route = String(row.reference_doctype || '').toLowerCase().replace(/[\s_]+/g, '-')
	return `/app/${route}/${encodeURIComponent(row.reference_name)}`
}

function statusClass(status: string) {
	return {
		Draft: 'status status-neutral',
		Shadow: 'status status-shadow',
		Operational: 'status status-live',
		Completed: 'status status-good',
		Cancelled: 'status status-neutral',
	}[status] || 'status status-neutral'
}

function scoreClass(value: number | null) {
	if (value == null) return 'score score-neutral'
	return value >= 95 ? 'score score-good' : 'score score-bad'
}

function outcomeClass(outcome: string) {
	if (outcome === 'Task Created') return 'score score-good'
	if (outcome === 'Shadow Match' || outcome === 'Existing Task') return 'score score-shadow'
	if (outcome === 'No Assignee' || outcome === 'Error') return 'score score-bad'
	return 'score score-neutral'
}

onMounted(loadDashboard)
</script>

<style scoped>
.control-input { @apply h-8 border border-gray-200 dark:border-gray-600 rounded px-2 text-xs bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200; }
.icon-button { @apply h-8 w-8 flex items-center justify-center rounded text-gray-500 hover:text-blue-600 hover:bg-gray-100 dark:hover:bg-gray-700; }
.metric-cell { @apply px-4 py-3 border-r border-b md:border-b-0 border-gray-100 dark:border-gray-700; }
.panel { @apply min-w-0 p-4 md:p-5 bg-white dark:bg-gray-800 border-b border-r border-gray-200 dark:border-gray-700; }
.section-heading { @apply flex items-start justify-between gap-3 mb-4; }
.section-heading h3 { @apply text-sm font-semibold text-gray-900 dark:text-gray-100; }
.section-heading p { @apply text-[11px] text-gray-500 dark:text-gray-400 mt-0.5; }
.data-table { @apply w-full text-xs text-left text-gray-600 dark:text-gray-300; }
.data-table th { @apply py-2 pr-3 text-[10px] font-medium uppercase text-gray-400 border-b border-gray-200 dark:border-gray-700; }
.data-table td { @apply py-2 pr-3 border-b border-gray-100 dark:border-gray-700; }
.empty-cell { @apply py-6 text-center text-xs text-gray-400; }
.status, .score, .ready-badge, .hold-badge { @apply inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium; }
.status-neutral, .score-neutral { @apply bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300; }
.status-shadow, .score-shadow { @apply bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300; }
.status-live { @apply bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300; }
.status-good, .score-good, .ready-badge { @apply bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300; }
.score-bad, .hold-badge { @apply bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300; }
.baseline-row { @apply flex items-end justify-between border-b border-gray-100 dark:border-gray-700 pb-2 text-xs text-gray-500; }
.baseline-row strong { @apply text-sm text-gray-900 dark:text-gray-100; }
</style>
