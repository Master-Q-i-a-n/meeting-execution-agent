export type HealthStatus = {
  status: string;
  service?: string;
  database?: string;
  redis?: string;
  qdrant?: string;
};

export type MeetingSummary = {
  id: string;
  title: string | null;
  source_type: string;
  status: string;
  occurred_at: string | null;
  content_length: number;
  content_preview: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ExternalTaskMapping = {
  id: string;
  provider: string;
  external_task_id: string;
  external_identifier: string | null;
  external_url: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
};

export type DecisionDraft = {
  id: string;
  summary: string;
  source_excerpt: string | null;
  confidence: number | null;
  status: string;
};

export type ActionItemDraft = {
  id: string;
  title: string;
  description: string | null;
  owner_name: string | null;
  deadline_text: string | null;
  due_at: string | null;
  priority: "low" | "medium" | "high" | "urgent" | null;
  source_excerpt: string | null;
  confidence: number | null;
  status: string;
  external_tasks: ExternalTaskMapping[];
};

export type ActionItemBoard = ActionItemDraft & {
  analysis_draft_id: string;
  meeting_id: string;
};

export type RiskItemDraft = {
  id: string;
  title: string;
  description: string | null;
  source_excerpt: string | null;
  confidence: number | null;
  status: string;
};

export type UnconfirmedItemDraft = {
  id: string;
  question: string;
  description: string | null;
  source_excerpt: string | null;
  confidence: number | null;
  status: string;
};

export type AnalysisDraft = {
  id: string;
  status: string;
  model_name: string;
  prompt_version: string;
  decision_summary: string | null;
  decisions: DecisionDraft[];
  action_items: ActionItemDraft[];
  risk_items: RiskItemDraft[];
  unconfirmed_items: UnconfirmedItemDraft[];
  created_at: string;
  updated_at: string;
};

export type MeetingDetail = MeetingSummary & {
  raw_content: string | null;
  analysis_draft: AnalysisDraft | null;
};

export type WorkflowRun = {
  id: string;
  meeting_id: string | null;
  workflow_type: string;
  current_node: string | null;
  status: string;
  payload_json: Record<string, unknown> | null;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
};

export type ToolCall = {
  id: string;
  workflow_run_id: string | null;
  tool_name: string;
  idempotency_key: string | null;
  status: string;
  request_json: Record<string, unknown> | null;
  response_json: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type AnalyzeResponse = {
  meeting_id: string;
  workflow_run_id: string;
  task_id: string;
  status: string;
};

export type DraftDispatchResponse = {
  draft_id: string;
  workflow_run_id: string;
  task_id: string;
  status: string;
};

export type DraftConfirmationResponse = {
  draft: AnalysisDraft;
  snapshot: {
    id: string;
    analysis_draft_id: string;
    agent_suggestion_json: Record<string, unknown>;
    confirmed_draft_json: Record<string, unknown>;
    created_at: string;
  };
  dispatch: DraftDispatchResponse | null;
};

export type Reminder = {
  id: string;
  action_item_id: string;
  reminder_type: string;
  status: string;
  message: string;
  due_at: string;
  triggered_at: string;
  read_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type AskResponse = {
  answer: string;
  citations: Array<Record<string, unknown>>;
  structured_facts: Record<string, unknown>;
};
