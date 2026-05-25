from __future__ import annotations

from typing import Any

from langsmith.evaluation import run_evaluator

from app.evals.scoring import (
    score_extraction_result,
    score_qa_result,
    score_tool_stability_result,
)


@run_evaluator
def schema_valid(run: Any, example: Any) -> dict[str, Any]:
    outputs = _run_outputs(run)
    return {
        "key": "schema_valid",
        "score": float(outputs.get("schema_valid") is True),
        "comment": outputs.get("error"),
    }


@run_evaluator
def action_item_recall(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "action_item_recall",
        score_extraction_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


@run_evaluator
def owner_accuracy(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "owner_accuracy",
        score_extraction_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


@run_evaluator
def deadline_accuracy(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "deadline_accuracy",
        score_extraction_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


@run_evaluator
def clarification_accuracy(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "clarification_accuracy",
        score_extraction_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


@run_evaluator
def qa_answer_grounded(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "qa_answer_grounded",
        score_qa_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


@run_evaluator
def citation_hit(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "citation_hit",
        score_qa_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


@run_evaluator
def tool_idempotency_stable(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "tool_idempotency_stable",
        score_tool_stability_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


@run_evaluator
def tool_provider_match(run: Any, example: Any) -> dict[str, Any]:
    return _metric_result(
        "tool_provider_match",
        score_tool_stability_result(
            actual_outputs=_run_outputs(run),
            reference_outputs=_example_outputs(example),
        ),
    )


EXTRACTION_EVALUATORS = [
    schema_valid,
    action_item_recall,
    owner_accuracy,
    deadline_accuracy,
    clarification_accuracy,
]
QA_EVALUATORS = [qa_answer_grounded, citation_hit]
TOOL_STABILITY_EVALUATORS = [tool_idempotency_stable, tool_provider_match]


def _metric_result(key: str, scores: dict[str, float]) -> dict[str, Any]:
    return {"key": key, "score": scores[key], "value": scores}


def _run_outputs(run: Any) -> dict[str, Any]:
    if isinstance(run, dict):
        return dict(run.get("outputs") or {})
    return dict(getattr(run, "outputs", None) or {})


def _example_outputs(example: Any) -> dict[str, Any]:
    if example is None:
        return {}
    if isinstance(example, dict):
        return dict(example.get("outputs") or {})
    return dict(getattr(example, "outputs", None) or {})
