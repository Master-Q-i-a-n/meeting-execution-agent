import asyncio
from dataclasses import dataclass
from uuid import uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import PointStruct
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.llm.dashscope import embed_texts
from app.models.analysis import AnalysisDraft
from app.models.chunk import MeetingChunk
from app.models.meeting import Meeting
from app.retrieval.qdrant_store import replace_meeting_points

logger = get_logger(__name__)

DEFAULT_CHUNK_MAX_CHARS = 900
DEFAULT_CHUNK_OVERLAP_CHARS = 100
MEETING_CHUNK_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "；",
    "，",
    "、",
    " ",
    "",
]


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str


@dataclass(frozen=True)
class IndexDocument:
    source_type: str
    source_id: str | None
    analysis_draft_id: str | None
    chunk_index: int
    text: str
    source_excerpt: str | None


@dataclass(frozen=True)
class SemanticIndexResult:
    status: str
    chunk_count: int
    error_message: str | None = None


def chunk_meeting_content(
    raw_content: str,
    *,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[TextChunk]:
    """用递归分割器切会议原文，优先保留段落和中文标点边界。"""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    # 递归分割器会按 separators 顺序尝试切分：
    # 先尽量保留段落，再退到句号、逗号，最后才按字符长度硬切。
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=overlap_chars,
        separators=MEETING_CHUNK_SEPARATORS,
        length_function=len,
        keep_separator=True,
        strip_whitespace=True,
    )
    texts = [text for text in splitter.split_text(raw_content) if text.strip()]
    return [TextChunk(chunk_index=index, text=text) for index, text in enumerate(texts)]


def build_index_documents(meeting: Meeting, draft: AnalysisDraft) -> list[IndexDocument]:
    """把原文 chunk、决策和待办统一成待向量化文档。"""
    # 原文索引保存会议上下文，后续追问时可以召回原始表述。
    documents = [
        IndexDocument(
            source_type="transcript",
            source_id=None,
            analysis_draft_id=None,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            source_excerpt=chunk.text,
        )
        for chunk in chunk_meeting_content(meeting.raw_content or "")
    ]

    # 决策和待办单独做文档，能让“谁负责什么”这类问题更容易命中结构化结果。
    documents.extend(
        IndexDocument(
            source_type="decision",
            source_id=item.id,
            analysis_draft_id=draft.id,
            chunk_index=index,
            text=f"决策：{item.summary}",
            source_excerpt=item.source_excerpt,
        )
        for index, item in enumerate(draft.decisions)
    )
    documents.extend(
        IndexDocument(
            source_type="action_item",
            source_id=item.id,
            analysis_draft_id=draft.id,
            chunk_index=index,
            text=_build_action_item_text(item),
            source_excerpt=item.source_excerpt,
        )
        for index, item in enumerate(draft.action_items)
    )
    return documents


async def index_meeting_documents(
    *,
    db: AsyncSession,
    meeting: Meeting,
    draft: AnalysisDraft,
) -> SemanticIndexResult:
    """重建当前会议的语义索引，并把结果状态回写 MySQL。"""
    documents = build_index_documents(meeting, draft)
    logger.info(
        "语义索引文档构建完成 meeting_id=%s draft_id=%s document_count=%s decisions=%s action_items=%s",
        meeting.id,
        draft.id,
        len(documents),
        len(draft.decisions),
        len(draft.action_items),
    )
    # 当前策略是按会议整体重建索引，先清理旧的 MySQL chunk 映射。
    await db.execute(delete(MeetingChunk).where(MeetingChunk.meeting_id == meeting.id))

    chunks = [_build_meeting_chunk(meeting, document) for document in documents]
    db.add_all(chunks)
    # Qdrant payload 要用 chunk.id，所以先 flush 让 ORM 映射进入当前事务。
    await db.flush()

    try:
        # embedding 和 Qdrant 客户端是同步调用，放到线程中避免阻塞异步数据库流程。
        logger.info(
            "语义索引向量化开始 meeting_id=%s draft_id=%s document_count=%s",
            meeting.id,
            draft.id,
            len(documents),
        )
        vectors = await asyncio.to_thread(embed_texts, [document.text for document in documents])
        logger.info(
            "语义索引向量化完成 meeting_id=%s draft_id=%s vector_count=%s",
            meeting.id,
            draft.id,
            len(vectors),
        )
        points = build_qdrant_points(
            meeting_id=meeting.id,
            draft_status=draft.status,
            chunks=chunks,
            documents=documents,
            vectors=vectors,
        )
        logger.info(
            "语义索引写入 Qdrant 开始 meeting_id=%s draft_id=%s point_count=%s",
            meeting.id,
            draft.id,
            len(points),
        )
        await asyncio.to_thread(replace_meeting_points, meeting_id=meeting.id, points=points)
    except Exception as exc:
        # 草稿已经成功生成时，索引失败只记录状态，不能把草稿结果一起抹掉。
        error_message = str(exc)
        logger.exception(
            "语义索引写入失败 meeting_id=%s draft_id=%s error=%s",
            meeting.id,
            draft.id,
            error_message,
        )
        for chunk in chunks:
            chunk.index_status = "failed"
            chunk.error_message = error_message
        await db.flush()
        return SemanticIndexResult(
            status="failed",
            chunk_count=len(chunks),
            error_message=error_message,
        )

    for chunk in chunks:
        chunk.index_status = "indexed"
        chunk.error_message = None
    await db.flush()
    logger.info(
        "语义索引写入成功 meeting_id=%s draft_id=%s chunk_count=%s",
        meeting.id,
        draft.id,
        len(chunks),
    )
    return SemanticIndexResult(status="indexed", chunk_count=len(chunks))


def build_qdrant_points(
    *,
    meeting_id: str,
    draft_status: str,
    chunks: list[MeetingChunk],
    documents: list[IndexDocument],
    vectors: list[list[float]],
) -> list[PointStruct]:
    """把 MySQL chunk 映射和向量组合成 Qdrant points。"""
    if not (len(chunks) == len(documents) == len(vectors)):
        raise ValueError("chunks, documents and vectors must have the same length")

    points: list[PointStruct] = []
    for chunk, document, vector in zip(chunks, documents, vectors, strict=True):
        # payload 放回查业务事实所需的关联键，也保留检索结果可展示的文本。
        points.append(
            PointStruct(
                id=chunk.qdrant_point_id,
                vector=vector,
                payload={
                    "meeting_id": meeting_id,
                    "chunk_id": chunk.id,
                    "chunk_type": _payload_chunk_type(document.source_type),
                    "text": chunk.text,
                    "source_id": document.source_id,
                    "draft_id": document.analysis_draft_id,
                    "status": draft_status,
                    "source_excerpt": document.source_excerpt,
                },
            )
        )
    return points


def _build_meeting_chunk(meeting: Meeting, document: IndexDocument) -> MeetingChunk:
    chunk_id = str(uuid4())
    # MySQL chunk ID 与 Qdrant point ID 保持一致，后续更新和回查更直接。
    return MeetingChunk(
        id=chunk_id,
        meeting_id=meeting.id,
        analysis_draft_id=document.analysis_draft_id,
        source_type=document.source_type,
        source_id=document.source_id,
        chunk_index=document.chunk_index,
        text=document.text,
        qdrant_point_id=chunk_id,
        index_status="pending",
    )


def _build_action_item_text(item) -> str:
    # 向量化时把负责人和截止时间一起拼进文本，语义检索能命中这些关键信息。
    parts = [f"待办：{item.title}"]
    if item.description:
        parts.append(f"说明：{item.description}")
    if item.owner_name:
        parts.append(f"负责人：{item.owner_name}")
    if item.deadline_text:
        parts.append(f"截止时间：{item.deadline_text}")
    return "\n".join(parts)


def _payload_chunk_type(source_type: str) -> str:
    if source_type == "transcript":
        return "transcript_chunk"
    return source_type
