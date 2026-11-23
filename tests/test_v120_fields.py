# -*- coding: utf-8 -*-
"""V1.2.0 劳动合同/劳务合同字段的规则单测。

覆盖：身份证校验、枚举映射、手写日期/数字容错、序号编号、新字段提取。
"""
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from pdfrenamer.rules import normalize_idcard, normalize_enum, normalize_date, normalize_person_name
from pdfrenamer.models import Field, FIELD_TYPES
from pdfrenamer.presets import MODES
from pdfrenamer.engine import ExtractEngine


class IdcardTests(unittest.TestCase):
    def test_valid_18(self):
        self.assertEqual(normalize_idcard("110101199001011234"), "110101199001011234")

    def test_handwritten_letter_o(self):
        # 手写/OCR 把 0 认成字母 O，容错后应还原
        self.assertEqual(normalize_idcard("11010119900101123O"), "110101199001011230")

    def test_handwritten_letter_l(self):
        self.assertEqual(normalize_idcard("11010119900101123l"), "110101199001011231")

    def test_strip_suffix_hao(self):
        self.assertEqual(normalize_idcard("110101199001011234号"), "110101199001011234")

    def test_invalid_length(self):
        self.assertEqual(normalize_idcard("12345"), "")

    def test_not_digits(self):
        self.assertEqual(normalize_idcard("11010119900101123X"), "11010119900101123X")


class EnumTests(unittest.TestCase):
    CHOICES = ["办公室", "财务室", "交通", "物业", "服务一部", "服务二部", "资产"]

    def test_exact(self):
        self.assertEqual(normalize_enum("财务室", self.CHOICES), "财务室")

    def test_with_space(self):
        self.assertEqual(normalize_enum("财 务 室", self.CHOICES), "财务室")

    def test_unknown_returns_raw(self):
        self.assertEqual(normalize_enum("后勤部", self.CHOICES), "后勤部")

    def test_empty(self):
        self.assertEqual(normalize_enum("", self.CHOICES), "")


class DateTests(unittest.TestCase):
    def test_standard(self):
        self.assertEqual(normalize_date("2023年5月30日"), "2023-05-30")

    def test_handwritten_o(self):
        self.assertEqual(normalize_date("2o23年5月3o日"), "2023-05-30")

    def test_handwritten_l(self):
        self.assertEqual(normalize_date("2Ol3年5月3l日"), "2013-05-31")

    def test_ocr_year_month_confusion(self):
        # V1.2.1：OCR 把「年」认成「日」、「月」认成「区」
        self.assertEqual(normalize_date("2023日5区30日"), "2023-05-30")


class PersonNameTests(unittest.TestCase):
    def test_plain_name(self):
        self.assertEqual(normalize_person_name("张明远"), "张明远")

    def test_inner_space(self):
        self.assertEqual(normalize_person_name("李 四"), "李四")

    def test_glued_dept_label(self):
        # 局部识别把相邻行标签粘连进来时应截断
        self.assertEqual(normalize_person_name("张明远 用工部门 服务一部"), "张明远")
        self.assertEqual(normalize_person_name("张明远 签订日期 2023年5月30日"), "张明远")


class ConfigAlignTests(unittest.TestCase):
    def test_yifang_type_aligned_from_text(self):
        # 用户历史配置里乙方是 text，加载时应被对齐成 person_name
        from pdfrenamer.config import _align_contract_field_types
        cfg = {"modes": {"contract": {"fields": [
            {"name": "乙方", "type": "text", "keywords": ["乙方"]},
            {"name": "身份证号", "type": "text"},
            {"name": "合同类型", "type": "text"},
        ]}}}
        _align_contract_field_types(cfg)
        types = {f["name"]: f["type"] for f in cfg["modes"]["contract"]["fields"]}
        self.assertEqual(types["乙方"], "person_name")
        self.assertEqual(types["身份证号"], "idcard")
        self.assertEqual(types["合同类型"], "enum")

    def test_align_preserves_custom_regex(self):
        from pdfrenamer.config import _align_contract_field_types
        cfg = {"modes": {"contract": {"fields": [
            {"name": "乙方", "type": "text", "regex": "自定义正则"},
        ]}}}
        _align_contract_field_types(cfg)
        self.assertEqual(cfg["modes"]["contract"]["fields"][0]["regex"], "自定义正则")


class TriggerTests(unittest.TestCase):
    """V1.2.1：两阶段触发——有文本层但手写字段缺失时也应触发 RapidOCR。"""

    def test_need_rapid_when_handwriting_missing(self):
        from pdfrenamer.models import ExtractResult, FieldResult, ST_MISSING, ST_OK
        from pdfrenamer.presets import MODES as M
        eng = ExtractEngine("contract", M["contract"], scan_rapid_enabled=True)
        doc = type("D", (), {})()
        res = ExtractResult("x.pdf", "x.pdf", "contract")
        # 乙方/日期缺失
        for f in eng.fields:
            res.fields[f.name] = FieldResult(f.name, "", "", ST_MISSING)
        self.assertTrue(eng._need_rapid(doc, res, was_no_text=False))

    def test_skip_rapid_when_all_handwriting_present(self):
        from pdfrenamer.models import ExtractResult, FieldResult, ST_OK
        from pdfrenamer.presets import MODES as M
        eng = ExtractEngine("contract", M["contract"], scan_rapid_enabled=True)
        doc = type("D", (), {})()
        res = ExtractResult("x.pdf", "x.pdf", "contract")
        for f in eng.fields:
            res.fields[f.name] = FieldResult(f.name, "值", "值", ST_OK)
        self.assertFalse(eng._need_rapid(doc, res, was_no_text=False))

    def test_no_rapid_when_disabled(self):
        from pdfrenamer.models import ExtractResult, FieldResult, ST_MISSING
        from pdfrenamer.presets import MODES as M
        eng = ExtractEngine("contract", M["contract"], scan_rapid_enabled=False)
        doc = type("D", (), {})()
        res = ExtractResult("x.pdf", "x.pdf", "contract")
        for f in eng.fields:
            res.fields[f.name] = FieldResult(f.name, "", "", ST_MISSING)
        self.assertFalse(eng._need_rapid(doc, res, was_no_text=False))


class ModelTests(unittest.TestCase):
    def test_new_field_types(self):
        self.assertIn("idcard", FIELD_TYPES)
        self.assertIn("enum", FIELD_TYPES)

    def test_choices_roundtrip(self):
        f = Field.from_dict({"name": "用工部门", "type": "enum",
                             "choices": ["办公室", "财务室"]})
        self.assertEqual(f.choices, ["办公室", "财务室"])
        d = f.to_dict()
        self.assertEqual(d["choices"], ["办公室", "财务室"])


class ContractFieldsTests(unittest.TestCase):
    def test_new_fields_present(self):
        names = [f["name"] for f in MODES["contract"]["fields"]]
        for expected in ("合同类型", "乙方", "身份证号", "开始日期",
                         "结束日期", "签订日期", "用工部门"):
            self.assertIn(expected, names)

    def test_old_fields_removed(self):
        names = [f["name"] for f in MODES["contract"]["fields"]]
        for old in ("合同名称", "甲方", "供方", "时间", "金额"):
            self.assertNotIn(old, names)

    def test_template(self):
        self.assertEqual(MODES["contract"]["template"],
                         "{合同类型}_{签订年份}_{序号}_{乙方}")


if __name__ == "__main__":
    unittest.main()
