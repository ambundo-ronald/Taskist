<template>
	<div class="flex-shrink-0 w-64 md:w-72 flex flex-col bg-gray-100 dark:bg-gray-800/50 rounded-xl">
		<div class="flex items-center justify-between px-4 py-3">
			<div class="flex items-center gap-2">
				<div class="w-2 h-2 rounded-full" :class="columnColor"></div>
				<h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300">{{ column }}</h3>
				<span class="text-xs text-gray-400 bg-gray-200 dark:bg-gray-700 rounded-full px-2 py-0.5">{{ tasks.length }}</span>
			</div>
		</div>
		<div
			class="flex-1 overflow-auto px-3 pb-3 space-y-2 min-h-[100px]"
			@dragover.prevent="onDragOver"
			@drop="onDrop"
			@dragleave="dragOver = false"
			:class="dragOver ? 'bg-blue-50 dark:bg-blue-900/20 rounded-lg' : ''"
			data-drop-target
			:data-drop-column="column"
		>
			<div
				v-for="item in orderedTasks"
				:key="item.task.name"
				draggable="true"
				@dragstart="onDragStart($event, item.task)"
				@dragend="dragOver = false"
				:style="{ marginLeft: item.depth * 12 + 'px' }"
				data-draggable
				:data-drag-value="JSON.stringify({ taskName: item.task.name })"
			>
				<TaskCard :task="item.task" />
			</div>
			<div v-if="!tasks.length" class="text-center py-8 text-sm text-gray-400 dark:text-gray-500">No tasks</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import TaskCard from '@/components/task/TaskCard.vue'
import { useTaskStore, type Task } from '@/stores/taskStore'

const taskStore = useTaskStore()

const props = defineProps<{ column: string; tasks: Task[] }>()
const emit = defineEmits<{ (e: 'move', payload: { taskName: string; column: string; index: number }): void }>()

const dragOver = ref(false)

const columnColor = computed(() => {
	const colors: Record<string, string> = {
		'Open': 'bg-gray-400',
		'Working': 'bg-blue-500',
		'Pending Review': 'bg-yellow-500',
		'Overdue': 'bg-red-500',
		'Completed': 'bg-green-500',
		'Cancelled': 'bg-gray-700 dark:bg-gray-400',
	}
	return colors[props.column] || 'bg-gray-400'
})

/** Order tasks so children appear right after their parent */
const orderedTasks = computed(() => {
	const taskSet = new Set(props.tasks.map(t => t.name))
	const childrenMap: Record<string, Task[]> = {}
	const roots: Task[] = []

	for (const task of props.tasks) {
		if (task.parent_task && taskSet.has(task.parent_task)) {
			if (!childrenMap[task.parent_task]) childrenMap[task.parent_task] = []
			childrenMap[task.parent_task].push(task)
		} else {
			roots.push(task)
		}
	}

	const sort = taskStore.nameSort
	const sortFn = sort !== 'none'
		? (a: Task, b: Task) => {
			const cmp = (a.subject || '').localeCompare(b.subject || '')
			return sort === 'desc' ? -cmp : cmp
		}
		: null

	if (sortFn) roots.sort(sortFn)

	const result: Array<{ task: Task; depth: number }> = []
	function add(task: Task, depth: number) {
		result.push({ task, depth })
		if (!taskStore.isCollapsed(task.name)) {
			const children = [...(childrenMap[task.name] || [])]
			if (sortFn) children.sort(sortFn)
			for (const child of children) {
				add(child, depth + 1)
			}
		}
	}
	for (const root of roots) {
		add(root, 0)
	}
	return result
})

function onDragStart(event: DragEvent, task: Task) {
	if (event.dataTransfer) {
		event.dataTransfer.effectAllowed = 'move'
		event.dataTransfer.setData('text/plain', JSON.stringify({ taskName: task.name }))
	}
}

function onDragOver(event: DragEvent) {
	dragOver.value = true
	if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function onDrop(event: DragEvent) {
	dragOver.value = false
	if (!event.dataTransfer) return
	try {
		const data = JSON.parse(event.dataTransfer.getData('text/plain'))
		if (data.taskName) {
			emit('move', { taskName: data.taskName, column: props.column, index: props.tasks.length })
		}
	} catch (e) { console.error('Drop failed:', e) }
}
</script>
