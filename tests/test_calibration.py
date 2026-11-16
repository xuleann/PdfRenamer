# -*- coding: utf-8 -*-
"""真实样本校准后的新增规则回归测试。

覆盖：论文结构化来源、配置升级迁移、空白合同范本占位判定、括号别名防误取。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.config import (  # noqa: E402
    _merge_preset_fields, _migrate_v4, _migrate_v5, load_config,
)
from pdfrenamer.engine import ExtractEngine, _by_keyword  # noqa: E402
from pdfrenamer.models import ST_MISSING, Field  # noqa: E402
from pdfrenamer.presets import DEFAULT_CONFIG, MODES  # noqa: E402
from pdfrenamer.rules import is_placeholder, normalize_money  # noqa: E402
from pdfrenamer.structured import parse_paper  # noqa: E402

USER = ROOT / "samples" / "user"


class StructuredTests(unittest.TestCase):
    def test_ieee_metadata_subject(self):
        md = {
            "title": "A Very Long Paper Title That Is Complete",
            "author": "Jane Doe, John Roe",
            "subject": "IEEE Internet of Things Journal;2025;12;19;10.1109/JIOT.2025.1",
        }
        head = ("IEEE INTERNET OF THINGS JOURNAL, VOL. 12, NO. 19, 1 OCTOBER 2025\n"
                "40415\nA Very Long Paper Title That Is Complete\nJane Doe, John Roe\n"
                "Abstract—Some text here.")
        r = parse_paper(head, md, head)
        self.assertIn("Very Long Paper Title", r["title"][0])
        self.assertIn("Jane Doe", r["authors"][0])
        self.assertEqual(r["venue"][0], "IEEE Internet of Things Journal")
        self.assertEqual(r["year"][0], "2025")

    def test_truncated_metadata_title_completed_by_head(self):
        md = {"title": "Model Decomposition and Reassembly for Purified Knowledge Transfer "
                       "in Personalized Federat"}
        head = ("IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 24, NO. 1, JANUARY 2025\n"
                "379\nModel Decomposition and Reassembly for Purified\n"
                "Knowledge Transfer in Personalized\nFederated Learning\n"
                "Jie Zhang, Member, IEEE, Song Guo\nAbstract—Text")
        r = parse_paper(head, md, head)
        self.assertTrue(r["title"][0].endswith("Federated Learning"))
        self.assertIn("Jie Zhang", r["authors"][0])

    def test_no_metadata_falls_back_to_layout(self):
        head = ("Communication-Efficient Learning of Deep Networks\nfrom Decentralized Data\n"
                "H. Brendan McMahan\nEider Moore\nGoogle, Inc., Seattle, USA\nAbstract\n")
        r = parse_paper(head, {}, head + " Proceedings of AISTATS 2017, Copyright 2017")
        self.assertIn("Communication-Efficient", r["title"][0])
        self.assertIn("McMahan", r["authors"][0])
        self.assertEqual(r["year"][0], "2017")

    def test_field_source_is_used_before_regex(self):
        f = Field.from_dict({"name": "发表年份", "type": "year", "source": "paper_year",
                             "regex": r"Year:\s*(\d{4})"})
        e = ExtractEngine("paper", {"fields": [f.to_dict()]})
        structured = parse_paper("", {"subject": "Some Journal;2022;1;1;x"}, "")
        r = e._field_result("Year: 1999", f, structured)
        self.assertEqual(r.value, "2022")


class PlaceholderTests(unittest.TestCase):
    def test_blank_template_values_are_placeholders(self):
        for v in ("年 月 日", "____", "XXX", "—", "  ", "、，：", "年  月  日"):
            self.assertTrue(is_placeholder(v), f"应判为占位: {v!r}")
        for v in ("2024-03-05", "华东某某科技有限公司", "1200000元", "2025"):
            self.assertFalse(is_placeholder(v), f"不应判为占位: {v!r}")

    def test_money_without_digits_is_missing(self):
        self.assertEqual(normalize_money("人民币 XXX 元(大写： 元)"), "")

    def test_bracket_alias_does_not_leak_next_line(self):
        text = "出租方(甲方)：\n联系电话：\n营业执照或身份证号码：\n"
        self.assertEqual(_by_keyword(text, "甲方"), "")
        text2 = "出租方(甲方)：杭州某某置业有限公司\n联系电话：\n"
        self.assertEqual(_by_keyword(text2, "甲方"), "杭州某某置业有限公司")

    def test_english_generic_label_needs_separator(self):
        text = "the authors of this paper propose a novel method\nAuthor: Jane Doe\n"
        self.assertEqual(_by_keyword(text, "Author"), "Jane Doe")


class MigrationTests(unittest.TestCase):
    def test_v2_config_gets_source_and_new_keywords(self):
        old = {
            "config_version": 2,
            "modes": {
                "paper": {"fields": [
                    {"name": "论文题目", "keywords": ["自定义标签"], "regex": "",
                     "type": "text", "enabled": True, "required": True, "max_len": 80},
                    {"name": "我的自定义字段", "keywords": ["Foo"], "regex": "", "type": "text"},
                ], "template": "{论文题目}_自定义"},
                "contract": {"fields": []},
            },
        }
        merged = _merge_preset_fields(DEFAULT_CONFIG, old)
        pf = merged["modes"]["paper"]["fields"]
        self.assertEqual(pf[0]["source"], "paper_title")
        self.assertIn("自定义标签", pf[0]["keywords"])
        self.assertIn("Title", pf[0]["keywords"])
        self.assertNotIn("source", pf[1])       # 自定义字段不被注入
        self.assertEqual(merged["modes"]["paper"]["template"], "{论文题目}_自定义")
        # 合同空字段列表保持为空，不被强制覆盖
        self.assertEqual(merged["modes"]["contract"]["fields"], [])

    def test_factory_config_has_sources(self):
        cfg = load_config()
        self.assertEqual(cfg["config_version"], 5)
        sources = {f["name"]: f.get("source", "") for f in cfg["modes"]["paper"]["fields"]}
        self.assertEqual(sources.get("论文题目"), "paper_title")
        self.assertEqual(sources.get("发表年份"), "paper_year")
        # V1.1.2：出厂配置带齐 7 个扫描件离线 OCR 键
        self.assertTrue(cfg["scan_ocr_enabled"])
        self.assertEqual(cfg["scan_ocr_max_pages"], 2)
        self.assertTrue(cfg["scan_ocr_include_last_page"])
        self.assertEqual(cfg["scan_ocr_dpi"], 200)
        self.assertEqual(cfg["scan_ocr_max_side"], 2400)
        self.assertEqual(cfg["scan_ocr_timeout"], 60)
        self.assertEqual(cfg["scan_ocr_lang"], "auto")

    def test_v3_to_v4_migration(self):
        """v3 老配置升级：修误取 + 补别名 + 换出厂正则，用户资产一律保留。"""
        from pdfrenamer.config import _V3_CONTRACT_REGEX
        old = {
            "config_version": 3,
            "modes": {
                "contract": {
                    "fields": [
                        {"name": "合同名称",
                         "keywords": ["合同名称", "项目名称", "合同标题", "协议名称", "标题"],
                         "regex": _V3_CONTRACT_REGEX["合同名称"],
                         "type": "text", "enabled": True, "required": True, "max_len": 80},
                        {"name": "金额", "keywords": ["合同金额"],
                         "regex": _V3_CONTRACT_REGEX["金额"],
                         "type": "money", "enabled": True, "required": False, "max_len": 40},
                        {"name": "甲方", "keywords": ["甲方", "我的自定义标签"],
                         "regex": r"MY_CUSTOM_REGEX",
                         "type": "company", "enabled": True, "required": True, "max_len": 60},
                        {"name": "我的字段", "keywords": ["Foo"], "regex": "",
                         "type": "text", "enabled": True},
                    ],
                    "template": "{合同名称}_自定义",
                },
                "paper": {"fields": []},
            },
        }
        merged = _migrate_v4(_merge_preset_fields(DEFAULT_CONFIG, old), DEFAULT_CONFIG)
        f = {x["name"]: x for x in merged["modes"]["contract"]["fields"]}
        # 误取同义词被删、新别名已追加、出厂正则已更新
        self.assertNotIn("项目名称", f["合同名称"]["keywords"])
        self.assertNotIn("标题", f["合同名称"]["keywords"])
        self.assertIn("合同全称", f["合同名称"]["keywords"])
        self.assertNotEqual(f["合同名称"]["regex"], _V3_CONTRACT_REGEX["合同名称"])
        self.assertNotEqual(f["金额"]["regex"], _V3_CONTRACT_REGEX["金额"])
        # 用户自定义正则、自定义关键词、自定义字段、模板全保留
        self.assertEqual(f["甲方"]["regex"], "MY_CUSTOM_REGEX")
        self.assertIn("我的自定义标签", f["甲方"]["keywords"])
        self.assertIn("委托单位", f["甲方"]["keywords"])
        self.assertEqual(f["我的字段"]["keywords"], ["Foo"])
        self.assertEqual(merged["modes"]["contract"]["template"], "{合同名称}_自定义")
        # 新开关注入且不覆盖用户显式值
        self.assertTrue(merged["contract_type_gate"])
        self.assertEqual(merged["contract_gate_threshold"], 2)
        self.assertEqual(merged["last_input_mode"], "folder")

    def test_v4_to_v5_migration(self):
        """v4 → v5：只注入 OCR 键，用户显式关闭的值与全部字段资产都不被覆盖。"""
        old = {
            "config_version": 4,
            "scan_ocr_enabled": False,          # 用户显式关闭过 → 必须保留
            "scan_ocr_timeout": 120,
            "modes": {"contract": {"fields": [
                {"name": "甲方", "keywords": ["甲方", "我的标签"],
                 "regex": "MY_CUSTOM_REGEX", "type": "company"},
                {"name": "我的字段", "keywords": ["Foo"]},
            ], "template": "{合同名称}_我的模板"}, "paper": {"fields": []}},
        }
        merged = _migrate_v5(dict(old), DEFAULT_CONFIG)
        self.assertFalse(merged["scan_ocr_enabled"], "用户显式值不能被 setdefault 覆盖")
        self.assertEqual(merged["scan_ocr_timeout"], 120)
        for key in ("scan_ocr_max_pages", "scan_ocr_include_last_page", "scan_ocr_dpi",
                    "scan_ocr_max_side", "scan_ocr_lang"):
            self.assertIn(key, merged)
        f = {x["name"]: x for x in merged["modes"]["contract"]["fields"]}
        self.assertEqual(f["甲方"]["regex"], "MY_CUSTOM_REGEX")
        self.assertIn("我的标签", f["甲方"]["keywords"])
        self.assertEqual(f["我的字段"]["keywords"], ["Foo"])
        self.assertEqual(merged["modes"]["contract"]["template"], "{合同名称}_我的模板")

    def test_v3_to_v5_chain(self):
        """v3 → v4 → v5 链式：v4 的删词/换正则与 v5 的注入都要生效，且互不覆盖。"""
        from pdfrenamer.config import _V3_CONTRACT_REGEX
        old = {
            "config_version": 3,
            "modes": {"contract": {"fields": [
                {"name": "合同名称",
                 "keywords": ["合同名称", "项目名称", "标题"],
                 "regex": _V3_CONTRACT_REGEX["合同名称"], "type": "text"},
                {"name": "甲方", "keywords": ["甲方"], "regex": "MY_CUSTOM_REGEX",
                 "type": "company"},
            ], "template": "{合同名称}_自定义"}, "paper": {"fields": []}},
        }
        merged = _merge_preset_fields(DEFAULT_CONFIG, old)
        merged = _migrate_v4(merged, DEFAULT_CONFIG)
        merged = _migrate_v5(merged, DEFAULT_CONFIG)
        f = {x["name"]: x for x in merged["modes"]["contract"]["fields"]}
        self.assertNotIn("项目名称", f["合同名称"]["keywords"])
        self.assertNotEqual(f["合同名称"]["regex"], _V3_CONTRACT_REGEX["合同名称"])
        self.assertEqual(f["甲方"]["regex"], "MY_CUSTOM_REGEX")
        self.assertEqual(merged["modes"]["contract"]["template"], "{合同名称}_自定义")
        self.assertTrue(merged["contract_type_gate"])
        self.assertTrue(merged["scan_ocr_enabled"])


@unittest.skipUnless(any(USER.glob("*.pdf")), "未提供真实样本，跳过命中率断言")
class RealSampleTests(unittest.TestCase):
    def test_real_paper_hit_rate(self):
        from calibrate import EXPECT, hit  # 同目录脚本
        engine = ExtractEngine("paper", MODES["paper"])
        total = good = 0
        for name, exp in EXPECT.items():
            p = USER / name
            if not p.exists():
                continue
            r = engine.extract_file(p)
            for field, expected in exp.items():
                fr = r.fields.get(field)
                total += 1
                good += int(bool(fr and hit(field, fr.value, expected)))
        self.assertGreater(total, 0)
        self.assertGreaterEqual(good / total, 0.95, f"真实样本命中率退化: {good}/{total}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
