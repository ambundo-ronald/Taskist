<template>
	<transition name="slide">
		<div
			v-if="taskStore.showDetail && taskStore.selectedTask"
			class="fixed right-0 top-0 h-full w-full sm:w-[480px] bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 shadow-xl z-40 flex flex-col"
		>
			<div class="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-gray-200 dark:border-gray-700">
				<div class="flex items-center gap-1.5 min-w-0">
					<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">Task Details</h2>
					<a
						v-if="taskStore.selectedTask?.name"
						:href="`/desk/task/${taskStore.selectedTask.name}`"
						target="_blank"
						class="text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 flex-shrink-0"
						title="Open in Desk"
					>
						<FeatherIcon name="external-link" class="w-4 h-4" />
					</a>
					<a
						v-if="sourceUrl"
						:href="sourceUrl"
						target="_blank"
						class="text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 flex-shrink-0"
						:title="`Open ${doc?.taskist_reference_doctype} ${doc?.taskist_reference_name}`"
					>
						<FeatherIcon name="file-text" class="w-4 h-4" />
					</a>
				</div>
				<div class="flex items-center gap-2">
					<Button
						v-if="doc?.status === 'Open'"
						@click="acknowledgeTask"
						size="sm"
						variant="subtle"
						theme="blue"
						label="Acknowledge"
					/>
					<Button
						@click="markCompleted"
						size="sm"
						:variant="isCompleted ? 'subtle' : 'ghost'"
						:theme="isCompleted ? 'green' : 'gray'"
						:label="isCompleted ? 'Completed' : 'Mark Completed'"
					/>
					<Button
						@click="taskStore.closeDetail()"
						size="sm"
						variant="ghost"
						label="Close"
					/>
				</div>
			</div>

			<div v-if="doc" class="flex-1 overflow-auto px-3 sm:px-4 py-3 space-y-3">
				<!-- Save error banner -->
				<div v-if="saveError" class="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded px-3 py-2 text-xs text-red-700 dark:text-red-300 flex items-start gap-2">
					<FeatherIcon name="alert-circle" class="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
					<div class="flex-1 whitespace-pre-line">{{ saveError }}</div>
					<button @click="saveError = ''" class="text-red-400 hover:text-red-600 flex-shrink-0">
						<FeatherIcon name="x" class="w-3.5 h-3.5" />
					</button>
				</div>
				<div v-if="queueWarning" class="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 rounded px-3 py-2 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2">
					<FeatherIcon name="clock" class="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
					<div class="flex-1 whitespace-pre-line">{{ queueWarning }}</div>
					<button @click="queueWarning = ''" class="text-amber-500 hover:text-amber-700 flex-shrink-0">
						<FeatherIcon name="x" class="w-3.5 h-3.5" />
					</button>
				</div>

				<!-- Subject -->
				<TextInput v-model="doc.subject" @blur="save" class="w-full text-sm font-medium" />

				<!-- Source Document -->
				<a
					v-if="sourceUrl"
					:href="sourceUrl"
					target="_blank"
					class="flex items-center gap-1.5 px-2 py-1.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-xs text-blue-700 dark:text-blue-300 hover:text-blue-900 dark:hover:text-blue-100"
				>
					<FeatherIcon name="file-text" class="w-3.5 h-3.5 flex-shrink-0" />
					<span class="text-blue-500 dark:text-blue-400">Source:</span>
					<span class="font-medium truncate">{{ doc.taskist_reference_doctype }} {{ doc.taskist_reference_name }}</span>
				</a>
				<div
					v-if="taskCountdown"
					class="flex items-center justify-between gap-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50 px-3 py-2"
				>
					<div class="flex items-center gap-2 text-sm font-medium" :class="taskCountdownClass">
						<FeatherIcon name="clock" class="w-4 h-4" />
						{{ taskCountdown }}
					</div>
					<div class="text-[11px] text-gray-500 dark:text-gray-400">
						{{ taskCountdownTarget }}
					</div>
				</div>

				<!-- Process output and chain -->
				<div v-if="processChain?.tasks?.length" class="space-y-2">
					<div v-if="processChain.output_type !== 'None'" class="border-y border-gray-100 dark:border-gray-700 py-2">
						<div class="flex items-start justify-between gap-2">
							<div class="min-w-0">
								<h3 class="text-[11px] font-medium text-gray-400 dark:text-gray-500">Required Output</h3>
								<div class="text-xs font-medium text-gray-700 dark:text-gray-200">{{ processChain.output_type }}</div>
								<div v-if="processChain.output_standard" class="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
									{{ processChain.output_standard }}
								</div>
							</div>
							<div v-if="processChain.approval_required" class="flex-shrink-0">
								<Badge
									v-if="doc.taskist_manager_approved_by"
									label="Approved"
									size="sm"
									theme="green"
								/>
								<Button
									v-else-if="processChain.can_approve"
									@click="approveOutput"
									size="sm"
									variant="subtle"
									theme="blue"
									label="Approve"
								/>
								<Badge v-else label="Approval Required" size="sm" theme="yellow" />
							</div>
						</div>
						<div v-if="checklistItems.length" class="mt-2 space-y-1">
							<label
								v-for="(item, index) in checklistItems"
								:key="item.label"
								class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300"
							>
								<input
									type="checkbox"
									:checked="!!item.completed"
									@change="toggleChecklistItem(index)"
									class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
								/>
								<span :class="item.completed ? 'line-through text-gray-400' : ''">{{ item.label }}</span>
							</label>
						</div>
					</div>
					<div>
						<h3 class="text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-1">Process Chain</h3>
						<div class="flex items-center gap-1 overflow-x-auto pb-1">
							<template v-for="(stage, index) in processChain.tasks" :key="stage.name">
								<button
									@click="stage.can_open && taskStore.selectTask(stage)"
									:disabled="!stage.can_open"
									class="flex-shrink-0 max-w-[150px] px-2 py-1 border text-left"
									:class="stage.name === doc.name
										? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-900/20'
										: stage.can_open
											? 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50'
											: 'border-gray-200 dark:border-gray-700 opacity-60 cursor-default'"
								>
									<div class="text-[10px] text-gray-400">Stage {{ stage.taskist_process_sequence || index + 1 }}</div>
									<div class="text-[11px] font-medium text-gray-700 dark:text-gray-200 truncate">{{ stage.taskist_process_rule }}</div>
									<div class="text-[10px]" :class="stageStatusClass(stage.status)">{{ stage.status }}</div>
								</button>
								<FeatherIcon
									v-if="index < processChain.tasks.length - 1"
									name="chevron-right"
									class="w-3 h-3 text-gray-300 flex-shrink-0"
								/>
							</template>
						</div>
					</div>
				</div>

				<!-- SLA -->
				<div v-if="slaTrackers.length" class="space-y-1.5">
					<h3 class="text-[11px] font-medium text-gray-400 dark:text-gray-500">SLA</h3>
					<div
						v-for="sla in slaTrackers"
						:key="sla.name"
						class="flex items-center justify-between gap-2 px-2 py-1.5 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-xs"
					>
						<div class="min-w-0">
							<div class="flex items-center gap-1.5">
								<Badge :label="slaLabel(sla.status)" size="sm" :theme="slaTheme(sla.status)" />
								<span class="font-medium text-gray-700 dark:text-gray-300 truncate">{{ sla.rule }}</span>
							</div>
							<div class="flex flex-wrap gap-x-3 text-[11px] text-gray-400 dark:text-gray-500 mt-0.5">
								<span>{{ sla.priority || 'Default' }} priority</span>
								<span v-if="sla.response_due_at">
									Response {{ sla.response_status }} · {{ formatTime(sla.response_due_at) }}
								</span>
								<span>Resolution due {{ formatTime(sla.due_at) }}</span>
								<span v-if="sla.current_escalation_level">
									Escalation level {{ sla.current_escalation_level }}
								</span>
							</div>
						</div>
						<FeatherIcon v-if="sla.status === 'Breached'" name="alert-triangle" class="w-4 h-4 text-red-500 flex-shrink-0" />
					</div>
					<div v-if="pauseState?.tracker" class="flex items-center gap-2">
						<Button
							v-if="pauseState.tracker.pause_status === 'Not Paused'"
							@click="openDelayDialog('pause')"
							size="sm"
							variant="subtle"
							theme="gray"
							label="Request SLA Pause"
						/>
						<Button
							v-if="pauseState.tracker.pause_status === 'Not Paused' && !extensionState?.extension"
							@click="openDelayDialog('extension')"
							size="sm"
							variant="subtle"
							theme="gray"
							label="Request Extension"
						/>
						<Badge
							v-if="extensionState?.extension"
							label="Extension Requested"
							size="sm"
							theme="yellow"
						/>
						<Badge
							v-else
							:label="pauseState.tracker.pause_status"
							size="sm"
							:theme="pauseState.tracker.pause_status === 'Paused' ? 'orange' : 'yellow'"
						/>
						<Button
							v-if="pauseState.tracker.pause_status === 'Paused'"
							@click="resumeSla"
							size="sm"
							variant="subtle"
							theme="blue"
							label="Resume SLA"
						/>
						<span v-if="pauseState.tracker.total_paused_minutes" class="text-[11px] text-gray-400">
							{{ pauseState.tracker.total_paused_minutes }} paused minutes
						</span>
						<span v-if="pauseState.pause?.delay_reason" class="text-[11px] text-gray-500 dark:text-gray-400">
							{{ pauseState.pause.delay_reason }}
						</span>
					</div>
				</div>

				<!-- Status + Priority row -->
				<div class="grid grid-cols-2 gap-2">
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Status</label>
						<FrappeSelect
							:model-value="doc.status"
							@update:modelValue="handleStatusChange"
							:options="['Open', 'Working', 'Pending Review', 'Overdue', 'Completed', 'Cancelled']"
							class="w-full"
						/>
					</div>
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Priority</label>
						<PrioritySlider v-model="doc.priority" @update:modelValue="save" />
					</div>
				</div>

				<!-- Type + Project row -->
				<div class="grid grid-cols-2 gap-2">
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Type</label>
						<LinkField
							:model-value="doc.type || ''"
							@update:model-value="(v: string) => { doc.type = v; save() }"
							placeholder="Bug, Feature..."
							search-method="taskist.api.search_task_types"
							create-method="taskist.api.create_task_type"
							:allow-create="true"
						/>
					</div>
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Project</label>
						<LinkField
							:model-value="doc.project || ''"
							@update:model-value="(v: string) => { doc.project = v; save() }"
							placeholder="Select project..."
							search-method="taskist.api.search_projects"
						/>
					</div>
				</div>

				<!-- Dates row -->
				<div class="grid grid-cols-2 gap-2">
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Start</label>
						<DatetimePicker
							:model-value="doc.exp_start_date || ''"
							@update:model-value="(v: string) => { doc.exp_start_date = v; debouncedSave() }"
							placeholder="Start date/time"
							input-class="w-full border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-xs bg-white dark:bg-gray-700 dark:text-gray-200"
						/>
					</div>
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">End</label>
						<DatetimePicker
							:model-value="doc.exp_end_date || ''"
							@update:model-value="(v: string) => { doc.exp_end_date = v; debouncedSave() }"
							placeholder="End date/time"
							input-class="w-full border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-xs bg-white dark:bg-gray-700 dark:text-gray-200"
						/>
					</div>
				</div>

				<!-- Hours + Progress row -->
				<div class="grid grid-cols-3 gap-2">
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Est. Hrs</label>
						<input v-model.number="doc.expected_time" @change="save" type="number" min="0" step="0.5" class="w-full border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-xs bg-white dark:bg-gray-700 dark:text-gray-200" />
					</div>
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Actual</label>
						<input :value="doc.actual_time || 0" disabled class="w-full border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-xs bg-gray-50 dark:bg-gray-700/50 dark:text-gray-400 cursor-not-allowed" />
					</div>
					<div>
						<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">{{ doc.progress || 0 }}%</label>
						<input v-model.number="doc.progress" @change="save" type="range" min="0" max="100" step="10" class="w-full mt-1" />
					</div>
				</div>

				<!-- Color, Flags & Recurrence inline -->
				<div class="flex items-center gap-3 flex-wrap">
					<div class="flex items-center gap-1.5">
						<input v-model="doc.color" @change="save" type="color" class="w-5 h-5 rounded border border-gray-200 dark:border-gray-600 cursor-pointer bg-transparent" />
						<button v-if="doc.color" @click="doc.color = ''; save()" class="text-[10px] text-gray-400 hover:text-red-500">clear</button>
					</div>
					<FrappeCheckbox
						:model-value="!!doc.is_milestone"
						@update:model-value="(v: boolean) => { doc.is_milestone = v ? 1 : 0; save() }"
						label="Milestone"
					/>
					<FrappeCheckbox
						:model-value="!!doc.is_group"
						@update:model-value="(v: boolean) => { doc.is_group = v ? 1 : 0; save() }"
						label="Group"
					/>
					<RecurrenceEditor
						:model-value="doc.taskist_recurrence_rule || ''"
						:is-recurring="!!doc.taskist_is_recurring"
						@update:model-value="(v: string) => { doc.taskist_recurrence_rule = v; save() }"
						@update:is-recurring="(v: boolean) => { doc.taskist_is_recurring = v ? 1 : 0; save() }"
					/>
				</div>

				<!-- Description -->
				<div>
					<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">Description</label>
					<FrappeTextarea v-model="doc.description" @blur="save" :rows="2" placeholder="Add a description..." />
				</div>

				<!-- Assignees -->
				<div>
					<label class="block text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-1">
						Assigned To
						<button @click="assignToMe" class="ml-1 text-blue-500 hover:text-blue-700 dark:hover:text-blue-300 hover:underline">(assign to me)</button>
					</label>
					<div v-if="assignees.length" class="flex flex-wrap gap-1 mb-1.5">
						<div
							v-for="assignee in assignees"
							:key="assignee.email"
							class="flex items-center gap-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full pl-1 pr-0.5 py-0.5 text-[11px]"
						>
							<Avatar :label="assignee.full_name" size="xs" />
							<span class="px-1">{{ assignee.full_name }}</span>
							<button @click="removeAssignee(assignee.email)" class="p-0.5 rounded-full hover:bg-blue-200 dark:hover:bg-blue-800">
								<FeatherIcon name="x" class="w-2.5 h-2.5" />
							</button>
						</div>
					</div>
					<div class="relative">
						<input
							v-model="userSearch"
							@input="searchUsers"
							@focus="showUserDropdown = true"
							type="text"
							placeholder="Search users..."
							class="w-full border border-gray-200 dark:border-gray-600 rounded px-2.5 py-1 text-xs bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400"
						/>
						<div
							v-if="showUserDropdown && userResults.length"
							class="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-10 max-h-32 overflow-auto"
						>
							<button
								v-for="user in userResults"
								:key="user.name"
								@mousedown.prevent="addAssignee(user.name)"
								class="w-full text-left px-2.5 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-200 flex items-center gap-2"
							>
								<Avatar :label="user.full_name || user.name" size="xs" />
								<div class="truncate">
									<span class="font-medium">{{ user.full_name || user.name }}</span>
									<span v-if="user.full_name" class="text-gray-400 dark:text-gray-500 ml-1">{{ user.name }}</span>
								</div>
							</button>
						</div>
					</div>
				</div>

				<!-- Attachments -->
				<TaskAttachments v-if="doc.name" :task-name="doc.name" />

				<!-- Parent Task -->
				<div v-if="doc.parent_task" class="flex items-center gap-1.5 px-2 py-1.5 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
					<FeatherIcon name="corner-up-left" class="w-3.5 h-3.5 text-purple-500 flex-shrink-0" />
					<span class="text-[11px] text-gray-500 dark:text-gray-400">Parent:</span>
					<button
						@click="taskStore.selectTask({ name: doc.parent_task } as any)"
						class="text-[11px] font-medium text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-300 hover:underline truncate"
					>
						{{ doc.parent_task }}
					</button>
				</div>

				<!-- Subtasks -->
				<div>
					<div class="flex items-center justify-between mb-1">
						<h3 class="text-[11px] font-medium text-gray-400 dark:text-gray-500">Subtasks</h3>
						<button @click="showSubtaskAdd = true" class="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400" title="Add subtask">
							<FeatherIcon name="plus" class="w-3.5 h-3.5" />
						</button>
					</div>
					<div v-if="showSubtaskAdd" class="mb-1.5 flex gap-1.5">
						<input
							ref="subtaskInput"
							v-model="subtaskSubject"
							@keydown.enter="createSubtask"
							@keydown.escape="showSubtaskAdd = false"
							type="text"
							placeholder="Subtask name..."
							class="flex-1 border border-gray-200 dark:border-gray-600 rounded px-2.5 py-1 text-xs bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
						/>
						<Button @click="createSubtask" :disabled="!subtaskSubject.trim()" size="sm" variant="solid" theme="blue" label="Add" />
					</div>
					<div v-if="childTasks.length" class="space-y-0.5">
						<div
							v-for="child in childTasks"
							:key="child.name"
							@click="taskStore.selectTask(child)"
							class="flex items-center gap-1.5 px-1.5 py-1 rounded hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer text-xs"
						>
							<div class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="childPriorityColor(child.priority)"></div>
							<FeatherIcon v-if="child.is_group" name="folder" class="w-3 h-3 text-blue-500 flex-shrink-0" />
							<span class="truncate" :class="child.status === 'Completed' ? 'text-gray-400 line-through' : 'text-gray-700 dark:text-gray-300'">{{ child.subject }}</span>
							<FeatherIcon v-if="child.status === 'Completed'" name="check" class="w-3 h-3 text-green-500 ml-auto flex-shrink-0" />
						</div>
					</div>
					<div v-else-if="!showSubtaskAdd" class="text-[11px] text-gray-400 dark:text-gray-500">No subtasks</div>
				</div>

				<!-- Activity timeline -->
				<div>
					<div class="flex items-center justify-between mb-2">
						<h3 class="text-[11px] font-medium text-gray-400 dark:text-gray-500">Activity</h3>
						<a
							:href="auditReportUrl"
							target="_blank"
							class="text-[11px] text-blue-500 hover:text-blue-700 dark:hover:text-blue-300"
						>
							Audit report
						</a>
					</div>
					<div class="grid grid-cols-4 border-y border-gray-100 dark:border-gray-700 py-2 mb-3">
						<div v-for="metric in timelineMetricItems" :key="metric.label" class="min-w-0 px-1 text-center">
							<div class="text-xs font-semibold text-gray-700 dark:text-gray-200 truncate">{{ formatDuration(metric.value) }}</div>
							<div class="text-[10px] text-gray-400 dark:text-gray-500">{{ metric.label }}</div>
						</div>
					</div>
					<div v-if="timelineEvents.length" class="relative ml-1">
						<div class="absolute left-[5px] top-1 bottom-1 w-px bg-gray-200 dark:bg-gray-700"></div>
						<div v-for="event in timelineEvents" :key="event.name" class="relative flex gap-2.5 pb-3 last:pb-0">
							<div class="relative z-10 mt-1 h-[11px] w-[11px] rounded-full border-2 border-white dark:border-gray-800 flex-shrink-0" :class="eventDotClass(event.event_type)"></div>
							<div class="min-w-0 flex-1">
								<div class="flex items-baseline justify-between gap-2">
									<span class="text-xs font-medium text-gray-700 dark:text-gray-200">{{ event.event_type }}</span>
									<span class="text-[10px] text-gray-400 flex-shrink-0">{{ formatTime(event.event_time) }}</span>
								</div>
								<div v-if="event.notes" class="text-[11px] text-gray-500 dark:text-gray-400 whitespace-pre-line">{{ event.notes }}</div>
								<div v-if="event.previous_value || event.new_value" class="text-[10px] text-gray-400 dark:text-gray-500 truncate">
									<span v-if="event.previous_value">{{ event.previous_value }}</span>
									<span v-if="event.previous_value && event.new_value"> -> </span>
									<span v-if="event.new_value">{{ event.new_value }}</span>
								</div>
								<div v-if="event.actor" class="text-[10px] text-gray-400 dark:text-gray-500">{{ event.actor }}</div>
							</div>
						</div>
					</div>
					<div v-else class="text-[11px] text-gray-400 dark:text-gray-500">No recorded activity yet</div>
				</div>

				<!-- Comments -->
				<div>
					<h3 class="text-[11px] font-medium text-gray-400 dark:text-gray-500 mb-1">Comments</h3>
					<div class="space-y-2">
						<div v-for="comment in comments" :key="comment.name" class="bg-gray-50 dark:bg-gray-700/50 rounded p-2">
							<div class="flex items-center gap-1.5 mb-0.5">
								<span class="text-[11px] font-medium text-gray-700 dark:text-gray-300">{{ comment.comment_by }}</span>
								<span class="text-[10px] text-gray-400">{{ formatTime(comment.creation) }}</span>
							</div>
							<div class="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-line">{{ plainText(comment.content) }}</div>
						</div>
					</div>
					<div class="mt-2 flex gap-1.5">
						<input v-model="newComment" @keydown.enter="addComment" type="text" placeholder="Add a comment..." class="flex-1 border border-gray-200 dark:border-gray-600 rounded px-2.5 py-1 text-xs bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400" />
						<Button @click="addComment" size="sm" variant="solid" theme="blue" label="Send" :disabled="!newComment.trim()" />
					</div>
				</div>
			</div>

			<div v-else class="flex-1 flex items-center justify-center">
				<LoadingIndicator class="w-6 h-6" />
			</div>
		</div>
	</transition>

	<div
		v-if="delayDialogMode"
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
		@click.self="closeDelayDialog"
	>
		<div class="w-full max-w-md rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-xl p-4 space-y-3">
			<h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
				{{ delayDialogTitle }}
			</h3>
			<input
				v-if="delayDialogMode === 'extension'"
				v-model="requestedDueAt"
				type="datetime-local"
				class="w-full border border-gray-200 dark:border-gray-600 rounded px-2.5 py-2 text-sm bg-white dark:bg-gray-700 dark:text-gray-200"
			/>
			<select
				v-model="selectedDelayReason"
				class="w-full border border-gray-200 dark:border-gray-600 rounded px-2.5 py-2 text-sm bg-white dark:bg-gray-700 dark:text-gray-200"
			>
				<option value="" disabled>Select delay reason</option>
				<option v-for="reason in delayReasons" :key="reason.name" :value="reason.name">
					{{ reason.name }} · {{ reason.responsible_party }}
				</option>
			</select>
			<textarea
				v-model="delayNotes"
				rows="4"
				placeholder="Explain what caused the delay and the next action."
				class="w-full border border-gray-200 dark:border-gray-600 rounded px-2.5 py-2 text-sm bg-white dark:bg-gray-700 dark:text-gray-200"
			></textarea>
			<p v-if="selectedReasonRequiresEvidence" class="text-xs text-amber-600 dark:text-amber-400">
				This reason requires a file in the Task attachments section.
			</p>
			<div class="flex justify-end gap-2">
				<Button @click="closeDelayDialog" size="sm" variant="ghost" label="Cancel" />
				<Button
					@click="confirmDelayAction"
					:disabled="!selectedDelayReason || !delayNotes.trim() || (delayDialogMode === 'extension' && !requestedDueAt)"
					size="sm"
					variant="solid"
					theme="blue"
					:label="delayDialogActionLabel"
				/>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useTaskStore } from '@/stores/taskStore'
import { getDoc, call } from '@/data/api'
import { documentUrl } from '@/utils/frappeRoute'
import { countdownLabel, countdownTheme, slaLabel, slaTheme } from '@/utils/sla'
import { useMinuteNow } from '@/composables/useMinuteNow'
import PrioritySlider from '@/components/common/PrioritySlider.vue'
import RecurrenceEditor from '@/components/common/RecurrenceEditor.vue'
import LinkField from '@/components/common/LinkField.vue'
import TaskAttachments from '@/components/task/TaskAttachments.vue'
import DatetimePicker from '@/components/common/DatetimePicker.vue'
import dayjs from 'dayjs'

const taskStore = useTaskStore()
const now = useMinuteNow()
const doc = ref<any>(null)
const saveError = ref('')
const queueWarning = ref('')
const comments = ref<any[]>([])
const slaTrackers = ref<any[]>([])
const timeline = ref<{ events: any[]; metrics: Record<string, number> }>({
	events: [],
	metrics: { active_minutes: 0, waiting_minutes: 0, paused_minutes: 0, handoff_minutes: 0 },
})
const processChain = ref<any>(null)
const pauseState = ref<any>(null)
const extensionState = ref<any>(null)
const delayDialogMode = ref<'completion' | 'pause' | 'extension' | 'rework' | null>(null)
const delayReasons = ref<any[]>([])
const selectedDelayReason = ref('')
const delayNotes = ref('')
const requestedDueAt = ref('')
const pendingStatus = ref('')
const newComment = ref('')
const assignees = ref<Array<{ email: string; full_name: string }>>([])
const userSearch = ref('')
const userResults = ref<Array<{ name: string; full_name: string }>>([])
const showUserDropdown = ref(false)
const childTasks = ref<any[]>([])
const showSubtaskAdd = ref(false)
const subtaskSubject = ref('')
const subtaskInput = ref<HTMLInputElement | null>(null)

const isCompleted = computed(() => doc.value && doc.value.status === 'Completed')
const hasBreachedSla = computed(() => slaTrackers.value.some(sla => sla.status === 'Breached'))
const selectedReasonRequiresEvidence = computed(() => {
	const reason = delayReasons.value.find(item => item.name === selectedDelayReason.value)
	return !!reason?.evidence_required
})
const delayDialogTitle = computed(() => ({
	completion: 'Explain SLA Delay',
	pause: 'Request SLA Pause',
	extension: 'Request SLA Extension',
	rework: 'Return Work for Correction',
}[delayDialogMode.value || 'completion']))
const delayDialogActionLabel = computed(() => ({
	completion: 'Complete Task',
	pause: 'Request Pause',
	extension: 'Request Extension',
	rework: 'Return Task',
}[delayDialogMode.value || 'completion']))
const sourceUrl = computed(() => documentUrl(doc.value?.taskist_reference_doctype, doc.value?.taskist_reference_name))
const taskCountdownDeadline = computed(() => {
	const firstTracker = slaTrackers.value?.[0]
	return firstTracker?.due_at || doc.value?.exp_end_date || ''
})
const taskCountdown = computed(() => {
	if (!doc.value || !taskCountdownDeadline.value || ['Completed', 'Cancelled'].includes(doc.value.status)) return ''
	return countdownLabel(taskCountdownDeadline.value, now.value)
})
const taskCountdownClass = computed(() => countdownTheme(taskCountdownDeadline.value, now.value))
const taskCountdownTarget = computed(() => {
	if (!taskCountdownDeadline.value) return ''
	return `Due ${dayjs(taskCountdownDeadline.value).format('MMM D, h:mm A')}`
})
const auditReportUrl = computed(() => {
	const task = encodeURIComponent(doc.value?.name || '')
	return `/app/query-report/Taskist%20SLA%20Audit%20Timeline?task=${task}`
})
const timelineEvents = computed(() => [...(timeline.value.events || [])].reverse())
const timelineMetricItems = computed(() => [
	{ label: 'Active', value: timeline.value.metrics?.active_minutes || 0 },
	{ label: 'Waiting', value: timeline.value.metrics?.waiting_minutes || 0 },
	{ label: 'Paused', value: timeline.value.metrics?.paused_minutes || 0 },
	{ label: 'Handoff', value: timeline.value.metrics?.handoff_minutes || 0 },
])
const checklistItems = computed<any[]>(() => {
	try {
		return JSON.parse(doc.value?.taskist_checklist_json || '[]')
	} catch {
		return []
	}
})

watch(() => taskStore.selectedTask, async (task) => {
	if (!task) { doc.value = null; return }
	try {
		doc.value = await call('taskist.api.get_task', { task_name: task.name })
		await Promise.all([
			loadComments(),
			loadAssignees(),
			loadChildTasks(),
			loadSlaTrackers(),
			loadPauseState(),
			loadExtensionState(),
			loadTimeline(),
			loadProcessChain(),
		])
	} catch (e) {
		console.error('Failed to load task:', e)
	}
}, { immediate: true })

let saveTimeout: ReturnType<typeof setTimeout> | null = null

function debouncedSave() {
	if (saveTimeout) clearTimeout(saveTimeout)
	saveTimeout = setTimeout(save, 300)
}

async function save() {
	if (!doc.value) return
	saveError.value = ''
	try {
		const saved = await call('taskist.api.save_task', { doc: doc.value })
		if (saved && doc.value) {
			Object.assign(doc.value, {
				modified: saved.modified,
				docstatus: saved.docstatus,
				_assign: saved._assign,
			})
		}
		await Promise.all([taskStore.fetchTasks(), loadTimeline(), loadProcessChain()])
	} catch (e: any) {
		const msg = e?.message || 'Failed to save'
		saveError.value = msg
		console.error('Failed to save:', msg)
		if (doc.value?.name) {
			try {
				const fresh = await call('taskist.api.get_task', { task_name: doc.value.name })
				if (fresh) doc.value = fresh
			} catch { /* keep current state if reload also fails */ }
		}
	}
}

async function loadComments() {
	if (!doc.value) return
	try {
		comments.value = await call('taskist.api.get_task_comments', { task_name: doc.value.name }) || []
	} catch { comments.value = [] }
}

async function loadSlaTrackers() {
	if (!doc.value) return
	try {
		slaTrackers.value = await call('taskist.api.get_task_sla', { task_name: doc.value.name }) || []
	} catch { slaTrackers.value = [] }
}

async function loadPauseState() {
	if (!doc.value) return
	try {
		pauseState.value = await call('taskist.delay.get_task_pause_state', { task_name: doc.value.name })
	} catch { pauseState.value = null }
}

async function loadExtensionState() {
	if (!doc.value) return
	try {
		extensionState.value = await call('taskist.delay.get_task_extension_state', { task_name: doc.value.name })
	} catch { extensionState.value = null }
}

async function loadTimeline() {
	if (!doc.value) return
	try {
		timeline.value = await call('taskist.events.get_task_timeline', { task_name: doc.value.name }) || {
			events: [],
			metrics: {},
		}
	} catch {
		timeline.value = { events: [], metrics: {} }
	}
}

async function loadProcessChain() {
	if (!doc.value?.taskist_process_rule) {
		processChain.value = null
		return
	}
	try {
		processChain.value = await call('taskist.process.get_process_chain', { task_name: doc.value.name })
	} catch {
		processChain.value = null
	}
}

async function toggleChecklistItem(index: number) {
	if (!doc.value) return
	const items = checklistItems.value.map((item, itemIndex) => ({
		...item,
		completed: itemIndex === index ? (item.completed ? 0 : 1) : (item.completed ? 1 : 0),
	}))
	try {
		const updated = await call('taskist.process.update_task_checklist', {
			task_name: doc.value.name,
			items,
		})
		doc.value.taskist_checklist_json = JSON.stringify(updated || [])
		await loadTimeline()
	} catch (e: any) {
		saveError.value = e?.message || 'Could not update checklist'
	}
}

async function approveOutput() {
	if (!doc.value) return
	try {
		await call('taskist.process.approve_task_output', { task_name: doc.value.name })
		doc.value = await call('taskist.api.get_task', { task_name: doc.value.name })
		await Promise.all([loadProcessChain(), loadTimeline()])
	} catch (e: any) {
		saveError.value = e?.message || 'Could not approve output'
	}
}

async function addComment() {
	if (!newComment.value.trim() || !doc.value) return
	try {
		await call('taskist.api.add_task_comment', { task_name: doc.value.name, content: newComment.value.trim() })
		newComment.value = ''
		await Promise.all([loadComments(), loadTimeline()])
	} catch (e) {
		console.error('Failed to add comment:', e)
	}
}

async function loadAssignees() {
	if (!doc.value) return
	try {
		const assignStr = doc.value._assign
		if (!assignStr) { assignees.value = []; return }
		const emails = JSON.parse(assignStr)
		assignees.value = emails.map((email: string) => ({ email, full_name: email.split('@')[0] }))
		for (const a of assignees.value) {
			try {
				const user = await getDoc('User', a.email)
				if (user?.full_name) a.full_name = user.full_name
			} catch { /* keep email as fallback */ }
		}
	} catch { assignees.value = [] }
}

let searchTimeout: ReturnType<typeof setTimeout> | null = null

function searchUsers() {
	showUserDropdown.value = true
	if (searchTimeout) clearTimeout(searchTimeout)
	searchTimeout = setTimeout(async () => {
		if (!userSearch.value.trim()) { userResults.value = []; return }
		try {
			userResults.value = await call('taskist.api.search_users', { query: userSearch.value })
		} catch { userResults.value = [] }
	}, 200)
}

async function assignToMe() {
	if (!doc.value) return
	try {
		const user = await call('frappe.auth.get_logged_user')
		if (user && !assignees.value.some(a => a.email === user)) {
			await addAssignee(user)
		}
	} catch (e) {
		console.error('Failed to get current user:', e)
	}
}

async function addAssignee(email: string) {
	if (!doc.value) return
	showUserDropdown.value = false
	userSearch.value = ''
	userResults.value = []
	try {
		const result = await call('taskist.api.assign_task', { task_name: doc.value.name, user: email })
		assignees.value = result || []
		queueWarning.value = ''
		await loadQueueAdvisory(email)
		await Promise.all([taskStore.fetchTasks(), loadTimeline()])
	} catch (e) {
		console.error('Failed to assign:', e)
	}
}

async function loadQueueAdvisory(email: string) {
	if (!doc.value) return
	try {
		const advisory = await call('taskist.queue.get_queue_advisory', {
			user: email,
			proposed_start: doc.value.exp_start_date || doc.value._sla_start_time || undefined,
			proposed_end: doc.value.exp_end_date || undefined,
			exclude_task: doc.value.name,
		})
		if (advisory && !advisory.available) {
			queueWarning.value = `${email} already has ${advisory.overlap_count} active task(s) in that window. Suggested start: ${dayjs(advisory.next_available_from).format('MMM D, h:mm A')}.`
		}
	} catch {
		// Queue advice should never block assignment.
	}
}

async function removeAssignee(email: string) {
	if (!doc.value) return
	try {
		const result = await call('taskist.api.unassign_task', { task_name: doc.value.name, user: email })
		assignees.value = result || []
		await Promise.all([taskStore.fetchTasks(), loadTimeline()])
	} catch (e) {
		console.error('Failed to unassign:', e)
	}
}

async function markCompleted() {
	if (!doc.value) return
	if (isCompleted.value) {
		doc.value.status = 'Open'
		await save()
		return
	}
	if (hasBreachedSla.value) {
		await openDelayDialog('completion')
		return
	}
	doc.value.status = 'Completed'
	await save()
}

async function acknowledgeTask() {
	if (!doc.value) return
	doc.value.status = 'Working'
	await save()
}

async function handleStatusChange(status: string) {
	if (!doc.value) return
	if (doc.value.status === 'Pending Review' && ['Open', 'Working'].includes(status)) {
		pendingStatus.value = status
		await openDelayDialog('rework')
		return
	}
	if (status === 'Completed' && hasBreachedSla.value) {
		await openDelayDialog('completion')
		return
	}
	doc.value.status = status
	await save()
}

async function openDelayDialog(mode: 'completion' | 'pause' | 'extension' | 'rework') {
	delayDialogMode.value = mode
	selectedDelayReason.value = ''
	delayNotes.value = ''
	requestedDueAt.value = mode === 'extension' && extensionState.value?.current_due_at
		? dayjs(extensionState.value.current_due_at).add(1, 'hour').format('YYYY-MM-DDTHH:mm')
		: ''
	try {
		delayReasons.value = await call('taskist.delay.get_delay_reasons', {
			pause_eligible: mode === 'pause' ? 1 : undefined,
		}) || []
	} catch {
		delayReasons.value = []
	}
}

function closeDelayDialog() {
	delayDialogMode.value = null
	selectedDelayReason.value = ''
	delayNotes.value = ''
	requestedDueAt.value = ''
	pendingStatus.value = ''
}

async function confirmDelayAction() {
	if (!doc.value || !delayDialogMode.value) return
	saveError.value = ''
	try {
		if (delayDialogMode.value === 'completion') {
			await call('taskist.api.update_task_status', {
				task_name: doc.value.name,
				status: 'Completed',
				delay_reason: selectedDelayReason.value,
				delay_notes: delayNotes.value.trim(),
			})
			doc.value.status = 'Completed'
			await Promise.all([
				loadSlaTrackers(),
				loadPauseState(),
				loadExtensionState(),
				loadProcessChain(),
				taskStore.fetchTasks(),
			])
		} else if (delayDialogMode.value === 'pause') {
			pauseState.value = await call('taskist.delay.request_sla_pause', {
				task_name: doc.value.name,
				delay_reason: selectedDelayReason.value,
				notes: delayNotes.value.trim(),
			})
			await loadSlaTrackers()
		} else if (delayDialogMode.value === 'extension') {
			extensionState.value = await call('taskist.delay.request_sla_extension', {
				task_name: doc.value.name,
				requested_due_at: requestedDueAt.value.replace('T', ' '),
				delay_reason: selectedDelayReason.value,
				notes: delayNotes.value.trim(),
			})
		} else {
			if (processChain.value?.rework_available) {
				const result = await call('taskist.process.request_process_rework', {
					task_name: doc.value.name,
					delay_reason: selectedDelayReason.value,
					notes: delayNotes.value.trim(),
				})
				closeDelayDialog()
				await taskStore.fetchTasks()
				if (result?.rework_task) {
					taskStore.selectTask({ name: result.rework_task } as any)
				}
				return
			}
			await call('taskist.api.update_task_status', {
				task_name: doc.value.name,
				status: pendingStatus.value,
				delay_reason: selectedDelayReason.value,
				delay_notes: delayNotes.value.trim(),
			})
			doc.value.status = pendingStatus.value
			await Promise.all([loadSlaTrackers(), taskStore.fetchTasks()])
		}
		await loadTimeline()
		closeDelayDialog()
	} catch (e: any) {
		saveError.value = e?.message || 'Could not update SLA'
	}
}

async function resumeSla() {
	if (!doc.value) return
	try {
		pauseState.value = await call('taskist.delay.resume_sla', { task_name: doc.value.name })
		await loadSlaTrackers()
		await Promise.all([taskStore.fetchTasks(), loadTimeline()])
	} catch (e: any) {
		saveError.value = e?.message || 'Could not resume SLA'
	}
}

async function loadChildTasks() {
	if (!doc.value) { childTasks.value = []; return }
	try {
		childTasks.value = await call('taskist.api.get_child_tasks', { parent_task: doc.value.name })
	} catch { childTasks.value = [] }
}

async function createSubtask() {
	if (!subtaskSubject.value.trim() || !doc.value) return
	try {
		await taskStore.quickCreate({
			subject: subtaskSubject.value.trim(),
			parent_task: doc.value.name,
			project: doc.value.project || undefined,
			priority: 'Medium',
		})
		subtaskSubject.value = ''
		showSubtaskAdd.value = false
		await loadChildTasks()
	} catch (e) {
		console.error('Failed to create subtask:', e)
	}
}

function childPriorityColor(priority: string) {
	const colors: Record<string, string> = { High: 'bg-orange-500', Medium: 'bg-yellow-500', Low: 'bg-green-500' }
	return colors[priority] || 'bg-gray-400'
}

function formatTime(dt: string) {
	return dayjs(dt).format('MMM D, h:mm A')
}

function formatDuration(minutes: number) {
	if (!minutes) return '0m'
	if (minutes < 60) return `${minutes}m`
	const hours = Math.floor(minutes / 60)
	const remainder = minutes % 60
	if (hours < 24) return remainder ? `${hours}h ${remainder}m` : `${hours}h`
	const days = Math.floor(hours / 24)
	const remainingHours = hours % 24
	return remainingHours ? `${days}d ${remainingHours}h` : `${days}d`
}

function eventDotClass(eventType: string) {
	if (['Completed', 'Acknowledged'].includes(eventType)) return 'bg-green-500'
	if (['Cancelled', 'Breached', 'Response Breached', 'Notification Failed'].includes(eventType)) return 'bg-red-500'
	if (['Warning', 'Escalated', 'Manual Escalation', 'Pause Requested', 'Extension Requested'].includes(eventType)) return 'bg-amber-500'
	if (['Paused', 'Resumed', 'Extension Approved'].includes(eventType)) return 'bg-blue-500'
	if (['Assigned', 'Reassigned', 'Started', 'Reopened'].includes(eventType)) return 'bg-indigo-500'
	return 'bg-gray-400'
}

function stageStatusClass(status: string) {
	if (status === 'Completed') return 'text-green-600 dark:text-green-400'
	if (status === 'Cancelled') return 'text-red-500 dark:text-red-400'
	if (status === 'Working') return 'text-blue-600 dark:text-blue-400'
	return 'text-gray-400'
}

function plainText(html: string | null | undefined) {
	if (!html) return ''
	const el = document.createElement('div')
	el.innerHTML = html
	return el.textContent || el.innerText || ''
}
</script>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: transform 0.2s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
