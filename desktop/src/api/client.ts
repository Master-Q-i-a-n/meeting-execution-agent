import type {
  ActionItemBoard,
  ActionItemDraft,
  AnalyzeResponse,
  AskResponse,
  HealthStatus,
  MeetingDeleteResponse,
  MeetingDetail,
  MeetingSummary,
  Reminder,
  ToolCall,
  WorkflowContinueResponse,
  WorkflowRun,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8003";

type RequestOptions = RequestInit & {
  query?: Record<string, string | number | null | undefined>;
};

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  Object.entries(options.query ?? {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });

  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail ?? response.statusText;
    throw new ApiError(String(detail), response.status);
  }

  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthStatus>("/health"),
  redisHealth: () => request<HealthStatus>("/health/redis"),
  qdrantHealth: () => request<HealthStatus>("/health/qdrant"),
  listMeetings: (status?: string) =>
    request<MeetingSummary[]>("/meetings", { query: { status } }),
  getMeeting: (meetingId: string) => request<MeetingDetail>(`/meetings/${meetingId}`),
  deleteMeeting: (meetingId: string) =>
    request<MeetingDeleteResponse>(`/meetings/${meetingId}`, { method: "DELETE" }),
  updateMeetingContent: (
    meetingId: string,
    body: { content: string; title?: string | null; occurred_at?: string | null },
  ) =>
    request<MeetingSummary>(`/meetings/${meetingId}/content`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  createMeeting: (body: {
    title: string | null;
    source_type: "text" | "markdown";
    content: string;
    occurred_at: string | null;
  }) =>
    request<MeetingSummary>("/meetings", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  uploadMeeting: (form: FormData) =>
    request<MeetingSummary>("/meetings/upload", {
      method: "POST",
      body: form,
    }),
  analyzeMeeting: (meetingId: string) =>
    request<AnalyzeResponse>(`/meetings/${meetingId}/analyze`, { method: "POST" }),
  updateActionItem: (draftId: string, actionItemId: string, body: Partial<ActionItemDraft>) =>
    request<ActionItemDraft>(`/analysis-drafts/${draftId}/action-items/${actionItemId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  confirmDraft: (draftId: string) =>
    request<WorkflowContinueResponse>(`/analysis-drafts/${draftId}/confirm`, {
      method: "POST",
    }),
  dispatchDraft: (draftId: string) =>
    request<WorkflowContinueResponse>(`/analysis-drafts/${draftId}/dispatch`, {
      method: "POST",
    }),
  continueWorkflow: (
    workflowRunId: string,
    action: WorkflowContinueResponse["action"],
  ) =>
    request<WorkflowContinueResponse>(`/workflow-runs/${workflowRunId}/continue`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  listActionItems: (query?: {
    status?: string;
    owner_name?: string;
    due_before?: string;
  }) => request<ActionItemBoard[]>("/action-items", { query }),
  updateActionItemStatus: (actionItemId: string, status: "done" | "cancelled") =>
    request<ActionItemDraft>(`/action-items/${actionItemId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  listWorkflowRuns: (meetingId?: string) =>
    request<WorkflowRun[]>("/workflow-runs", { query: { meeting_id: meetingId } }),
  getWorkflowRun: (workflowRunId: string) =>
    request<WorkflowRun>(`/workflow-runs/${workflowRunId}`),
  listToolCalls: (workflowRunId: string) =>
    request<ToolCall[]>(`/workflow-runs/${workflowRunId}/tool-calls`),
  listReminders: (status = "unread") => request<Reminder[]>("/reminders", { query: { status } }),
  markReminderRead: (reminderId: string) =>
    request<Reminder>(`/reminders/${reminderId}/read`, { method: "PATCH" }),
  testLinear: () =>
    request<Record<string, unknown>>("/integrations/linear/test", { method: "POST" }),
  askMeeting: (meetingId: string, question: string, top_k = 5) =>
    request<AskResponse>(`/meetings/${meetingId}/ask`, {
      method: "POST",
      body: JSON.stringify({ question, top_k }),
    }),
  askAcrossMeetings: (question: string, top_k = 5) =>
    request<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify({ question, top_k }),
    }),
};

export { API_BASE_URL, ApiError };
