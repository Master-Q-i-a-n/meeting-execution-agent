<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Send } from "lucide-vue-next";

import { api } from "@/api/client";
import type { AskResponse } from "@/api/types";
import { useAppStore } from "@/stores/app";

const appStore = useAppStore();
const selectedMeetingId = ref("");
const question = ref("");
const topK = ref(5);
const result = ref<AskResponse | null>(null);
const loading = ref(false);

onMounted(() => {
  void appStore.loadMeetings();
});

async function ask() {
  loading.value = true;
  try {
    result.value = selectedMeetingId.value
      ? await api.askMeeting(selectedMeetingId.value, question.value, topK.value)
      : await api.askAcrossMeetings(question.value, topK.value);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="page-grid ask-layout">
    <div class="workspace-column">
      <div class="page-title">
        <div>
          <h1>Ask</h1>
          <p>基于 MySQL 结构化事实和 Qdrant 语义片段追问。</p>
        </div>
      </div>

      <article class="panel">
        <div class="form-grid">
          <label>
            会议范围
            <select v-model="selectedMeetingId">
              <option value="">跨会议</option>
              <option v-for="meeting in appStore.meetings" :key="meeting.id" :value="meeting.id">
                {{ meeting.title || meeting.id }}
              </option>
            </select>
          </label>
          <label>
            Top K
            <input v-model.number="topK" type="number" min="1" max="10" />
          </label>
        </div>
        <textarea v-model="question" rows="5" placeholder="例：上次会议里谁负责接口联调？"></textarea>
        <button class="primary-button" :disabled="!question || loading" @click="ask">
          <Send :size="17" />
          Ask
        </button>
      </article>

      <article v-if="result" class="panel answer-panel">
        <h2>Answer</h2>
        <p>{{ result.answer }}</p>
      </article>
    </div>

    <aside class="trace-panel">
      <h2>Citations</h2>
      <div v-if="!result?.citations.length" class="empty-block">暂无引用</div>
      <div v-for="(citation, index) in result?.citations" :key="index" class="tool-call-row">
        <div>
          <strong>[{{ index + 1 }}] {{ citation.chunk_type }}</strong>
          <span>{{ citation.score }}</span>
        </div>
        <small>{{ citation.meeting_id }} / {{ citation.chunk_id }}</small>
        <p>{{ citation.source_excerpt || citation.text }}</p>
      </div>
    </aside>
  </section>
</template>
