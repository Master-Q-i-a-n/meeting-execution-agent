from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import Any

from docx import Document
from pypdf import PdfReader

MAX_MEETING_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_MEETING_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}


class MeetingContentError(ValueError):
    """会议内容解析失败时抛出的业务异常。"""


class UnsupportedMeetingFileType(MeetingContentError):
    """上传文件类型不在当前阶段支持范围内。"""


class EmptyMeetingContent(MeetingContentError):
    """解析后没有得到有效会议文本。"""


@dataclass(frozen=True)
class ParsedMeetingContent:
    """不同输入格式统一后的会议内容。

    后续 LLM 解析、分块入 Qdrant、追问检索都优先消费这里的 text。
    """

    source_type: str
    text: str
    metadata: dict[str, Any]


def normalize_pasted_content(content: str) -> str:
    """清洗用户直接粘贴的会议纪要文本。"""
    normalized = _normalize_text(content)
    if not normalized:
        raise EmptyMeetingContent("meeting content is empty")
    return normalized


def parse_uploaded_meeting_file(
    *,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> ParsedMeetingContent:
    """把上传的 txt/Markdown/PDF/Word 文件解析成纯文本。

    阶段二先只做“格式统一”，暂时不在这里做摘要、待办抽取。
    """
    if not content:
        raise EmptyMeetingContent("uploaded file is empty")

    suffix = PurePath(filename).suffix.lower()
    if suffix not in SUPPORTED_MEETING_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_MEETING_EXTENSIONS))
        raise UnsupportedMeetingFileType(f"unsupported meeting file type: {suffix or 'unknown'}; supported: {supported}")

    # 先按文件类型抽取文本，后面的会议分析只面对统一的纯文本。
    if suffix == ".txt":
        source_type = "text"
        text = _decode_text_bytes(content)
    elif suffix in {".md", ".markdown"}:
        source_type = "markdown"
        text = _decode_text_bytes(content)
    elif suffix == ".pdf":
        source_type = "pdf"
        text = _extract_pdf_text(content)
    else:
        # python-docx 只支持 docx；老式 .doc 后续可通过转换服务补上。
        source_type = "word"
        text = _extract_docx_text(content)

    # 不同解析器抽出的换行和空白风格不一致，入库前统一清洗一遍。
    normalized = _normalize_text(text)
    if not normalized:
        raise EmptyMeetingContent("no readable meeting content was extracted")

    # metadata 留下输入来源，后续排查“这段正文从哪里来”会轻松很多。
    return ParsedMeetingContent(
        source_type=source_type,
        text=normalized,
        metadata={
            "input_mode": "upload",
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(content),
        },
    )


def build_paste_metadata(content: str) -> dict[str, Any]:
    """构造粘贴文本的 metadata，方便后续追踪来源。"""
    return {
        "input_mode": "paste",
        "size_chars": len(content),
    }


def _decode_text_bytes(content: bytes) -> str:
    """尽量兼容常见中文会议纪要编码。"""
    # utf-8-sig 先处理带 BOM 的文本，gb18030 兼容常见中文本地文件。
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise MeetingContentError("text file encoding is not supported")


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise MeetingContentError(f"failed to read PDF file: {exc}") from exc

    # pypdf 按页抽取文本；扫描版 PDF 需要 OCR，放到后续阶段。
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page_text for page_text in pages if page_text.strip())


def _extract_docx_text(content: bytes) -> str:
    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise MeetingContentError(f"failed to read Word docx file: {exc}") from exc

    parts: list[str] = []
    parts.extend(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())

    # 表格里也经常有负责人/截止时间，所以把单元格文本一起保留下来。
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)

    return "\n".join(parts)


def _normalize_text(content: str) -> str:
    # 数据库中统一保存 \n，避免 Windows 和其他来源的换行符混杂。
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()
