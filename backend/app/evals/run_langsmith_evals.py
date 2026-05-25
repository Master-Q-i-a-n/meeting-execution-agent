from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from typing import Any

from langsmith import evaluate

from app.core.config import config
from app.evals.dataset_loader import (
    ALL_SUITES,
    EXTRACTION_SUITE,
    LANGSMITH_DATASET_NAME,
    QA_SUITE,
    TOOL_STABILITY_SUITE,
    load_meeting_eval_cases,
)
from app.evals.evaluators import (
    EXTRACTION_EVALUATORS,
    QA_EVALUATORS,
    TOOL_STABILITY_EVALUATORS,
)
from app.evals.langsmith_sync import (
    get_langsmith_client,
    list_langsmith_examples_for_suite,
    sync_langsmith_dataset,
)
from app.evals.targets import (
    run_extraction_target,
    run_qa_target,
    run_tool_stability_target,
)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    _configure_langsmith_environment()

    cases = load_meeting_eval_cases()
    client = get_langsmith_client()
    sync_result = sync_langsmith_dataset(
        cases,
        client=client,
        dataset_name=args.dataset,
        suite=args.suite,
    )
    print(
        "LangSmith dataset sync:",
        f"dataset={sync_result.dataset_name}",
        f"created_dataset={sync_result.created_dataset}",
        f"created_examples={sync_result.created_examples}",
        f"skipped_examples={sync_result.skipped_examples}",
        f"total={sync_result.total_examples}",
    )

    suites = list(ALL_SUITES if args.suite == "all" else [args.suite])
    for suite in suites:
        _run_suite(client=client, dataset_name=args.dataset, suite=suite, limit=args.limit)


def _run_suite(*, client: Any, dataset_name: str, suite: str, limit: int | None) -> None:
    examples = list_langsmith_examples_for_suite(
        client=client,
        dataset_name=dataset_name,
        suite=suite,
    )
    if limit is not None:
        examples = examples[:limit]
    if not examples:
        print(f"Skip suite={suite}: no examples found.")
        return

    target, evaluators = _suite_runtime(suite)
    print(f"Running LangSmith suite={suite} examples={len(examples)}")
    evaluate(
        target,
        data=examples,
        evaluators=evaluators,
        client=client,
        experiment_prefix=f"meeting-execution-agent-{suite}",
        description=f"Meeting Execution Agent {suite} evals with DashScope and local services.",
        metadata={
            "suite": suite,
            "dataset": dataset_name,
            "llm_model": config.llm_model,
            "embedding_model": config.embedding_model,
        },
        max_concurrency=0,
        blocking=True,
        error_handling="log",
    )


def _suite_runtime(suite: str) -> tuple[Any, list[Any]]:
    if suite == EXTRACTION_SUITE:
        return run_extraction_target, EXTRACTION_EVALUATORS
    if suite == QA_SUITE:
        return run_qa_target, QA_EVALUATORS
    if suite == TOOL_STABILITY_SUITE:
        return run_tool_stability_target, TOOL_STABILITY_EVALUATORS
    raise ValueError(f"unsupported eval suite: {suite}")


def _configure_langsmith_environment() -> None:
    # LangSmith SDK still reads these from the process environment for tracing.
    os.environ.setdefault("LANGSMITH_TRACING", str(config.langsmith_tracing).lower())
    os.environ.setdefault("LANGSMITH_PROJECT", config.langsmith_project)
    if config.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", config.langsmith_api_key)
    if config.langsmith_endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", config.langsmith_endpoint)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Meeting Execution Agent LangSmith evals.")
    parser.add_argument(
        "--suite",
        choices=["all", *ALL_SUITES],
        default="all",
        help="Eval suite to run.",
    )
    parser.add_argument(
        "--dataset",
        default=LANGSMITH_DATASET_NAME,
        help="LangSmith dataset name.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional per-suite example limit for smoke testing.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
