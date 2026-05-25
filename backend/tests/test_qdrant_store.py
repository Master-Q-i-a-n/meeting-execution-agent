from app.core.config import config
from app.retrieval import qdrant_store
from app.retrieval.qdrant_store import (
    MEETING_CHUNKS_COLLECTION,
    build_debug_vector,
    delete_meeting_points,
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


def test_delete_meeting_points_filters_by_meeting_id(monkeypatch) -> None:
    """删除会议时只清理同一个 meeting_id 的 Qdrant points。"""
    captured_kwargs = {}

    class FakeQdrantClient:
        def collection_exists(self, collection_name: str) -> bool:
            assert collection_name == MEETING_CHUNKS_COLLECTION
            return True

        def delete(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(qdrant_store, "get_qdrant_client", lambda: FakeQdrantClient())

    result = delete_meeting_points(meeting_id="meeting-1")

    assert result["status"] == "ok"
    assert result["meeting_id"] == "meeting-1"
    assert captured_kwargs["collection_name"] == MEETING_CHUNKS_COLLECTION
    assert captured_kwargs["wait"] is True
