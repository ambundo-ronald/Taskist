<template>
	<div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
		<header class="px-3 md:px-6 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
			<div class="flex flex-wrap items-center gap-3">
				<div>
					<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">SLA and Flow Analytics</h2>
					<p class="text-xs text-gray-500 dark:text-gray-400">Compliance, bottlenecks, delay ownership, and delivery health</p>
				</div>
				<div class="ml-auto flex flex-wrap items-center gap-2">
					<input v-model="filters.from_date" type="date" class="filter-input" aria-label="From date" />
					<input v-model="filters.to_date" type="date" class="filter-input" aria-label="To date" />
					<select v-model="filters.department" class="filter-input" aria-label="Department">
						<option value="">All departments</option>
						<option v-for="item in dashboard.filters?.departments || []" :key="item" :value="item">{{ item }}</option>
					</select>
					<select v-model="filters.process_rule" class="filter-input" aria-label="Process">
						<option value="">All processes</option>
						<option v-for="item in dashboard.filters?.processes || []" :key="item" :value="item">{{ item }}</option>
					</select>
					<select v-model="filters.priority" class="filter-input" aria-label="Priority">
						<option value="">All priorities</option>
						<option v-for="item in dashboard.filters?.priorities || []" :key="item" :value="item">{{ item }}</option>
					</select>
					<button @click="loadDashboard" class="icon-button" title="Apply filters">
						<FeatherIcon name="filter" class="w-4 h-4" />
					</button>
					<button @click="loadAll" class="icon-button" title="Refresh analytics">
						<FeatherIcon name="refresh-cw" class="w-4 h-4" />
					</button>
				</div>
			</div>
		</header>

		<div v-if="loading" class="flex-1 flex items-center justify-center">
			<LoadingIndicator class="w-6 h-6" />
		</div>
		<div v-else-if="error" class="flex-1 flex items-center justify-center px-6 text-sm text-red-600">
			{{ error }}
		</div>
		<main v-else class="flex-1 overflow-auto">
			<section class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
				<div v-for="metric in summaryMetrics" :key="metric.label" class="px-4 py-3 border-r border-b md:border-b-0 border-gray-100 dark:border-gray-700">
					<div class="text-[11px] text-gray-500 dark:text-gray-400">{{ metric.label }}</div>
					<div class="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{{ metric.value }}</div>
					<div class="text-[10px] text-gray-400">{{ metric.detail }}</div>
				</div>
			</section>

			<div class="grid xl:grid-cols-2">
				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Department Scorecard</h3>
							<p>Volume, throughput, compliance, and open workload</p>
						</div>
						<FeatherIcon name="users" class="w-4 h-4 text-gray-400" />
					</div>
					<div class="overflow-auto">
						<table class="data-table min-w-[620px]">
							<thead><tr><th>Department</th><th>Volume</th><th>Done</th><th>Backlog</th><th>SLA</th><th>Flow</th><th>Breaches</th></tr></thead>
							<tbody>
								<tr v-for="row in dashboard.by_department" :key="row.label">
									<td class="font-medium">{{ row.label }}</td>
									<td>{{ row.volume }}</td>
									<td>{{ row.completed }}</td>
									<td>{{ row.backlog }}</td>
									<td><span :class="scoreClass(row.sla_compliance_pct)">{{ percent(row.sla_compliance_pct) }}</span></td>
									<td>{{ percent(row.flow_efficiency_pct) }}</td>
									<td>{{ row.breaches }}</td>
								</tr>
								<tr v-if="!dashboard.by_department?.length"><td colspan="7" class="empty-cell">No department data</td></tr>
							</tbody>
						</table>
					</div>
				</section>

				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Value Stream</h3>
							<p>Average processing compared with waiting and approved pause time</p>
						</div>
						<FeatherIcon name="activity" class="w-4 h-4 text-gray-400" />
					</div>
					<div class="space-y-3">
						<div v-for="row in dashboard.by_process?.slice(0, 10)" :key="row.label">
							<div class="flex items-center gap-3 text-xs">
								<span class="w-40 truncate font-medium text-gray-700 dark:text-gray-200" :title="row.label">{{ row.label }}</span>
								<div class="flex-1 h-3 flex overflow-hidden bg-gray-100 dark:bg-gray-700">
									<div class="bg-emerald-500" :style="{ width: streamWidth(row, 'active') }" title="Active work"></div>
									<div class="bg-amber-400" :style="{ width: streamWidth(row, 'waiting') }" title="Waiting"></div>
									<div class="bg-blue-400" :style="{ width: streamWidth(row, 'pause') }" title="Approved pause"></div>
								</div>
								<span class="w-12 text-right text-gray-500">{{ percent(row.flow_efficiency_pct) }}</span>
							</div>
							<div class="ml-43 mt-1 text-[10px] text-gray-400">
								{{ duration(row.avg_active_minutes) }} active · {{ duration(row.avg_waiting_minutes) }} waiting · {{ duration(row.avg_pause_minutes) }} paused
							</div>
						</div>
						<div v-if="!dashboard.by_process?.length" class="empty-cell">No process data</div>
					</div>
					<div class="flex gap-4 mt-4 text-[10px] text-gray-500">
						<span class="legend"><i class="bg-emerald-500"></i>Active</span>
						<span class="legend"><i class="bg-amber-400"></i>Waiting</span>
						<span class="legend"><i class="bg-blue-400"></i>Approved pause</span>
					</div>
				</section>

				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Workflow Bottlenecks</h3>
							<p>States with the highest average waiting time</p>
						</div>
						<FeatherIcon name="alert-triangle" class="w-4 h-4 text-gray-400" />
					</div>
					<div class="overflow-auto">
						<table class="data-table min-w-[580px]">
							<thead><tr><th>Workflow state</th><th>Waiting</th><th>Rework</th><th>Handoff</th><th>Breaches</th><th>SLA</th></tr></thead>
							<tbody>
								<tr v-for="row in dashboard.bottlenecks" :key="row.label">
									<td class="font-medium">{{ row.label }}</td>
									<td>{{ duration(row.avg_waiting_minutes) }}</td>
									<td>{{ duration(row.avg_rework_minutes) }}</td>
									<td>{{ duration(row.avg_handoff_minutes) }}</td>
									<td>{{ row.breaches }}</td>
									<td><span :class="scoreClass(row.sla_compliance_pct)">{{ percent(row.sla_compliance_pct) }}</span></td>
								</tr>
								<tr v-if="!dashboard.bottlenecks?.length"><td colspan="6" class="empty-cell">No bottleneck data</td></tr>
							</tbody>
						</table>
					</div>
				</section>

				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Process Heatmap</h3>
							<p>SLA compliance by process and owning department</p>
						</div>
						<FeatherIcon name="grid" class="w-4 h-4 text-gray-400" />
					</div>
					<div class="overflow-auto">
						<table class="heatmap-table">
							<thead>
								<tr><th>Process</th><th v-for="item in dashboard.heatmap?.departments" :key="item">{{ item }}</th></tr>
							</thead>
							<tbody>
								<tr v-for="row in dashboard.heatmap?.rows" :key="row.process">
									<td>{{ row.process }}</td>
									<td v-for="(cell, index) in row.values" :key="index">
										<span v-if="cell" :class="heatClass(cell.sla_compliance_pct)" :title="`${cell.breaches} breaches`">
											{{ percent(cell.sla_compliance_pct) }}
										</span>
										<span v-else class="heat-empty">-</span>
									</td>
								</tr>
								<tr v-if="!dashboard.heatmap?.rows?.length"><td class="empty-cell">No heatmap data</td></tr>
							</tbody>
						</table>
					</div>
				</section>

				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Delay Ownership</h3>
							<p>Recorded exceptions by responsible party and reason</p>
						</div>
						<span class="text-xs text-gray-500">{{ dashboard.delays?.total || 0 }} logs</span>
					</div>
					<div class="grid md:grid-cols-2 gap-6">
						<div>
							<h4 class="subheading">Responsible party</h4>
							<BarRow v-for="row in dashboard.delays?.by_responsible_party || []" :key="row.label" :row="row" :max="maxCount(dashboard.delays?.by_responsible_party)" />
							<div v-if="!dashboard.delays?.by_responsible_party?.length" class="empty-cell">No delay ownership data</div>
						</div>
						<div>
							<h4 class="subheading">Top reasons</h4>
							<BarRow v-for="row in dashboard.delays?.by_reason?.slice(0, 6) || []" :key="row.label" :row="row" :max="maxCount(dashboard.delays?.by_reason)" />
							<div v-if="!dashboard.delays?.by_reason?.length" class="empty-cell">No delay reasons recorded</div>
						</div>
					</div>
				</section>

				<section class="panel">
					<div class="section-heading">
						<div>
							<h3>Notification Health</h3>
							<p>Audited delivery attempts by channel</p>
						</div>
						<span :class="scoreClass(dashboard.notifications?.success_rate_pct)">{{ percent(dashboard.notifications?.success_rate_pct) }}</span>
					</div>
					<div class="grid grid-cols-4 gap-3 mb-4">
						<div class="mini-stat"><strong>{{ dashboard.notifications?.sent || 0 }}</strong><span>Sent</span></div>
						<div class="mini-stat"><strong>{{ dashboard.notifications?.failed || 0 }}</strong><span>Failed</span></div>
						<div class="mini-stat"><strong>{{ dashboard.notifications?.pending || 0 }}</strong><span>Pending</span></div>
						<div class="mini-stat"><strong>{{ dashboard.summary?.acknowledgement_pct == null ? '-' : percent(dashboard.summary.acknowledgement_pct) }}</strong><span>Acknowledged</span></div>
					</div>
					<div class="overflow-auto">
						<table class="data-table">
							<thead><tr><th>Channel</th><th>Total</th><th>Sent</th><th>Failed</th><th>Pending</th></tr></thead>
							<tbody>
								<tr v-for="row in dashboard.notifications?.channels || []" :key="row.label">
									<td class="font-medium">{{ row.label }}</td><td>{{ row.total }}</td><td>{{ row.sent }}</td><td>{{ row.failed }}</td><td>{{ row.pending }}</td>
								</tr>
								<tr v-if="!dashboard.notifications?.channels?.length"><td colspan="5" class="empty-cell">No delivery records</td></tr>
							</tbody>
						</table>
					</div>
				</section>

				<section class="panel xl:col-span-2">
					<div class="section-heading">
						<div>
							<h3>Volume and Throughput</h3>
							<p>Tasks created, completed, and breached during the selected period</p>
						</div>
						<FeatherIcon name="bar-chart-2" class="w-4 h-4 text-gray-400" />
					</div>
					<div class="h-36 flex items-end gap-1 overflow-x-auto pb-5">
						<div v-for="row in dashboard.trend" :key="row.date" class="h-full min-w-5 flex-1 flex flex-col justify-end group relative">
							<div class="flex items-end justify-center gap-px h-full">
								<div class="w-1/3 bg-blue-500" :style="{ height: trendHeight(row.created) }" title="Created"></div>
								<div class="w-1/3 bg-emerald-500" :style="{ height: trendHeight(row.completed) }" title="Completed"></div>
								<div class="w-1/3 bg-red-500" :style="{ height: trendHeight(row.breached) }" title="Breached"></div>
							</div>
							<span class="absolute -bottom-4 left-1/2 -translate-x-1/2 text-[9px] text-gray-400">{{ shortDate(row.date) }}</span>
						</div>
					</div>
					<div class="flex gap-4 mt-2 text-[10px] text-gray-500">
						<span class="legend"><i class="bg-blue-500"></i>Created</span>
						<span class="legend"><i class="bg-emerald-500"></i>Completed</span>
						<span class="legend"><i class="bg-red-500"></i>Breached</span>
					</div>
				</section>

				<section class="panel xl:col-span-2">
					<div class="section-heading">
						<div>
							<h3>Monthly KPI History</h3>
							<p>Immutable snapshots preserve historical results after policy changes</p>
						</div>
						<FeatherIcon name="archive" class="w-4 h-4 text-gray-400" />
					</div>
					<div class="overflow-auto">
						<table class="data-table min-w-[700px]">
							<thead><tr><th>Month</th><th>Volume</th><th>Completed</th><th>Backlog</th><th>SLA</th><th>Flow</th><th>Breaches</th><th>Generated</th></tr></thead>
							<tbody>
								<tr v-for="row in snapshots" :key="row.name">
									<td class="font-medium">{{ monthLabel(row.month_start) }}</td>
									<td>{{ row.metrics?.summary?.volume || 0 }}</td>
									<td>{{ row.metrics?.summary?.completed || 0 }}</td>
									<td>{{ row.metrics?.summary?.backlog || 0 }}</td>
									<td>{{ percent(row.metrics?.summary?.sla_compliance_pct) }}</td>
									<td>{{ percent(row.metrics?.summary?.flow_efficiency_pct) }}</td>
									<td>{{ row.metrics?.summary?.breaches || 0 }}</td>
									<td>{{ dateTime(row.generated_on) }}</td>
								</tr>
								<tr v-if="!snapshots.length"><td colspan="8" class="empty-cell">Snapshots appear after the first monthly scheduler run</td></tr>
							</tbody>
						</table>
					</div>
				</section>
			</div>
		</main>
	</div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { call } from '@/data/api'

const loading = ref(false)
const error = ref('')
const dashboard = ref<any>({ summary: {}, filters: {}, delays: {}, notifications: {}, heatmap: {}, trend: [] })
const snapshots = ref<any[]>([])
const filters = reactive({
	from_date: dayjs().subtract(29, 'day').format('YYYY-MM-DD'),
	to_date: dayjs().format('YYYY-MM-DD'),
	department: '',
	process_rule: '',
	priority: '',
})

const BarRow = defineComponent({
	props: { row: { type: Object, required: true }, max: { type: Number, default: 1 } },
	setup(props) {
		return () => h('div', { class: 'flex items-center gap-2 py-1.5 text-xs' }, [
			h('span', { class: 'w-32 truncate text-gray-600 dark:text-gray-300', title: props.row.label }, props.row.label),
			h('div', { class: 'flex-1 h-2 bg-gray-100 dark:bg-gray-700' }, [
				h('div', { class: 'h-full bg-blue-500', style: { width: `${Math.max((props.row.count / props.max) * 100, 4)}%` } }),
			]),
			h('span', { class: 'w-8 text-right text-gray-500' }, String(props.row.count)),
		])
	},
})

const summaryMetrics = computed(() => {
	const row = dashboard.value.summary || {}
	return [
		{ label: 'SLA compliance', value: percent(row.sla_compliance_pct), detail: `${row.breaches || 0} breaches` },
		{ label: 'Response SLA', value: percent(row.response_compliance_pct), detail: `${duration(row.avg_response_minutes)} average` },
		{ label: 'Resolution', value: duration(row.avg_resolution_minutes), detail: 'average lead time' },
		{ label: 'Flow efficiency', value: percent(row.flow_efficiency_pct), detail: `${duration(row.avg_waiting_minutes)} waiting` },
		{ label: 'Throughput', value: row.completed || 0, detail: `${row.volume || 0} new tasks` },
		{ label: 'Open backlog', value: row.backlog || 0, detail: `${duration(row.avg_backlog_age_minutes)} average age` },
		{ label: 'Rework', value: duration(row.avg_rework_minutes), detail: 'average per task' },
		{ label: 'Handoff', value: duration(row.avg_handoff_minutes), detail: 'average acceptance' },
	]
})

const maxTrend = computed(() => Math.max(1, ...((dashboard.value.trend || []).flatMap((row: any) => [row.created, row.completed, row.breached]))))

async function loadDashboard() {
	loading.value = true
	error.value = ''
	try {
		dashboard.value = await call('taskist.analytics.get_kpi_dashboard', { ...filters })
	} catch (value: any) {
		error.value = value?.message || 'Unable to load analytics'
	} finally {
		loading.value = false
	}
}

async function loadAll() {
	loading.value = true
	error.value = ''
	try {
		const [data, history] = await Promise.all([
			call('taskist.analytics.get_kpi_dashboard', { ...filters }),
			call('taskist.analytics.get_kpi_snapshots', { limit: 12 }),
		])
		dashboard.value = data
		snapshots.value = history || []
	} catch (value: any) {
		error.value = value?.message || 'Unable to load analytics'
	} finally {
		loading.value = false
	}
}

function percent(value: number | null | undefined) {
	return value == null ? '-' : `${value}%`
}

function duration(value: number | null | undefined) {
	const minutes = Math.max(Number(value || 0), 0)
	if (minutes < 60) return `${Math.round(minutes)}m`
	if (minutes < 1440) return `${(minutes / 60).toFixed(minutes < 600 ? 1 : 0)}h`
	return `${(minutes / 1440).toFixed(1)}d`
}

function scoreClass(value: number | null | undefined) {
	if (value == null) return 'score score-neutral'
	if (value >= 90) return 'score score-good'
	if (value >= 75) return 'score score-warning'
	return 'score score-bad'
}

function heatClass(value: number | null | undefined) {
	if (value == null) return 'heat heat-neutral'
	if (value >= 90) return 'heat heat-good'
	if (value >= 75) return 'heat heat-warning'
	return 'heat heat-bad'
}

function streamWidth(row: any, field: 'active' | 'waiting' | 'pause') {
	const values = {
		active: Number(row.avg_active_minutes || 0),
		waiting: Number(row.avg_waiting_minutes || 0),
		pause: Number(row.avg_pause_minutes || 0),
	}
	const total = values.active + values.waiting + values.pause
	return total ? `${values[field] * 100 / total}%` : '0%'
}

function trendHeight(value: number) {
	return `${Math.max((Number(value || 0) / maxTrend.value) * 100, value ? 6 : 0)}%`
}

function maxCount(rows: any[] | undefined) {
	return Math.max(1, ...((rows || []).map(row => Number(row.count || 0))))
}

function shortDate(value: string) {
	return dayjs(value).format('D')
}

function monthLabel(value: string) {
	return dayjs(value).format('MMMM YYYY')
}

function dateTime(value: string) {
	return value ? dayjs(value).format('MMM D, YYYY h:mm A') : '-'
}

onMounted(loadAll)
</script>

<style scoped>
.filter-input { @apply h-8 border border-gray-200 dark:border-gray-600 rounded px-2 text-xs bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200; }
.icon-button { @apply h-8 w-8 flex items-center justify-center rounded text-gray-500 hover:text-blue-600 hover:bg-gray-100 dark:hover:bg-gray-700; }
.panel { @apply min-w-0 p-4 md:p-5 bg-white dark:bg-gray-800 border-b border-r border-gray-200 dark:border-gray-700; }
.section-heading { @apply flex items-start justify-between gap-3 mb-4; }
.section-heading h3 { @apply text-sm font-semibold text-gray-900 dark:text-gray-100; }
.section-heading p { @apply text-[11px] text-gray-500 dark:text-gray-400 mt-0.5; }
.subheading { @apply mb-2 text-[11px] font-medium uppercase text-gray-400; }
.data-table { @apply w-full text-xs text-left text-gray-600 dark:text-gray-300; }
.data-table th { @apply py-2 pr-3 text-[10px] font-medium uppercase text-gray-400 border-b border-gray-200 dark:border-gray-700; }
.data-table td { @apply py-2 pr-3 border-b border-gray-100 dark:border-gray-700; }
.empty-cell { @apply py-6 text-center text-xs text-gray-400; }
.score { @apply inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium; }
.score-good { @apply bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300; }
.score-warning { @apply bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300; }
.score-bad { @apply bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300; }
.score-neutral { @apply bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300; }
.heatmap-table { @apply min-w-full text-xs text-left; }
.heatmap-table th { @apply p-2 text-[10px] font-medium text-gray-400 whitespace-nowrap; }
.heatmap-table td { @apply p-1 text-gray-600 dark:text-gray-300 whitespace-nowrap; }
.heat { @apply block min-w-14 px-2 py-2 text-center text-[10px] font-semibold; }
.heat-good { @apply bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200; }
.heat-warning { @apply bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200; }
.heat-bad { @apply bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200; }
.heat-neutral, .heat-empty { @apply block min-w-14 px-2 py-2 text-center bg-gray-100 text-gray-400 dark:bg-gray-700; }
.mini-stat { @apply flex flex-col border-l-2 border-gray-200 dark:border-gray-600 pl-2; }
.mini-stat strong { @apply text-base font-semibold text-gray-900 dark:text-gray-100; }
.mini-stat span { @apply text-[10px] text-gray-500; }
.legend { @apply inline-flex items-center gap-1; }
.legend i { @apply block w-2 h-2; }
</style>
