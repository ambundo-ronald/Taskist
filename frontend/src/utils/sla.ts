export function slaTheme(status?: string | null) {
	if (status === 'Breached') return 'red'
	if (status === 'Warning') return 'yellow'
	if (status === 'Completed') return 'green'
	if (status === 'Cancelled') return 'gray'
	if (status === 'Paused') return 'orange'
	return 'blue'
}

export function slaLabel(status?: string | null) {
	if (!status) return ''
	return `SLA ${status}`
}

export function countdownLabel(deadline?: string | null, nowValue: Date = new Date()) {
	if (!deadline) return ''
	const due = new Date(deadline.replace(' ', 'T'))
	const diffMs = due.getTime() - nowValue.getTime()
	const absMinutes = Math.max(Math.ceil(Math.abs(diffMs) / 60000), 0)
	const days = Math.floor(absMinutes / 1440)
	const hours = Math.floor((absMinutes % 1440) / 60)
	const minutes = absMinutes % 60
	const compact = days ? `${days}d ${hours}h` : hours ? `${hours}h ${minutes}m` : `${minutes}m`
	return diffMs < 0 ? `${compact} late` : `${compact} left`
}

export function countdownTheme(deadline?: string | null, nowValue: Date = new Date()) {
	if (!deadline) return 'text-gray-500 dark:text-gray-400'
	const due = new Date(deadline.replace(' ', 'T'))
	const diffMinutes = Math.floor((due.getTime() - nowValue.getTime()) / 60000)
	if (diffMinutes < 0) return 'text-red-500'
	if (diffMinutes <= 60) return 'text-orange-500'
	if (diffMinutes <= 240) return 'text-amber-500'
	return 'text-gray-500 dark:text-gray-400'
}
