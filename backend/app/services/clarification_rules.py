from app.core.logger import get_logger
from app.schemas.analysis import (
    ExtractedActionItem,
    ExtractedUnconfirmedItem,
    MeetingDraftExtraction,
)

logger = get_logger(__name__)

UNKNOWN_OWNER_TOKENS = {
    "某人",
    "待定",
    "负责人待定",
    "未知",
    "unknown",
    "tbd",
}


def normalize_meeting_clarifications(
    extraction: MeetingDraftExtraction,
) -> MeetingDraftExtraction:
    """补齐模型漏掉的待澄清项。

    LLM 有时会把负责人解析成 null 或“某人”，但忘记写入 unconfirmed_items。
    这里用确定性规则做兜底，让 LangGraph 的等待节点不完全依赖模型自觉。
    """
    normalized_actions = [
        _normalize_action_item_fields(action_item)
        for action_item in extraction.action_items
    ]
    unconfirmed_items = list(extraction.unconfirmed_items)
    existing_keys = {
        _build_unconfirmed_key(item.question, item.source_excerpt)
        for item in unconfirmed_items
    }

    for action_item in normalized_actions:
        generated_items = _build_action_item_clarifications(action_item)
        for item in generated_items:
            key = _build_unconfirmed_key(item.question, item.source_excerpt)
            if key in existing_keys:
                continue
            unconfirmed_items.append(item)
            existing_keys.add(key)

    logger.info(
        "会议澄清项归一完成 action_items=%s unconfirmed=%s",
        len(normalized_actions),
        len(unconfirmed_items),
    )
    return extraction.model_copy(
        update={
            "action_items": normalized_actions,
            "unconfirmed_items": unconfirmed_items,
        }
    )


def _normalize_action_item_fields(action_item: ExtractedActionItem) -> ExtractedActionItem:
    owner_name = action_item.owner_name.strip() if action_item.owner_name else None
    deadline_text = (
        action_item.deadline_text.strip() if action_item.deadline_text else None
    ) or None
    normalized_owner = (
        owner_name
        if owner_name and owner_name.lower() not in UNKNOWN_OWNER_TOKENS
        else None
    )
    return action_item.model_copy(
        update={
            "owner_name": normalized_owner,
            "deadline_text": deadline_text,
        }
    )


def _build_action_item_clarifications(
    action_item: ExtractedActionItem,
) -> list[ExtractedUnconfirmedItem]:
    items: list[ExtractedUnconfirmedItem] = []
    if action_item.owner_name is None:
        items.append(
            ExtractedUnconfirmedItem(
                question=f"待办「{action_item.title}」的负责人是谁？",
                description="该待办缺少明确负责人，确认后才能可靠派发和提醒。",
                source_excerpt=action_item.source_excerpt,
                confidence=action_item.confidence,
            )
        )
    if action_item.deadline_text is None and action_item.due_at is None:
        items.append(
            ExtractedUnconfirmedItem(
                question=f"待办「{action_item.title}」的截止时间是什么？",
                description="该待办缺少截止时间，确认后才能生成到期提醒。",
                source_excerpt=action_item.source_excerpt,
                confidence=action_item.confidence,
            )
        )
    return items


def _build_unconfirmed_key(question: str, source_excerpt: str | None) -> str:
    return f"{question.strip()}::{(source_excerpt or '').strip()}"
