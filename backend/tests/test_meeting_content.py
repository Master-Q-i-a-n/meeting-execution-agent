from io import BytesIO

import pytest
from docx import Document

from app.services.meeting_content import (
    EmptyMeetingContent,
    UnsupportedMeetingFileType,
    normalize_pasted_content,
    parse_uploaded_meeting_file,
)


def test_normalize_pasted_content_strips_outer_blank_lines() -> None:
    """粘贴文本会被清理成后续解析更稳定的格式。"""
    content = normalize_pasted_content("\n\n会议结论：继续推进\r\n负责人：张三  \n")

    assert content == "会议结论：继续推进\n负责人：张三"


def test_parse_markdown_file_as_text() -> None:
    """Markdown 阶段二先作为纯文本保存，后续再做结构化解析。"""
    parsed = parse_uploaded_meeting_file(
        filename="weekly.md",
        content="# 周会\n\n- 李四负责接口联调".encode(),
        content_type="text/markdown",
    )

    assert parsed.source_type == "markdown"
    assert "李四负责接口联调" in parsed.text
    assert parsed.metadata["filename"] == "weekly.md"


def test_parse_docx_file_extracts_paragraph_text() -> None:
    """Word docx 可以抽取段落文本，先覆盖最常见会议纪要格式。"""
    document = Document()
    document.add_paragraph("项目复盘会议")
    document.add_paragraph("王五下周三前完成风险清单")
    buffer = BytesIO()
    document.save(buffer)

    parsed = parse_uploaded_meeting_file(
        filename="review.docx",
        content=buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert parsed.source_type == "word"
    assert "王五下周三前完成风险清单" in parsed.text


def test_parse_uploaded_file_rejects_unsupported_extension() -> None:
    """当前阶段不支持的文件类型要明确报错。"""
    with pytest.raises(UnsupportedMeetingFileType):
        parse_uploaded_meeting_file(filename="image.png", content=b"fake")


def test_parse_uploaded_file_rejects_empty_text() -> None:
    """空文件或解析后为空的文件不能进入后续 Agent 流程。"""
    with pytest.raises(EmptyMeetingContent):
        parse_uploaded_meeting_file(filename="empty.txt", content=b"")
