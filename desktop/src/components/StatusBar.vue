<script setup lang="ts">
import { onMounted } from "vue";
import { CheckCircle2, Database, PlugZap, RefreshCw, Server, XCircle } from "lucide-vue-next";

import { useAppStore } from "@/stores/app";

const appStore = useAppStore();

onMounted(() => {
  void appStore.refreshHealth();
});

function isOnline(value: unknown) {
  return value !== null && value !== undefined;
}
</script>

<template>
  <header class="status-bar">
    <div class="service-tile" :class="{ online: isOnline(appStore.health.backend) }">
      <Server :size="18" />
      <div>
        <strong>Backend {{ isOnline(appStore.health.backend) ? "Online" : "Offline" }}</strong>
        <span>API responding</span>
      </div>
    </div>

    <div class="service-tile" :class="{ online: isOnline(appStore.health.redis) }">
      <CheckCircle2 v-if="isOnline(appStore.health.redis)" :size="18" />
      <XCircle v-else :size="18" />
      <div>
        <strong>Redis {{ isOnline(appStore.health.redis) ? "Ready" : "Offline" }}</strong>
        <span>Queue status</span>
      </div>
    </div>

    <div class="service-tile" :class="{ online: isOnline(appStore.health.qdrant) }">
      <Database :size="18" />
      <div>
        <strong>Qdrant {{ isOnline(appStore.health.qdrant) ? "Indexed" : "Offline" }}</strong>
        <span>Collections ready</span>
      </div>
    </div>

    <div class="service-tile" :class="{ online: isOnline(appStore.health.linear) }">
      <PlugZap :size="18" />
      <div>
        <strong>Linear {{ isOnline(appStore.health.linear) ? "Connected" : "Offline" }}</strong>
        <span>Workspace check</span>
      </div>
    </div>

    <button class="outline-button" title="刷新连接状态" @click="appStore.refreshHealth">
      <RefreshCw :size="16" />
      View Integrations
    </button>
  </header>
</template>
