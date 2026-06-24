<template>
	<Dialog
		:model-value="true"
		@update:model-value="(v) => { if (!v) $emit('close') }"
		:options="{ title: parentTask ? 'New Subtask' : 'New Task', size: 'md' }"
	>
		<template #body-content>
			<div class="space-y-3">
				<div v-if="createError" class="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded px-3 py-2 text-xs text-red-700 dark:text-red-300">{{ createError }}</div>
				<div v-if="queueAdvisory && !queueAdvisory.available" class="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 rounded px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
					<div class="font-medium">You already have {{ queueAdvisory.overlap_count }} active task(s) in that window.</div>
					<div>Suggested start: {{ formatDateTime(queueAdvisory.next_available_from) }}</div>
				</div>
				<div v-if="parentTask" class="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400">
					<FeatherIcon name="folder" class="w-3.5 h-3.5" />
					Subtask of: {{ parentTask }}
				</div>
				<div>
					<label for="taskist-quick-subject" class="field-label">Task subject <span class="text-red-500">*</span></label>
					<input
						id="taskist-quick-subject"
						ref="input"
						v-model="subject"
						@input="createError = ''"
						@keydown.enter="create"
						@keydown.escape="$emit('close')"
						type="text"
						:placeholder="parentTask ? 'Enter subtask name' : 'What needs to be done?'"
						class="control-input w-full"
						autocomplete="off"
						autofocus
					/>
				</div>
				<PrioritySlider v-model="priority" />
				<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
					<div>
						<label class="field-label">Project</label>
						<select v-model="project" class="control-input w-full">
							<option value="">Non-Project Task</option>
							<option v-for="item in projects" :key="item" :value="item">{{ item }}</option>
						</select>
					</div>
					<div>
						<label class="field-label">Status</label>
						<select v-model="status" class="control-input w-full">
							<option value="Open">Open</option>
							<option value="Working">Working</option>
							<option value="Pending Review">Pending Review</option>
						</select>
					</div>
					<div class="sm:col-span-2">
						<label class="field-label">Due date and time</label>
						<DatetimePicker
							:model-value="dueDatetime"
							@update:model-value="handleDueChange"
							placeholder="Select date and time"
							input-class="control-input w-full"
						/>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<Button
				@click="create"
				:disabled="!subject.trim() || creating"
				:loading="creating"
				variant="solid"
				theme="blue"
				:label="creating ? 'Adding...' : 'Add Task'"
			/>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import { call } from '@/data/api'
import { useTaskStore } from '@/stores/taskStore'
import PrioritySlider from '@/components/common/PrioritySlider.vue'
import DatetimePicker from '@/components/common/DatetimePicker.vue'

const props = defineProps<{ prefillDate?: string; parentTask?: string }>()
const emit = defineEmits(['close'])
const taskStore = useTaskStore()

const input = ref<HTMLInputElement | null>(null)
const subject = ref('')
const project = ref('')
const projects = ref<string[]>([])
const priority = ref('Medium')
const status = ref('Open')

const dueDatetime = ref(props.prefillDate || '')
const creating = ref(false)
const createError = ref('')
const queueAdvisory = ref<any>(null)

async function create() {
	if (!subject.value.trim() || creating.value) return
	creating.value = true
	try {
		let exp_start_date: string | undefined
		let exp_end_date: string | undefined

		if (dueDatetime.value) {
			const dt = dueDatetime.value
			const hasTime = dt.length > 10
			if (hasTime) {
				exp_start_date = dt
				const timePart = dt.substring(11, 16)
				const startHour = parseInt(timePart.split(':')[0], 10)
				const startMin = timePart.split(':')[1] || '00'
				const endHour = String(Math.min(startHour + 1, 23)).padStart(2, '0')
				exp_end_date = `${dt.substring(0, 10)} ${endHour}:${startMin}:00`
			} else {
				exp_end_date = dt.substring(0, 10)
			}
		}

		await taskStore.quickCreate({
			subject: subject.value.trim(),
			project: project.value || undefined,
			priority: priority.value,
			status: status.value,
			exp_start_date,
			exp_end_date,
			parent_task: props.parentTask || undefined,
		})
		emit('close')
	} catch (e: any) {
		createError.value = e?.message || 'Failed to create task'
		console.error('Task creation failed:', e)
	} finally {
		creating.value = false
	}
}

async function handleDueChange(value: string) {
	dueDatetime.value = value
	queueAdvisory.value = null
	if (!value || value.length <= 10) return
	try {
		queueAdvisory.value = await call('taskist.queue.get_queue_advisory', {
			proposed_start: value,
			duration_minutes: 60,
		})
	} catch {
		queueAdvisory.value = null
	}
}

function formatDateTime(value: string) {
	return value ? dayjs(value).format('MMM D, h:mm A') : ''
}

onMounted(async () => {
	try {
		projects.value = await call('taskist.api.get_task_projects') || []
	} catch {
		projects.value = []
	}
	input.value?.focus()
})
</script>

<style scoped>
.field-label { @apply block mb-1 text-xs font-medium text-gray-500 dark:text-gray-400; }
.control-input { @apply min-h-10 rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100; }
</style>
