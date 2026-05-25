import { api } from "@/api/client";
import type { WorkflowContinueResponse } from "@/api/types";
import { waitForWorkflowStatus } from "@/utils/workflows";

type MaybePromise<T> = T | Promise<T>;

type DirectDispatchOptions = {
  workflowRunId: string;
  draftId: string;
  onProgress?: (message: string) => void;
  onForceContinueQueued?: (response: WorkflowContinueResponse) => void;
  onReadyForConfirmation?: () => MaybePromise<void>;
  onConfirmQueued?: (response: WorkflowContinueResponse) => void;
  onComplete?: () => MaybePromise<void>;
  onError?: (error: unknown) => void;
};

export function startClarificationDirectDispatch(options: DirectDispatchOptions): void {
  void runClarificationDirectDispatch(options).catch((error: unknown) => {
    options.onError?.(error);
  });
}

async function runClarificationDirectDispatch(options: DirectDispatchOptions): Promise<void> {
  options.onProgress?.("已选择直接派送，系统会先跳过澄清，再自动确认并派送到 Linear。");

  const forceResponse = await api.continueWorkflow(options.workflowRunId, "force_continue");
  options.onForceContinueQueued?.(forceResponse);

  options.onProgress?.("已跳过澄清，正在等待工作流进入草稿确认节点。");
  await waitForWorkflowStatus(forceResponse.workflow_run_id, ["waiting_confirmation"]);
  await options.onReadyForConfirmation?.();

  const confirmResponse = await api.confirmDraft(options.draftId);
  options.onConfirmQueued?.(confirmResponse);
  options.onProgress?.("已开始确认草稿并派送到 Linear。");
  await options.onComplete?.();
}
