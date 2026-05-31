<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  CalendarDays,
  Clock3,
  ExternalLink,
  FileText,
  ListFilter,
  PlayCircle,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  Users,
} from "lucide-vue-next";

import { api } from "@/api/client";
import type { AskResponse, MeetingSummary } from "@/api/types";
import ClarificationDecisionDialog from "@/components/ClarificationDecisionDialog.vue";
import { useAppStore } from "@/stores/app";
import { usePollingStore } from "@/stores/polling";
import { startClarificationDirectDispatch } from "@/utils/clarificationDispatch";
import { formatDate, shortId } from "@/utils/format";

const appStore = useAppStore();
const pollingStore = usePollingStore();
const LOCKED_REANALYSIS_DRAFT_STATUSES = new Set(["confirmed", "dispatching", "completed", "failed"]);
const reanalysisDisabledMessage =
  "This meeting has already been confirmed or dispatched. Re-analysis is disabled to avoid duplicate external tasks.";

const searchText = ref("");
const statusFilter = ref("");
const sourceFilter = ref("");
const activeTab = ref<"draft" | "summary" | "transcript">("draft");
const askQuestion = ref("");
const askResult = ref<AskResponse | null>(null);
const askLoading = ref(false);
const actionMessage = ref("");
const actionError = ref("");
const showClarificationDialog = ref(false);

const selectedDraft = computed(() => appStore.selectedMeeting?.analysis_draft ?? null);
const isReanalysisLocked = computed(() => {
  const status = selectedDraft.value?.status;
  return status !== undefined && LOCKED_REANALYSIS_DRAFT_STATUSES.has(status);
});

const filteredMeetings = computed(() => {
  const keyword = searchText.value.trim().toLowerCase();
  return appStore.meetings.filter((meeting) => {
    const title = meeting.title?.toLowerCase() ?? "";
    const preview = meeting.content_preview?.toLowerCase() ?? "";
    const matchesKeyword = !keyword || title.includes(keyword) || preview.includes(keyword);
    const matchesSource = !sourceFilter.value || meeting.source_type === sourceFilter.value;
    return matchesKeyword && matchesSource;
  });
});

const actionItems = computed(() => selectedDraft.value?.action_items ?? []);
const decisions = computed(() => selectedDraft.value?.decisions ?? []);
const riskItems = computed(() => selectedDraft.value?.risk_items ?? []);
const unconfirmedItems = computed(() => selectedDraft.value?.unconfirmed_items ?? []);
const latestWorkflows = computed(() => appStore.workflows.slice(0, 6));
const unreadReminders = computed(() => appStore.reminders.slice(0, 3));
const clarificationWorkflow = computed(() => {
  const draftId = selectedDraft.value?.id;
  if (!draftId) {
    return null;
  }
  return (
    appStore.workflows.find((workflow) => {
      const payloadDraftId = workflow.payload_json?.draft_id;
      return (
        payloadDraftId === draftId &&
        (workflow.status === "waiting_clarification" ||
          workflow.current_node === "wait_for_clarification")
      );
    }) ?? null
  );
});

onMounted(async () => {
  await Promise.all([appStore.refreshHealth(), refreshMeetings(), appStore.loadReminders()]);
  if (!appStore.selectedMeeting && appStore.meetings[0]) {
    await selectMeeting(appStore.meetings[0]);
  }
});

async function refreshMeetings() {
  await appStore.loadMeetings(statusFilter.value);
}

async function selectMeeting(meeting: MeetingSummary) {
  actionMessage.value = "";
  actionError.value = "";
  askResult.value = null;
  await appStore.loadMeeting(meeting.id);
}

async function analyzeSelectedMeeting() {
  if (!appStore.selectedMeeting) {
    return;
  }
  actionError.value = "";
  if (isReanalysisLocked.value) {
    actionError.value = reanalysisDisabledMessage;
    return;
  }
  try {
    const response = await api.analyzeMeeting(appStore.selectedMeeting.id);
    pollingStore.start(response.workflow_run_id);
    await appStore.loadWorkflows(appStore.selectedMeeting.id);
    actionMessage.value = "Analysis task queued. Trace will refresh while the worker runs.";
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  }
}

async function confirmCurrentDraft() {
  const draft = selectedDraft.value;
  if (!draft || !appStore.selectedMeeting) {
    return;
  }
  if (clarificationWorkflow.value) {
    showClarificationDialog.value = true;
    return;
  }
  await queueDraftConfirmation();
}

async function queueDraftConfirmation() {
  const draft = selectedDraft.value;
  if (!draft || !appStore.selectedMeeting) {
    return;
  }
  const response = await api.confirmDraft(draft.id);
  pollingStore.start(response.workflow_run_id);
  await appStore.loadMeeting(appStore.selectedMeeting.id);
  await appStore.loadReminders();
  actionMessage.value = "Draft confirmation queued. Trace will continue from confirm_draft.";
}

function keepEditingClarifications() {
  showClarificationDialog.value = false;
  activeTab.value = "draft";
  actionMessage.value = "请先补充待澄清信息，保存后可重新抽取或再次确认草稿。";
}

function forceContinueAndDispatch() {
  const workflow = clarificationWorkflow.value;
  const draft = selectedDraft.value;
  const meeting = appStore.selectedMeeting;
  if (!workflow || !draft || !meeting) {
    return;
  }

  showClarificationDialog.value = false;
  actionError.value = "";
  startClarificationDirectDispatch({
    workflowRunId: workflow.id,
    draftId: draft.id,
    onProgress: (message) => {
      actionMessage.value = message;
    },
    onForceContinueQueued: (response) => {
      pollingStore.start(response.workflow_run_id);
    },
    onReadyForConfirmation: async () => {
      await appStore.loadWorkflows(meeting.id);
    },
    onConfirmQueued: (response) => {
      pollingStore.start(response.workflow_run_id);
    },
    onComplete: async () => {
      await appStore.loadMeeting(meeting.id);
      await appStore.loadReminders();
    },
    onError: (error) => {
      actionError.value = error instanceof Error ? error.message : String(error);
    },
  });
}

async function dispatchCurrentDraft() {
  const draft = selectedDraft.value;
  if (!draft || !appStore.selectedMeeting) {
    return;
  }
  const response = await api.dispatchDraft(draft.id);
  pollingStore.start(response.workflow_run_id);
  await appStore.loadWorkflows(appStore.selectedMeeting.id);
  actionMessage.value = "Dispatch task queued.";
}

async function deleteSelectedMeeting() {
  const meeting = appStore.selectedMeeting;
  if (!meeting) {
    return;
  }
  const title = meeting.title || meeting.id;
  const confirmed = window.confirm(`Delete meeting "${title}"? This cannot be undone.`);
  if (!confirmed) {
    return;
  }
  actionMessage.value = "";
  actionError.value = "";
  try {
    await appStore.deleteMeeting(meeting.id);
    await refreshMeetings();
    await appStore.loadReminders();
    if (appStore.meetings[0]) {
      await selectMeeting(appStore.meetings[0]);
    }
    actionMessage.value = "Meeting deleted.";
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  }
}

async function askSelectedMeeting() {
  if (!appStore.selectedMeeting || !askQuestion.value.trim()) {
    return;
  }
  askLoading.value = true;
  askResult.value = null;
  try {
    askResult.value = await api.askMeeting(appStore.selectedMeeting.id, askQuestion.value.trim(), 5);
  } finally {
    askLoading.value = false;
  }
}

function sourceLabel(meeting: MeetingSummary) {
  return meeting.source_type === "markdown" ? "Markdown" : meeting.source_type;
}

function priorityLabel(priority: string | null) {
  return priority ?? "medium";
}

function citationText(citation: Record<string, unknown>) {
  if (citation.source_type === "audio") {
    return `录音 ${formatAudioTime(citation.start_time)}-${formatAudioTime(citation.end_time)}：${String(citation.text ?? citation.source_excerpt ?? "")}`;
  }
  if (citation.source_type === "image") {
    return `图片 OCR 来源：${String(citation.text ?? citation.source_excerpt ?? "")}`;
  }
  return String(citation.text ?? citation.source_excerpt ?? citation.chunk_type ?? "source");
}

function formatAudioTime(value: unknown) {
  if (typeof value !== "number") {
    return "??:??";
  }
  const total = Math.floor(value);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
</script>

<template>
  <section class="meeting-workbench">
    <aside class="meeting-list-card">
      <div class="card-heading">
        <div>
          <h1>Meetings</h1>
          <p>{{ filteredMeetings.length }} of {{ appStore.meetings.length }} meetings</p>
        </div>
        <button
          class="icon-button"
          :class="{ 'is-refreshing': appStore.refreshing.meetings }"
          :disabled="appStore.refreshing.meetings"
          title="刷新会议列表"
          @click="refreshMeetings"
        >
          <RefreshCw class="refresh-icon" :size="16" />
        </button>
      </div>

      <label class="search-field">
        <Sparkles :size="16" />
        <input v-model="searchText" placeholder="Search meetings..." />
      </label>

      <div class="filter-row">
        <select v-model="sourceFilter">
          <option value="">All Types</option>
          <option value="text">Text</option>
          <option value="markdown">Markdown</option>
          <option value="upload">Upload</option>
        </select>
        <select v-model="statusFilter" @change="refreshMeetings">
          <option value="">All Statuses</option>
          <option value="uploaded">uploaded</option>
          <option value="analyzing">analyzing</option>
          <option value="draft">draft</option>
          <option value="confirmed">confirmed</option>
          <option value="failed">failed</option>
        </select>
        <ListFilter :size="18" />
      </div>

      <div class="meeting-list">
        <button
          v-for="meeting in filteredMeetings"
          :key="meeting.id"
          class="meeting-card-row"
          :class="{ active: appStore.selectedMeeting?.id === meeting.id }"
          @click="selectMeeting(meeting)"
        >
          <div>
            <strong>{{ meeting.title || "Untitled meeting" }}</strong>
            <p>{{ sourceLabel(meeting) }} · {{ formatDate(meeting.occurred_at || meeting.created_at) }}</p>
          </div>
          <span class="status-chip" :class="meeting.status">{{ meeting.status }}</span>
          <FileText :size="17" />
        </button>
        <div v-if="!filteredMeetings.length" class="empty-block">No meetings match the current filter.</div>
      </div>
    </aside>

    <article class="meeting-detail-card">
      <div v-if="!appStore.selectedMeeting" class="empty-state-large">
        Select a meeting to review the draft, trace, reminders and Q&A.
      </div>

      <template v-else>
        <div class="detail-header">
          <div>
            <div class="title-line">
              <h1>{{ appStore.selectedMeeting.title || "Untitled meeting" }}</h1>
              <span class="status-chip" :class="appStore.selectedMeeting.status">
                {{ appStore.selectedMeeting.status }}
              </span>
            </div>
            <div class="meeting-meta">
              <span><CalendarDays :size="16" /> {{ formatDate(appStore.selectedMeeting.occurred_at || appStore.selectedMeeting.created_at) }}</span>
              <span><Clock3 :size="16" /> {{ appStore.selectedMeeting.content_length }} chars</span>
              <span><Users :size="16" /> {{ shortId(appStore.selectedMeeting.id) }}</span>
            </div>
          </div>
          <div class="header-actions">
            <button
              class="outline-button"
              :disabled="isReanalysisLocked"
              :title="isReanalysisLocked ? reanalysisDisabledMessage : 'Analyze meeting'"
              @click="analyzeSelectedMeeting"
            >
              <PlayCircle :size="17" />
              Analyze
            </button>
            <button
              class="outline-button"
              :disabled="!selectedDraft || selectedDraft.status !== 'draft'"
              @click="confirmCurrentDraft"
            >
              Confirm Draft
            </button>
            <button
              class="primary-button"
              :disabled="!selectedDraft || !['confirmed', 'failed'].includes(selectedDraft.status)"
              @click="dispatchCurrentDraft"
            >
              Dispatch to Linear
            </button>
            <button
              class="danger-button"
              :disabled="appStore.deletingMeetingId === appStore.selectedMeeting?.id"
              @click="deleteSelectedMeeting"
            >
              <Trash2 :size="17" />
              Delete
            </button>
          </div>
        </div>

        <div class="tabs">
          <button :class="{ active: activeTab === 'draft' }" @click="activeTab = 'draft'">Draft Review</button>
          <button :class="{ active: activeTab === 'summary' }" @click="activeTab = 'summary'">Summary</button>
          <button :class="{ active: activeTab === 'transcript' }" @click="activeTab = 'transcript'">Transcript</button>
        </div>

        <div v-if="actionMessage" class="result-banner">{{ actionMessage }}</div>
        <div v-if="isReanalysisLocked" class="result-banner">{{ reanalysisDisabledMessage }}</div>
        <div v-if="actionError" class="error-banner">{{ actionError }}</div>
        <div v-if="pollingStore.workflow" class="polling-strip">
          Latest task: {{ pollingStore.workflow.current_node || "-" }} / {{ pollingStore.workflow.status }}
        </div>

        <section v-if="activeTab === 'draft'" class="review-section">
          <div class="section-heading">
            <h2>Action Items ({{ actionItems.length }})</h2>
            <span v-if="selectedDraft" class="status-chip" :class="selectedDraft.status">{{ selectedDraft.status }}</span>
          </div>

          <div v-if="!selectedDraft" class="empty-block">No analysis draft yet. Click Analyze to create one.</div>
          <div v-else-if="!actionItems.length" class="empty-block">No action items were extracted.</div>
          <table v-else class="action-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Action Item</th>
                <th>Owner</th>
                <th>Due Date</th>
                <th>Priority</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in actionItems" :key="item.id">
                <td>{{ index + 1 }}</td>
                <td>
                  <strong>{{ item.title }}</strong>
                  <p>{{ item.description || item.source_excerpt || "No description" }}</p>
                </td>
                <td>{{ item.owner_name || "Unassigned" }}</td>
                <td>{{ item.due_at ? new Date(item.due_at).toLocaleDateString() : item.deadline_text || "-" }}</td>
                <td>
                  <span class="priority-badge" :class="priorityLabel(item.priority)">
                    {{ priorityLabel(item.priority) }}
                  </span>
                </td>
                <td>
                  <a v-if="item.external_tasks?.[0]?.external_url" :href="item.external_tasks[0].external_url" target="_blank">
                    <ExternalLink :size="15" />
                  </a>
                  <span v-else>{{ item.source_excerpt ? "excerpt" : "-" }}</span>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="fact-columns">
            <div>
              <h3>Decisions ({{ decisions.length }})</h3>
              <ul v-if="decisions.length">
                <li v-for="decision in decisions" :key="decision.id">{{ decision.summary }}</li>
              </ul>
              <p v-else class="muted">No decisions extracted.</p>
            </div>
            <div>
              <h3>Risks ({{ riskItems.length }})</h3>
              <ul v-if="riskItems.length">
                <li v-for="risk in riskItems" :key="risk.id">{{ risk.title }}</li>
              </ul>
              <p v-else class="muted">No risks extracted.</p>
            </div>
            <div>
              <h3>Need Clarification ({{ unconfirmedItems.length }})</h3>
              <ul v-if="unconfirmedItems.length">
                <li v-for="item in unconfirmedItems" :key="item.id">{{ item.question }}</li>
              </ul>
              <p v-else class="muted">No open questions.</p>
            </div>
          </div>
        </section>

        <section v-else-if="activeTab === 'summary'" class="review-section">
          <h2>Decision Summary</h2>
          <p class="summary-copy">{{ selectedDraft?.decision_summary || "No summary generated yet." }}</p>
        </section>

        <section v-else class="review-section">
          <h2>Transcript</h2>
          <pre class="content-preview">{{ appStore.selectedMeeting.raw_content || "No transcript content." }}</pre>
        </section>
      </template>
    </article>

    <aside class="right-rail">
      <section class="side-card">
        <div class="section-heading">
          <h2>Execution Trace</h2>
          <span v-if="appStore.selectedWorkflow" class="status-chip" :class="appStore.selectedWorkflow.status">
            {{ appStore.selectedWorkflow.status }}
          </span>
        </div>
        <div v-if="!latestWorkflows.length" class="empty-block">No workflow runs yet.</div>
        <ol v-else class="timeline">
          <li
            v-for="workflow in latestWorkflows"
            :key="workflow.id"
            :class="workflow.status"
            @click="appStore.loadWorkflow(workflow.id)"
          >
            <span></span>
            <div>
              <strong>{{ workflow.current_node || workflow.workflow_type }}</strong>
              <p>{{ workflow.error_message || workflow.workflow_type }}</p>
            </div>
            <time>{{ new Date(workflow.updated_at).toLocaleTimeString() }}</time>
          </li>
        </ol>
      </section>

      <section class="side-card">
        <div class="section-heading">
          <h2>Upcoming Reminders</h2>
          <button class="text-button" @click="appStore.loadReminders">View all</button>
        </div>
        <div v-if="!unreadReminders.length" class="empty-block">No unread reminders.</div>
        <div v-for="reminder in unreadReminders" :key="reminder.id" class="reminder-row">
          <FileText :size="18" />
          <div>
            <strong>{{ reminder.message }}</strong>
            <p>{{ formatDate(reminder.due_at) }}</p>
          </div>
          <span class="priority-badge" :class="reminder.reminder_type">{{ reminder.reminder_type }}</span>
        </div>
      </section>

      <section class="side-card ask-card">
        <h2>Ask about this meeting</h2>
        <div v-if="askResult" class="answer-bubble">
          <p>{{ askResult.answer }}</p>
          <div v-if="askResult.citations.length" class="citations">
            <strong>Citations</strong>
            <small v-for="citation in askResult.citations.slice(0, 3)" :key="JSON.stringify(citation)">
              {{ citationText(citation) }}
            </small>
          </div>
        </div>
        <form class="ask-form" @submit.prevent="askSelectedMeeting">
          <input v-model="askQuestion" :disabled="!appStore.selectedMeeting" placeholder="Ask a question..." />
          <button class="send-button" :disabled="askLoading || !appStore.selectedMeeting || !askQuestion.trim()">
            <Send :size="18" />
          </button>
        </form>
      </section>
    </aside>
  </section>
  <ClarificationDecisionDialog
    :open="showClarificationDialog"
    :loading="false"
    :unconfirmed-items="unconfirmedItems"
    @close="showClarificationDialog = false"
    @add-info="keepEditingClarifications"
    @direct-dispatch="forceContinueAndDispatch"
  />
</template>
