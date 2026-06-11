<template>
	<div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
		<div class="px-3 md:px-6 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
			<div class="flex items-center gap-3">
				<div>
					<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">Daily SLA Review</h2>
					<p class="text-xs text-gray-500 dark:text-gray-400">Owners, blockers, deadlines, and escalations</p>
				</div>
				<button @click="loadReview" class="ml-auto p-2 text-gray-500 hover:text-blue-600" title="Refresh review">
					<FeatherIcon name="refresh-cw" class="w-4 h-4" />
				</button>
			</div>
			<div class="grid grid-cols-4 gap-2 mt-3">
				<button
					v-for="band in bands"
					:key="band"
					@click="bandFilter = bandFilter === band ? '' : band"
					class="border-b-2 px-2 py-2 text-left transition-colors"
					:class="bandFilter === band ? bandActiveClass(band) : 'border-gray-100 dark:border-gray-700'"
				>
					<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">{{ review.counts?.[band] || 0 }}</div>
					<div class="text-[11px]" :class="bandTextClass(band)">{{ band }}</div>
				</button>
			</div>
			<div v-if="review.can_manage && selectedNames.length" class="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
				<span class="text-xs text-gray-500">{{ selectedNames.length }} selected</span>
				<input
					v-model="userSearch"
					@input="searchUsers"
					type="text"
					placeholder="User email or name"
					class="w-48 border border-gray-200 dark:border-gray-600 rounded px-2 py-1.5 text-xs bg-white dark:bg-gray-700 dark:text-gray-200"
				/>
				<select
					v-if="userResults.length"
					v-model="selectedUser"
					class="w-52 border border-gray-200 dark:border-gray-600 rounded px-2 py-1.5 text-xs bg-white dark:bg-gray-700 dark:text-gray-200"
				>
					<option value="" disabled>Select user</option>
					<option v-for="user in userResults" :key="user.name" :value="user.name">
						{{ user.full_name || user.name }}
					</option>
				</select>
				<Button
					@click="bulkReassign"
					:disabled="!selectedUser"
					size="sm"
					variant="subtle"
					theme="blue"
					label="Reassign"
				/>
				<Button
					@click="bulkEscalate"
					:disabled="!selectedUser"
					size="sm"
					variant="subtle"
					theme="orange"
					label="Escalate"
				/>
			</div>
		</div>

		<div class="flex-1 overflow-auto">
			<div v-if="loading" class="h-48 flex items-center justify-center">
				<LoadingIndicator class="w-6 h-6" />
			</div>
			<div v-else-if="!filteredTasks.length" class="h-48 flex items-center justify-center text-sm text-gray-400">
				No tasks in this review band
			</div>
			<div v-else class="min-w-[880px]">
				<div class="grid grid-cols-[32px_minmax(220px,2fr)_110px_150px_120px_120px_110px] gap-3 px-4 py-2 text-[11px] font-medium text-gray-400 border-b border-gray-200 dark:border-gray-700">
					<input v-if="review.can_manage" type="checkbox" :checked="allSelected" @change="toggleAll" />
					<span>Task</span>
					<span>SLA</span>
					<span>Owner</span>
					<span>Blocker</span>
					<span>Next Action</span>
					<span>Age</span>
				</div>
				<div
					v-for="task in filteredTasks"
					:key="task.name"
					@click="taskStore.selectTask(task)"
					class="grid grid-cols-[32px_minmax(220px,2fr)_110px_150px_120px_120px_110px] gap-3 px-4 py-2.5 items-center bg-white dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer"
				>
					<input
						v-if="review.can_manage"
						type="checkbox"
						:checked="selected.has(task.name)"
						@click.stop
						@change="toggleTask(task.name)"
					/>
					<span v-else></span>
					<div class="min-w-0">
						<div class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ task.subject }}</div>
						<div class="text-[11px] text-gray-400 truncate">
							{{ task.taskist_process_rule || task.taskist_reference_doctype || 'General Task' }}
						</div>
					</div>
					<div>
						<Badge :label="task._review_band" size="sm" :theme="bandTheme(task._review_band)" />
						<div v-if="task._sla_due_at" class="text-[10px] text-gray-400 mt-0.5">{{ formatDue(task._sla_due_at) }}</div>
					</div>
					<div class="text-xs text-gray-600 dark:text-gray-300 truncate">{{ ownerLabel(task) }}</div>
					<div class="text-xs text-gray-600 dark:text-gray-300 truncate">
						{{ task._delay_reason || (task.status === 'Pending Review' ? 'Pending Review' : 'None') }}
					</div>
					<div class="text-xs text-gray-600 dark:text-gray-300 truncate">{{ nextAction(task) }}</div>
					<div class="text-xs text-gray-500">
						{{ task._overdue_hours ? `${task._overdue_hours}h overdue` : `${task._age_hours}h old` }}
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { call } from '@/data/api'
import { useTaskStore } from '@/stores/taskStore'
import dayjs from 'dayjs'

const taskStore = useTaskStore()
const review = ref<any>({ tasks: [], counts: {}, can_manage: false })
const loading = ref(false)
const bandFilter = ref('')
const selected = ref(new Set<string>())
const userSearch = ref('')
const userResults = ref<any[]>([])
const selectedUser = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null
const bands = ['Green', 'Amber', 'Red', 'Escalated']

const filteredTasks = computed(() =>
	bandFilter.value
		? review.value.tasks.filter((task: any) => task._review_band === bandFilter.value)
		: review.value.tasks,
)
const selectedNames = computed(() => Array.from(selected.value))
const allSelected = computed(() =>
	!!filteredTasks.value.length && filteredTasks.value.every((task: any) => selected.value.has(task.name)),
)

async function loadReview() {
	loading.value = true
	try {
		review.value = await call('taskist.operations.get_daily_review')
		selected.value = new Set()
	} finally {
		loading.value = false
	}
}

function toggleTask(name: string) {
	const next = new Set(selected.value)
	if (next.has(name)) next.delete(name)
	else next.add(name)
	selected.value = next
}

function toggleAll() {
	if (allSelected.value) selected.value = new Set()
	else selected.value = new Set(filteredTasks.value.map((task: any) => task.name))
}

function searchUsers() {
	if (searchTimer) clearTimeout(searchTimer)
	searchTimer = setTimeout(async () => {
		if (!userSearch.value.trim()) {
			userResults.value = []
			selectedUser.value = ''
			return
		}
		userResults.value = await call('taskist.api.search_users', { query: userSearch.value }) || []
		if (userResults.value.length === 1) selectedUser.value = userResults.value[0].name
	}, 200)
}

async function bulkReassign() {
	await call('taskist.operations.bulk_reassign_tasks', {
		task_names: selectedNames.value,
		user: selectedUser.value,
	})
	await Promise.all([loadReview(), taskStore.fetchTasks()])
}

async function bulkEscalate() {
	await call('taskist.operations.bulk_escalate_tasks', {
		task_names: selectedNames.value,
		recipient: selectedUser.value,
		notes: 'Escalated during the daily SLA review.',
	})
	await Promise.all([loadReview(), taskStore.fetchTasks()])
}

function ownerLabel(task: any) {
	try {
		const users = JSON.parse(task._assign || '[]')
		return users.join(', ') || 'Unassigned'
	} catch {
		return 'Unassigned'
	}
}

function nextAction(task: any) {
	if (task._sla_pause_status === 'Paused') return 'Resume SLA'
	if (task.status === 'Pending Review') return 'Review output'
	if (task.status === 'Open') return 'Acknowledge'
	if (task.status === 'Working') return 'Complete work'
	return task.status
}

function formatDue(value: string) {
	return dayjs(value).format('MMM D, h:mm A')
}

function bandTheme(band: string) {
	return ({ Green: 'green', Amber: 'yellow', Red: 'red', Escalated: 'orange' } as any)[band] || 'gray'
}

function bandTextClass(band: string) {
	return ({
		Green: 'text-green-600 dark:text-green-400',
		Amber: 'text-amber-600 dark:text-amber-400',
		Red: 'text-red-600 dark:text-red-400',
		Escalated: 'text-orange-600 dark:text-orange-400',
	} as any)[band]
}

function bandActiveClass(band: string) {
	return ({
		Green: 'border-green-500 bg-green-50 dark:bg-green-900/20',
		Amber: 'border-amber-500 bg-amber-50 dark:bg-amber-900/20',
		Red: 'border-red-500 bg-red-50 dark:bg-red-900/20',
		Escalated: 'border-orange-500 bg-orange-50 dark:bg-orange-900/20',
	} as any)[band]
}

onMounted(loadReview)
</script>
