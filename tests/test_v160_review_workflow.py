# -*- coding: utf-8 -*-
"""V1.6.0 新流程测试：先出复核表 → 人工改 Excel → 按表改名。"""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image

from pdfrenamer.excel import (IMAGE_COL_SUFFIX, REVIEW_IMAGE_FIELDS, ExcelWriter,
                              image_col_name, read_reviewed_values, result_col_name,
                              update_excel_after_rename)
from pdfrenamer.models import ExtractResult, FieldResult, DOC_OK, ST_OK


SIX = ["乙方", "身份证号", "开始日期", "结束日期", "签订日期", "用工部门"]


def _result(name="a.pdf", **vals):
    r = ExtractResult(name, name, "contract")
    r.doc_status = DOC_OK
    for k, v in vals.items():
        r.fields[k] = FieldResult(k, v, v, ST_OK)
    return r


class TestSixImageColumns(unittest.TestCase):
    def test_all_six_expand(self):
        self.assertEqual(REVIEW_IMAGE_FIELDS, tuple(SIX))
        w = ExcelWriter(tempfile.mkdtemp(), "contract", "合同汇总", "合同", ["合同类型"] + SIX)
        self.assertEqual(w.image_fields, SIX)
        for f in SIX:
            self.assertIn(image_col_name(f), w.header)
            self.assertEqual(w.header[w.header.index(result_col_name(f)) + 1], image_col_name(f))

    def test_paper_unchanged(self):
        w = ExcelWriter(tempfile.mkdtemp(), "paper", "论文汇总", "论文",
                        ["论文题目", "作者", "期刊", "发表年份"])
        self.assertFalse(any(h.endswith(IMAGE_COL_SUFFIX) for h in w.header))

    def test_build_row_blank_image_cells(self):
        w = ExcelWriter(tempfile.mkdtemp(), "contract", "合同汇总", "合同", SIX)
        r = _result(**{f: f + "值" for f in SIX})
        row = w.build_row(r, None)
        for f in SIX:
            self.assertEqual(row[result_col_name(f)], f + "值")
            self.assertEqual(row[image_col_name(f)], "")


class TestReviewReadback(unittest.TestCase):
    def test_read_and_update_preserves_fields_and_images(self):
        d = Path(tempfile.mkdtemp())
        names = SIX
        w = ExcelWriter(d, "contract", "合同汇总", "合同", names)
        w.prepare()
        r = _result(**{f: "原值" for f in SIX})
        buf = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(buf, format="JPEG")
        # 六字段各嵌一张图
        w.append_row(w.build_row(r, None), {f: buf.getvalue() for f in SIX}, save=False)
        w.finish()
        p = d / "信息汇总.xlsx"
        self.assertEqual(len(load_workbook(p)["合同汇总"]._images), 6)

        # 人工改两个字段（模拟 Excel 修改）
        wb = load_workbook(p)
        ws = wb["合同汇总"]
        hdr = [c.value for c in ws[1]]
        ws.cell(row=2, column=hdr.index(result_col_name("乙方")) + 1, value="张三")
        ws.cell(row=2, column=hdr.index(result_col_name("用工部门")) + 1, value="财务室")
        wb.save(p)
        wb.close()

        # 读回复核值
        reviewed = read_reviewed_values(p, "合同汇总", names)
        self.assertEqual(reviewed["a.pdf"]["乙方"], "张三")
        self.assertEqual(reviewed["a.pdf"]["用工部门"], "财务室")
        self.assertEqual(reviewed["a.pdf"]["身份证号"], "原值")  # 未改的也读到

        # 改名后只更新新文件名列
        n = update_excel_after_rename(p, "合同汇总", {"a.pdf": "劳动合同_2023_01_张三.pdf"})
        self.assertEqual(n, 1)
        wb = load_workbook(p)
        ws = wb["合同汇总"]
        hdr = [c.value for c in ws[1]]
        self.assertEqual(ws.cell(row=2, column=hdr.index("新文件名") + 1).value,
                         "劳动合同_2023_01_张三.pdf")
        self.assertEqual(ws.cell(row=2, column=hdr.index(result_col_name("乙方")) + 1).value, "张三",
                         "更新新文件名不得覆盖人工复核的乙方值")
        self.assertEqual(len(ws._images), 6, "更新新文件名不得丢失截图")
        wb.close()

    def test_read_missing_sheet_returns_empty(self):
        self.assertEqual(read_reviewed_values(Path("/nonexistent.xlsx"), "合同汇总", SIX), {})


class TestBatchSave(unittest.TestCase):
    def test_defer_save_works(self):
        d = Path(tempfile.mkdtemp())
        w = ExcelWriter(d, "contract", "合同汇总", "合同", ["乙方"])
        w.prepare()
        for i in range(3):
            r = _result(f"{i}.pdf", 乙方="张三")
            w.append_row(w.build_row(r, None), save=False)
        # finish 前磁盘上表未落定（prepare 已建表头）；finish 一次落盘
        w.finish()
        wb = load_workbook(d / "信息汇总.xlsx")
        self.assertEqual(wb["合同汇总"].max_row, 4)
        wb.close()


if __name__ == "__main__":
    unittest.main()
