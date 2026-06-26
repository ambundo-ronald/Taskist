<template>
	<div class="h-14 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex items-center px-3 md:px-6 gap-2 md:gap-4 transition-colors">
		<!-- Mobile hamburger menu -->
		<button @click="$emit('toggle-menu')" class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 md:hidden">
			<FeatherIcon name="menu" class="w-5 h-5 text-gray-600 dark:text-gray-400" />
		</button>
		<!-- Search -->
		<div class="flex-1 max-w-md relative">
			<FeatherIcon name="search" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
			<input
				ref="searchInput"
				v-model="taskStore.searchQuery"
				type="text"
				placeholder="Search tasks... ( / )"
				class="w-full pl-10 pr-4 py-2 bg-gray-100 dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white dark:focus:bg-gray-600"
			/>
		</div>

		<!-- New Task -->
		<Button variant="solid" theme="blue" icon-left="plus" @click="showQuickAdd = true" label="New Task" class="hidden sm:flex" />
		<Button variant="solid" theme="blue" icon="plus" @click="showQuickAdd = true" class="sm:hidden" />

		<!-- Right-side icon group -->
		<div class="flex items-center gap-1 ml-auto">
			<!-- Dark / Light mode toggle -->
			<div class="relative">
				<button
					@click="toggleNotifications"
					class="relative p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
					:class="notifications.hasUnread.value ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400'"
					title="Notifications"
				>
					<FeatherIcon name="bell" class="w-5 h-5" />
					<span
						v-if="notifications.unreadCount.value"
						class="absolute -right-0.5 -top-0.5 min-w-[18px] h-[18px] rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-[18px] text-white text-center"
					>
						{{ notifications.unreadCount.value > 9 ? '9+' : notifications.unreadCount.value }}
					</span>
				</button>

				<div
					v-if="showNotifications"
					class="absolute right-0 z-50 mt-2 w-[min(92vw,380px)] overflow-hidden rounded-lg border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-800"
				>
					<div class="flex items-center justify-between border-b border-gray-100 px-3 py-2 dark:border-gray-700">
						<div>
							<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">Notifications</div>
							<div class="text-xs text-gray-500 dark:text-gray-400">{{ push.statusLabel.value }}</div>
						</div>
						<button
							v-if="notifications.unreadCount.value"
							@click="notifications.markAllRead()"
							class="text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
						>
							Mark all read
						</button>
					</div>

					<div class="flex items-center gap-2 border-b border-gray-100 px-3 py-2 dark:border-gray-700">
						<Button
							:variant="push.enabled.value ? 'subtle' : 'solid'"
							:theme="push.enabled.value ? 'gray' : 'blue'"
							:label="push.enabled.value ? 'Disable push' : 'Enable push'"
							:loading="push.loading.value"
							@click="togglePush"
						/>
						<Button
							v-if="push.enabled.value"
							variant="subtle"
							theme="gray"
							label="Test"
							:loading="push.loading.value"
							@click="push.sendTest()"
						/>
					</div>

					<div v-if="notifications.loading.value" class="px-3 py-6 text-center text-sm text-gray-500">
						Loading notifications...
					</div>
					<div v-else-if="notifications.error.value" class="px-3 py-4 text-sm text-red-600">
						{{ notifications.error.value }}
					</div>
					<div v-else-if="!notifications.notifications.value.length" class="px-3 py-6 text-center text-sm text-gray-500">
						No notifications yet
					</div>
					<div v-else class="max-h-96 overflow-auto">
						<button
							v-for="item in notifications.notifications.value"
							:key="item.name"
							@click="openNotification(item)"
							class="block w-full border-b border-gray-100 px-3 py-2 text-left last:border-0 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-700/60"
						>
							<div class="flex items-start gap-2">
								<span
									class="mt-1.5 h-2 w-2 shrink-0 rounded-full"
									:class="item.read ? 'bg-transparent' : 'bg-blue-500'"
								/>
								<div class="min-w-0 flex-1">
									<div class="truncate text-sm font-medium text-gray-900 dark:text-gray-100">{{ item.subject }}</div>
									<div v-if="item.body" class="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">{{ item.body }}</div>
									<div class="mt-1 text-[11px] text-gray-400">{{ formatNotificationTime(item.creation) }}</div>
								</div>
							</div>
						</button>
					</div>
				</div>
			</div>

			<button
				@click="toggle()"
				class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
				:title="isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'"
			>
				<FeatherIcon v-if="isDark" name="sun" class="w-5 h-5 text-yellow-400" />
				<FeatherIcon v-else name="moon" class="w-5 h-5 text-gray-500" />
			</button>

			<!-- Keyboard shortcuts info -->
			<button
				@click="$emit('show-shortcuts')"
				class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors hidden sm:block"
				title="Keyboard Shortcuts (?)"
			>
				<FeatherIcon name="info" class="w-5 h-5 text-gray-500 dark:text-gray-400" />
			</button>

			<!-- Open in Frappe Desk -->
			<a
				href="/app/task"
				target="_blank"
				class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
				title="Open Tasks in Desk"
			>
				<FeatherIcon name="external-link" class="w-5 h-5 text-gray-500 dark:text-gray-400" />
			</a>
		</div>
	</div>

	<TaskQuickAdd v-if="showQuickAdd" @close="showQuickAdd = false" :prefill-date="prefillDate" />
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { ref } from 'vue'
import { onMounted } from 'vue'
import { useTaskStore } from '@/stores/taskStore'
import { useDarkMode } from '@/composables/useDarkMode'
import { usePushNotifications } from '@/composables/usePushNotifications'
import { useTaskistNotifications, type TaskistNotification } from '@/composables/useTaskistNotifications'
import TaskQuickAdd from '@/components/task/TaskQuickAdd.vue'

defineEmits(['show-shortcuts', 'toggle-menu'])

const taskStore = useTaskStore()
const showQuickAdd = ref(false)
const prefillDate = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const { isDark, toggle } = useDarkMode()
const push = usePushNotifications()
const notifications = useTaskistNotifications()
const showNotifications = ref(false)

onMounted(() => {
	push.refreshStatus()
	notifications.refresh()
	bindRealtimeNotifications()
})

async function togglePush() {
	if (push.enabled.value) {
		await push.disable()
		return
	}
	await push.enable()
	if (push.enabled.value) {
		await push.sendTest()
	}
}

async function toggleNotifications() {
	showNotifications.value = !showNotifications.value
	if (showNotifications.value) {
		await notifications.refresh()
	}
}

async function openNotification(item: TaskistNotification) {
	if (!item.read) {
		await notifications.markRead(item.name)
	}
	window.location.href = item.url || '/taskist'
}

function formatNotificationTime(value: string) {
	return value ? dayjs(value).format('MMM D, h:mm A') : ''
}

function bindRealtimeNotifications() {
	const frappeRealtime = (window as any).frappe?.realtime
	if (!frappeRealtime?.on) return
	frappeRealtime.on('taskist_notification', () => notifications.refresh())
}

function openQuickAdd(date?: string) {
	prefillDate.value = date || ''
	showQuickAdd.value = true
}

function focusSearch() {
	searchInput.value?.focus()
}

defineExpose({ openQuickAdd, focusSearch })
</script>
