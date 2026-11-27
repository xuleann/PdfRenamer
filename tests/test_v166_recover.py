# -*- coding: utf-8 -*-
"""V1.6.6 回归：Excel 被占用写入失败后，关闭 Excel 点「恢复」应能补写，无需重扫。

旧实现的顺序是 prepare()「清空 rows.jsonl → 立即保存」：
Excel 打开时保存直接抛 ExcelBusyError，本轮一行都还没进日志，
恢复函数读到 0 行，用户只能重新扫描。

现在：
- prepare() 不保存、只把上一轮残留日志转存 .prev；
- append_row() 每行写完记录一条 ``saved`` 计数（已落盘行数）；
- 恢复只补 ``saved`` 之后的行，前面已进表的不重复；
- finish() 成功后才清空日志。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import load_workbook  # noqa: E402

from pdfrenamer.excel import (  # noqa: E402
    FILE_NAME,
    ExcelBusyError,
    ExcelWriter,
    _rows_path,
    recover_rows,
    result_col_name,
)

FIELDS = ["合同类型", "乙方"]
SHEET = "合同汇总"


def make_row(idx: int, name: str) -> dict:
    """按 v1.6.x 的「结果列（复核）/图片列（识别结果）」结构造一行。"""
    return {
        "原文件名": f"{idx}.pdf",
        "新文件名": f"劳动合同_2023_{idx:02d}_{name}.pdf",
        "合同类型": "劳动合同",
        result_col_name("乙方"): name,
        "提取状态": "成功",
        "PDF 类型": "合同",
    }


ROWS = [make_row(1, "张三"), make_row(2, "李四")]


class TestRecoverAfterExcelBusy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pdfr_recover_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prepare_does_not_save_when_excel_locked(self):
        """prepare 只读旧表，不该在 Excel 打开时失败。"""
        with patch("openpyxl.workbook.workbook.Workbook.save",
                   side_effect=PermissionError("locked")):
            w = ExcelWriter(self.tmp, "contract", SHEET, "合同", FIELDS)
            w.prepare()          # 旧实现会在这里抛 ExcelBusyError
            w.append_row(dict(ROWS[0]), save=False)

    def test_rows_recorded_before_save_failure(self):
        """保存失败时，失败那一行也必须已经在日志里。"""
        w = ExcelWriter(self.tmp, "contract", SHEET, "合同", FIELDS)
        w.prepare()
        w.append_row(dict(ROWS[0]), save=False)
        w.append_row(dict(ROWS[1]), save=False)
        with patch("openpyxl.workbook.workbook.Workbook.save",
                   side_effect=PermissionError("locked")):
            with self.assertRaises(ExcelBusyError):
                w.finish()
        payload = [json.loads(x) for x in
                   _rows_path(self.tmp).read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual(len([p for p in payload if "row" in p]), 2)

    def test_recover_writes_pending_rows_only(self):
        """第 1 行已落盘、第 2 行失败 → 恢复只补第 2 行，不重复第 1 行。"""
        w = ExcelWriter(self.tmp, "contract", SHEET, "合同", FIELDS)
        w.prepare()
        w.append_row(dict(ROWS[0]))                 # save=True，成功入表并记 saved=1
        w.append_row(dict(ROWS[1]), save=False)     # 只进日志
        with patch("openpyxl.workbook.workbook.Workbook.save",
                   side_effect=PermissionError("locked")):
            with self.assertRaises(ExcelBusyError):
                w.finish()

        n = recover_rows(self.tmp, "contract", SHEET, "合同", FIELDS)
        self.assertEqual(n, 1)

        ws = load_workbook(self.tmp / FILE_NAME)[SHEET]
        self.assertEqual(ws.max_row, 3)             # 表头 + 两行，没有重复
        self.assertEqual(ws.cell(row=2, column=2).value, "1.pdf")
        self.assertEqual(ws.cell(row=3, column=2).value, "2.pdf")

        # 再点一次恢复：日志已清空，不应再追加
        self.assertEqual(recover_rows(self.tmp, "contract", SHEET, "合同", FIELDS), 0)
        self.assertEqual(load_workbook(self.tmp / FILE_NAME)[SHEET].max_row, 3)

    def test_recover_reports_lock_error(self):
        """Excel 还没关就又点恢复，应抛 ExcelBusyError 让界面提示。"""
        w = ExcelWriter(self.tmp, "contract", SHEET, "合同", FIELDS)
        w.prepare()
        w.append_row(dict(ROWS[0]), save=False)
        with patch("openpyxl.workbook.workbook.Workbook.save",
                   side_effect=PermissionError("locked")):
            with self.assertRaises(ExcelBusyError):
                w.finish()
            with self.assertRaises(ExcelBusyError):
                recover_rows(self.tmp, "contract", SHEET, "合同", FIELDS)


if __name__ == "__main__":
    unittest.main()
