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

function citationTitle(citation: Record<string, unknown>, index: number) {
  if (citation.source_type === "audio") {
    return `[${index + 1}] 录音 ${formatAudioTime(citation.start_time)}-${formatAudioTime(citation.end_time)}`;
  }
  if (citation.source_type === "image") {
    return `[${index + 1}] 图片 OCR 来源`;
  }
  return `[${index + 1}] ${String(citation.chunk_type ?? "source")}`;
}

function citationMeta(citation: Record<string, unknown>) {
  const clues = [
    citation.emotion ? `emotion=${citation.emotion}` : "",
    citation.speech_rate ? `speech=${citation.speech_rate}` : "",
    citation.pause_before_ms ? `pause=${citation.pause_before_ms}ms` : "",
  ].filter(Boolean);
  return clues.length ? clues.join(" · ") : `${citation.meeting_id ?? ""} / ${citation.chunk_id ?? ""}`;
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
          <strong>{{ citationTitle(citation, index) }}</strong>
          <span>{{ citation.score }}</span>
        </div>
        <small>{{ citationMeta(citation) }}</small>
        <p>{{ citation.source_excerpt || citation.text }}</p>
      </div>
    </aside>
  </section>
</template>
