# -*- coding: utf-8 -*-
"""可选备用后端：pdfplumber（MIT）。中文版式兼容性略差，作为兜底。"""
from __future__ import annotations

from pathlib import Path

from .base import BasePdfExtractor, TextDoc, classify_text, clean_pdf_text, page_indices


class PdfPlumberExtractor(BasePdfExtractor):
    name = "pdfplumber"

    def extract(self, path: str | Path, first_pages: int = 3, last_pages: int = 0,
                start_page: int = 0) -> TextDoc:
        try:
            import pdfplumber
        except ImportError as exc:
            return self._failure(exc)
        try:
            with pdfplumber.open(str(path)) as pdf:
                count = len(pdf.pages)
                try:
                    metadata = {str(k): str(v) for k, v in dict(pdf.metadata or {}).items() if v}
                except Exception:
                    metadata = {}
                try:
                    head_text = pdf.pages[0].extract_text() or "" if count else ""
                except Exception:
                    head_text = ""
                parts = []
                for i in page_indices(count, first_pages, last_pages, start_page):
                    try:
                        parts.append(pdf.pages[i].extract_text() or "")
                    except Exception:
                        parts.append("")
                text = clean_pdf_text("\n".join(parts))
        except Exception as exc:
            return self._failure(exc)
        status, note = classify_text(text)
        return TextDoc(text, status, len(text.replace("\n", "").strip()), count, note,
                       metadata=metadata, head_text=head_text, start_page=start_page)
