import { computed, ref } from 'vue'
import { call } from '@/data/api'

export interface TaskistNotification {
	name: string
	subject: string
	body: string
	document_type: string | null
	document_name: string | null
	read: boolean
	creation: string
	url: string
}

const notifications = ref<TaskistNotification[]>([])
const unreadCount = ref(0)
const loading = ref(false)
const error = ref('')

async function refresh(limit = 20) {
	loading.value = true
	error.value = ''
	try {
		const result = await call('taskist.notifications.get_recent_notifications', { limit })
		notifications.value = result?.notifications || []
		unreadCount.value = Number(result?.unread_count || 0)
	} catch (e: any) {
		error.value = e?.message || 'Failed to load notifications'
	} finally {
		loading.value = false
	}
}

async function markRead(name: string) {
	await call('taskist.notifications.mark_notification_read', { notification_name: name })
	const item = notifications.value.find((row) => row.name === name)
	if (item && !item.read) {
		item.read = true
		unreadCount.value = Math.max(0, unreadCount.value - 1)
	}
}

async function markAllRead() {
	await call('taskist.notifications.mark_notification_read', { mark_all: true })
	for (const item of notifications.value) item.read = true
	unreadCount.value = 0
}

export function useTaskistNotifications() {
	return {
		notifications,
		unreadCount,
		loading,
		error,
		hasUnread: computed(() => unreadCount.value > 0),
		refresh,
		markRead,
		markAllRead,
	}
}
