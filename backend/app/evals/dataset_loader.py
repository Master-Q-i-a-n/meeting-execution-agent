from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DATASET_PATH = Path(__file__).parent / "datasets" / "meeting_eval_cases.jsonl"
LANGSMITH_DATASET_NAME = "meeting-execution-agent-v1"

EXTRACTION_SUITE = "extraction"
QA_SUITE = "qa"
TOOL_STABILITY_SUITE = "tool_stability"
ALL_SUITES = (EXTRACTION_SUITE, QA_SUITE, TOOL_STABILITY_SUITE)


class EvalCase(BaseModel):
    """Local mirror of one meeting-eval case."""

    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    inputs: dict[str, Any]
    reference_outputs: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_meeting_eval_cases(path: Path = DATASET_PATH) -> list[EvalCase]:
    """Load the JSONL dataset and validate the basic structure with Pydantic."""
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            cases.append(EvalCase.model_validate(payload))
    return cases


def build_langsmith_example_payloads(
    cases: list[EvalCase],
    *,
    suite: str = "all",
) -> list[dict[str, Any]]:
    """Expand local cases into LangSmith examples.

    The same LangSmith dataset stores extraction, QA, and tool-stability examples.
    metadata.suite is the selector used by the runner.
    """
    selected_suites = set(ALL_SUITES if suite == "all" else [suite])
    payloads: list[dict[str, Any]] = []
    if EXTRACTION_SUITE in selected_suites:
        payloads.extend(_build_extraction_payloads(cases))
    if QA_SUITE in selected_suites:
        payloads.extend(_build_qa_payloads(cases))
    if TOOL_STABILITY_SUITE in selected_suites:
        payloads.extend(_build_tool_stability_payloads())
    return payloads


def _build_extraction_payloads(cases: list[EvalCase]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for case in cases:
        payloads.append(
            {
                "inputs": {
                    "case_id": case.case_id,
                    "title": case.title,
                    **case.inputs,
                },
                "outputs": case.reference_outputs,
                "metadata": {
                    **case.metadata,
                    "suite": EXTRACTION_SUITE,
                    "eval_case_id": f"{EXTRACTION_SUITE}:{case.case_id}",
                    "base_case_id": case.case_id,
                    "title": case.title,
                },
                "split": EXTRACTION_SUITE,
            }
        )
    return payloads


def _build_qa_payloads(cases: list[EvalCase]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for case in cases:
        for index, qa_case in enumerate(case.reference_outputs.get("qa_cases", []), start=1):
            eval_case_id = f"{QA_SUITE}:{case.case_id}:{index}"
            payloads.append(
                {
                    "inputs": {
                        "case_id": eval_case_id,
                        "base_case_id": case.case_id,
                        "title": case.title,
                        "raw_content": case.inputs["raw_content"],
                        "occurred_at": case.inputs["occurred_at"],
                        "question": qa_case["question"],
                        "top_k": 5,
                        "eval_meeting_id": f"eval-{case.case_id}",
                    },
                    "outputs": {
                        "expected_answer_keywords": qa_case.get(
                            "expected_answer_keywords", []
                        ),
                        "expected_citation_keywords": qa_case.get(
                            "expected_citation_keywords", []
                        ),
                    },
                    "metadata": {
                        **case.metadata,
                        "suite": QA_SUITE,
                        "eval_case_id": eval_case_id,
                        "base_case_id": case.case_id,
                        "title": case.title,
                    },
                    "split": QA_SUITE,
                }
            )
    return payloads


def _build_tool_stability_payloads() -> list[dict[str, Any]]:
    return [
        {
            "inputs": {
                "case_id": "tool_stability:linear_idempotency",
                "provider": "linear",
                "draft_id": "eval-draft",
                "action_item_id": "eval-action-item",
            },
            "outputs": {
                "expected_idempotent": True,
                "expected_provider": "linear",
            },
            "metadata": {
                "suite": TOOL_STABILITY_SUITE,
                "eval_case_id": "tool_stability:linear_idempotency",
                "tags": ["tool_stability", "idempotency", "linear_mock"],
            },
            "split": TOOL_STABILITY_SUITE,
        }
    ]
