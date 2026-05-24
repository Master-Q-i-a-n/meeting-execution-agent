import { defineStore } from "pinia";

import { api } from "@/api/client";
import type {
  ActionItemBoard,
  HealthStatus,
  MeetingDetail,
  MeetingSummary,
  Reminder,
  ToolCall,
  WorkflowRun,
} from "@/api/types";

export const useAppStore = defineStore("app", {
  state: () => ({
    meetings: [] as MeetingSummary[],
    selectedMeeting: null as MeetingDetail | null,
    actionItems: [] as ActionItemBoard[],
    reminders: [] as Reminder[],
    workflows: [] as WorkflowRun[],
    selectedWorkflow: null as WorkflowRun | null,
    toolCalls: [] as ToolCall[],
    health: {
      backend: null as HealthStatus | null,
      redis: null as HealthStatus | null,
      qdrant: null as HealthStatus | null,
      linear: null as Record<string, unknown> | null,
    },
    lastSyncedAt: null as string | null,
    lastResponseMs: null as number | null,
    loading: false,
    error: "",
  }),
  actions: {
    setError(error: unknown) {
      this.error = error instanceof Error ? error.message : String(error);
    },
    async refreshHealth() {
      const startedAt = performance.now();
      const [backend, redis, qdrant, linear] = await Promise.allSettled([
        api.health(),
        api.redisHealth(),
        api.qdrantHealth(),
        api.testLinear(),
      ]);
      this.health.backend = backend.status === "fulfilled" ? backend.value : null;
      this.health.redis = redis.status === "fulfilled" ? redis.value : null;
      this.health.qdrant = qdrant.status === "fulfilled" ? qdrant.value : null;
      this.health.linear = linear.status === "fulfilled" ? linear.value : null;
      this.lastResponseMs = Math.round(performance.now() - startedAt);
      this.lastSyncedAt = new Date().toISOString();
    },
    async loadMeetings(status?: string) {
      this.loading = true;
      try {
        this.meetings = await api.listMeetings(status);
      } catch (error) {
        this.setError(error);
      } finally {
        this.loading = false;
      }
    },
    async loadMeeting(meetingId: string) {
      this.loading = true;
      try {
        this.selectedMeeting = await api.getMeeting(meetingId);
        await this.loadWorkflows(meetingId);
      } catch (error) {
        this.setError(error);
      } finally {
        this.loading = false;
      }
    },
    async loadActionItems(status?: string) {
      this.actionItems = await api.listActionItems({ status });
    },
    async loadReminders() {
      this.reminders = await api.listReminders("unread");
    },
    async loadWorkflows(meetingId?: string) {
      this.workflows = await api.listWorkflowRuns(meetingId);
      this.selectedWorkflow = this.workflows[0] ?? null;
      if (this.selectedWorkflow) {
        await this.loadToolCalls(this.selectedWorkflow.id);
      }
    },
    async loadWorkflow(workflowRunId: string) {
      this.selectedWorkflow = await api.getWorkflowRun(workflowRunId);
      await this.loadToolCalls(workflowRunId);
    },
    async loadToolCalls(workflowRunId: string) {
      this.toolCalls = await api.listToolCalls(workflowRunId);
    },
  },
});
