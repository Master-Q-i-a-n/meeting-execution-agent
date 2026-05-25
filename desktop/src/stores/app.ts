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
    refreshing: {
      health: false,
      meetings: false,
      actionItems: false,
      reminders: false,
      workflows: false,
    },
    lastSyncedAt: null as string | null,
    lastResponseMs: null as number | null,
    deletingMeetingId: null as string | null,
    loading: false,
    error: "",
  }),
  actions: {
    setError(error: unknown) {
      this.error = error instanceof Error ? error.message : String(error);
    },
    async refreshHealth() {
      this.refreshing.health = true;
      const startedAt = performance.now();
      try {
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
      } finally {
        this.refreshing.health = false;
      }
    },
    async loadMeetings(status?: string) {
      this.loading = true;
      this.refreshing.meetings = true;
      try {
        this.meetings = await api.listMeetings(status);
      } catch (error) {
        this.setError(error);
      } finally {
        this.loading = false;
        this.refreshing.meetings = false;
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
    async deleteMeeting(meetingId: string) {
      this.deletingMeetingId = meetingId;
      try {
        const response = await api.deleteMeeting(meetingId);
        this.meetings = this.meetings.filter((meeting) => meeting.id !== meetingId);
        if (this.selectedMeeting?.id === meetingId) {
          this.selectedMeeting = null;
          this.workflows = [];
          this.selectedWorkflow = null;
          this.toolCalls = [];
        }
        return response;
      } finally {
        this.deletingMeetingId = null;
      }
    },
    async loadActionItems(status?: string) {
      this.refreshing.actionItems = true;
      try {
        this.actionItems = await api.listActionItems({ status });
      } finally {
        this.refreshing.actionItems = false;
      }
    },
    async loadReminders() {
      this.refreshing.reminders = true;
      try {
        this.reminders = await api.listReminders("unread");
      } finally {
        this.refreshing.reminders = false;
      }
    },
    async loadWorkflows(meetingId?: string) {
      this.refreshing.workflows = true;
      try {
        this.workflows = await api.listWorkflowRuns(meetingId);
        this.selectedWorkflow = this.workflows[0] ?? null;
        if (this.selectedWorkflow) {
          await this.loadToolCalls(this.selectedWorkflow.id);
        }
      } finally {
        this.refreshing.workflows = false;
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
