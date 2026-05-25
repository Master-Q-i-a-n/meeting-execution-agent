import { api } from "@/api/client";
import type { WorkflowRun } from "@/api/types";

const DEFAULT_INTERVAL_MS = 1500;
const DEFAULT_TIMEOUT_MS = 60000;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function waitForWorkflowStatus(
  workflowRunId: string,
  targetStatuses: string[],
  options: {
    timeoutMs?: number;
    intervalMs?: number;
    terminalStatuses?: string[];
  } = {},
): Promise<WorkflowRun> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS;
  const terminalStatuses = options.terminalStatuses ?? ["failed", "cancelled", "completed"];
  const startedAt = Date.now();

  while (Date.now() - startedAt <= timeoutMs) {
    const workflow = await api.getWorkflowRun(workflowRunId);
    if (targetStatuses.includes(workflow.status)) {
      return workflow;
    }
    if (terminalStatuses.includes(workflow.status)) {
      throw new Error(workflow.error_message || `Workflow stopped at ${workflow.status}`);
    }
    await sleep(intervalMs);
  }

  throw new Error("Workflow did not reach the expected waiting state in time");
}
