# -*- coding: utf-8 -*-
"""V1.3.0 新功能单测：合同期限范围、合同类型判定、手写截图。

不依赖真实合同；日期/类型用纯文本，截图用合成 PDF（系统字体）。
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from pdfrenamer.rules import (parse_duration_range, detect_contract_type,
                              find_department, find_person_name, normalize_person_name)
from pdfrenamer.extractor.field_crop import crop_field_images, FIELD_ANCHORS


class DurationRangeTests(unittest.TestCase):
    def test_qi_zhi(self):
        self.assertEqual(parse_duration_range("合同期限：自2023年5月1日起至2024年4月30日止"),
                         ("2023-05-01", "2024-04-30"))

    def test_dao_zhi(self):
        self.assertEqual(parse_duration_range("从2022年3月1日到2023年2月28日止"),
                         ("2022-03-01", "2023-02-28"))

    def test_dot_format(self):
        self.assertEqual(parse_duration_range("合同期限 2023.5.1-2024.4.30"),
                         ("2023-05-01", "2024-04-30"))

    def test_none(self):
        self.assertEqual(parse_duration_range("合同期限：一年"), ("", ""))

    def test_ocr_confusion(self):
        # 年→日、月→区 的 OCR 误识也能解析
        self.assertEqual(parse_duration_range("合同期限：自2023日5区1日起至2024日4区30日止"),
                         ("2023-05-01", "2024-04-30"))

    def test_real_contract_sentence(self):
        # 技术要求文档里的真实写法：自X起生效，至Y终止（中间夹「生效，」）
        t = "第一条 劳动合同期限\n本合同自2023年5月30日起生效，至2026年5月29日终止，共3年。其中试用期为6个月。"
        self.assertEqual(parse_duration_range(t), ("2023-05-30", "2026-05-29"))


class ContractTypeTests(unittest.TestCase):
    def test_labor_title(self):
        self.assertEqual(detect_contract_type("劳动合同书\n甲方：某公司\n乙方：张三"), "劳动合同")

    def test_service_title(self):
        self.assertEqual(detect_contract_type("劳务合同\n劳务报酬每月结算"), "劳务合同")

    def test_service_by_body(self):
        self.assertEqual(detect_contract_type("用工协议\n甲方：某公司\n乙方：李四\n提供劳务服务，劳务费按月结算"),
                         "劳务合同")

    def test_labor_by_law(self):
        self.assertEqual(detect_contract_type("用工协议\n根据《劳动法》订立，劳动者遵守规章制度"),
                         "劳动合同")

    def test_service_contract_mixes_labor_words(self):
        # 劳务合同常沿用劳动合同模板，正文出现「劳动合同期限/劳动法」，
        # 但有「劳务关系/劳务报酬」专一信号，应判劳务。
        t = "劳务合同\n第一条 劳动合同期限\n根据劳动法相关规定，双方建立劳务关系，提供劳务服务，劳务费按月结算"
        self.assertEqual(detect_contract_type(t), "劳务合同")

    def test_unknown(self):
        self.assertEqual(detect_contract_type("采购协议\n甲方供货乙方付款"), "")


class HandwritingFieldTests(unittest.TestCase):
    """V1.3.4：乙方姓名 / 用工部门专提。"""

    def test_yifang_name(self):
        self.assertEqual(find_person_name("乙方：孟梅\n用工部门：财务室"), "孟梅")
        self.assertEqual(find_person_name("乙方（签字）：李小明"), "李小明")
        self.assertEqual(find_person_name("甲方：某公司\n乙方：王五"), "王五")

    def test_name_normalize_label_bug(self):
        # 旧 bug：「乙方：孟梅」被截成「乙方」
        self.assertEqual(normalize_person_name("乙方：孟梅"), "孟梅")

    def test_department_in_sentence(self):
        # 真实合同截图：部门值嵌在句子里，旧逻辑误取「工作」
        self.assertEqual(find_department("甲方安排乙方在财务室（部门）工作"), "财务室")

    def test_department_ocr_variants(self):
        self.assertEqual(find_department("在务室（部门）"), "财务室")  # OCR漏「财」
        self.assertEqual(find_department("服务1部"), "服务一部")
        self.assertEqual(find_department("服务2部"), "服务二部")
        self.assertEqual(find_department("在资产（部门）"), "资产")

    def test_department_ignore_expense_words(self):
        # 正文「交通费」不该被当成部门
        self.assertEqual(find_department("第一条\n交通费按规定报销\n乙方在财务室（部门）"), "财务室")

    def test_department_from_clause2(self):
        # V1.4.3：岗位固定在第二条第二点——优先在该章节找，且不受其它条款干扰
        t = ("第一条 合同期限\n一、签章\n交通费另算\n"
             "第二条 工作内容和工作地点\n1. 服从安排\n2. 在交通部（室）客运岗\n"
             "第三条 劳动报酬")
        self.assertEqual(find_department(t), "交通")
        # 第二条写财务室
        t2 = "第二条 工作内容\n2. 在财务室（部门）工作岗\n第三条 报酬"
        self.assertEqual(find_department(t2), "财务室")


class FieldCropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 合成一份带文本层标签的 PDF（无需真实合同）
        try:
            import pymupdf
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            cls.pdf = None
            return
        doc = pymupdf.open()
        page = doc.new_page(width=1000, height=700)
        rows = [(80, "身份证号码：", "110101199003075678"),
                (200, "乙方：", "张三"),
                (320, "用工部门：", "办公室"),
                (440, "签订日期：", "2023年5月1日")]
        for y, label, val in rows:
            page.insert_text((40, y), label, fontname="china-s", fontsize=20)
            page.insert_text((300, y), val, fontname="china-s", fontsize=18)
        tmp = Path(tempfile.gettempdir()) / "v130_crop_fixture.pdf"
        doc.save(str(tmp)); doc.close()
        cls.pdf = str(tmp)

    def test_crop_small_images(self):
        if not getattr(self, "pdf", None):
            self.skipTest("pymupdf 不可用")
        imgs = crop_field_images(self.pdf, ["乙方", "用工部门", "签订日期", "身份证号"])
        self.assertEqual(set(imgs.keys()), {"乙方", "用工部门", "签订日期", "身份证号"})
        for name, data in imgs.items():
            self.assertTrue(data, f"{name} 图片为空")
            self.assertLess(len(data), 60_000, f"{name} 图片过大: {len(data)}")

    def test_excel_embed(self):
        if not getattr(self, "pdf", None):
            self.skipTest("pymupdf 不可用")
        from openpyxl import load_workbook
        from pdfrenamer.excel import ExcelWriter
        from pdfrenamer.models import ExtractResult, RenameRecord, FieldResult, ST_OK
        d = tempfile.mkdtemp()
        names = ["合同类型", "乙方", "身份证号", "签订日期", "用工部门"]
        w = ExcelWriter(d, "contract", "合同汇总", "合同", names, strategy="append")
        w.prepare()
        r = ExtractResult("x.pdf", "x.pdf", "contract")
        for n in names:
            r.fields[n] = FieldResult(n, "值", "值", ST_OK)
        rec = RenameRecord("x.pdf", "n.pdf", "x.pdf", "n.pdf", "done")
        imgs = crop_field_images(self.pdf, ["乙方", "身份证号"])
        w.append_row(w.build_row(r, rec), imgs)
        w.finish()
        xlsx = Path(d) / "信息汇总.xlsx"
        self.assertTrue(xlsx.exists())
        wb = load_workbook(xlsx)
        self.assertEqual(len(wb["合同汇总"]._images), 2)


if __name__ == "__main__":
    unittest.main()
