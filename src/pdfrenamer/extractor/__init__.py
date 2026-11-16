# -*- coding: utf-8 -*-
"""PDF 后端工厂。切换后端只需改 config.backend，业务代码零改动。"""
from __future__ import annotations

from .base import BasePdfExtractor, TextDoc, clean_pdf_text, classify_text, page_indices
from .pdfplumber_extractor import PdfPlumberExtractor
from .pymupdf_extractor import PyMuPdfExtractor
from .pypdf_extractor import PyPdfExtractor

_REGISTRY = {
    "pymupdf": PyMuPdfExtractor,
    "pypdf": PyPdfExtractor,
    "pdfplumber": PdfPlumberExtractor,
}


def get_extractor(backend: str = "pymupdf") -> BasePdfExtractor:
    cls = _REGISTRY.get(backend)
    if cls is None:
        cls = PyMuPdfExtractor
    return cls()


def available_backends() -> list[str]:
    return list(_REGISTRY.keys())


__all__ = [
    "BasePdfExtractor", "TextDoc", "clean_pdf_text", "classify_text",
    "page_indices", "get_extractor", "available_backends",
]
