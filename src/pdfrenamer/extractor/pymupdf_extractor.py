# -*- coding: utf-8 -*-
"""主 PDF 后端：PyMuPDF 1.26.x（无 ML 依赖）。
必须锁 1.26.x，PyMuPDF>=2.0 会强拉 onnxruntime 等推理库，违反「不嵌 AI」。
"""
from __future__ import annotations

from pathlib import Path

from ..models import DOC_ENCRYPTED
from .base import BasePdfExtractor, TextDoc, classify_text, clean_pdf_text, page_indices


class PyMuPdfExtractor(BasePdfExtractor):
    name = "pymupdf"

    def extract(self, path: str | Path, first_pages: int = 3, last_pages: int = 0) -> TextDoc:
        try:
            import pymupdf  # PyMuPDF 1.24+ 的正式包名
        except ImportError:  # pragma: no cover - 兼容旧版别名
            try:
                import fitz as pymupdf  # type: ignore
            except ImportError as exc:
                return self._failure(exc)

        try:
            with pymupdf.open(str(path)) as doc:
                count = doc.page_count
                if getattr(doc, "needs_pass", False) or getattr(doc, "is_encrypted", False):
                    return TextDoc("", DOC_ENCRYPTED, 0, count, "PDF 已加密，需要密码")
                try:
                    metadata = {k: v for k, v in dict(doc.metadata or {}).items() if v}
                except Exception:
                    metadata = {}
                try:
                    head_text = doc.load_page(0).get_text("text") if count else ""
                except Exception:
                    head_text = ""
                parts = []
                for i in page_indices(count, first_pages, last_pages):
                    try:
                        parts.append(doc.load_page(i).get_text("text", sort=True))
                    except Exception:
                        parts.append("")
                text = clean_pdf_text("\n".join(parts))
        except Exception as exc:
            return self._failure(exc)

        status, note = classify_text(text)
        return TextDoc(text, status, len(text.replace("\n", "").strip()), count, note,
                       metadata=metadata, head_text=head_text)
