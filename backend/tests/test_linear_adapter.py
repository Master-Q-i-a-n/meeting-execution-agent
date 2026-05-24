import pytest

from app.integrations.linear import LinearIntegrationError, LinearTaskDispatchAdapter
from app.models.analysis import ActionItem


class FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self.payload)


def test_linear_adapter_creates_issue_and_keeps_key_out_of_request_record() -> None:
    client = FakeClient(
        {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "issue-1",
                        "identifier": "MEE-10",
                        "title": "完成后端联调",
                        "url": "https://linear.app/test/issue/MEE-10",
                    },
                }
            }
        }
    )
    action_item = ActionItem(
        id="action-1",
        title="完成后端联调",
        owner_name="张三",
        deadline_text="本周五",
        priority="high",
        source_excerpt="张三负责联调。",
    )
    adapter = LinearTaskDispatchAdapter(
        api_key="linear-secret",
        team_id="team-1",
        client=client,
    )

    request_json = adapter.build_create_request(action_item)
    result = adapter.create_task(action_item)

    assert result.external_task_id == "issue-1"
    assert result.external_identifier == "MEE-10"
    assert "张三" in request_json["description"]
    assert "linear-secret" not in str(request_json)
    assert client.calls[0]["headers"]["Authorization"] == "linear-secret"


def test_linear_adapter_rejects_graphql_errors() -> None:
    adapter = LinearTaskDispatchAdapter(
        api_key="linear-secret",
        team_id="team-1",
        client=FakeClient({"errors": [{"message": "permission denied"}]}),
    )

    with pytest.raises(LinearIntegrationError, match="permission denied"):
        adapter.create_task(ActionItem(id="action-1", title="联调"))


def test_linear_adapter_rejects_unsuccessful_issue_create() -> None:
    adapter = LinearTaskDispatchAdapter(
        api_key="linear-secret",
        team_id="team-1",
        client=FakeClient({"data": {"issueCreate": {"success": False}}}),
    )

    with pytest.raises(LinearIntegrationError, match="did not succeed"):
        adapter.create_task(ActionItem(id="action-1", title="联调"))
