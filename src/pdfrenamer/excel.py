# -*- coding: utf-8 -*-
"""Excel 汇总：固定输出到用户所选目录的「信息汇总.xlsx」。

- 按模式分 sheet 追加（论文汇总 / 合同汇总），旧数据不丢
- 每处理一个 PDF 都增量写 rows.jsonl，Excel 被占用/中途崩溃后可恢复
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .config import rows_dir
from .models import (DOC_GARBLED, DOC_ENCRYPTED, DOC_ERROR, DOC_NOT_CONTRACT,
                     DOC_NO_TEXT, DOC_OK, DOC_PARTIAL, ExtractResult, RenameRecord)
from .undo import directory_key

FILE_NAME = "信息汇总.xlsx"
# V1.1.1：末尾追加「PDF 类型」标签列（A 列「模式」保留，兼容旧表）
HEADER_TAIL = ["提取状态", "缺失字段", "处理时间", "备注", "PDF 类型"]
STATUS_CN = {
    DOC_OK: "完整", DOC_PARTIAL: "部分缺失", DOC_NO_TEXT: "需人工处理",
    DOC_GARBLED: "需人工处理", DOC_ENCRYPTED: "需人工处理", DOC_ERROR: "需人工处理",
    DOC_NOT_CONTRACT: "非合同文档（不改名）",
}
TYPE_FILL = {
    "论文": PatternFill("solid", fgColor="DDEBF7"),
    "合同": PatternFill("solid", fgColor="E2EFDA"),
}

_HEADER_FILL = PatternFill("solid", fgColor="D9E2F3")
_MISS_FILL = PatternFill("solid", fgColor="FFF2CC")
_ALERT_FILL = PatternFill("solid", fgColor="F8CBAD")


class ExcelBusyError(Exception):
    """Excel 文件正被其它程序占用，无法写入。"""


def _rows_path(directory: str | Path) -> Path:
    return rows_dir() / f"{directory_key(directory)}.jsonl"


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(f"{path.stem}_备份_{stamp}{path.suffix}")
    n = 1
    while dst.exists():
        dst = path.with_name(f"{path.stem}_备份_{stamp}_{n}{path.suffix}")
        n += 1
    shutil.copy2(path, dst)
    return dst


class ExcelWriter:
    def __init__(self, directory: str | Path, mode: str, sheet_name: str,
                 mode_label: str, field_names: list[str], missing_value: str = "未知",
                 strategy: str = "append"):
        self.directory = Path(directory)
        self.path = self.directory / FILE_NAME
        self.mode = mode
        self.sheet_name = sheet_name
        self.mode_label = mode_label
        self.field_names = list(field_names)
        self.missing_value = missing_value
        self.strategy = strategy
        self.header = ["模式", "原文件名", "新文件名"] + self.field_names + HEADER_TAIL
        self.wb: Workbook | None = None
        self.ws = None
        self.rows_written = 0
        self.backup_path: Path | None = None

    def _new_workbook(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = self.sheet_name
        ws.append(self.header)
        self._style_header(ws)
        self.wb, self.ws = wb, ws

    def _style_header(self, ws) -> None:
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = _HEADER_FILL
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 22
        for i, name in enumerate(self.header, 1):
            width = 12
            if name in ("原文件名", "新文件名"):
                width = 42
            elif name == "备注":
                width = 36
            elif name == "处理时间":
                width = 20
            elif name in self.field_names:
                width = max(14, min(40, len(name) * 2 + 16))
            ws.column_dimensions[get_column_letter(i)].width = width

    def _can_upgrade(self, current: list) -> bool:
        """旧表头是当前表头的严格前缀，且只在末尾少了「PDF 类型」一列。"""
        if not current or len(current) >= len(self.header):
            return False
        if self.header[:len(current)] != current:
            return False
        if current[-1] != "备注":
            return False
        return self.header[len(current):] == ["PDF 类型"]

    def _upgrade_columns(self, ws, current: list) -> None:
        """就地追加新列并按 A 列「模式」回填旧行类型。不备份、不重建、不丢历史。"""
        start = len(current) + 1
        for j, name in enumerate(self.header[len(current):], start=start):
            c = ws.cell(row=1, column=j, value=name)
            c.font = Font(bold=True)
            c.fill = _HEADER_FILL
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[get_column_letter(j)].width = 12
        last = len(self.header)
        for r in range(2, ws.max_row + 1):
            mode = ws.cell(row=r, column=1).value or self.mode_label
            val = mode if mode in TYPE_FILL else self.mode_label
            c = ws.cell(row=r, column=last, value=val)
            c.alignment = Alignment(vertical="top")
            if val in TYPE_FILL:
                c.fill = TYPE_FILL[val]
        ws.freeze_panes = "A2"

    def prepare(self) -> None:
        """按策略打开/新建工作簿，并重置本轮 rows.jsonl。"""
        if self.strategy in ("backup", "overwrite") and self.path.exists():
            self.backup_path = _backup(self.path)
            self._new_workbook()
        elif self.path.exists():
            try:
                self.wb = load_workbook(self.path)
            except Exception:
                self.backup_path = _backup(self.path)
                self._new_workbook()
            else:
                if self.sheet_name in self.wb.sheetnames:
                    ws = self.wb[self.sheet_name]
                    current = [c.value for c in ws[1]] if ws.max_row >= 1 else []
                    if current == self.header:
                        self.ws = ws
                    elif self._can_upgrade(current):
                        # 仅末尾新增「PDF 类型」列 → 无损升列，保留全部历史行
                        self._upgrade_columns(ws, current)
                        self.ws = ws
                    else:
                        # 表头确实不兼容 → 备份后重建（历史留档）
                        self.backup_path = _backup(self.path)
                        self._new_workbook()
                else:
                    ws = self.wb.create_sheet(self.sheet_name)
                    ws.append(self.header)
                    self._style_header(ws)
                    self.ws = ws
                # 清掉无内容的默认 Sheet
                for name in list(self.wb.sheetnames):
                    s = self.wb[name]
                    if s.max_row == 1 and all(c.value is None for c in s[1]) and name != self.sheet_name:
                        self.wb.remove(s)
        else:
            self._new_workbook()

        rp = _rows_path(self.directory)
        rp.write_text("", encoding="utf-8")
        self._save()

    def _save(self) -> None:
        if self.wb is None:
            return
        try:
            self.wb.save(self.path)
        except PermissionError as exc:
            raise ExcelBusyError(
                "无法保存「信息汇总.xlsx」：文件可能正被 Excel 打开。请关闭后重试，"
                "本轮结果已保存在还原日志中，可用「恢复上次结果」补写。"
            ) from exc

    def build_row(self, result: ExtractResult, record: RenameRecord | None) -> dict:
        new_name = result.original_name
        if record and record.status in ("planned", "done", "unchanged"):
            new_name = record.new_name
        elif record and record.status == "skipped":
            new_name = "（未改名）"
        row = {
            "模式": self.mode_label,
            "原文件名": result.original_name,
            "新文件名": new_name,
        }
        for name in self.field_names:
            fr = result.fields.get(name)
            row[name] = fr.value if fr and not fr.is_missing else self.missing_value
        row["提取状态"] = STATUS_CN.get(result.doc_status, result.doc_status)
        row["缺失字段"] = "、".join(result.missing_names())
        row["处理时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notes = [x for x in (result.note, result.skip_reason, record.reason if record else "") if x]
        row["备注"] = "；".join(dict.fromkeys(notes))
        row["PDF 类型"] = self.mode_label
        return row

    def append_row(self, row: dict) -> None:
        if self.ws is None:
            raise RuntimeError("请先调用 prepare()")
        values = [row.get(h, "") for h in self.header]
        self.ws.append(values)
        r = self.ws.max_row
        for i, h in enumerate(self.header, 1):
            cell = self.ws.cell(row=r, column=i)
            cell.alignment = Alignment(vertical="top", wrap_text=(h in ("原文件名", "新文件名", "备注") + tuple(self.field_names)))
            if cell.value == self.missing_value:
                cell.fill = _MISS_FILL
            if h == "提取状态" and cell.value == "需人工处理":
                cell.fill = _ALERT_FILL
            if h == "PDF 类型" and cell.value in TYPE_FILL:
                cell.fill = TYPE_FILL[cell.value]
        self.rows_written += 1
        # 增量兜底：先写 jsonl，再存 Excel
        with _rows_path(self.directory).open("a", encoding="utf-8") as f:
            f.write(json.dumps({"mode": self.mode, "row": row}, ensure_ascii=False) + "\n")
        self._save()

    def finish(self) -> None:
        if self.ws is not None and self.ws.max_row >= 1:
            self.ws.auto_filter.ref = f"A1:{get_column_letter(len(self.header))}{self.ws.max_row}"
        self._save()


def has_recoverable_rows(directory: str | Path) -> bool:
    rp = _rows_path(directory)
    return rp.exists() and rp.stat().st_size > 0


def recover_rows(directory: str | Path, mode: str, sheet_name: str, mode_label: str,
                 field_names: list[str], missing_value: str = "未知") -> int:
    """从 rows.jsonl 重建本轮结果（Excel 被占用 / 中途崩溃后使用）。"""
    rp = _rows_path(directory)
    if not rp.exists():
        return 0
    rows = []
    for line in rp.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            if d.get("mode") == mode:
                rows.append(d["row"])
        except (ValueError, KeyError):
            continue
    if not rows:
        return 0
    # V1.1.0 及以前的 jsonl 行没有「PDF 类型」键，补齐后写回保持一致
    for row in rows:
        row.setdefault("PDF 类型", mode_label)
    w = ExcelWriter(directory, mode, sheet_name, mode_label, field_names,
                    missing_value, strategy="append")
    w.prepare()
    # prepare 会清空 jsonl，这里改为从内存写回，避免数据丢失
    for row in rows:
        values = [row.get(h, "") for h in w.header]
        w.ws.append(values)
        w.rows_written += 1
    with rp.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps({"mode": mode, "row": row}, ensure_ascii=False) + "\n")
    w.finish()
    return len(rows)
