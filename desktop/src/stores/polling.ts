import { defineStore } from "pinia";

import { api } from "@/api/client";
import type { WorkflowRun } from "@/api/types";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export const usePollingStore = defineStore("polling", {
  state: () => ({
    workflow: null as WorkflowRun | null,
    timer: 0,
  }),
  actions: {
    stop() {
      if (this.timer) {
        window.clearInterval(this.timer);
        this.timer = 0;
      }
    },
    async pollOnce(workflowRunId: string) {
      this.workflow = await api.getWorkflowRun(workflowRunId);
      if (TERMINAL_STATUSES.has(this.workflow.status)) {
        this.stop();
      }
    },
    start(workflowRunId: string) {
      this.stop();
      void this.pollOnce(workflowRunId);
      this.timer = window.setInterval(() => {
        void this.pollOnce(workflowRunId);
      }, 2000);
    },
  },
});
