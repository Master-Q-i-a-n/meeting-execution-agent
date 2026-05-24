from app.core.config import config
from app.retrieval import qdrant_store
from app.retrieval.qdrant_store import (
    MEETING_CHUNKS_COLLECTION,
    build_debug_vector,
    get_qdrant_client,
)


def test_debug_vector_matches_embedding_dimensions() -> None:
    """测试向量维度必须和 embedding 配置一致。"""
    vector = build_debug_vector()

    assert len(vector) == config.embedding_dimensions
    assert vector[:3] == [1.0, 0.5, 0.25]


def test_meeting_chunks_collection_name() -> None:
    """阶段一固定使用 meeting_chunks 作为会议片段 collection。"""
    assert MEETING_CHUNKS_COLLECTION == "meeting_chunks"


def test_qdrant_client_disables_proxy_and_compatibility_check(monkeypatch) -> None:
    """本地 Qdrant 客户端不要读取系统代理，避免 127.0.0.1 请求被代理成 502。"""
    captured_kwargs = {}

    class FakeQdrantClient:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(qdrant_store, "QdrantClient", FakeQdrantClient)

    client = get_qdrant_client()

    assert isinstance(client, FakeQdrantClient)
    assert captured_kwargs["url"] == config.qdrant_url
    assert captured_kwargs["timeout"] == 3
    assert captured_kwargs["trust_env"] is False
    assert captured_kwargs["check_compatibility"] is False
