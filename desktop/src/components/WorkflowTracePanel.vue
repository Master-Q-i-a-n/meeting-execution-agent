<script setup lang="ts">
import type { ToolCall, WorkflowRun } from "@/api/types";

defineProps<{
  workflow: WorkflowRun | null;
  toolCalls: ToolCall[];
}>();
</script>

<template>
  <aside class="trace-panel">
    <div class="section-heading">
      <h2>Trace</h2>
      <span v-if="workflow" class="status-chip" :class="workflow.status">
        {{ workflow.status }}
      </span>
    </div>

    <div v-if="!workflow" class="empty-block">No workflow records yet.</div>
    <template v-else>
      <dl class="trace-list">
        <div>
          <dt>Workflow</dt>
          <dd>{{ workflow.workflow_type }}</dd>
        </div>
        <div>
          <dt>Node</dt>
          <dd>{{ workflow.current_node || "-" }}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{{ new Date(workflow.updated_at).toLocaleString() }}</dd>
        </div>
        <div v-if="workflow.error_message">
          <dt>Error</dt>
          <dd class="error-text">{{ workflow.error_message }}</dd>
        </div>
      </dl>
      <pre class="json-block">{{ JSON.stringify(workflow.payload_json ?? {}, null, 2) }}</pre>

      <h3>Tool Calls</h3>
      <div v-if="!toolCalls.length" class="empty-block">No tool calls yet.</div>
      <div v-for="toolCall in toolCalls" :key="toolCall.id" class="tool-call-row">
        <div>
          <strong>{{ toolCall.tool_name }}</strong>
          <span>{{ toolCall.status }}</span>
        </div>
        <small>{{ toolCall.idempotency_key || toolCall.id }}</small>
        <p v-if="toolCall.error_message">{{ toolCall.error_message }}</p>
      </div>
    </template>
  </aside>
</template>
