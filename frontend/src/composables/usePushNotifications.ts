import { computed, ref } from 'vue'
import { call } from '@/data/api'

const supported = typeof window !== 'undefined'
	&& 'serviceWorker' in navigator
	&& 'PushManager' in window
	&& 'Notification' in window

const enabled = ref(false)
const configured = ref(false)
const loading = ref(false)
const error = ref('')
const publicKey = ref('')

function urlBase64ToUint8Array(base64String: string) {
	const padding = '='.repeat((4 - base64String.length % 4) % 4)
	const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
	const rawData = window.atob(base64)
	const outputArray = new Uint8Array(rawData.length)
	for (let i = 0; i < rawData.length; ++i) {
		outputArray[i] = rawData.charCodeAt(i)
	}
	return outputArray
}

async function refreshStatus() {
	error.value = ''
	if (!supported) return

	try {
		const config = await call('taskist.push.get_push_config')
		configured.value = !!config?.enabled
		publicKey.value = config?.public_key || ''
		const registration = await navigator.serviceWorker.ready
		enabled.value = !!await registration.pushManager.getSubscription()
	} catch (e: any) {
		error.value = e?.message || 'Failed to load notification settings'
	}
}

async function enable() {
	error.value = ''
	if (!supported) {
		error.value = 'Push notifications are not supported in this browser'
		return
	}
	if (!configured.value || !publicKey.value) {
		error.value = 'Push notifications are not configured on this site'
		return
	}

	loading.value = true
	try {
		const permission = await Notification.requestPermission()
		if (permission !== 'granted') {
			error.value = 'Notification permission was not granted'
			return
		}

		const registration = await navigator.serviceWorker.ready
		const subscription = await registration.pushManager.subscribe({
			userVisibleOnly: true,
			applicationServerKey: urlBase64ToUint8Array(publicKey.value),
		})
		await call('taskist.push.save_push_subscription', { subscription: subscription.toJSON() })
		enabled.value = true
	} catch (e: any) {
		error.value = e?.message || 'Failed to enable push notifications'
	} finally {
		loading.value = false
	}
}

async function disable() {
	error.value = ''
	if (!supported) return

	loading.value = true
	try {
		const registration = await navigator.serviceWorker.ready
		const subscription = await registration.pushManager.getSubscription()
		if (subscription) {
			await call('taskist.push.remove_push_subscription', { endpoint: subscription.endpoint })
			await subscription.unsubscribe()
		}
		enabled.value = false
	} catch (e: any) {
		error.value = e?.message || 'Failed to disable push notifications'
	} finally {
		loading.value = false
	}
}

async function sendTest() {
	error.value = ''
	loading.value = true
	try {
		await call('taskist.push.send_test_push')
	} catch (e: any) {
		error.value = e?.message || 'Failed to send test notification'
	} finally {
		loading.value = false
	}
}

export function usePushNotifications() {
	return {
		supported,
		configured,
		enabled,
		loading,
		error,
		statusLabel: computed(() => {
			if (error.value) return error.value
			if (!supported) return 'Push notifications are not supported'
			if (!configured.value) return 'Push notifications are not configured'
			return enabled.value ? 'Push notifications enabled' : 'Enable push notifications'
		}),
		refreshStatus,
		enable,
		disable,
		sendTest,
	}
}
