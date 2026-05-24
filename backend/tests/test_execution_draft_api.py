from fastapi.testclient import TestClient

import app.api.routers.analysis_drafts as analysis_drafts_router


async def _missing_draft(*_args, **_kwargs):
    return None


def test_confirm_draft_returns_404_when_draft_is_missing(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(analysis_drafts_router, "_load_analysis_draft_detail", _missing_draft)

    response = client.post("/analysis-drafts/missing/confirm")

    assert response.status_code == 404
    assert response.json()["detail"] == "analysis draft not found"


def test_edit_action_item_returns_404_when_draft_is_missing(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(analysis_drafts_router, "_load_analysis_draft_detail", _missing_draft)

    response = client.patch(
        "/analysis-drafts/missing/action-items/item-1",
        json={"owner_name": "张三"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "analysis draft not found"


def test_dispatch_draft_returns_404_when_draft_is_missing(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(analysis_drafts_router, "_load_analysis_draft_detail", _missing_draft)

    response = client.post("/analysis-drafts/missing/dispatch")

    assert response.status_code == 404
    assert response.json()["detail"] == "analysis draft not found"
