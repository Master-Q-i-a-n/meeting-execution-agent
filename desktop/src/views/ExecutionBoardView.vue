<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Check, RefreshCw, X } from "lucide-vue-next";

import { api } from "@/api/client";
import { useAppStore } from "@/stores/app";
import { formatDate } from "@/utils/format";

const appStore = useAppStore();
const statusFilter = ref("");
const columns = ["draft", "confirmed", "dispatched", "done", "cancelled"];

const grouped = computed(() =>
  columns.map((status) => ({
    status,
    items: appStore.actionItems.filter((item) => item.status === status),
  })),
);

async function loadBoard() {
  await appStore.loadActionItems(statusFilter.value || undefined);
}

async function updateStatus(actionItemId: string, status: "done" | "cancelled") {
  await api.updateActionItemStatus(actionItemId, status);
  await loadBoard();
}

onMounted(loadBoard);
</script>

<template>
  <section class="workspace-column">
    <div class="page-title">
      <div>
        <h1>Execution Board</h1>
        <p>查看已确认、已派发和已完成的执行项。</p>
      </div>
      <button
        class="icon-text-button"
        :class="{ 'is-refreshing': appStore.refreshing.actionItems }"
        :disabled="appStore.refreshing.actionItems"
        @click="loadBoard"
      >
        <RefreshCw class="refresh-icon" :size="16" />
        刷新
      </button>
    </div>

    <div class="toolbar">
      <label>
        状态
        <select v-model="statusFilter" @change="loadBoard">
          <option value="">全部</option>
          <option v-for="status in columns" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
    </div>

    <div class="board-grid">
      <section v-for="column in grouped" :key="column.status" class="board-column">
        <h2>{{ column.status }} <span>{{ column.items.length }}</span></h2>
        <article v-for="item in column.items" :key="item.id" class="task-card">
          <strong>{{ item.title }}</strong>
          <p>{{ item.description || "暂无说明" }}</p>
          <dl>
            <div><dt>Owner</dt><dd>{{ item.owner_name || "-" }}</dd></div>
            <div><dt>Due</dt><dd>{{ formatDate(item.due_at) }}</dd></div>
            <div><dt>Priority</dt><dd>{{ item.priority || "-" }}</dd></div>
          </dl>
          <a
            v-for="external in item.external_tasks"
            :key="external.id"
            :href="external.external_url || '#'"
            target="_blank"
          >
            {{ external.provider }} · {{ external.external_identifier || external.status }}
          </a>
          <div class="task-actions">
            <button class="icon-button" title="标记完成" @click="updateStatus(item.id, 'done')">
              <Check :size="15" />
            </button>
            <button class="icon-button" title="取消待办" @click="updateStatus(item.id, 'cancelled')">
              <X :size="15" />
            </button>
          </div>
        </article>
      </section>
    </div>
  </section>
</template>
