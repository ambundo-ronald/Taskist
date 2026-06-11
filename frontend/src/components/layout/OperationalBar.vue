<template>
	<div class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-3 md:px-6 py-2 space-y-2">
		<div class="flex items-center gap-1 overflow-x-auto">
			<button
				v-for="queue in visibleQueues"
				:key="queue.value"
				@click="taskStore.activeQueue = queue.value as any"
				class="px-2.5 py-1.5 text-xs font-medium border-b-2 whitespace-nowrap transition-colors"
				:class="taskStore.activeQueue === queue.value
					? 'border-blue-600 text-blue-600'
					: 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'"
			>
				{{ queue.label }}
				<span class="ml-1 text-[10px] text-gray-400">{{ queueCount(queue.value) }}</span>
			</button>
			<button
				v-if="hasActiveFilters"
				@click="clearFilters"
				class="ml-auto p-1.5 text-gray-400 hover:text-red-500 flex-shrink-0"
				title="Clear operational filters"
			>
				<FeatherIcon name="x" class="w-4 h-4" />
			</button>
		</div>
		<div class="flex items-center gap-2 overflow-x-auto">
			<FrappeSelect
				v-model="taskStore.slaFilter"
				size="sm"
				:options="slaOptions"
				class="w-28 flex-shrink-0"
			/>
			<FrappeSelect
				v-model="taskStore.priorityFilter"
				size="sm"
				:options="priorityOptions"
				class="w-28 flex-shrink-0"
			/>
			<FrappeSelect
				v-model="taskStore.processFilter"
				size="sm"
				:options="processOptions"
				class="w-40 flex-shrink-0"
			/>
			<FrappeSelect
				v-model="taskStore.delayOwnerFilter"
				size="sm"
				:options="delayOwnerOptions"
				class="w-36 flex-shrink-0"
			/>
			<FrappeSelect
				v-model="taskStore.departmentFilter"
				size="sm"
				:options="departmentOptions"
				class="w-40 flex-shrink-0"
			/>
			<FrappeSelect
				v-model="taskStore.ageingFilter"
				size="sm"
				:options="ageingOptions"
				class="w-32 flex-shrink-0"
			/>
			<select
				v-if="savedViews.length"
				@change="handleSavedViewChange"
				class="h-7 w-36 flex-shrink-0 border border-gray-200 dark:border-gray-600 rounded px-2 text-xs bg-white dark:bg-gray-700 dark:text-gray-200"
				title="Saved operational views"
			>
				<option value="">Saved views</option>
				<option v-for="view in savedViews" :key="view.name" :value="view.name">{{ view.name }}</option>
			</select>
			<button @click="saveCurrentView" class="p-1.5 text-gray-400 hover:text-blue-600 flex-shrink-0" title="Save current view">
				<FeatherIcon name="bookmark" class="w-4 h-4" />
			</button>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useTaskStore, type Task } from '@/stores/taskStore'

const taskStore = useTaskStore()
const savedViews = ref<any[]>(loadSavedViews())

const queues = [
	{ label: 'My Tasks', value: 'my' },
	{ label: 'Shared', value: 'shared' },
	{ label: 'Team', value: 'team' },
	{ label: 'Escalated', value: 'escalated' },
	{ label: 'Waiting', value: 'waiting' },
	{ label: 'All', value: 'all' },
]

const visibleQueues = computed(() => queues.filter(queue => {
	if (queue.value === 'team' || queue.value === 'all') {
		return taskStore.accessScope.view_all_tasks || taskStore.accessScope.visible_users.length > 1
	}
	return true
}))

const slaOptions = [
	{ label: 'All SLA', value: '' },
	{ label: 'Green', value: 'Green' },
	{ label: 'Amber', value: 'Amber' },
	{ label: 'Red', value: 'Red' },
	{ label: 'Escalated', value: 'Escalated' },
]
const priorityOptions = [
	{ label: 'All Priority', value: '' },
	{ label: 'Urgent', value: 'Urgent' },
	{ label: 'High', value: 'High' },
	{ label: 'Medium', value: 'Medium' },
	{ label: 'Low', value: 'Low' },
]
const processOptions = computed(() => [
	{ label: 'All Processes', value: '' },
	...Array.from(new Set(taskStore.tasks.map(task => task.taskist_process_rule).filter(Boolean)))
		.sort()
		.map(value => ({ label: value as string, value: value as string })),
])
const delayOwnerOptions = computed(() => [
	{ label: 'All Delay Owners', value: '' },
	...Array.from(new Set(taskStore.tasks.map(task => task._delay_owner).filter(Boolean)))
		.sort()
		.map(value => ({ label: value as string, value: value as string })),
])
const departmentOptions = computed(() => [
	{ label: 'All Departments', value: '' },
	...Array.from(new Set(taskStore.tasks.map(task => task._department).filter(Boolean)))
		.sort()
		.map(value => ({ label: value as string, value: value as string })),
])
const ageingOptions = [
	{ label: 'All Ages', value: '' },
	{ label: 'Older than 4h', value: '4' },
	{ label: 'Older than 24h', value: '24' },
	{ label: 'Older than 72h', value: '72' },
	{ label: 'Older than 7d', value: '168' },
]

const hasActiveFilters = computed(() =>
	!!taskStore.slaFilter
	|| !!taskStore.priorityFilter
	|| !!taskStore.processFilter
	|| !!taskStore.delayOwnerFilter
	|| !!taskStore.departmentFilter
	|| !!taskStore.ageingFilter
)

function assignees(task: Task) {
	try { return JSON.parse(task._assign || '[]') as string[] } catch { return [] }
}

function queueCount(queue: string) {
	const currentUser = taskStore.accessScope.user
	if (queue === 'my') return taskStore.tasks.filter(task => {
		const users = assignees(task)
		return users.includes(currentUser) || (!users.length && task.owner === currentUser)
	}).length
	if (queue === 'shared') return taskStore.tasks.filter(task => {
		const users = assignees(task)
		return users.includes(currentUser) && users.length > 1
	}).length
	if (queue === 'team') return taskStore.tasks.filter(task => assignees(task).some(user => user !== currentUser)).length
	if (queue === 'escalated') return taskStore.tasks.filter(task =>
		task._sla_status === 'Breached' || (task._sla_escalation_level || 0) > 0 || task._manual_escalated,
	).length
	if (queue === 'waiting') return taskStore.tasks.filter(task =>
		task.status === 'Pending Review' || task._sla_pause_status === 'Paused' || !!task._delay_reason,
	).length
	return taskStore.tasks.length
}

function clearFilters() {
	taskStore.slaFilter = ''
	taskStore.priorityFilter = ''
	taskStore.processFilter = ''
	taskStore.delayOwnerFilter = ''
	taskStore.departmentFilter = ''
	taskStore.ageingFilter = ''
}

function loadSavedViews() {
	try { return JSON.parse(localStorage.getItem('taskist-saved-views') || '[]') } catch { return [] }
}

function saveCurrentView() {
	const name = window.prompt('View name')
	if (!name?.trim()) return
	const view = {
		name: name.trim(),
		queue: taskStore.activeQueue,
		sla: taskStore.slaFilter,
		priority: taskStore.priorityFilter,
		process: taskStore.processFilter,
		delayOwner: taskStore.delayOwnerFilter,
		department: taskStore.departmentFilter,
		ageing: taskStore.ageingFilter,
	}
	savedViews.value = [...savedViews.value.filter(item => item.name !== view.name), view]
	localStorage.setItem('taskist-saved-views', JSON.stringify(savedViews.value))
}

function loadSavedView(name: string) {
	const view = savedViews.value.find(item => item.name === name)
	if (!view) return
	taskStore.activeQueue = view.queue || 'my'
	taskStore.slaFilter = view.sla || ''
	taskStore.priorityFilter = view.priority || ''
	taskStore.processFilter = view.process || ''
	taskStore.delayOwnerFilter = view.delayOwner || ''
	taskStore.departmentFilter = view.department || ''
	taskStore.ageingFilter = view.ageing || ''
}

function handleSavedViewChange(event: Event) {
	loadSavedView((event.target as HTMLSelectElement).value)
}
</script>
