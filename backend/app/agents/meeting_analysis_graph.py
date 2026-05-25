# ruff: noqa: F401,F403,I001
"""兼容旧导入路径。

真实长流程已经从“会议分析图”升级为“会议执行图”，新代码请直接导入
app.agents.meeting_execution_graph。这里保留 re-export，避免旧脚本和测试临时断掉。
"""

from app.agents.meeting_execution_graph import *  # noqa: F403
from app.agents import meeting_execution_graph as _execution_graph
from app.agents.meeting_execution_graph import (  # noqa: F401
    MeetingExecutionState as MeetingAnalysisState,
    build_meeting_execution_graph as build_meeting_analysis_graph,
    resume_meeting_execution_workflow as resume_meeting_workflow,
    run_meeting_execution_graph as run_meeting_analysis_graph,
)

_build_dispatch_payload = _execution_graph._build_dispatch_payload
_build_initial_state = _execution_graph._build_initial_state
_build_resume_state = _execution_graph._build_resume_state
_invoke_graph = _execution_graph._invoke_graph
_load_draft_detail = _execution_graph._load_draft_detail
_record_analysis_failure = _execution_graph._record_analysis_failure
_route_from_dispatch_result = _execution_graph._route_from_dispatch_result
_route_from_input_quality = _execution_graph._route_from_input_quality
_route_from_resume_action = _execution_graph._route_from_resume_action
_route_from_unconfirmed_items = _execution_graph._route_from_unconfirmed_items
_update_workflow = _execution_graph._update_workflow
