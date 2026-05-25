from app.evals.dataset_loader import load_meeting_eval_cases


def test_meeting_eval_dataset_has_twenty_unique_cases() -> None:
    cases = load_meeting_eval_cases()

    assert len(cases) == 20
    assert len({case.case_id for case in cases}) == 20


def test_meeting_eval_dataset_contains_required_fields() -> None:
    cases = load_meeting_eval_cases()

    for case in cases:
        assert case.title
        assert case.inputs["raw_content"]
        assert case.inputs["occurred_at"]
        assert case.reference_outputs["expected_decisions"]
        assert case.reference_outputs["expected_action_items"]
        assert "expected_unconfirmed_questions" in case.reference_outputs
        assert "qa_cases" in case.reference_outputs
        assert case.metadata["tags"]


def test_meeting_eval_dataset_covers_required_scenarios() -> None:
    cases = load_meeting_eval_cases()
    tags = {tag for case in cases for tag in case.metadata["tags"]}

    assert {
        "multi_people",
        "missing_owner",
        "missing_deadline",
        "fuzzy_deadline",
        "multiple_decisions",
        "qa_single_meeting",
        "qa_cross_meeting",
    }.issubset(tags)
