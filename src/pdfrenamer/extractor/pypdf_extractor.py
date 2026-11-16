# -*- coding: utf-8 -*-
"""可选备用后端：pypdf（纯 Python，BSD）。"""
from __future__ import annotations

from pathlib import Path

from ..models import DOC_ENCRYPTED
from .base import BasePdfExtractor, TextDoc, classify_text, clean_pdf_text, page_indices


class PyPdfExtractor(BasePdfExtractor):
    name = "pypdf"

    def extract(self, path: str | Path, first_pages: int = 3, last_pages: int = 0) -> TextDoc:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            return self._failure(exc)
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    return TextDoc("", DOC_ENCRYPTED, 0, len(reader.pages), "PDF 已加密，需要密码")
            count = len(reader.pages)
            try:
                metadata = {str(k).lstrip("/"): str(v) for k, v in dict(reader.metadata or {}).items() if v}
            except Exception:
                metadata = {}
            try:
                head_text = reader.pages[0].extract_text() or "" if count else ""
            except Exception:
                head_text = ""
            parts = []
            for i in page_indices(count, first_pages, last_pages):
                try:
                    parts.append(reader.pages[i].extract_text() or "")
                except Exception:
                    parts.append("")
            text = clean_pdf_text("\n".join(parts))
        except Exception as exc:
            return self._failure(exc)
        status, note = classify_text(text)
        return TextDoc(text, status, len(text.replace("\n", "").strip()), count, note,
                       metadata=metadata, head_text=head_text)
