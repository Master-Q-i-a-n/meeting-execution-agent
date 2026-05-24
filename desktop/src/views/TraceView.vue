<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RefreshCw } from "lucide-vue-next";

import WorkflowTracePanel from "@/components/WorkflowTracePanel.vue";
import { useAppStore } from "@/stores/app";
import { formatDate } from "@/utils/format";

const appStore = useAppStore();
const selectedMeetingId = ref("");

async function loadTrace() {
  await appStore.loadWorkflows(selectedMeetingId.value || undefined);
}

async function selectWorkflow(workflowRunId: string) {
  await appStore.loadWorkflow(workflowRunId);
}

onMounted(async () => {
  await appStore.loadMeetings();
  await loadTrace();
});
</script>

<template>
  <section class="page-grid with-side-panel">
    <div class="workspace-column">
      <div class="page-title">
        <div>
          <h1>Trace</h1>
          <p>查看工作流节点、payload、错误和外部工具调用。</p>
        </div>
        <button class="icon-text-button" @click="loadTrace">
          <RefreshCw :size="16" />
          刷新
        </button>
      </div>

      <div class="toolbar">
        <label>
          会议
          <select v-model="selectedMeetingId" @change="loadTrace">
            <option value="">全部工作流</option>
            <option v-for="meeting in appStore.meetings" :key="meeting.id" :value="meeting.id">
              {{ meeting.title || meeting.id }}
            </option>
          </select>
        </label>
      </div>

      <div class="workflow-list">
        <button
          v-for="workflow in appStore.workflows"
          :key="workflow.id"
          class="workflow-row"
          :class="{ active: appStore.selectedWorkflow?.id === workflow.id }"
          @click="selectWorkflow(workflow.id)"
        >
          <div>
            <strong>{{ workflow.workflow_type }}</strong>
            <p>{{ workflow.current_node || "-" }} · {{ formatDate(workflow.updated_at) }}</p>
          </div>
          <span class="status-chip" :class="workflow.status">{{ workflow.status }}</span>
        </button>
      </div>
    </div>

    <WorkflowTracePanel :workflow="appStore.selectedWorkflow" :tool-calls="appStore.toolCalls" />
  </section>
</template>
