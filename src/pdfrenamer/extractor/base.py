# -*- coding: utf-8 -*-
"""PDF 文本层提取抽象层。

只读 PDF 的既有文本层，不做 OCR、不做任何模型推理、不联网。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..models import DOC_ENCRYPTED, DOC_ERROR, DOC_GARBLED, DOC_NO_TEXT, DOC_OK

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS = re.compile(r"[ \t\u00a0\u3000]+")


@dataclass
class TextDoc:
    text: str
    status: str = DOC_OK
    chars: int = 0
    pages: int = 0
    note: str = ""
    # 论文结构化解析所需的原始信息（纯本地读取，不含任何推理）
    metadata: dict = field(default_factory=dict)
    head_text: str = ""   # 首页未重排的原文，保留标题/作者的行边界


def clean_pdf_text(raw: str) -> str:
    """逐行 NFKC 归一化，保留换行结构（关键词取值依赖行边界）。"""
    if not raw:
        return ""
    lines: list[str] = []
    for line in str(raw).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        t = unicodedata.normalize("NFKC", line)
        t = _ZERO_WIDTH.sub("", t)
        t = _CONTROL.sub(" ", t)
        t = _WS.sub(" ", t).strip()
        lines.append(t)
    return "\n".join(lines)


def classify_text(text: str, min_chars: int = 20) -> tuple[str, str]:
    """根据文本层质量判定文档状态。"""
    stripped = re.sub(r"\s+", "", text)
    n = len(stripped)
    if n < min_chars:
        return DOC_NO_TEXT, "未检测到有效文本层（可能是扫描件/图片型 PDF）"
    bad = text.count("\ufffd") + len(re.findall(r"[\ue000-\uf8ff]", text))
    if bad / max(1, n) > 0.15:
        return DOC_GARBLED, "文本层疑似乱码（嵌入字体缺少 ToUnicode 映射）"
    return DOC_OK, ""


def page_indices(page_count: int, first_pages: int = 3, last_pages: int = 0) -> list[int]:
    """按「前 N 页 + 后 M 页」选取，去重并保持原顺序。"""
    if page_count <= 0:
        return []
    head = list(range(min(page_count, max(0, first_pages))))
    tail = list(range(max(0, page_count - last_pages), page_count)) if last_pages > 0 else []
    seen: set[int] = set()
    out: list[int] = []
    for i in head + tail:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


class BasePdfExtractor:
    name = "base"

    def extract(self, path: str | Path, first_pages: int = 3, last_pages: int = 0) -> TextDoc:
        raise NotImplementedError

    def _failure(self, exc: Exception, pages: int = 0) -> TextDoc:
        msg = str(exc)
        status = DOC_ENCRYPTED if ("password" in msg.lower() or "encrypt" in msg.lower()) else DOC_ERROR
        return TextDoc("", status, 0, pages, f"{type(exc).__name__}: {msg}")
