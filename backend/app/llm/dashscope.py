import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from openai import OpenAI, OpenAIError

from app.core.config import config
from app.core.logger import get_logger

logger = get_logger(__name__)

MEETING_ANALYSIS_PROMPT_VERSION = "meeting-draft-v1"
EMBEDDING_BATCH_SIZE = 10


@dataclass(frozen=True)
class TranscribedAudioSegment:
    """百炼 ASR 标准化后的语音片段。"""

    text: str
    start_time: float | None = None
    end_time: float | None = None
    speaker: str | None = None
    emotion: str | None = None
    confidence: float | None = None


class DashScopeConfigurationError(RuntimeError):
    """百炼配置缺失，当前还不能调用模型。"""


class DashScopeResponseError(RuntimeError):
    """百炼返回的内容不能进入后续结构化校验。"""


class DashScopeEmbeddingError(RuntimeError):
    """百炼 embedding 返回数量或向量维度不符合配置。"""


@lru_cache
def get_dashscope_client() -> OpenAI:
    """统一创建百炼 OpenAI-compatible 客户端。"""
    if not config.dashscope_api_key:
        raise DashScopeConfigurationError("DASHSCOPE_API_KEY is required")
    logger.info("百炼客户端创建 base_url=%s", config.dashscope_base_url)
    return OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)


def extract_meeting_draft_json(
    *,
    raw_content: str,
    occurred_at: datetime | None,
    client: Any | None = None,
) -> dict[str, Any]:
    """让百炼把会议纪要转成 JSON 草稿。

    这里先只负责拿到 JSON 字典；字段是否合法由后面的 Pydantic 节点校验。
    """
    logger.info(
        "百炼会议解析请求开始 model=%s content_chars=%s",
        config.llm_model,
        len(raw_content),
    )
    response = (client or get_dashscope_client()).chat.completions.create(
        model=config.llm_model,
        temperature=config.llm_temperature,
        max_tokens=config.llm_max_output_tokens,
        response_format={"type": "json_object"},
        messages=build_meeting_analysis_messages(
            raw_content=raw_content,
            occurred_at=occurred_at,
        ),
    )

    content = response.choices[0].message.content
    if not content:
        raise DashScopeResponseError("DashScope returned empty meeting analysis content")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DashScopeResponseError("DashScope returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise DashScopeResponseError("DashScope JSON root must be an object")
    logger.info(
        "百炼会议解析请求完成 model=%s result_keys=%s",
        config.llm_model,
        sorted(parsed.keys()),
    )
    return parsed


def transcribe_audio_file(
    *,
    content: bytes,
    mime_type: str,
    client: Any | None = None,
) -> list[TranscribedAudioSegment]:
    """调用 Qwen ASR，把本地上传音频转成带时间戳的片段。"""
    logger.info(
        "百炼 ASR 请求开始 model=%s audio_bytes=%s mime_type=%s",
        config.asr_model,
        len(content),
        mime_type,
    )
    try:
        response = (client or get_dashscope_client()).chat.completions.create(
            model=config.asr_model,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": _build_data_url(content=content, mime_type=mime_type),
                        },
                    },
                ],
            }
        ],
        extra_body={
            "asr_options": {
                "enable_itn": True,
            }
        },
        timeout=240,
    )
    except OpenAIError as exc:
        raise DashScopeResponseError(f"DashScope ASR request failed: {exc}") from exc
    message = response.choices[0].message
    segments = _extract_audio_segments_from_message(message)
    if not segments:
        content_text = (message.content or "").strip()
        if content_text:
            metadata = _extract_audio_metadata(message)
            segments = [
                TranscribedAudioSegment(
                    text=content_text,
                    emotion=_optional_str(metadata.get("emotion")),
                    confidence=_float_value(metadata.get("confidence")),
                )
            ]
    if not segments:
        raise DashScopeResponseError("DashScope ASR returned no transcript")
    logger.info("百炼 ASR 请求完成 segment_count=%s", len(segments))
    return segments


def ocr_meeting_image(
    *,
    content: bytes,
    mime_type: str,
    client: Any | None = None,
) -> str:
    """调用 Qwen VL OCR，把会议图片或手写纪要转成纯文本。"""
    logger.info(
        "百炼 OCR 请求开始 model=%s image_bytes=%s mime_type=%s",
        config.vision_model,
        len(content),
        mime_type,
    )
    try:
        response = (client or get_dashscope_client()).chat.completions.create(
            model=config.vision_model,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _build_data_url(content=content, mime_type=mime_type),
                            },
                        },
                        {
                            "type": "text",
                            "text": "请只提取图片中的会议纪要文字，保持原有段落和列表结构，不要补充解释。",
                        },
                    ],
                }
            ],
        )
    except OpenAIError as exc:
        raise DashScopeResponseError(f"DashScope OCR request failed: {exc}") from exc
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise DashScopeResponseError("DashScope OCR returned empty text")
    logger.info("百炼 OCR 请求完成 text_chars=%s", len(text))
    return text


def embed_texts(
    texts: Sequence[str],
    *,
    client: Any | None = None,
) -> list[list[float]]:
    """批量生成文本向量，返回顺序和输入文本顺序一致。"""
    if not texts:
        return []

    embedding_client = client or get_dashscope_client()
    vectors: list[list[float]] = []
    logger.info(
        "百炼 embedding 请求开始 model=%s text_count=%s dimensions=%s",
        config.embedding_model,
        len(texts),
        config.embedding_dimensions,
    )

    # text-embedding-v3 的批量输入需要控制单次条数，避免一个请求塞得太满。
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = list(texts[start : start + EMBEDDING_BATCH_SIZE])
        response = embedding_client.embeddings.create(
            model=config.embedding_model,
            input=batch,
            dimensions=config.embedding_dimensions,
            encoding_format="float",
        )
        data = sorted(response.data, key=lambda item: item.index)
        if len(data) != len(batch):
            raise DashScopeEmbeddingError("DashScope embedding count does not match input count")

        for item in data:
            vector = list(item.embedding)
            if len(vector) != config.embedding_dimensions:
                raise DashScopeEmbeddingError(
                    "DashScope embedding dimensions do not match EMBEDDING_DIMENSIONS"
                )
            vectors.append(vector)

    logger.info("百炼 embedding 请求完成 vector_count=%s", len(vectors))
    return vectors


def generate_meeting_question_answer(
    *,
    question: str,
    citations: list[dict[str, Any]],
    structured_facts: dict[str, Any],
    client: Any | None = None,
) -> str:
    """基于检索证据生成会后追问答案。

    追问答案不是开放聊天，只允许引用 MySQL 和 Qdrant 找到的会议证据。
    """
    logger.info(
        "百炼追问回答请求开始 model=%s citation_count=%s",
        config.llm_model,
        len(citations),
    )
    response = (client or get_dashscope_client()).chat.completions.create(
        model=config.llm_model,
        temperature=0.1,
        max_tokens=config.llm_max_output_tokens,
        messages=build_meeting_question_answer_messages(
            question=question,
            citations=citations,
            structured_facts=structured_facts,
        ),
    )
    content = response.choices[0].message.content
    if not content:
        raise DashScopeResponseError("DashScope returned empty question answer content")
    logger.info("百炼追问回答请求完成 answer_chars=%s", len(content.strip()))
    return content.strip()


def build_meeting_question_answer_messages(
    *,
    question: str,
    citations: list[dict[str, Any]],
    structured_facts: dict[str, Any],
) -> list[dict[str, str]]:
    """构造追问回答提示词，强制模型只基于证据回答。"""
    evidence_json = json.dumps(
        {
            "citations": citations,
            "structured_facts": structured_facts,
        },
        ensure_ascii=False,
        default=str,
    )
    system_prompt = """
你是会议执行追问助手。
你只能基于提供的 citations 和 structured_facts 回答。
如果证据不足，直接说明“没有找到足够的会议依据回答这个问题”。
回答中涉及具体结论时，尽量用 [1]、[2] 这样的编号引用 citations 的顺序。
不要编造负责人、截止时间、会议结论或外部任务状态。
""".strip()
    user_prompt = f"""
用户问题：
{question}

检索证据 JSON：
{evidence_json}
""".strip()
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_meeting_analysis_messages(
    *,
    raw_content: str,
    occurred_at: datetime | None,
) -> list[dict[str, str]]:
    """构造抽取提示词。

    百炼 JSON mode 需要提示词里明确写出 JSON，这里把返回契约也一起写清楚。
    """
    occurred_at_text = occurred_at.isoformat() if occurred_at is not None else "未提供"
    system_prompt = """
你是会议执行草稿抽取助手。
你只能依据用户提供的会议原文抽取信息，不要编造负责人、截止时间、风险或决策。
请只输出一个 JSON 对象，不要输出 Markdown、解释、代码块或额外文本。
JSON 必须包含 decision_summary、decisions、action_items、risk_items、unconfirmed_items。
每个数组字段即使没有内容也返回 []。
due_at 仅在能够根据会议时间确定时返回 ISO 8601 datetime，否则返回 null。
deadline_text 要保留原文里的截止时间表达，例如“下周三”。
每条决策、待办、风险和未确认项尽量附带 source_excerpt。
confidence 是 0 到 1 之间的数字；不确定时可返回 null。
""".strip()
    system_prompt = f"""{system_prompt}
如果待办负责人写成“某人”“待定”“负责人待定”“未知”“unknown”“TBD”，这不是有效负责人，owner_name 必须返回 null。
如果负责人或截止时间不明确，不要猜测；请在 unconfirmed_items 里写出需要用户澄清的问题。
后端还会再次校验 owner_name 和 due_at/deadline_text，所以 JSON 必须如实表达不确定性。
如果原文包含类似 [00:00:12-00:00:18][pause=800ms][neutral][slow] 的语音线索，
它们只能作为风险、犹豫、不确定性和优先级判断的辅助信号，不是会议事实本身。
明显停顿、语速变慢或犹豫表述可以进入 risk_items 或 unconfirmed_items，但不要据此编造结论。
""".strip()
    user_prompt = f"""
请把下面会议纪要抽取为 JSON。

会议发生时间：
{occurred_at_text}

JSON 结构：
{{
  "decision_summary": "本次会议决策摘要",
  "decisions": [
    {{
      "summary": "决策内容",
      "source_excerpt": "原文片段",
      "confidence": 0.9
    }}
  ],
  "action_items": [
    {{
      "title": "待办标题",
      "description": "待办说明",
      "owner_name": "负责人名称或 null",
      "deadline_text": "原文截止时间或 null",
      "due_at": "ISO 8601 datetime 或 null",
      "source_excerpt": "原文片段",
      "confidence": 0.9
    }}
  ],
  "risk_items": [
    {{
      "title": "风险标题",
      "description": "风险说明",
      "source_excerpt": "原文片段",
      "confidence": 0.8
    }}
  ],
  "unconfirmed_items": [
    {{
      "question": "需要确认的问题",
      "description": "为什么需要确认",
      "source_excerpt": "原文片段",
      "confidence": 0.7
    }}
  ]
}}

会议原文：
{raw_content}
""".strip()
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_data_url(*, content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_audio_segments_from_message(message: Any) -> list[TranscribedAudioSegment]:
    annotations = _as_plain_data(getattr(message, "annotations", None))
    candidates = _collect_segment_candidates(annotations)
    segments: list[TranscribedAudioSegment] = []
    seen: set[tuple[str, float | None, float | None]] = set()
    for candidate in candidates:
        segment = _parse_audio_segment(candidate)
        if segment is None:
            continue
        key = (segment.text, segment.start_time, segment.end_time)
        if key in seen:
            continue
        seen.add(key)
        segments.append(segment)
    return segments


def _extract_audio_metadata(message: Any) -> dict[str, Any]:
    annotations = _as_plain_data(getattr(message, "annotations", None))
    if isinstance(annotations, list):
        for item in annotations:
            if isinstance(item, dict):
                audio_info = item.get("audio_info")
                return audio_info if isinstance(audio_info, dict) else item
    if isinstance(annotations, dict):
        audio_info = annotations.get("audio_info")
        return audio_info if isinstance(audio_info, dict) else annotations
    return {}


def _collect_segment_candidates(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        candidates: list[dict[str, Any]] = []
        for item in value:
            candidates.extend(_collect_segment_candidates(item))
        return candidates
    if not isinstance(value, dict):
        return []

    candidates = []
    for key in ("segments", "sentences", "sentence", "transcripts"):
        nested = value.get(key)
        if isinstance(nested, list):
            candidates.extend(item for item in nested if isinstance(item, dict))

    if value.get("text") or value.get("transcript"):
        candidates.append(value)

    for nested_value in value.values():
        if isinstance(nested_value, dict | list):
            candidates.extend(_collect_segment_candidates(nested_value))
    return candidates


def _parse_audio_segment(data: dict[str, Any]) -> TranscribedAudioSegment | None:
    text = str(data.get("text") or data.get("transcript") or "").strip()
    if not text:
        return None
    return TranscribedAudioSegment(
        text=text,
        start_time=_seconds_value(data.get("start_time") or data.get("begin_time") or data.get("start")),
        end_time=_seconds_value(data.get("end_time") or data.get("finish_time") or data.get("end")),
        speaker=_optional_str(data.get("speaker") or data.get("speaker_id")),
        emotion=_optional_str(data.get("emotion")),
        confidence=_float_value(data.get("confidence")),
    )


def _as_plain_data(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_as_plain_data(item) for item in value]
    if isinstance(value, dict):
        return {key: _as_plain_data(item) for key, item in value.items()}
    return value


def _seconds_value(value: Any) -> float | None:
    number = _float_value(value)
    if number is None:
        return None
    # 部分 ASR 返回毫秒，数值很大时转换成秒。
    return number / 1000 if number > 10000 else number


def _float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
