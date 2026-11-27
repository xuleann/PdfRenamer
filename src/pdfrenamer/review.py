# -*- coding: utf-8 -*-
"""核对占位符分配（V1.4.9，纯本地）。

对「乙方」这类开放集手写字段，OCR/正则认不准时不要用错值参与改名，
改用 xx1、xx2…… 这样的顺序占位符，配合 Excel 里的原件图列由人工核对补录。
人工已补录的字段（ST_MANUAL）不再分配占位符。

设计要点：
- 只对合同模式、且字段名在待核对集合里的字段分配；
- 跨结果全局递增编号（与文件处理顺序一致），xx1/xx2 不重复；
- 幂等：同一批结果重复调用不会产生新编号（已有 review_code 直接复用）；
- 跳过状态为 skip 的文档，不给它们占号。
"""
from __future__ import annotations

from .models import SKIP_DOC_STATUSES, ST_MANUAL, ExtractResult
from .rules import needs_review

# 需要核对占位符的字段（乙方姓名为开放集手写，最易错）
REVIEW_FIELDS = ("乙方",)


def assign_review_codes(results: list[ExtractResult],
                        fields: tuple[str, ...] = REVIEW_FIELDS,
                        prefix: str = "xx") -> int:
    """为不可信字段分配 xxN 占位符，写入 FieldResult.review_code 与 file_value。

    返回本批新分配的占位符数量。已有 review_code 的结果会被复用（幂等）。
    """
    next_no = 1
    assigned = 0
    for r in results:
        if r.doc_status in SKIP_DOC_STATUSES:
            continue
        for name in fields:
            fr = r.fields.get(name)
            if fr is None:
                continue
            # 已有占位符 → 复用其编号，保持编号连续
            if fr.review_code:
                digits = fr.review_code[len(prefix):]
                if digits.isdigit():
                    next_no = max(next_no, int(digits) + 1)
                continue
            # 人工补录 / 可信值 → 不分配
            if fr.status == ST_MANUAL or not needs_review(name, fr.value, fr.status):
                continue
            code = f"{prefix}{next_no}"
            next_no += 1
            assigned += 1
            fr.review_code = code
            fr.file_value = code
    return assigned


def clear_review_codes(results: list[ExtractResult],
                       fields: tuple[str, ...] = REVIEW_FIELDS) -> None:
    """清除占位符（切换模式/重新扫描时调用）。"""
    for r in results:
        for name in fields:
            fr = r.fields.get(name)
            if fr is not None:
                fr.review_code = ""
