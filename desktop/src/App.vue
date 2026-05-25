<script setup lang="ts">
import {
  Bot,
  CalendarCheck2,
  ChevronDown,
  GitBranch,
  KanbanSquare,
  MessageSquareText,
  Plug,
  RefreshCw,
  Settings,
  UploadCloud,
} from "lucide-vue-next";
import { computed } from "vue";
import { RouterLink, RouterView } from "vue-router";

import StatusBar from "@/components/StatusBar.vue";
import { useAppStore } from "@/stores/app";

const appStore = useAppStore();

const navItems = [
  { to: "/meetings", label: "Meetings", icon: CalendarCheck2 },
  { to: "/upload", label: "Upload", icon: UploadCloud },
  { to: "/draft-review", label: "Draft Review", icon: Bot },
  { to: "/board", label: "Execution Board", icon: KanbanSquare },
  { to: "/ask", label: "Ask", icon: MessageSquareText },
  { to: "/integrations", label: "Integrations", icon: Plug },
  { to: "/trace", label: "Trace", icon: GitBranch },
];

const footerSyncText = computed(() => {
  if (!appStore.lastSyncedAt) {
    return "Not synced yet";
  }
  return new Date(appStore.lastSyncedAt).toLocaleTimeString();
});

function isOnline(value: unknown) {
  return value !== null && value !== undefined;
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span>MA</span>
        <div>
          <strong>Meeting Agent</strong>
          <small>meeting.agent@lab.com</small>
        </div>
      </div>

      <nav>
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
          <component :is="item.icon" :size="19" />
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="workspace-switcher">
        <small>Workspace</small>
        <strong>Meeting Agent Lab</strong>
        <ChevronDown :size="17" />
      </div>

      <div class="sidebar-user">
        <span>MA</span>
        <div>
          <strong>Meeting Agent</strong>
          <small>meeting.agent@lab.com</small>
        </div>
        <Settings :size="19" />
      </div>
    </aside>

    <main class="main-shell">
      <StatusBar />
      <RouterView />
    </main>

    <footer class="desktop-footer">
      <span>v1.0.0</span>
      <span class="footer-status" :class="{ online: isOnline(appStore.health.backend) }">
        Backend {{ isOnline(appStore.health.backend) ? "Online" : "Offline" }}
      </span>
      <span class="footer-status" :class="{ online: isOnline(appStore.health.qdrant) }">
        Qdrant {{ isOnline(appStore.health.qdrant) ? "Indexed" : "Offline" }}
      </span>
      <span>Response {{ appStore.lastResponseMs ?? "-" }} ms</span>
      <button
        class="footer-refresh"
        :class="{ 'is-refreshing': appStore.refreshing.health }"
        :disabled="appStore.refreshing.health"
        title="Refresh status"
        @click="appStore.refreshHealth"
      >
        <RefreshCw class="refresh-icon" :size="15" />
      </button>
      <span>Last sync: {{ footerSyncText }}</span>
    </footer>
  </div>
</template>
