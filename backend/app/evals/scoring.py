from __future__ import annotations

from typing import Any


def score_extraction_result(
    *,
    actual_outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, float]:
    """Rule-based extraction scores that can be reused by LangSmith evaluators."""
    expected_actions = reference_outputs.get("expected_action_items", [])
    actual_actions = actual_outputs.get("action_items", [])
    expected_questions = reference_outputs.get("expected_unconfirmed_questions", [])
    actual_questions = actual_outputs.get("unconfirmed_items", [])

    return {
        "action_item_recall": _score_action_recall(expected_actions, actual_actions),
        "owner_accuracy": _score_owner_accuracy(expected_actions, actual_actions),
        "deadline_accuracy": _score_deadline_accuracy(expected_actions, actual_actions),
        "clarification_accuracy": _score_clarifications(
            expected_questions, actual_questions
        ),
    }


def score_qa_result(
    *,
    actual_outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, float]:
    """Score whether the answer and citations hit the expected facts."""
    answer = _normalize_text(actual_outputs.get("answer"))
    expected_answer_keywords = [
        _normalize_text(keyword)
        for keyword in reference_outputs.get("expected_answer_keywords", [])
    ]
    citations = actual_outputs.get("citations", [])
    citation_text = _normalize_text(
        " ".join(
            str(citation.get("text") or citation.get("source_excerpt") or "")
            for citation in citations
        )
    )
    expected_citation_keywords = [
        _normalize_text(keyword)
        for keyword in reference_outputs.get("expected_citation_keywords", [])
    ]

    return {
        "qa_answer_grounded": _score_keywords(answer, expected_answer_keywords),
        "citation_hit": _score_keywords(citation_text, expected_citation_keywords),
    }


def score_tool_stability_result(
    *,
    actual_outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, float]:
    """Score local tool invariants without calling real external systems."""
    expected_provider = reference_outputs.get("expected_provider")
    expected_idempotent = reference_outputs.get("expected_idempotent")
    return {
        "tool_idempotency_stable": float(
            actual_outputs.get("idempotent") is expected_idempotent
        ),
        "tool_provider_match": float(actual_outputs.get("provider") == expected_provider),
    }


def _score_action_recall(
    expected_actions: list[dict[str, Any]], actual_actions: list[dict[str, Any]]
) -> float:
    if not expected_actions:
        return 1.0
    matched = sum(
        1
        for expected in expected_actions
        if _find_matching_action(expected, actual_actions) is not None
    )
    return matched / len(expected_actions)


def _score_owner_accuracy(
    expected_actions: list[dict[str, Any]], actual_actions: list[dict[str, Any]]
) -> float:
    checked = 0
    matched = 0
    for expected in expected_actions:
        if "owner_name" not in expected:
            continue
        actual = _find_matching_action(expected, actual_actions)
        if actual is None:
            continue
        checked += 1
        expected_owner = _normalize_text(expected.get("owner_name"))
        actual_owner = _normalize_text(actual.get("owner_name"))
        if expected_owner == actual_owner:
            matched += 1
    return 1.0 if checked == 0 else matched / checked


def _score_deadline_accuracy(
    expected_actions: list[dict[str, Any]], actual_actions: list[dict[str, Any]]
) -> float:
    checked = 0
    matched = 0
    for expected in expected_actions:
        if "due_at" not in expected and "deadline_text" not in expected:
            continue
        actual = _find_matching_action(expected, actual_actions)
        if actual is None:
            continue
        checked += 1
        expected_due_at = _normalize_text(expected.get("due_at"))
        expected_deadline = _normalize_text(expected.get("deadline_text"))
        actual_due_at = _normalize_text(actual.get("due_at"))
        actual_deadline = _normalize_text(actual.get("deadline_text"))
        if expected_due_at and actual_due_at.startswith(expected_due_at):
            matched += 1
        elif expected_deadline and expected_deadline in actual_deadline:
            matched += 1
    return 1.0 if checked == 0 else matched / checked


def _score_clarifications(
    expected_questions: list[dict[str, Any]], actual_questions: list[dict[str, Any]]
) -> float:
    if not expected_questions:
        return 1.0
    matched = 0
    actual_texts = [
        _normalize_text(question.get("question"))
        + _normalize_text(question.get("description"))
        for question in actual_questions
    ]
    for expected in expected_questions:
        keywords = [_normalize_text(keyword) for keyword in expected.get("keywords", [])]
        if keywords and any(all(keyword in actual_text for keyword in keywords) for actual_text in actual_texts):
            matched += 1
    return matched / len(expected_questions)


def _find_matching_action(
    expected: dict[str, Any],
    actual_actions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    keywords = [_normalize_text(keyword) for keyword in expected.get("title_keywords", [])]
    for actual in actual_actions:
        text = "".join(
            [
                _normalize_text(actual.get("title")),
                _normalize_text(actual.get("description")),
                _normalize_text(actual.get("source_excerpt")),
            ]
        )
        if keywords and all(keyword in text for keyword in keywords):
            return actual
    return None


def _score_keywords(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    matched = sum(1 for keyword in keywords if keyword and keyword in text)
    return matched / len(keywords)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "")
