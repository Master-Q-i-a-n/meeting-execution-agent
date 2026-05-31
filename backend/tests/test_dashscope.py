from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.config import config
from app.llm.dashscope import (
    DashScopeEmbeddingError,
    DashScopeResponseError,
    embed_texts,
    extract_meeting_draft_json,
    ocr_meeting_image,
    transcribe_audio_file,
)


class FakeCompletions:
    def __init__(self, content: str, annotations=None) -> None:
        self.content = content
        self.annotations = annotations
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content=self.content, annotations=self.annotations)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, content: str, annotations=None) -> None:
        self.completions = FakeCompletions(content, annotations=annotations)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeEmbeddings:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        data = [
            SimpleNamespace(index=index, embedding=vector)
            for index, vector in enumerate(self.vectors)
        ]
        return SimpleNamespace(data=data)


class FakeEmbeddingClient:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.embeddings = FakeEmbeddings(vectors)


def test_dashscope_adapter_requests_json_mode() -> None:
    """百炼适配层只取 JSON 字典，结构校验交给 Pydantic。"""
    client = FakeClient('{"decision_summary":"继续推进","decisions":[]}')

    result = extract_meeting_draft_json(
        raw_content="会议决定继续推进。",
        occurred_at=datetime(2026, 5, 21, 10, 0),
        client=client,
    )

    assert result["decision_summary"] == "继续推进"
    assert client.completions.kwargs["response_format"] == {"type": "json_object"}
    assert "JSON" in client.completions.kwargs["messages"][0]["content"]


def test_dashscope_adapter_rejects_invalid_json() -> None:
    client = FakeClient("not-json")

    with pytest.raises(DashScopeResponseError, match="invalid JSON"):
        extract_meeting_draft_json(
            raw_content="会议正文",
            occurred_at=None,
            client=client,
        )


def test_dashscope_ocr_uses_image_url_data_url() -> None:
    client = FakeClient("会议纪要：张三负责接口联调。")

    result = ocr_meeting_image(
        content=b"fake-image",
        mime_type="image/png",
        client=client,
    )

    content = client.completions.kwargs["messages"][0]["content"]
    assert result.startswith("会议纪要")
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_dashscope_asr_extracts_annotation_segments() -> None:
    client = FakeClient(
        "",
        annotations=[
            {
                "sentences": [
                    {
                        "text": "张三负责接口联调。",
                        "start_time": 12000,
                        "end_time": 18000,
                        "emotion": "neutral",
                        "confidence": 0.9,
                    }
                ]
            }
        ],
    )

    segments = transcribe_audio_file(
        content=b"fake-audio",
        mime_type="audio/mpeg",
        client=client,
    )

    content = client.completions.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "input_audio"
    assert content[0]["input_audio"]["data"].startswith("data:audio/mpeg;base64,")
    assert segments[0].text == "张三负责接口联调。"
    assert segments[0].start_time == 12
    assert segments[0].end_time == 18
    assert segments[0].emotion == "neutral"


def test_dashscope_embedding_adapter_validates_dimensions() -> None:
    vector = [0.1] * config.embedding_dimensions
    client = FakeEmbeddingClient([vector, vector])

    result = embed_texts(["会议原文", "会议待办"], client=client)

    assert result == [vector, vector]
    assert client.embeddings.kwargs["model"] == config.embedding_model
    assert client.embeddings.kwargs["dimensions"] == config.embedding_dimensions


def test_dashscope_embedding_adapter_rejects_wrong_dimensions() -> None:
    client = FakeEmbeddingClient([[0.1, 0.2]])

    with pytest.raises(DashScopeEmbeddingError, match="dimensions"):
        embed_texts(["会议原文"], client=client)
