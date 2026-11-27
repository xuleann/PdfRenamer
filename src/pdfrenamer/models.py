# -*- coding: utf-8 -*-
"""数据模型：字段定义、提取结果、重命名记录。

纯数据结构，不依赖任何第三方库，便于单元测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 字段级状态
ST_OK = "ok"              # 正则命中
ST_FALLBACK = "fallback"  # 关键词命中
ST_HEURISTIC = "heuristic"  # 启发式兜底（需人工复核）
ST_MANUAL = "manual"      # V1.1.2 人工补录
ST_MISSING = "missing"    # 未提取到

# 文档级状态
DOC_OK = "ok"
DOC_PARTIAL = "partial"
DOC_NO_TEXT = "no_text_layer"
DOC_GARBLED = "garbled"
DOC_ENCRYPTED = "encrypted"
DOC_ERROR = "error"
# V1.1.1：合同模式下判定为「非合同文档」（绩效评价报告/工作方案等），不参与改名
DOC_NOT_CONTRACT = "not_contract"

SKIP_DOC_STATUSES = {DOC_NO_TEXT, DOC_GARBLED, DOC_ENCRYPTED, DOC_ERROR,
                     DOC_NOT_CONTRACT}

FIELD_TYPES = ("text", "list", "year", "company", "date", "money",
               "idcard", "enum", "person_name")


@dataclass
class Field:
    """一条「需要提取的信息」的定义。"""
    name: str
    keywords: list[str] = field(default_factory=list)
    regex: str = ""
    enabled: bool = True
    required: bool = False
    type: str = "text"
    max_len: int = 0          # 用于文件名的最大字符数，0 表示不限制
    source: str = ""          # 可选的结构化来源，如 paper_title / paper_year
    choices: list[str] = field(default_factory=list)  # V1.2.0：enum 字段的候选枚举项

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "keywords": list(self.keywords),
            "regex": self.regex,
            "enabled": bool(self.enabled),
            "required": bool(self.required),
            "type": self.type,
            "max_len": int(self.max_len),
            "source": self.source,
            "choices": list(self.choices),
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Field":
        t = str(d.get("type", "text"))
        if t not in FIELD_TYPES:
            t = "text"
        return Field(
            name=str(d.get("name", "")).strip(),
            keywords=[str(k) for k in d.get("keywords", []) if str(k).strip()],
            regex=str(d.get("regex", "") or ""),
            enabled=bool(d.get("enabled", True)),
            required=bool(d.get("required", False)),
            type=t,
            max_len=int(d.get("max_len", 0) or 0),
            source=str(d.get("source", "") or ""),
            choices=[str(c) for c in d.get("choices", []) if str(c).strip()],
        )


@dataclass
class FieldResult:
    """单个字段的提取结果。value 用于 Excel 展示，file_value 用于文件名。"""
    name: str
    value: str = ""
    file_value: str = ""
    status: str = ST_MISSING
    note: str = ""
    # V1.4.9：提取不可信时分配的核对占位符（如乙方 xx1/xx2），
    # 用于重命名与 Excel 展示，人工补录后自动清空。空串表示未分配。
    review_code: str = ""

    @property
    def is_missing(self) -> bool:
        return self.status == ST_MISSING or not self.value


@dataclass
class ExtractResult:
    """单个 PDF 的完整提取结果。"""
    path: str
    original_name: str
    mode: str
    fields: dict[str, FieldResult] = field(default_factory=dict)
    doc_status: str = DOC_OK
    text_chars: int = 0
    note: str = ""
    # V1.3.0：手写敏感字段的局部截图（字段名 -> 压缩 PNG 字节），嵌入 Excel 供人工核对
    field_images: dict[str, bytes] = field(default_factory=dict)

    @property
    def skip_reason(self) -> str:
        return {
            DOC_NO_TEXT: "无文本层（扫描件），需人工处理",
            DOC_GARBLED: "文本乱码，需人工处理",
            DOC_ENCRYPTED: "PDF 已加密，需人工处理",
            DOC_ERROR: "PDF 读取失败，需人工处理",
            DOC_NOT_CONTRACT: "判定为非合同文档（绩效评价报告/工作方案等），不参与改名",
        }.get(self.doc_status, "")

    def missing_names(self) -> list[str]:
        return [n for n, r in self.fields.items() if r.is_missing]


@dataclass
class RenameRecord:
    """一条重命名计划 / 执行记录。"""
    src: str
    dst: str
    original: str
    new_name: str
    status: str = "planned"   # planned / done / skipped / failed / unchanged
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "src": self.src, "dst": self.dst,
            "original": self.original, "new_name": self.new_name,
            "status": self.status, "reason": self.reason,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "RenameRecord":
        return RenameRecord(
            src=str(d.get("src", "")), dst=str(d.get("dst", "")),
            original=str(d.get("original", "")), new_name=str(d.get("new_name", "")),
            status=str(d.get("status", "planned")), reason=str(d.get("reason", "")),
        )
