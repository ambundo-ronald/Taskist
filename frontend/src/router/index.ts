import { createRouter, createWebHistory } from 'vue-router'

const routes = [
	{
		path: '/',
		redirect: '/kanban',
	},
	{
		path: '/kanban',
		name: 'Kanban',
		component: () => import('@/views/KanbanView.vue'),
	},
	{
		path: '/list',
		name: 'List',
		component: () => import('@/views/ListView.vue'),
	},
	{
		path: '/calendar',
		name: 'Calendar',
		component: () => import('@/views/CalendarView.vue'),
	},
	{
		path: '/summary',
		name: 'Summary',
		component: () => import('@/views/DailySummary.vue'),
	},
	{
		path: '/review',
		name: 'Daily Review',
		component: () => import('@/views/DailyReview.vue'),
	},
	{
		path: '/analytics',
		name: 'Analytics',
		component: () => import('@/views/AnalyticsView.vue'),
	},
	{
		path: '/pilot',
		name: 'Department Pilot',
		component: () => import('@/views/PilotView.vue'),
	},
	{
		path: '/governance',
		name: 'Governance',
		component: () => import('@/views/GovernanceView.vue'),
	},
	{
		path: '/health',
		name: 'System Health',
		component: () => import('@/views/HealthView.vue'),
	},
	{
		path: '/:pathMatch(.*)*',
		redirect: '/kanban',
	},
]

const router = createRouter({
	history: createWebHistory('/taskist'),
	routes,
})

export default router
