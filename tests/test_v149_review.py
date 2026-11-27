# -*- coding: utf-8 -*-
"""V1.4.9 核对增强测试：乙方 xxN 占位符 + Excel 乙方/用工部门双列 + 首页截图。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pdfrenamer.excel import (IMAGE_COL_SUFFIX, REVIEW_IMAGE_FIELDS, ExcelWriter,
                              image_col_name, result_col_name)
from pdfrenamer.models import (DOC_OK, ExtractResult, FieldResult, ST_HEURISTIC,
                               ST_MANUAL, ST_MISSING, ST_OK)
from pdfrenamer.renamer import RenameEngine
from pdfrenamer.review import assign_review_codes
from pdfrenamer.rules import needs_review


class TestReviewCode(unittest.TestCase):
    def test_assign_sequential_and_idempotent(self):
        results = [
            ExtractResult("a.pdf", "a.pdf", "contract"),
            ExtractResult("b.pdf", "b.pdf", "contract"),
            ExtractResult("c.pdf", "c.pdf", "contract"),
        ]
        # a：可疑姓名（超长机构名）；b：缺失；c：可信
        results[0].fields["乙方"] = FieldResult("乙方", "某某有限公司张三", "某某有限公司张三", ST_OK)
        results[1].fields["乙方"] = FieldResult("乙方", "", "未知", ST_MISSING)
        results[2].fields["乙方"] = FieldResult("乙方", "张三", "张三", ST_OK)
        for r in results:
            r.doc_status = DOC_OK

        n = assign_review_codes(results)
        self.assertEqual(n, 2)
        self.assertEqual(results[0].fields["乙方"].review_code, "xx1")
        self.assertEqual(results[1].fields["乙方"].review_code, "xx2")
        self.assertEqual(results[2].fields["乙方"].review_code, "")
        self.assertEqual(results[0].fields["乙方"].file_value, "xx1")

        # 幂等：再次调用不产生新编号
        self.assertEqual(assign_review_codes(results), 0)
        self.assertEqual(results[0].fields["乙方"].review_code, "xx1")
        self.assertEqual(results[1].fields["乙方"].review_code, "xx2")

    def test_manual_override_not_assigned(self):
        r = ExtractResult("a.pdf", "a.pdf", "contract")
        r.doc_status = DOC_OK
        r.fields["乙方"] = FieldResult("乙方", "张三", "张三", ST_MANUAL, "人工补录")
        assign_review_codes([r])
        self.assertEqual(r.fields["乙方"].review_code, "")

    def test_rename_uses_code(self):
        r = ExtractResult("a.pdf", "a.pdf", "contract")
        r.doc_status = DOC_OK
        # 可疑值：有原始识别值（不会触发「模板字段全缺」跳过），
        # 但 file_value 已被 assign_review_codes 改成 xx1。
        fr = FieldResult("乙方", "某某有限公司张三", "某某有限公司张三", ST_OK)
        r.fields["乙方"] = fr
        assign_review_codes([r])
        self.assertEqual(fr.review_code, "xx1")
        renamer = RenameEngine("{乙方}_合同.pdf", "未知", 120)
        recs = renamer.plan([r], Path(tempfile.mkdtemp()))
        self.assertIn("xx1", recs[0].new_name)

    def test_needs_review(self):
        self.assertTrue(needs_review("乙方", "", ST_MISSING))
        self.assertTrue(needs_review("乙方", "张三", ST_HEURISTIC))
        self.assertTrue(needs_review("乙方", "某某有限公司", ST_OK))
        self.assertFalse(needs_review("乙方", "张三", ST_OK))
        self.assertFalse(needs_review("乙方", "张三", ST_MANUAL))


class TestExcelReviewColumns(unittest.TestCase):
    def test_header_has_image_columns(self):
        names = ["合同类型", "乙方", "身份证号", "用工部门", "签订日期"]
        w = ExcelWriter(tempfile.mkdtemp(), "contract", "合同汇总", "合同", names)
        # V1.6.0：六个手写字段都有图片列（此测试 names 里出现的四个都应展开）
        self.assertEqual(w.image_fields, ["乙方", "身份证号", "用工部门", "签订日期"])
        self.assertIn(image_col_name("乙方"), w.header)
        self.assertIn(image_col_name("用工部门"), w.header)
        # 图片列紧跟对应复核结果列
        self.assertEqual(w.header[w.header.index(result_col_name("乙方")) + 1],
                         image_col_name("乙方"))
        self.assertEqual(w.header[w.header.index(result_col_name("用工部门")) + 1],
                         image_col_name("用工部门"))

    def test_paper_mode_no_image_columns(self):
        names = ["论文题目", "作者", "期刊", "发表年份"]
        w = ExcelWriter(tempfile.mkdtemp(), "paper", "论文汇总", "论文", names)
        self.assertEqual(w.image_fields, [])
        self.assertFalse(any(h.endswith(IMAGE_COL_SUFFIX) for h in w.header))

    def test_build_row_keeps_raw_value_not_code(self):
        """V1.5.0：xxN 只用于文件名，表格乙方列保留识别原值。"""
        names = ["乙方", "用工部门"]
        w = ExcelWriter(tempfile.mkdtemp(), "contract", "合同汇总", "合同", names)
        r = ExtractResult("a.pdf", "a.pdf", "contract")
        r.doc_status = DOC_OK
        bf = FieldResult("乙方", "错识别值", "xx1", ST_OK)
        bf.review_code = "xx1"
        r.fields["乙方"] = bf
        r.fields["用工部门"] = FieldResult("用工部门", "办公室", "办公室", ST_OK)
        row = w.build_row(r, None)
        self.assertEqual(row[result_col_name("乙方")], "错识别值")   # 表格显示原识别值
        self.assertNotIn("xx1", row["备注"])         # 备注不再塞占位说明
        self.assertEqual(row[image_col_name("乙方")], "")
        self.assertEqual(row[result_col_name("用工部门")], "办公室")

    def test_embed_image_goes_to_image_column(self):
        from openpyxl import load_workbook
        d = tempfile.mkdtemp()
        names = ["乙方", "用工部门"]
        w = ExcelWriter(d, "contract", "合同汇总", "合同", names)
        w.prepare()
        r = ExtractResult("a.pdf", "a.pdf", "contract")
        r.doc_status = DOC_OK
        r.fields["乙方"] = FieldResult("乙方", "张三", "张三", ST_OK)
        r.fields["用工部门"] = FieldResult("用工部门", "办公室", "办公室", ST_OK)
        # 1x1 白色 JPEG（最小合法图片）
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(buf, format="JPEG")
        w.append_row(w.build_row(r, None), {"乙方": buf.getvalue()})
        w.finish()
        wb = load_workbook(Path(d) / "信息汇总.xlsx")
        ws = wb["合同汇总"]
        self.assertEqual(len(ws._images), 1)
        anchor_col = ws._images[0].anchor._from.col + 1  # openpyxl 列 0-based
        hdr_idx = [c.value for c in ws[1]].index(image_col_name("乙方")) + 1
        self.assertEqual(anchor_col, hdr_idx, "乙方图片应锚定到原件图列而非文字列")
        wb.close()

    def test_upgrade_old_table_inserts_image_columns(self):
        import pdfrenamer.excel as xm
        from openpyxl import load_workbook
        old_tail = xm.HEADER_TAIL
        old_image_fields = xm.REVIEW_IMAGE_FIELDS
        base_names = ["乙方", "用工部门"]
        try:
            xm.HEADER_TAIL = ["提取状态", "缺失字段", "处理时间", "备注", "PDF 类型"]
            xm.REVIEW_IMAGE_FIELDS = ()   # 模拟旧版：无图片列
            d = tempfile.mkdtemp()
            w = ExcelWriter(d, "contract", "合同汇总", "合同", base_names)
            w.prepare()
            r = ExtractResult("a.pdf", "a.pdf", "contract")
            r.doc_status = DOC_OK
            r.fields["乙方"] = FieldResult("乙方", "张三", "张三", ST_OK)
            r.fields["用工部门"] = FieldResult("用工部门", "办公室", "办公室", ST_OK)
            w.append_row(w.build_row(r, None))
            w.finish()
            wb = load_workbook(Path(d) / "信息汇总.xlsx")
            self.assertNotIn(image_col_name("乙方"), [c.value for c in wb["合同汇总"][1]])
            wb.close()
        finally:
            xm.REVIEW_IMAGE_FIELDS = old_image_fields
        # V1.6.5：旧表头（纯字段名）→ 新表头带「（复核）」属于重命名，
        # 就地升级会列错位，改为备份旧表 + 重建正确结构（历史留档不丢）。
        w2 = ExcelWriter(d, "contract", "合同汇总", "合同", base_names)
        w2.prepare()
        w2.finish()
        wb = load_workbook(Path(d) / "信息汇总.xlsx")
        ws = wb["合同汇总"]
        headers = [c.value for c in ws[1]]
        self.assertIn(image_col_name("乙方"), headers)
        self.assertIn(image_col_name("用工部门"), headers)
        self.assertIn(result_col_name("乙方"), headers)
        self.assertEqual(len(headers), len(set(headers)), "表头不得有重复列")
        self.assertTrue(w2.backup_path, "旧表应被备份留档")
        wb.close()


class TestSequenceReset(unittest.TestCase):
    def test_sequence_starts_at_one(self):
        """序号每批从 01 开始（V1.5.0，不再跨批递增）。"""
        from pdfrenamer.config import _factory_defaults, _validate
        cfg = _factory_defaults()
        cfg["sequence_counter"] = 4
        cfg = _validate(cfg)
        self.assertEqual(cfg["sequence_counter"], 1)
        ren = RenameEngine("{序号}_x.pdf", "未知", 120, sequence_start=1)
        rs = [ExtractResult(f"{i}.pdf", f"{i}.pdf", "contract") for i in range(3)]
        for r in rs:
            r.doc_status = DOC_OK
        recs = ren.plan(rs, Path(tempfile.mkdtemp()))
        names = [x.new_name for x in recs]
        self.assertTrue(all(n.startswith("0") for n in names), names)
        self.assertIn("01_x", names[0])
        self.assertIn("02_x", names[1])
        self.assertIn("03_x", names[2])


class TestImageQuality(unittest.TestCase):
    def test_department_image_high_quality(self):
        """用工部门截图：分辨率与画质显著高于其它字段。"""
        from pdfrenamer.extractor import field_crop as fc
        self.assertIn("用工部门", fc._HQ_FIELDS)
        self.assertGreater(fc._HQ_MAX_SIDE, fc._MAX_SIDE * 2)
        self.assertGreater(fc._HQ_JPEG_QUALITY, fc._JPEG_QUALITY)
        self.assertGreater(fc._HQ_CAP_BYTES, fc._CAP_BYTES * 3)

    def test_excel_hq_display_limits(self):
        import pdfrenamer.excel as xm
        self.assertGreater(xm.ExcelWriter._IMG_HQ_MAX_W, xm.ExcelWriter._IMG_MAX_W)
        self.assertGreater(xm.ExcelWriter._IMG_HQ_MAX_H, xm.ExcelWriter._IMG_MAX_H)


if __name__ == "__main__":
    unittest.main()
