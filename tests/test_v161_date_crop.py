# -*- coding: utf-8 -*-
"""V1.6.1 日期截图定位测试：开始/结束按日期数字、签订日期取末页落款。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pdfrenamer.extractor import field_crop as fc


class TestDateSpan(unittest.TestCase):
    def test_date_spans_two_dates(self):
        txt = "本合同自2023年5月30日起生效，至2026年5月29日终止，共3年。"
        spans = fc._date_spans(txt)
        self.assertEqual(len(spans), 2)
        self.assertEqual(txt[spans[0][0]:spans[0][1]], "2023年5月30日")
        self.assertEqual(txt[spans[1][0]:spans[1][1]], "2026年5月29日")

    def test_date_spans_formats(self):
        self.assertEqual(len(fc._date_spans("2023-5-1")), 1)
        self.assertEqual(len(fc._date_spans("2023/05/01")), 1)
        self.assertEqual(len(fc._date_spans("2023年5月")), 1)
        self.assertEqual(len(fc._date_spans("第一条 合同期限")), 0)  # 标题无日期

    def test_pick_date_span(self):
        spans = [(0, 3), (5, 8)]
        self.assertEqual(fc._pick_date_span(spans, 0), (0, 3))
        self.assertEqual(fc._pick_date_span(spans, 1), (5, 8))
        self.assertEqual(fc._pick_date_span(spans, -1), (5, 8))  # 末个


class TestTermBelowLocator(unittest.TestCase):
    """V1.6.2：开始/结束日期只从「合同期限」标题下方提取。"""

    def test_term_header_and_filter(self):
        rows = [
            (100, "第一条劳动合同期限", [], (0, 100, 300, 120)),
            (180, "本合同自2023年5月30日起至2026年5月29日止",
             [(6, 16), (22, 32)], (0, 180, 600, 200)),
            (900, "2024年1月1日", [(0, 11)], (0, 900, 200, 920)),  # 远处另一个日期
        ]
        hy = fc._term_header_y(rows)
        self.assertEqual(hy, 100)
        kept = fc._filter_rows_below_term(rows, hy)
        self.assertEqual(len(kept), 1)          # 远处的日期被排除
        self.assertIn("2023", kept[0][1])

    def test_no_header_falls_back(self):
        rows = [(200, "2023年5月1日", [(0, 11)], (0, 200, 200, 220))]
        self.assertIsNone(fc._term_header_y(rows))
        self.assertEqual(len(fc._filter_rows_below_term(rows, None)), 1)

    def test_text_pdf_prefers_title_below(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf 不可用")
        doc = pymupdf.open()
        page = doc.new_page(width=900, height=700)
        page.insert_text((40, 100), "第一条 劳动合同期限", fontname="china-s", fontsize=18)
        page.insert_text((40, 170),
                         "本合同自2023年5月30日起生效，至2026年5月29日终止，",
                         fontname="china-s", fontsize=14)
        page.insert_text((40, 600), "2024年1月1日", fontname="china-s", fontsize=14)
        s = fc._find_date_rect(page, "开始日期")
        e = fc._find_date_rect(page, "结束日期")
        self.assertIsNotNone(s) and self.assertIsNotNone(e)
        self.assertLess(s.y0, 250)   # 取标题下方的期限行，不是 600 处的远处日期
        # V1.6.3：开始/结束都截同一整行（对齐红框），不再各自切一块
        self.assertEqual(s, e)
        doc.close()


class TestDateFieldRegistration(unittest.TestCase):
    def test_three_date_fields(self):
        for f in ("开始日期", "结束日期", "签订日期"):
            self.assertIn(f, fc._DATE_FIELDS)
        self.assertEqual(fc._DATE_INDEX["开始日期"], 0)
        self.assertEqual(fc._DATE_INDEX["结束日期"], 1)
        self.assertEqual(fc._DATE_INDEX["签订日期"], -1)


class TestTextLayerDateCrop(unittest.TestCase):
    def test_date_rect_skips_title_line(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf 不可用")
        doc = pymupdf.open()
        page = doc.new_page(width=900, height=600)
        # 标题行（无日期）应在上，日期行在下；日期定位必须跳过标题命中日期行
        page.insert_text((40, 100), "第一条 劳动合同期限", fontname="china-s", fontsize=18)
        page.insert_text((40, 200),
                         "本合同自2023年5月30日起生效，至2026年5月29日终止，共3年。",
                         fontname="china-s", fontsize=14)
        start = fc._find_date_rect(page, "开始日期")
        end = fc._find_date_rect(page, "结束日期")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        # 两个日期的 y 都在日期行（约 200），不在标题行（约 100）
        self.assertGreater(start.y0, 150)
        self.assertGreater(end.y0, 150)
        # V1.6.3：开始/结束都截同一整行（对齐红框），不再各自切一块
        self.assertEqual(end, start)
        doc.close()

    def test_crop_two_dates_on_text_pdf(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf 不可用")
        doc = pymupdf.open()
        page = doc.new_page(width=900, height=600)
        page.insert_text((40, 100), "第一条 劳动合同期限", fontname="china-s", fontsize=18)
        page.insert_text((40, 200),
                         "本合同自2023年5月30日起生效，至2026年5月29日终止，共3年。",
                         fontname="china-s", fontsize=14)
        p = Path(tempfile.mkdtemp()) / "date.pdf"
        doc.save(str(p)); doc.close()
        imgs = fc.crop_field_images(str(p), ["开始日期", "结束日期"])
        self.assertIn("开始日期", imgs)
        self.assertIn("结束日期", imgs)


class TestRealSampleDateRows(unittest.TestCase):
    """V1.6.3：用用户提供的 Test 目录样本验证日期整行定位。"""

    def test_term_below_required(self):
        # 封面页只有日期无期限标题 → 开始/结束不应截；期限页有标题 → 应截
        rows_cover = [(200, "2022年9月", [(0, 7)], (0, 200, 200, 220))]
        self.assertIsNone(fc._term_header_y(rows_cover))
        rows_term = [(100, "第一条劳动合同期限", [], (0, 100, 300, 120)),
                     (180, "本合同自2023年5月30日起至2026年5月29日止",
                      [(6, 16), (22, 32)], (0, 180, 600, 200))]
        hy = fc._term_header_y(rows_term)
        self.assertIsNotNone(hy)
        kept = fc._filter_rows_below_term(rows_term, hy)
        self.assertEqual(len(kept), 1)
        self.assertIn("2023", kept[0][1])
        self.assertIn("2026", kept[0][1])


if __name__ == "__main__":
    unittest.main()
