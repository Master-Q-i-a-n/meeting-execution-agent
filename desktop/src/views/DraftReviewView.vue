<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { CheckCircle2, Save } from "lucide-vue-next";

import { api } from "@/api/client";
import type { ActionItemDraft } from "@/api/types";
import { useAppStore } from "@/stores/app";
import { usePollingStore } from "@/stores/polling";

const appStore = useAppStore();
const pollingStore = usePollingStore();
const selectedMeetingId = ref("");
const editing = reactive<Record<string, Partial<ActionItemDraft>>>({});
const message = ref("");

const draft = computed(() => appStore.selectedMeeting?.analysis_draft ?? null);

onMounted(async () => {
  await appStore.loadMeetings();
});

async function loadMeeting() {
  if (selectedMeetingId.value) {
    await appStore.loadMeeting(selectedMeetingId.value);
  }
}

function editModel(item: ActionItemDraft) {
  if (!editing[item.id]) {
    editing[item.id] = {
      title: item.title,
      description: item.description,
      owner_name: item.owner_name,
      deadline_text: item.deadline_text,
      due_at: item.due_at ? item.due_at.slice(0, 16) : null,
      priority: item.priority,
    };
  }
  return editing[item.id];
}

async function saveActionItem(item: ActionItemDraft) {
  if (!draft.value) {
    return;
  }
  const updates = { ...editModel(item) };
  if (updates.due_at) {
    updates.due_at = new Date(updates.due_at).toISOString();
  }
  await api.updateActionItem(draft.value.id, item.id, updates);
  await loadMeeting();
  message.value = "待办已保存";
}

async function confirmDraft() {
  if (!draft.value) {
    return;
  }
  const response = await api.confirmDraft(draft.value.id);
  message.value = "草稿已确认，派发任务已投递";
  if (response.dispatch) {
    pollingStore.start(response.dispatch.workflow_run_id);
  }
  await loadMeeting();
}
</script>

<template>
  <section class="workspace-column">
    <div class="page-title">
      <div>
        <h1>Draft Review</h1>
        <p>审核 Agent 生成的决策、待办、风险和待澄清项。</p>
      </div>
      <button class="primary-button" :disabled="!draft || draft.status !== 'draft'" @click="confirmDraft">
        <CheckCircle2 :size="17" />
        Confirm Draft
      </button>
    </div>

    <div class="toolbar">
      <label>
        会议
        <select v-model="selectedMeetingId" @change="loadMeeting">
          <option value="">选择会议</option>
          <option v-for="meeting in appStore.meetings" :key="meeting.id" :value="meeting.id">
            {{ meeting.title || meeting.id }} · {{ meeting.status }}
          </option>
        </select>
      </label>
      <span v-if="draft" class="status-chip" :class="draft.status">{{ draft.status }}</span>
    </div>

    <div v-if="message" class="result-banner">{{ message }}</div>
    <div v-if="!draft" class="empty-block">请选择已经分析出草稿的会议</div>

    <template v-else>
      <article class="panel">
        <h2>决策摘要</h2>
        <p>{{ draft.decision_summary || "暂无摘要" }}</p>
      </article>

      <div class="review-grid">
        <article class="panel wide-panel">
          <h2>Action Items</h2>
          <div v-for="item in draft.action_items" :key="item.id" class="editable-task">
            <div class="form-grid compact">
              <label>
                标题
                <input v-model="editModel(item).title" :disabled="draft.status !== 'draft'" />
              </label>
              <label>
                负责人
                <input v-model="editModel(item).owner_name" :disabled="draft.status !== 'draft'" />
              </label>
              <label>
                原文截止
                <input v-model="editModel(item).deadline_text" :disabled="draft.status !== 'draft'" />
              </label>
              <label>
                标准截止
                <input v-model="editModel(item).due_at" type="datetime-local" :disabled="draft.status !== 'draft'" />
              </label>
              <label>
                优先级
                <select v-model="editModel(item).priority" :disabled="draft.status !== 'draft'">
                  <option :value="null">未设置</option>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                  <option value="urgent">urgent</option>
                </select>
              </label>
            </div>
            <textarea v-model="editModel(item).description" rows="3" :disabled="draft.status !== 'draft'"></textarea>
            <p class="source-line">{{ item.source_excerpt }}</p>
            <button class="icon-text-button" :disabled="draft.status !== 'draft'" @click="saveActionItem(item)">
              <Save :size="16" />
              保存
            </button>
          </div>
        </article>

        <article class="panel">
          <h2>Decisions</h2>
          <div v-for="decision in draft.decisions" :key="decision.id" class="fact-row">
            <strong>{{ decision.summary }}</strong>
            <small>{{ decision.source_excerpt }}</small>
          </div>
        </article>

        <article class="panel">
          <h2>Risks</h2>
          <div v-for="risk in draft.risk_items" :key="risk.id" class="fact-row">
            <strong>{{ risk.title }}</strong>
            <small>{{ risk.description }}</small>
          </div>
        </article>

        <article class="panel">
          <h2>Unconfirmed</h2>
          <div v-for="item in draft.unconfirmed_items" :key="item.id" class="fact-row">
            <strong>{{ item.question }}</strong>
            <small>{{ item.description }}</small>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>
