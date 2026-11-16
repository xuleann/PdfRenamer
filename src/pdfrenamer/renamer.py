# -*- coding: utf-8 -*-
"""重命名引擎：模板渲染 → 文件名合法化 → 冲突去重 → dry-run plan → 原地执行。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

from .models import ExtractResult, RenameRecord, SKIP_DOC_STATUSES, ST_MISSING
from .rules import sanitize_filename, unique_name

PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class RenameEngine:
    def __init__(self, template: str, missing_value: str = "未知", max_len: int = 120):
        self.template = template or ""
        self.missing_value = missing_value
        self.max_len = max_len

    def placeholders(self) -> list[str]:
        return PLACEHOLDER_RE.findall(self.template)

    def unknown_placeholders(self, field_names: list[str]) -> list[str]:
        return [p for p in self.placeholders() if p not in field_names]

    def _render(self, result: ExtractResult) -> tuple[str, list[str]]:
        used_missing: list[str] = []

        def repl(m: re.Match) -> str:
            name = m.group(1)
            fr = result.fields.get(name)
            if fr is None:
                used_missing.append(name)
                return self.missing_value
            if fr.is_missing:
                used_missing.append(name)
                return self.missing_value
            return fr.file_value or self.missing_value

        return PLACEHOLDER_RE.sub(repl, self.template), used_missing

    def plan(self, results: list[ExtractResult], directory: str | Path) -> list[RenameRecord]:
        """只生成计划，不碰任何文件。"""
        root = Path(directory)
        src_paths = {str(Path(r.path).resolve()).lower() for r in results}
        used_lower: set[str] = set()
        try:
            for f in root.iterdir():
                if f.is_file() and str(f.resolve()).lower() not in src_paths:
                    used_lower.add(f.name.lower())
        except OSError:
            pass

        records: list[RenameRecord] = []
        for r in results:
            src = Path(r.path)
            suffix = src.suffix.lower() or ".pdf"
            if r.doc_status in SKIP_DOC_STATUSES:
                records.append(RenameRecord(str(src), str(src), src.name, src.name,
                                            "skipped", r.skip_reason))
                continue

            rendered, missing = self._render(r)
            template_fields = self.placeholders()
            if template_fields and all(p in missing for p in template_fields):
                records.append(RenameRecord(str(src), str(src), src.name, src.name,
                                            "skipped", "模板字段全部未提取到，跳过以避免误改名"))
                continue

            if not rendered.strip():
                rendered = self.missing_value
            new_name = sanitize_filename(rendered + suffix, self.max_len)
            new_name = unique_name(new_name, used_lower)
            dst = root / new_name
            if new_name.lower() == src.name.lower():
                records.append(RenameRecord(str(src), str(dst), src.name, new_name,
                                            "unchanged", "新旧名称一致"))
                continue
            note = "、".join(sorted(set(missing)))
            reason = f"缺失字段：{note}" if note else ""
            records.append(RenameRecord(str(src), str(dst), src.name, new_name, "planned", reason))
        return records

    def execute(self, records: list[RenameRecord], progress: Callable | None = None) -> list[RenameRecord]:
        """原地重命名；任何一步失败都只标记该条，不影响其它文件。"""
        total = len(records)
        for i, rec in enumerate(records, 1):
            if rec.status != "planned":
                if progress:
                    progress(i, total, rec.original)
                continue
            src, dst = Path(rec.src), Path(rec.dst)
            try:
                if not src.exists():
                    rec.status, rec.reason = "failed", "源文件已不存在"
                elif dst.exists():
                    rec.status, rec.reason = "failed", "目标文件名已被占用"
                else:
                    os.rename(src, dst)
                    rec.status = "done"
            except OSError as exc:
                rec.status, rec.reason = "failed", f"{type(exc).__name__}: {exc}"
            if progress:
                progress(i, total, rec.original)
        return records
