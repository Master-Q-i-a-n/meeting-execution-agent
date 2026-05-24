from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import config
from app.core.logger import get_logger

logger = get_logger(__name__)

MEETING_CHUNKS_COLLECTION = "meeting_chunks"
DEBUG_POINT_ID = "00000000-0000-0000-0000-000000000001"


class QdrantCollectionMismatchError(RuntimeError):
    """本地 collection 还是旧向量维度时给出明确报错。"""


@dataclass(frozen=True)
class SemanticSearchPoint:
    """Qdrant 语义检索返回的单条结果。"""

    point_id: str
    score: float | None
    payload: dict[str, Any]


def get_qdrant_client() -> QdrantClient:
    """创建 Qdrant 客户端。

    Qdrant 是独立的向量数据库服务，后端通过 HTTP 地址连接它。
    当前地址来自 .env 里的 QDRANT_URL，例如 http://127.0.0.1:6333。
    """
    return QdrantClient(
        url=config.qdrant_url,
        timeout=3,
        # 本地 Qdrant 访问不能走系统代理，否则 Windows 代理可能返回 502。
        trust_env=False,
        # 本地开发已知版本兼容，跳过启动时版本探测，避免无意义 warning。
        check_compatibility=False,
    )


def build_debug_vector() -> list[float]:
    """生成阶段一使用的固定测试向量。

    真实项目里这里会换成 OpenAI embedding 生成的向量。
    向量长度必须和 collection 创建时的 vector size 一致，否则 Qdrant 会拒绝写入。
    """
    vector = [0.0] * config.embedding_dimensions
    vector[0] = 1.0
    vector[1] = 0.5
    vector[2] = 0.25
    return vector


def check_qdrant_connection() -> bool:
    """检查 Qdrant 是否可连接。"""
    logger.info("Qdrant 连接检查开始 url=%s", config.qdrant_url)
    client = get_qdrant_client()
    client.get_collections()
    logger.info("Qdrant 连接检查成功 url=%s", config.qdrant_url)
    return True


def ensure_meeting_chunks_collection() -> dict[str, Any]:
    """创建或确认 meeting_chunks collection。

    collection 可以理解为 Qdrant 里的“表”。
    meeting_chunks 以后专门保存会议原文片段、决策片段、待办片段的向量。
    """
    client = get_qdrant_client()

    if not client.collection_exists(MEETING_CHUNKS_COLLECTION):
        logger.info(
            "Qdrant collection 不存在，开始创建 collection=%s vector_size=%s",
            MEETING_CHUNKS_COLLECTION,
            config.embedding_dimensions,
        )
        client.create_collection(
            collection_name=MEETING_CHUNKS_COLLECTION,
            vectors_config=VectorParams(
                size=config.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )
    else:
        collection = client.get_collection(MEETING_CHUNKS_COLLECTION)
        vector_size = getattr(collection.config.params.vectors, "size", None)
        if vector_size != config.embedding_dimensions:
            logger.error(
                "Qdrant collection 维度不匹配 collection=%s actual=%s expected=%s",
                MEETING_CHUNKS_COLLECTION,
                vector_size,
                config.embedding_dimensions,
            )
            raise QdrantCollectionMismatchError(
                "meeting_chunks vector size mismatch: "
                f"collection={vector_size}, config={config.embedding_dimensions}. "
                "Rebuild the development collection before indexing."
            )
    logger.info(
        "Qdrant collection 已就绪 collection=%s vector_size=%s",
        MEETING_CHUNKS_COLLECTION,
        config.embedding_dimensions,
    )

    return {
        "status": "ok",
        "collection": MEETING_CHUNKS_COLLECTION,
        "vector_size": config.embedding_dimensions,
        "distance": "COSINE",
    }


def replace_meeting_points(*, meeting_id: str, points: list[PointStruct]) -> None:
    """先清理旧会议 point，再写入当前原文/决策/待办 point。"""
    logger.info(
        "Qdrant 替换会议 points 开始 meeting_id=%s point_count=%s",
        meeting_id,
        len(points),
    )
    ensure_meeting_chunks_collection()
    client = get_qdrant_client()
    client.delete(
        collection_name=MEETING_CHUNKS_COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="meeting_id", match=MatchValue(value=meeting_id))]
        ),
        wait=True,
    )
    if points:
        client.upsert(
            collection_name=MEETING_CHUNKS_COLLECTION,
            points=points,
            wait=True,
        )
    logger.info(
        "Qdrant 替换会议 points 完成 meeting_id=%s point_count=%s",
        meeting_id,
        len(points),
    )


def search_meeting_chunks(
    *,
    query_vector: list[float],
    limit: int,
    meeting_id: str | None = None,
) -> list[SemanticSearchPoint]:
    """按问题向量检索会议片段，供会后追问使用。

    meeting_id 为空时就是跨会议检索；传入时只检索单场会议。
    """
    logger.info(
        "Qdrant 语义检索开始 meeting_id=%s limit=%s",
        meeting_id or "all",
        limit,
    )
    ensure_meeting_chunks_collection()
    client = get_qdrant_client()
    query_filter = None
    if meeting_id is not None:
        query_filter = Filter(
            must=[FieldCondition(key="meeting_id", match=MatchValue(value=meeting_id))]
        )

    response = client.query_points(
        collection_name=MEETING_CHUNKS_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    points = [
        SemanticSearchPoint(
            point_id=str(point.id),
            score=point.score,
            payload=point.payload or {},
        )
        for point in response.points
    ]
    logger.info(
        "Qdrant 语义检索完成 meeting_id=%s result_count=%s",
        meeting_id or "all",
        len(points),
    )
    return points


def upsert_debug_point() -> dict[str, Any]:
    """写入一条测试 point。

    point 是 Qdrant 里的基本数据单位，通常包含：
    1. id：唯一标识。
    2. vector：用于相似度检索的向量。
    3. payload：业务元数据，例如 meeting_id、文本内容、来源等。
    """
    ensure_meeting_chunks_collection()
    client = get_qdrant_client()

    payload = {
        "meeting_id": "debug-meeting",
        "chunk_type": "transcript",
        "text": "这是一段测试会议内容",
        "source": "debug",
    }

    client.upsert(
        collection_name=MEETING_CHUNKS_COLLECTION,
        points=[
            PointStruct(
                id=DEBUG_POINT_ID,
                vector=build_debug_vector(),
                payload=payload,
            )
        ],
        wait=True,
    )

    return {
        "status": "ok",
        "collection": MEETING_CHUNKS_COLLECTION,
        "point_id": DEBUG_POINT_ID,
        "payload": payload,
    }


def search_debug_point(limit: int = 3) -> dict[str, Any]:
    """用固定测试向量搜索 meeting_chunks。

    这个接口用于证明 Qdrant 能把刚写入的测试 point 搜回来。
    后续真实追问会把用户问题转成 embedding，再用类似方式做语义搜索。
    """
    ensure_meeting_chunks_collection()
    client = get_qdrant_client()

    response = client.query_points(
        collection_name=MEETING_CHUNKS_COLLECTION,
        query=build_debug_vector(),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    points = [
        {
            "id": str(point.id),
            "score": point.score,
            "payload": point.payload,
        }
        for point in response.points
    ]

    return {
        "status": "ok",
        "collection": MEETING_CHUNKS_COLLECTION,
        "points": points,
    }
