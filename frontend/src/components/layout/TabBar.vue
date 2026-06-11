<template>
	<div class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-3 md:px-6 flex items-center">
		<nav class="flex gap-1 overflow-x-auto">
			<router-link
				v-for="tab in visibleTabs"
				:key="tab.route"
				:to="tab.route"
				class="px-3 md:px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
				:class="isActive(tab.route)
					? 'border-blue-600 text-blue-600'
					: 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'"
			>
				{{ tab.label }}
			</router-link>
		</nav>
		<button
			v-if="taskStore.groupFilter"
			@click="taskStore.toggleGroupFilter(taskStore.groupFilter!)"
			class="ml-2 flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/60 transition-colors flex-shrink-0"
			title="Clear group filter"
		>
			<FeatherIcon name="filter" class="w-3 h-3" />
			{{ groupFilterLabel }}
			<FeatherIcon name="x" class="w-3 h-3" />
		</button>
		<div class="flex items-center gap-1 ml-auto flex-shrink-0">
			<button
				v-if="isKanbanOrList"
				@click="taskStore.toggleNameSort()"
				class="p-1.5 rounded-lg transition-colors"
				:class="taskStore.nameSort !== 'none' ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'"
				:title="taskStore.nameSort === 'none' ? 'Sort by name A→Z' : taskStore.nameSort === 'asc' ? 'Sort by name Z→A' : 'Clear name sort'"
			>
				<FeatherIcon
					:name="taskStore.nameSort === 'asc' ? 'arrow-up' : taskStore.nameSort === 'desc' ? 'arrow-down' : 'arrow-up-down'"
					class="w-4 h-4"
				/>
			</button>
			<button
				@click="taskStore.allCollapsed ? taskStore.expandAllGroups() : taskStore.collapseAllGroups()"
				class="p-1.5 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
				:title="taskStore.allCollapsed ? 'Expand all groups' : 'Collapse all groups'"
			>
				<FeatherIcon :name="taskStore.allCollapsed ? 'maximize-2' : 'minimize-2'" class="w-4 h-4" />
			</button>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTaskStore } from '@/stores/taskStore'

const route = useRoute()
const taskStore = useTaskStore()

const tabs = [
	{ label: 'Kanban', route: '/kanban' },
	{ label: 'List', route: '/list' },
	{ label: 'Calendar', route: '/calendar' },
	{ label: 'Summary', route: '/summary' },
	{ label: 'Daily Review', route: '/review' },
	{ label: 'Analytics', route: '/analytics' },
	{ label: 'Pilot', route: '/pilot' },
	{ label: 'Governance', route: '/governance' },
	{ label: 'Health', route: '/health' },
]

const visibleTabs = computed(() =>
	tabs.filter(tab =>
		!['/analytics', '/pilot', '/governance', '/health'].includes(tab.route) || taskStore.accessScope.view_all_tasks
	),
)

function isActive(path: string) {
	return route.path === path
}

const groupFilterLabel = computed(() => {
	if (!taskStore.groupFilter) return ''
	const task = taskStore.tasks.find(t => t.name === taskStore.groupFilter)
	return task ? task.subject : taskStore.groupFilter
})

const isKanbanOrList = computed(() => route.path === '/kanban' || route.path === '/list')
</script>
