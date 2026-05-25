import { expect, test } from "@playwright/test";

const now = "2026-05-25T10:00:00.000Z";

const meetingSummary = {
  id: "meeting-1",
  title: "澄清流程测试会议",
  source_type: "markdown",
  status: "draft",
  occurred_at: now,
  content_length: 128,
  content_preview: "某人负责上线前检查，需要确认负责人。",
  metadata_json: null,
  created_at: now,
  updated_at: now,
};

const draft = {
  id: "draft-1",
  status: "draft",
  model_name: "qwen-plus",
  prompt_version: "v1",
  decision_summary: "先完成上线前检查。",
  decisions: [],
  action_items: [
    {
      id: "action-1",
      title: "完成上线前检查",
      description: "补齐上线前检查清单。",
      owner_name: null,
      deadline_text: "本周五",
      due_at: null,
      priority: "high",
      source_excerpt: "某人负责上线前检查，截止到本周五。",
      confidence: 0.82,
      status: "draft",
      external_tasks: [],
    },
  ],
  risk_items: [],
  unconfirmed_items: [
    {
      id: "unconfirmed-1",
      question: "待办「完成上线前检查」的负责人是谁？",
      description: null,
      source_excerpt: "某人负责上线前检查，截止到本周五。",
      confidence: 0.9,
      status: "draft",
    },
  ],
  created_at: now,
  updated_at: now,
};

function meetingDetail() {
  return {
    ...meetingSummary,
    raw_content: "# 测试会议\n\n- 某人负责上线前检查，截止到本周五。",
    analysis_draft: draft,
  };
}

function workflow(status = "waiting_clarification", currentNode = "wait_for_clarification") {
  return {
    id: "wf-clarify",
    meeting_id: "meeting-1",
    workflow_type: "meeting_execution",
    current_node: currentNode,
    status,
    payload_json: {
      draft_id: "draft-1",
      unconfirmed_count: 1,
    },
    error_message: null,
    retry_count: 0,
    created_at: now,
    updated_at: now,
  };
}

test("direct dispatch closes clarification dialog immediately and confirms in background", async ({ page }) => {
  let forceContinueCalled = false;
  let confirmCalled = 0;
  let workflowReadyForConfirmation = false;

  await page.route("http://127.0.0.1:8003/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    if (method === "GET" && url.pathname === "/health") {
      await route.fulfill({ json: { status: "ok", service: "meeting-execution-agent" } });
      return;
    }
    if (method === "GET" && url.pathname === "/health/redis") {
      await route.fulfill({ json: { status: "ok", redis: "connected" } });
      return;
    }
    if (method === "GET" && url.pathname === "/health/qdrant") {
      await route.fulfill({ json: { status: "ok", qdrant: "connected" } });
      return;
    }
    if (method === "POST" && url.pathname === "/integrations/linear/test") {
      await route.fulfill({ json: { status: "ok", team_id: "team-1" } });
      return;
    }
    if (method === "GET" && url.pathname === "/meetings") {
      await route.fulfill({ json: [meetingSummary] });
      return;
    }
    if (method === "GET" && url.pathname === "/meetings/meeting-1") {
      await route.fulfill({ json: meetingDetail() });
      return;
    }
    if (method === "GET" && url.pathname === "/reminders") {
      await route.fulfill({ json: [] });
      return;
    }
    if (method === "GET" && url.pathname === "/workflow-runs") {
      await route.fulfill({ json: [workflow()] });
      return;
    }
    if (method === "GET" && url.pathname === "/workflow-runs/wf-clarify") {
      const current = workflowReadyForConfirmation
        ? workflow("waiting_confirmation", "wait_for_confirmation")
        : workflow("running", "index_semantic_documents");
      await route.fulfill({ json: current });
      return;
    }
    if (method === "GET" && url.pathname === "/workflow-runs/wf-clarify/tool-calls") {
      await route.fulfill({ json: [] });
      return;
    }
    if (method === "POST" && url.pathname === "/workflow-runs/wf-clarify/continue") {
      const body = request.postDataJSON() as { action?: string };
      expect(body.action).toBe("force_continue");
      forceContinueCalled = true;
      await new Promise((resolve) => setTimeout(resolve, 500));
      await route.fulfill({
        json: {
          workflow_run_id: "wf-clarify",
          task_id: "task-force",
          action: "force_continue",
          status: "PENDING",
        },
      });
      return;
    }
    if (method === "POST" && url.pathname === "/analysis-drafts/draft-1/confirm") {
      confirmCalled += 1;
      await route.fulfill({
        json: {
          workflow_run_id: "wf-clarify",
          task_id: "task-confirm",
          action: "confirm_draft",
          status: "PENDING",
        },
      });
      return;
    }

    await route.fulfill({
      status: 404,
      json: { detail: `Unexpected mock request: ${method} ${url.pathname}` },
    });
  });

  await page.goto("/#/meetings");
  await expect(page.getByRole("heading", { name: "澄清流程测试会议" })).toBeVisible();

  await page.getByRole("button", { name: "Confirm Draft" }).click();
  await expect(page.getByRole("dialog", { name: "草稿还有待澄清信息" })).toBeVisible();

  await page.getByRole("button", { name: "直接派送" }).click();

  await expect(page.getByRole("dialog", { name: "草稿还有待澄清信息" })).toBeHidden();
  await expect(page.getByText("已选择直接派送，系统会先跳过澄清，再自动确认并派送到 Linear。")).toBeVisible();
  await expect.poll(() => forceContinueCalled).toBe(true);
  expect(confirmCalled).toBe(0);

  workflowReadyForConfirmation = true;
  await expect.poll(() => confirmCalled, { timeout: 8_000 }).toBe(1);
  await expect(page.getByText("已开始确认草稿并派送到 Linear。")).toBeVisible();
});
