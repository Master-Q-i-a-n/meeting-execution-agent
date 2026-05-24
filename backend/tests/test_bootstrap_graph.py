import pytest

from app.agents.bootstrap_graph import run_bootstrap_graph


def test_bootstrap_graph_success() -> None:
    """最小 LangGraph 流程能按固定节点顺序跑完。"""
    result = run_bootstrap_graph("debug-meeting")

    assert result["meeting_id"] == "debug-meeting"
    assert result["status"] == "ok"
    assert result["current_step"] == "finish"
    assert result["steps"] == ["validate_input", "prepare_context", "finish"]
    assert result["context"] == {"source": "debug", "ready": True}
    assert result["error_message"] is None


def test_bootstrap_graph_requires_meeting_id() -> None:
    """meeting_id 为空时，输入校验节点应该报错。"""
    with pytest.raises(ValueError, match="meeting_id is required"):
        run_bootstrap_graph("")
