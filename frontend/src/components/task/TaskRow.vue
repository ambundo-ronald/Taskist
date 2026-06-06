<template>
	<div
		class="flex flex-col py-2 bg-white dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
		:style="{ paddingLeft: (12 + depth * mobileIndent) + 'px', paddingRight: '12px' }"
		@click="taskStore.selectTask(task)"
	>
	<div class="flex items-center gap-2 md:gap-3 min-h-[28px]">
		<button
			@click.stop="toggleDone"
			class="w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors"
			:class="isDone ? 'bg-green-500 border-green-500' : 'border-gray-300 dark:border-gray-600 hover:border-blue-500'"
		>
			<FeatherIcon v-if="isDone" name="check" class="w-3 h-3 text-white" />
		</button>
		<button
			v-if="childCount > 0"
			@click.stop="taskStore.toggleCollapse(task.name)"
			class="w-4 h-4 flex items-center justify-center flex-shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-transform"
			:class="taskStore.isCollapsed(task.name) ? '' : 'rotate-90'"
			:title="taskStore.isCollapsed(task.name) ? 'Expand' : 'Collapse'"
		>
			<FeatherIcon name="chevron-right" class="w-3 h-3" />
		</button>
		<FeatherIcon v-if="task.is_group" name="folder" class="w-4 h-4 text-blue-500 flex-shrink-0" title="Group task" />
		<FeatherIcon v-if="task.is_milestone" name="star" class="w-4 h-4 text-amber-500 flex-shrink-0" title="Milestone" />
		<div class="w-2 h-2 rounded-full flex-shrink-0" :style="dotStyle" :class="!task.color ? priorityColor : ''"></div>
		<span class="flex-1 text-sm truncate flex items-center gap-1" :class="isDone ? 'text-gray-400 line-through' : 'text-gray-900 dark:text-gray-100'">
			{{ task.subject }}
			<FeatherIcon v-if="task.taskist_is_recurring" name="refresh-cw" class="w-3.5 h-3.5 text-blue-500 flex-shrink-0" title="Recurring task" />
			<a
				v-if="sourceUrl"
				:href="sourceUrl"
				target="_blank"
				@click.stop
				class="text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 flex-shrink-0"
				:title="`Open ${task.taskist_reference_doctype} ${task.taskist_reference_name}`"
			>
				<FeatherIcon name="external-link" class="w-3.5 h-3.5" />
			</a>
		</span>
		<span v-if="childCount > 0" class="text-xs text-blue-500 flex items-center gap-0.5 flex-shrink-0">
			<FeatherIcon name="folder" class="w-3 h-3" />
			{{ childCount }}
			<button
				@click.stop="taskStore.toggleGroupFilter(task.name)"
				class="ml-0.5 p-0.5 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
				:class="taskStore.groupFilter === task.name ? 'text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/40' : 'text-blue-400 hover:text-blue-600'"
				:title="taskStore.groupFilter === task.name ? 'Clear filter' : 'Show only children'"
			>
				<FeatherIcon name="filter" class="w-3 h-3" />
			</button>
		</span>
		<Badge :label="task.status || 'Open'" size="sm" theme="gray" class="hidden sm:inline-flex" />
		<Badge v-if="task._sla_status" :label="slaLabel(task._sla_status)" size="sm" :theme="slaTheme(task._sla_status)" class="hidden sm:inline-flex" />
		<Badge v-if="task._sla_response_status === 'Breached'" label="Response Breached" size="sm" theme="red" class="hidden lg:inline-flex" />
		<span v-if="task.project" class="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[120px] hidden md:inline">{{ task.project }}</span>
		<span v-if="task.exp_end_date" class="text-xs whitespace-nowrap" :class="isOverdue ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'">
			{{ formatDate(task.exp_end_date) }}
		</span>
		<div v-if="assignees.length" class="hidden md:flex -space-x-1 flex-shrink-0">
			<Avatar v-for="(user, i) in assignees.slice(0, 3)" :key="i" :label="user" size="xs" class="ring-2 ring-white dark:ring-gray-800" :title="user" />
		</div>
		<span v-if="task._last_comment" class="text-xs text-gray-400 dark:text-gray-500 truncate max-w-[180px] hidden lg:inline-flex items-center gap-1" :title="task._last_comment">
			<FeatherIcon name="message-square" class="w-3 h-3 flex-shrink-0" />
			{{ task._last_comment }}
			<span v-if="task._last_comment_at" class="text-gray-300 dark:text-gray-600">&middot; {{ timeAgo(task._last_comment_at) }}</span>
		</span>
	</div>
	<div v-if="task.progress > 0" class="mt-1 pl-7">
		<FrappeProgress :value="task.progress" size="sm" />
	</div>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTaskStore, type Task } from '@/stores/taskStore'
import { call } from '@/data/api'
import { documentUrl } from '@/utils/frappeRoute'
import { slaLabel, slaTheme } from '@/utils/sla'
import dayjs from 'dayjs'

const props = withDefaults(defineProps<{
	task: Task & { _depth?: number; _childCount?: number }
	depth?: number
}>(), {
	depth: 0,
})
const taskStore = useTaskStore()

const windowWidth = ref(window.innerWidth)
function onResize() { windowWidth.value = window.innerWidth }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
const mobileIndent = computed(() => windowWidth.value < 640 ? 12 : 24)

const isDone = computed(() => props.task.status === 'Completed')
const priorityColor = computed(() => {
	const colors: Record<string, string> = { High: 'bg-orange-500', Medium: 'bg-yellow-500', Low: 'bg-green-500' }
	return colors[props.task.priority] || 'bg-gray-400'
})
const dotStyle = computed(() => {
	if (props.task.color) return { backgroundColor: props.task.color }
	return {}
})
const assignees = computed(() => {
	if (!props.task._assign) return []
	try { return JSON.parse(props.task._assign) } catch { return [] }
})
const isOverdue = computed(() => props.task.exp_end_date && dayjs(props.task.exp_end_date).isBefore(dayjs(), 'day'))
const childCount = computed(() => {
	if (typeof props.task._childCount === 'number') return props.task._childCount
	return (taskStore.childrenMap[props.task.name] || []).length
})
const sourceUrl = computed(() => documentUrl(props.task.taskist_reference_doctype, props.task.taskist_reference_name))

async function toggleDone() {
	await call('taskist.api.update_task_status', {
		task_name: props.task.name,
		status: isDone.value ? 'Open' : 'Completed',
	})
	await taskStore.fetchTasks()
}

function formatDate(date: string) {
	const d = dayjs(date)
	if (d.isSame(dayjs(), 'day')) return 'Today'
	if (d.isSame(dayjs().add(1, 'day'), 'day')) return 'Tomorrow'
	return d.format('MMM D')
}

function timeAgo(dt: string) {
	const diff = dayjs().diff(dayjs(dt), 'minute')
	if (diff < 1) return 'now'
	if (diff < 60) return `${diff}m`
	const hours = Math.floor(diff / 60)
	if (hours < 24) return `${hours}h`
	const days = Math.floor(hours / 24)
	if (days < 30) return `${days}d`
	return dayjs(dt).format('MMM D')
}
</script>
