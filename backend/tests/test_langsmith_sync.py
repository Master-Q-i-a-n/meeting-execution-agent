from types import SimpleNamespace

from app.evals.dataset_loader import EXTRACTION_SUITE, load_meeting_eval_cases
from app.evals.langsmith_sync import (
    list_langsmith_examples_for_suite,
    sync_langsmith_dataset,
)


class FakeLangSmithClient:
    def __init__(self) -> None:
        self.dataset_exists = False
        self.created_datasets: list[str] = []
        self.examples: list[SimpleNamespace] = []

    def has_dataset(self, *, dataset_name: str) -> bool:
        return self.dataset_exists

    def create_dataset(self, *, dataset_name: str, **kwargs) -> SimpleNamespace:
        self.dataset_exists = True
        self.created_datasets.append(dataset_name)
        return SimpleNamespace(name=dataset_name, **kwargs)

    def list_examples(self, *, dataset_name: str) -> list[SimpleNamespace]:
        return self.examples

    def create_example(self, *, inputs, outputs, metadata, split, dataset_name):
        example = SimpleNamespace(
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            split=split,
            dataset_name=dataset_name,
        )
        self.examples.append(example)
        return example


def test_sync_langsmith_dataset_is_idempotent() -> None:
    client = FakeLangSmithClient()
    cases = load_meeting_eval_cases()[:2]

    first = sync_langsmith_dataset(
        cases,
        client=client,
        dataset_name="meeting-execution-agent-test",
        suite=EXTRACTION_SUITE,
    )
    second = sync_langsmith_dataset(
        cases,
        client=client,
        dataset_name="meeting-execution-agent-test",
        suite=EXTRACTION_SUITE,
    )

    assert client.created_datasets == ["meeting-execution-agent-test"]
    assert first.created_examples == 2
    assert first.skipped_examples == 0
    assert second.created_examples == 0
    assert second.skipped_examples == 2
    assert len(client.examples) == 2


def test_list_langsmith_examples_for_suite_filters_metadata() -> None:
    client = FakeLangSmithClient()
    client.examples = [
        SimpleNamespace(metadata={"suite": "extraction"}),
        SimpleNamespace(metadata={"suite": "qa"}),
    ]

    examples = list_langsmith_examples_for_suite(
        client=client,
        dataset_name="meeting-execution-agent-test",
        suite="qa",
    )

    assert len(examples) == 1
    assert examples[0].metadata["suite"] == "qa"
