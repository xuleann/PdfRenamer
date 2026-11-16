# -*- coding: utf-8 -*-
"""V1.1.1 负样本与合同规则回归测试（stdlib unittest，纯只读样本）。"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.contract_gate import is_contract_document  # noqa: E402
from pdfrenamer.engine import (  # noqa: E402
    ExtractEngine, _by_keyword, check_same_parent, normalize_pdf_paths,
)
from pdfrenamer.models import DOC_NOT_CONTRACT  # noqa: E402
from pdfrenamer.presets import MODES  # noqa: E402
from pdfrenamer.renamer import RenameEngine  # noqa: E402
from pdfrenamer.rules import normalize_date, normalize_money  # noqa: E402

from calibrate_negative import CONTRACT_FIELDS, NEGATIVE_FILES, USER  # noqa: E402

_HAS_SAMPLES = all((USER / n).exists() for n in NEGATIVE_FILES)


@unittest.skipUnless(_HAS_SAMPLES, "缺少 3 份绩效评价报告负样本")
class NegativeSampleTests(unittest.TestCase):
    def test_not_contract_all_missing_and_no_rename(self):
        engine = ExtractEngine("contract", MODES["contract"])
        renamer = RenameEngine(MODES["contract"]["template"], "未知", 120)
        for name in NEGATIVE_FILES:
            p = USER / name
            with self.subTest(sample=name):
                r = engine.extract_file(p)
                self.assertEqual(r.doc_status, DOC_NOT_CONTRACT,
                                 "绩效评价报告必须判为非合同文档")
                for f in CONTRACT_FIELDS:
                    fr = r.fields[f]
                    self.assertTrue(fr.is_missing, f"{name}/{f} 不应提取到值")
                    self.assertFalse(fr.value)
                    self.assertEqual(fr.file_value, "未知")
                self.assertNotIn("项目名称", r.fields["合同名称"].value or "")
                rec = renamer.plan([r], p.parent)[0]
                self.assertEqual(rec.status, "skipped", "非合同文档不得参与改名")


class ContractGateTests(unittest.TestCase):
    def test_real_contract_passes(self):
        head = ("设备采购合同\n"
                "合同名称：自检用服务器采购合同\n"
                "甲方（盖章）：华东某某科技有限公司\n"
                "供方（盖章）：北京某某信息技术有限公司\n"
                "签订日期：2024年3月5日\n"
                "合同金额：¥1,200,000.00元\n")
        ok, info = is_contract_document(head, head, threshold=2)
        self.assertTrue(ok, f"真实合同不应被误杀：{info}")

    def test_performance_report_is_vetoed(self):
        head = ("某市财政支出\n绩效评价报告\n"
                "项目名称：2018 年某公路日常养护项目\n"
                "评价机构：某某税务师事务所有限公司\n"
                "二〇一九年六月\n")
        ok, info = is_contract_document(head, head, threshold=2)
        self.assertFalse(ok, f"绩效评价报告应判非合同：{info}")
        self.assertGreater(info["neg"], 0)

    def test_party_fragment_without_colon_does_not_count(self):
        text = "绩效评价报告\n后，甲方支付材料费，乙方免收\n"
        ok, info = is_contract_document(text, text, threshold=2)
        self.assertFalse(ok)
        self.assertEqual(info["parties"], [])

    def test_strong_positive_whitelist(self):
        text = "合同编号：HT-2024-001\n签订地点：上海市\n"
        ok, info = is_contract_document("", text, threshold=2)
        self.assertTrue(ok)
        self.assertIn("白名单", info["reason"])


class NewRuleTests(unittest.TestCase):
    def test_chinese_numeral_date(self):
        self.assertEqual(normalize_date("二〇一八年十一月"), "2018-11")
        self.assertEqual(normalize_date("二〇一九年六月"), "2019-06")
        self.assertEqual(normalize_date("二〇二三年七月十五日"), "2023-07-15")
        # 原有阿拉伯数字路径不退化
        self.assertEqual(normalize_date("2024年3月5日"), "2024-03-05")
        self.assertEqual(normalize_date("2023 年7 月"), "2023-07")

    def test_narrative_money_regex(self):
        f = next(x for x in MODES["contract"]["fields"] if x["name"] == "金额")
        cases = {
            "合同总金额为123.4567 万元": "1234567元",
            "合同金额：¥1,200,000.00元": "1200000.00元",
            "合同价款为人民币 8500 元": "8500元",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                m = re.search(f["regex"], text)
                self.assertIsNotNone(m, f"金额正则未命中: {text}")
                self.assertEqual(normalize_money(m.group(1)), expected)

    def test_money_without_digits_still_missing(self):
        f = next(x for x in MODES["contract"]["fields"] if x["name"] == "金额")
        self.assertIsNone(re.search(f["regex"], "合同金额：人民币 XXX 元"))

    def test_continuation_line_merged(self):
        text = ("预算单位：某区平安街道办事处、\n"
                "某区向阳街道办事处、某区望湖街道办事处\n")
        v = _by_keyword(text, "预算单位")
        self.assertIn("向阳", v)
        self.assertIn("平安", v)

    def test_bracket_alias_still_returns_empty(self):
        text = "出租方(甲方)：\n联系电话：\n营业执照或身份证号码：\n"
        self.assertEqual(_by_keyword(text, "甲方"), "")


class SameParentTests(unittest.TestCase):
    def test_same_directory(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.pdf", Path(d) / "b.pdf"
            a.write_bytes(b"x")
            b.write_bytes(b"x")
            ok, parent = check_same_parent([a, b])
            self.assertTrue(ok)
            self.assertEqual(parent, Path(d).resolve())
            self.assertEqual(normalize_pdf_paths([a, b, Path(d) / "note.txt"]), [a, b])

    def test_cross_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            ok, parent = check_same_parent([Path(d1) / "a.pdf", Path(d2) / "b.pdf"])
            self.assertFalse(ok)
            self.assertIsNone(parent)

    def test_empty(self):
        self.assertEqual(check_same_parent([]), (True, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
