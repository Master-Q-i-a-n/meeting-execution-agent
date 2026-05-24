from dataclasses import dataclass
from typing import Protocol

from app.models.analysis import ActionItem


@dataclass(frozen=True)
class ExternalTaskCreateResult:
    """Adapter 统一返回的外部任务创建结果。"""

    provider: str
    external_task_id: str
    external_identifier: str | None
    external_url: str | None
    response_json: dict


class TaskDispatchAdapter(Protocol):
    provider: str

    def build_create_request(self, action_item: ActionItem) -> dict:
        """生成可记录到 tool_calls 的安全请求体。"""

    def create_task(self, action_item: ActionItem) -> ExternalTaskCreateResult:
        """在外部系统创建任务。"""


class MockTaskDispatchAdapter:
    """Jira、飞书和日历的 v1 mock，先固定 adapter 边界。"""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def build_create_request(self, action_item: ActionItem) -> dict:
        return {
            "provider": self.provider,
            "title": action_item.title,
            "mock": True,
        }

    def create_task(self, action_item: ActionItem) -> ExternalTaskCreateResult:
        return ExternalTaskCreateResult(
            provider=self.provider,
            external_task_id=f"mock-{self.provider}-{action_item.id}",
            external_identifier=f"MOCK-{action_item.id[:8]}",
            external_url=None,
            response_json={"mock": True, "title": action_item.title},
        )
