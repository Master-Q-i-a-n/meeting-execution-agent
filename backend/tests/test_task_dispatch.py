import pytest

from app.models.analysis import AnalysisDraft
from app.services.task_dispatch import (
    ExternalTaskDispatchError,
    build_dispatch_idempotency_key,
    ensure_draft_can_dispatch,
)


def test_dispatch_idempotency_key_is_stable_per_draft_item() -> None:
    key = build_dispatch_idempotency_key(
        provider="linear",
        draft_id="draft-1",
        action_item_id="action-1",
    )

    assert key == "linear:dispatch:draft-1:action-1"


def test_unconfirmed_draft_cannot_be_dispatched() -> None:
    draft = AnalysisDraft(id="draft-1", meeting_id="meeting-1", status="draft")

    with pytest.raises(ExternalTaskDispatchError, match="cannot be dispatched"):
        ensure_draft_can_dispatch(draft)
