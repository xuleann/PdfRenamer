# -*- coding: utf-8 -*-
"""V1.6.4 测试：页面方向自动校正 + OCR 页缓存提速。"""
from __future__ import annotations

import unittest

from pdfrenamer.extractor import ocr_rapid as ocr


class TestOrientation(unittest.TestCase):
    def test_score_upright_vs_garbage(self):
        good = ["甲方：某公司", "乙方：张三", "身份证号：1101", "合同期限", "签订日期"]
        bad = ["10-1H-<：。", "!@#$", "甲", "之", "?><"]
        self.assertGreater(ocr._orient_score(good), ocr._orient_score(bad))
        self.assertEqual(ocr._orient_score([]), 0)

    def test_boxes_to_pairs(self):
        txts = ["甲", "乙"]
        boxes = [[(0, 0), (10, 0), (10, 20), (0, 20)],
                 [(5, 3), (15, 3), (15, 23), (5, 23)]]
        pairs = ocr._boxes_to_pairs(txts, boxes)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0], ("甲", (0.0, 0.0, 10.0, 20.0)))

    def test_orient_keeps_upright_image(self):
        """正立合同页不应触发额外旋转（0 角度、只一次 OCR）。"""
        import pymupdf
        from PIL import Image
        engine = ocr._get_engine()
        if engine is None:
            self.skipTest("RapidOCR 不可用")
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 100), "甲方 乙方 合同 身份证 姓名 日期 期限",
                         fontname="china-s", fontsize=20)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        out_img, txts, boxes, angle = ocr._ocr_page_auto_orient(engine, img)
        self.assertEqual(angle, 0)   # 正立页零额外开销
        self.assertIsNotNone(out_img)
        self.assertIsInstance(txts, list)
        doc.close()


class TestPageCache(unittest.TestCase):
    def test_cache_roundtrip(self):
        ocr.clear_page_cache()
        ocr._page_cache_put("/tmp/fake.pdf", 0, "IMG", [("甲", (0, 0, 1, 1))])
        got = ocr._page_cache_get("/tmp/fake.pdf", 0)
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "IMG")
        self.assertEqual(len(got[1]), 1)
        ocr.clear_page_cache()
        self.assertIsNone(ocr._page_cache_get("/tmp/fake.pdf", 0))


if __name__ == "__main__":
    unittest.main()
