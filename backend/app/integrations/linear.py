from typing import Any

import httpx

from app.core.config import config
from app.core.logger import get_logger
from app.integrations.tasks import ExternalTaskCreateResult
from app.models.analysis import ActionItem

logger = get_logger(__name__)

LINEAR_PROVIDER = "linear"

LINEAR_CREATE_ISSUE_MUTATION = """
mutation CreateMeetingActionIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      title
      url
    }
  }
}
""".strip()

LINEAR_CONNECTION_QUERY = """
query TestLinearConnection($teamId: String!) {
  viewer {
    id
    name
    email
  }
  team(id: $teamId) {
    id
    name
    key
  }
}
""".strip()


class LinearIntegrationError(RuntimeError):
    """Linear 返回失败、错误 GraphQL 数据或缺少配置。"""


class LinearTaskDispatchAdapter:
    provider = LINEAR_PROVIDER

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        team_id: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or config.linear_api_key
        self.api_url = api_url or config.linear_api_url
        self.team_id = team_id or config.linear_default_team_id
        self.client = client
        if not self.api_key:
            raise LinearIntegrationError("LINEAR_API_KEY is required")
        if not self.team_id:
            raise LinearIntegrationError("LINEAR_DEFAULT_TEAM_ID is required")

    def build_create_request(self, action_item: ActionItem) -> dict:
        # 这个请求体会存进 tool_calls；密钥只放 HTTP Header，不能写进审计 JSON。
        return {
            "provider": self.provider,
            "team_id": self.team_id,
            "title": action_item.title,
            "description": build_linear_issue_description(action_item),
        }

    def create_task(self, action_item: ActionItem) -> ExternalTaskCreateResult:
        request = self.build_create_request(action_item)
        logger.info(
            "Linear Issue 创建开始 action_item_id=%s team_id=%s",
            action_item.id,
            self.team_id,
        )
        response_json = self._graphql(
            query=LINEAR_CREATE_ISSUE_MUTATION,
            variables={
                "input": {
                    "teamId": request["team_id"],
                    "title": request["title"],
                    "description": request["description"],
                }
            },
        )
        # GraphQL mutation 的业务结果在 data.issueCreate 下面。
        # HTTP 成功并不等于 Issue 创建成功，所以还要检查 success。
        payload = response_json.get("data", {}).get("issueCreate")
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise LinearIntegrationError("Linear issueCreate did not succeed")

        # 本地映射至少需要 Linear Issue ID；identifier/url 只是展示和跳转信息。
        issue = payload.get("issue")
        if not isinstance(issue, dict) or not issue.get("id"):
            raise LinearIntegrationError("Linear issueCreate returned no issue")
        logger.info(
            "Linear Issue 创建成功 action_item_id=%s issue_id=%s identifier=%s",
            action_item.id,
            issue["id"],
            issue.get("identifier"),
        )
        return ExternalTaskCreateResult(
            provider=self.provider,
            external_task_id=issue["id"],
            external_identifier=issue.get("identifier"),
            external_url=issue.get("url"),
            response_json=response_json,
        )

    def test_connection(self) -> dict:
        logger.info("Linear 连通性测试开始 team_id=%s", self.team_id)
        response_json = self._graphql(
            query=LINEAR_CONNECTION_QUERY,
            variables={"teamId": self.team_id},
        )
        data = response_json.get("data")
        if not isinstance(data, dict) or not data.get("viewer") or not data.get("team"):
            raise LinearIntegrationError("Linear connection test returned incomplete data")
        logger.info(
            "Linear 连通性测试成功 team_id=%s viewer_id=%s",
            self.team_id,
            data["viewer"].get("id"),
        )
        return {
            "status": "ok",
            "provider": self.provider,
            "viewer": data["viewer"],
            "team": data["team"],
        }

    def _graphql(self, *, query: str, variables: dict) -> dict:
        payload = {"query": query, "variables": variables}
        try:
            # 测试时可注入假的 client；真实运行时才走 httpx 访问 Linear。
            if self.client is not None:
                response = self.client.post(
                    self.api_url,
                    headers={"Authorization": self.api_key},
                    json=payload,
                )
            else:
                response = httpx.post(
                    self.api_url,
                    headers={"Authorization": self.api_key},
                    json=payload,
                    timeout=10,
                )
            response.raise_for_status()
            response_json = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.exception("Linear GraphQL 请求失败 error=%s", exc)
            raise LinearIntegrationError(f"Linear request failed: {exc}") from exc

        if not isinstance(response_json, dict):
            raise LinearIntegrationError("Linear returned invalid JSON")
        # GraphQL 常见情况是 HTTP 200 但 body.errors 有业务错误，必须显式拦住。
        errors = response_json.get("errors")
        if errors:
            messages = [
                error.get("message", "unknown GraphQL error")
                for error in errors
                if isinstance(error, dict)
            ]
            logger.error("Linear GraphQL 返回错误 messages=%s", messages)
            raise LinearIntegrationError(f"Linear GraphQL failed: {'; '.join(messages)}")
        return response_json


def build_linear_issue_description(action_item: ActionItem) -> str:
    """把人工确认后的待办上下文写入 Linear Markdown 描述。"""
    lines = [
        action_item.description or "由 Meeting Execution Agent 从会议草案派发。",
        "",
        "## Meeting context",
        f"- Owner: {action_item.owner_name or 'Unassigned'}",
        f"- Deadline text: {action_item.deadline_text or 'Not provided'}",
        f"- Due at: {action_item.due_at.isoformat() if action_item.due_at else 'Not provided'}",
        f"- Priority: {action_item.priority or 'Not provided'}",
    ]
    if action_item.source_excerpt:
        lines.extend(["", "## Source excerpt", action_item.source_excerpt])
    return "\n".join(lines)
