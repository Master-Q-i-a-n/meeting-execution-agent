<script setup lang="ts">
import { ref } from "vue";
import { Send, UploadCloud } from "lucide-vue-next";

import { api } from "@/api/client";
import type { MeetingSummary } from "@/api/types";

const title = ref("");
const occurredAt = ref("");
const content = ref("");
const sourceType = ref<"text" | "markdown">("markdown");
const selectedFile = ref<File | null>(null);
const createdMeeting = ref<MeetingSummary | null>(null);
const message = ref("");

async function createFromText() {
  createdMeeting.value = await api.createMeeting({
    title: title.value || null,
    source_type: sourceType.value,
    content: content.value,
    occurred_at: occurredAt.value || null,
  });
  message.value = "会议已创建";
}

async function uploadFile() {
  if (!selectedFile.value) {
    message.value = "请选择文件";
    return;
  }
  const form = new FormData();
  form.set("file", selectedFile.value);
  if (title.value) {
    form.set("title", title.value);
  }
  if (occurredAt.value) {
    form.set("occurred_at", occurredAt.value);
  }
  createdMeeting.value = await api.uploadMeeting(form);
  message.value = "文件已上传";
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
}
</script>

<template>
  <section class="workspace-column">
    <div class="page-title">
      <div>
        <h1>Upload</h1>
        <p>粘贴会议纪要，或上传 txt / md / pdf / docx / 图片 / 音频。</p>
      </div>
    </div>

    <div class="form-grid">
      <label>
        标题
        <input v-model="title" placeholder="例：支付回调联调会议" />
      </label>
      <label>
        会议时间
        <input v-model="occurredAt" type="datetime-local" />
      </label>
      <label>
        类型
        <select v-model="sourceType">
          <option value="markdown">Markdown</option>
          <option value="text">Text</option>
        </select>
      </label>
    </div>

    <div class="two-column">
      <article class="panel">
        <h2>粘贴内容</h2>
        <textarea v-model="content" rows="16" placeholder="把会议纪要贴在这里"></textarea>
        <button class="primary-button" @click="createFromText">
          <Send :size="17" />
          创建会议
        </button>
      </article>

      <article class="panel">
        <h2>上传文件</h2>
        <input type="file" accept=".txt,.md,.markdown,.pdf,.docx,.jpg,.jpeg,.png,.mp3,.wav,.m4a" @change="onFileChange" />
        <p class="muted">{{ selectedFile?.name || "未选择文件" }}</p>
        <p class="muted">图片会走 OCR；音频会走 ASR 并保留时间戳和语音线索。</p>
        <button class="primary-button" @click="uploadFile">
          <UploadCloud :size="17" />
          上传会议
        </button>
      </article>
    </div>

    <div v-if="message" class="result-banner">
      {{ message }}
      <span v-if="createdMeeting">ID: {{ createdMeeting.id }}</span>
    </div>
  </section>
</template>
