from app.evals.scoring import (
    score_extraction_result,
    score_qa_result,
    score_tool_stability_result,
)


def test_score_extraction_result_scores_matching_mock_output() -> None:
    reference_outputs = {
        "expected_action_items": [
            {
                "title_keywords": ["支付回调", "联调"],
                "owner_name": "张三",
                "due_at": "2026-05-22",
            },
            {
                "title_keywords": ["灰度开关", "文档"],
                "owner_name": "李四",
                "deadline_text": "本周五",
            },
        ],
        "expected_unconfirmed_questions": [
            {"keywords": ["生产配置", "负责人"]},
        ],
    }
    actual_outputs = {
        "action_items": [
            {
                "title": "完成支付回调接口联调",
                "owner_name": "张三",
                "due_at": "2026-05-22T18:00:00",
            },
            {
                "title": "补充灰度开关文档",
                "owner_name": "李四",
                "deadline_text": "本周五下班前",
            },
        ],
        "unconfirmed_items": [
            {"question": "待办「生产配置核对」的负责人是谁？"},
        ],
    }

    scores = score_extraction_result(
        actual_outputs=actual_outputs,
        reference_outputs=reference_outputs,
    )

    assert scores == {
        "action_item_recall": 1.0,
        "owner_accuracy": 1.0,
        "deadline_accuracy": 1.0,
        "clarification_accuracy": 1.0,
    }


def test_score_extraction_result_penalizes_wrong_owner_and_missing_clarification() -> None:
    reference_outputs = {
        "expected_action_items": [
            {
                "title_keywords": ["支付回调", "联调"],
                "owner_name": "张三",
                "due_at": "2026-05-22",
            }
        ],
        "expected_unconfirmed_questions": [
            {"keywords": ["生产配置", "负责人"]},
        ],
    }
    actual_outputs = {
        "action_items": [
            {
                "title": "完成支付回调接口联调",
                "owner_name": "李四",
                "due_at": "2026-05-23T18:00:00",
            }
        ],
        "unconfirmed_items": [],
    }

    scores = score_extraction_result(
        actual_outputs=actual_outputs,
        reference_outputs=reference_outputs,
    )

    assert scores["action_item_recall"] == 1.0
    assert scores["owner_accuracy"] == 0.0
    assert scores["deadline_accuracy"] == 0.0
    assert scores["clarification_accuracy"] == 0.0


def test_score_qa_result_scores_answer_and_citations() -> None:
    scores = score_qa_result(
        actual_outputs={
            "answer": "张三负责支付回调联调。",
            "citations": [{"text": "张三负责完成支付回调接口联调"}],
        },
        reference_outputs={
            "expected_answer_keywords": ["张三", "支付回调"],
            "expected_citation_keywords": ["张三", "接口联调"],
        },
    )

    assert scores == {"qa_answer_grounded": 1.0, "citation_hit": 1.0}


def test_score_tool_stability_result_scores_idempotency() -> None:
    scores = score_tool_stability_result(
        actual_outputs={"provider": "linear", "idempotent": True},
        reference_outputs={"expected_provider": "linear", "expected_idempotent": True},
    )

    assert scores == {"tool_idempotency_stable": 1.0, "tool_provider_match": 1.0}
