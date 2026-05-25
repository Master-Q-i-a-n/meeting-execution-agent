from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langsmith import Client

from app.core.config import config
from app.evals.dataset_loader import (
    LANGSMITH_DATASET_NAME,
    EvalCase,
    build_langsmith_example_payloads,
)


@dataclass(frozen=True)
class LangSmithDatasetSyncResult:
    dataset_name: str
    created_dataset: bool
    created_examples: int
    skipped_examples: int
    total_examples: int


def get_langsmith_client() -> Client:
    """Create a LangSmith client from .env-backed settings."""
    return Client(
        api_key=config.langsmith_api_key,
        api_url=config.langsmith_endpoint or None,
    )


def sync_langsmith_dataset(
    cases: list[EvalCase],
    *,
    client: Any | None = None,
    dataset_name: str = LANGSMITH_DATASET_NAME,
    suite: str = "all",
) -> LangSmithDatasetSyncResult:
    """Create the LangSmith dataset and idempotently add missing examples.

    Re-running the command is safe: examples are keyed by metadata.eval_case_id and
    existing rows are skipped instead of duplicated.
    """
    active_client = client or get_langsmith_client()
    payloads = build_langsmith_example_payloads(cases, suite=suite)
    created_dataset = _ensure_dataset(active_client, dataset_name)
    existing_ids = _list_existing_eval_case_ids(active_client, dataset_name)

    created_examples = 0
    skipped_examples = 0
    for payload in payloads:
        eval_case_id = payload["metadata"]["eval_case_id"]
        if eval_case_id in existing_ids:
            skipped_examples += 1
            continue
        active_client.create_example(
            dataset_name=dataset_name,
            inputs=payload["inputs"],
            outputs=payload["outputs"],
            metadata=payload["metadata"],
            split=payload["split"],
        )
        existing_ids.add(eval_case_id)
        created_examples += 1

    return LangSmithDatasetSyncResult(
        dataset_name=dataset_name,
        created_dataset=created_dataset,
        created_examples=created_examples,
        skipped_examples=skipped_examples,
        total_examples=len(payloads),
    )


def list_langsmith_examples_for_suite(
    *,
    client: Any,
    dataset_name: str,
    suite: str,
) -> list[Any]:
    """Fetch examples for one suite from the shared dataset."""
    return [
        example
        for example in client.list_examples(dataset_name=dataset_name)
        if _get_example_metadata(example).get("suite") == suite
    ]


def _ensure_dataset(client: Any, dataset_name: str) -> bool:
    if client.has_dataset(dataset_name=dataset_name):
        return False
    client.create_dataset(
        dataset_name=dataset_name,
        description="Meeting Execution Agent v1 offline eval cases.",
        metadata={"app": "meeting-execution-agent", "version": "v1"},
    )
    return True


def _list_existing_eval_case_ids(client: Any, dataset_name: str) -> set[str]:
    existing_ids: set[str] = set()
    for example in client.list_examples(dataset_name=dataset_name):
        eval_case_id = _get_example_metadata(example).get("eval_case_id")
        if eval_case_id:
            existing_ids.add(str(eval_case_id))
    return existing_ids


def _get_example_metadata(example: Any) -> dict[str, Any]:
    if isinstance(example, dict):
        return dict(example.get("metadata") or {})
    return dict(getattr(example, "metadata", None) or {})
