<script setup lang="ts">
import { ref } from "vue";
import { PlugZap } from "lucide-vue-next";

import { api } from "@/api/client";

const linearResult = ref<Record<string, unknown> | null>(null);
const error = ref("");

async function testLinear() {
  error.value = "";
  try {
    linearResult.value = await api.testLinear();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}
</script>

<template>
  <section class="workspace-column">
    <div class="page-title">
      <div>
        <h1>Integrations</h1>
        <p>第一版只检测后端已有 Linear API Key 和默认 Team ID。</p>
      </div>
    </div>

    <article class="panel integration-card">
      <div>
        <h2>Linear</h2>
        <p>用于把确认后的 action items 派发为 Linear Issues。</p>
      </div>
      <button class="primary-button" @click="testLinear">
        <PlugZap :size="17" />
        Test Linear
      </button>
    </article>

    <pre v-if="linearResult" class="json-block">{{ JSON.stringify(linearResult, null, 2) }}</pre>
    <div v-if="error" class="error-banner">{{ error }}</div>
  </section>
</template>
