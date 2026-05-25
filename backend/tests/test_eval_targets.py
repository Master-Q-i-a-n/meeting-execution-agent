from app.evals.targets import run_extraction_target, run_tool_stability_target


def test_run_extraction_target_normalizes_missing_owner(monkeypatch) -> None:
    def fake_extract_meeting_draft_json(**kwargs):
        return {
            "decision_summary": "",
            "decisions": [],
            "action_items": [
                {
                    "title": "sync payment callback",
                    "description": None,
                    "owner_name": "TBD",
                    "deadline_text": "Friday",
                    "due_at": None,
                    "source_excerpt": "TBD owner sync payment callback by Friday",
                    "confidence": 0.8,
                }
            ],
            "risk_items": [],
            "unconfirmed_items": [],
        }

    monkeypatch.setattr(
        "app.evals.targets.extract_meeting_draft_json",
        fake_extract_meeting_draft_json,
    )

    outputs = run_extraction_target(
        {
            "raw_content": "TBD owner sync payment callback by Friday",
            "occurred_at": "2026-05-20T10:00:00",
        }
    )

    assert outputs["schema_valid"] is True
    assert outputs["action_items"][0]["owner_name"] is None
    assert len(outputs["unconfirmed_items"]) == 1


def test_run_tool_stability_target_does_not_create_external_task() -> None:
    outputs = run_tool_stability_target(
        {
            "provider": "linear",
            "draft_id": "draft-1",
            "action_item_id": "action-1",
        }
    )

    assert outputs["provider"] == "linear"
    assert outputs["idempotent"] is True
    assert outputs["created_external_task"] is False
