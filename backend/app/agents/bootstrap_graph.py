from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph


class WorkflowState(TypedDict):
    """LangGraph 图里流转的状态。

    state 可以理解为“工作流上下文”：每个节点都会读取 state，并返回一部分新 state。
    LangGraph 会把节点返回值合并回总 state，然后传给下一个节点。
    """

    meeting_id: str
    status: str
    current_step: str
    steps: list[str]
    context: dict[str, Any]
    error_message: str | None


def validate_input(state: WorkflowState) -> dict[str, Any]:
    """第一个节点：校验输入。

    node 是 LangGraph 的一个处理步骤。这里先只检查 meeting_id，
    后面真实流程里可以改成检查 MySQL 里是否存在这场会议。
    """
    meeting_id = state["meeting_id"].strip()
    if not meeting_id:
        raise ValueError("meeting_id is required")

    return {
        "meeting_id": meeting_id,
        "status": "validating",
        "current_step": "validate_input",
        "steps": [*state["steps"], "validate_input"],
    }


def prepare_context(state: WorkflowState) -> dict[str, Any]:
    """第二个节点：准备上下文。

    现在只是模拟准备完成。后面这里会扩展为读取会议原文、查询历史记忆等。
    """
    return {
        "status": "preparing",
        "current_step": "prepare_context",
        "steps": [*state["steps"], "prepare_context"],
        "context": {
            "source": "debug",
            "ready": True,
        },
    }


def finish(state: WorkflowState) -> dict[str, Any]:
    """最后一个节点：标记流程完成。"""
    return {
        "status": "ok",
        "current_step": "finish",
        "steps": [*state["steps"], "finish"],
        "error_message": None,
    }


@lru_cache
def build_bootstrap_graph():
    """构建并编译最小 LangGraph。

    StateGraph 是 LangGraph 的图构建器。
    edge 表示节点之间的流转方向：A -> B 代表 A 执行完后进入 B。
    """
    graph = StateGraph(WorkflowState)

    graph.add_node("validate_input", validate_input)
    graph.add_node("prepare_context", prepare_context)
    graph.add_node("finish", finish)

    graph.set_entry_point("validate_input")
    graph.add_edge("validate_input", "prepare_context")
    graph.add_edge("prepare_context", "finish")
    graph.add_edge("finish", END)

    return graph.compile()


def run_bootstrap_graph(meeting_id: str) -> WorkflowState:
    """运行最小工作流，并返回最终 state。"""
    initial_state: WorkflowState = {
        "meeting_id": meeting_id,
        "status": "pending",
        "current_step": "start",
        "steps": [],
        "context": {},
        "error_message": None,
    }

    graph = build_bootstrap_graph()
    return graph.invoke(initial_state)
