import { ref } from 'vue'

const now = ref(new Date())
let timer: number | null = null

export function useMinuteNow() {
	if (timer === null && typeof window !== 'undefined') {
		timer = window.setInterval(() => {
			now.value = new Date()
		}, 60000)
	}
	return now
}
