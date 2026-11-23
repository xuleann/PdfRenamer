# -*- coding: utf-8 -*-
"""V1.4.4：用工部门定位在「第二条第二点」的回归测试。

真实合同原文（OCR 结果）：
  劳动合同 2.乙方同意根据甲方工作需要，在财务室（部门）出纳岗位工作。
  劳动合同 2.乙方同意根据甲方工作需要，在机关务二部部门）会务岗位工作。   ← 丢了一个括号
  劳务合同 2.乙方同意根据甲方工作需要，在之部（室）岗                      ← 手写没认出来

旧实现把「办公」当作「办公室」的变体，导致第二条第一点「…或办公地点工作」
让几乎所有合同都被判成「办公室」。以下用例锁死该缺陷。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfrenamer.rules import (  # noqa: E402
    DEPARTMENT_CHOICES,
    find_department,
    normalize_department,
)


class TestDepartmentAtClause2(unittest.TestCase):
    REAL_MENG = (
        "第二条工作岗位\n"
        "1.乙方须服从甲方的工作安排，在甲方指定的工作场所或办公地点工作。\n"
        "2.乙方同意根据甲方工作需要，在财务室（部门）出纳岗位工作。\n"
        "第三条工作时间和休息\n"
        "1.乙方所在岗位执行：②类。"
    )
    REAL_LIU = (
        "第二条工作岗位\n"
        "1.乙方须服从甲方的工作安排，在甲方指定的工作场所或办公地点工作。\n"
        "2.乙方同意根据甲方工作需要，在机关务二部部门）会务岗位工作。\n"
        "第三条工作时间"
    )
    REAL_QI = (
        "第二条工作岗位\n"
        "1.乙方必须服从甲方的工作安排，根据甲方工作要求完成劳务工作。\n"
        "2.乙方同意根据甲方工作需要，在之部（室）岗\n"
        "第三条工作时间"
    )

    def test_real_contract_returns_finance_room(self):
        """「办公地点」不得再被当成部门——真实合同是财务室。"""
        self.assertEqual(find_department(self.REAL_MENG), "财务室")

    def test_real_contract_with_missing_paren(self):
        """扫描件丢左括号 + 手写「服务二部」被识别成「务二部」，仍应命中。"""
        self.assertEqual(find_department(self.REAL_LIU), "服务二部")

    def test_unreadable_handwriting_returns_blank(self):
        """手写完全没识别出来时必须留空（交给截图人工核对），绝不猜成办公室。"""
        self.assertEqual(find_department(self.REAL_QI), "")

    def test_office_word_trap(self):
        """「办公地点/办公场所」不是部门。"""
        text = "第二条\n1.在甲方指定的办公地点工作\n2.在资产（部门）工作\n第三条"
        self.assertEqual(find_department(text), "资产")

    def test_tail_clause_not_department(self):
        """合同尾部「甲乙双方及用人部（室）各执壹份」不能被当成岗位部门。"""
        text = (
            "第二条工作岗位\n2.乙方同意根据甲方工作需要，在物业（部门）保洁岗位工作。\n"
            "第三条\n4.本合同一式叁份，甲乙双方及用人部（室）各执壹份。"
        )
        self.assertEqual(find_department(text), "物业")

    def test_all_seven_choices_supported(self):
        for dept in DEPARTMENT_CHOICES:
            text = f"第二条工作岗位\n2.乙方同意根据甲方工作需要，在{dept}（部门）岗位工作。"
            self.assertEqual(find_department(text), dept, f"{dept} 未识别")

    def test_normalize_handles_fullwidth_and_short(self):
        self.assertEqual(normalize_department("机关服务二部"), "服务二部")
        self.assertEqual(normalize_department("务室"), "财务室")
        self.assertEqual(normalize_department("服务1部"), "服务一部")


class TestNameNeedsScreenshot(unittest.TestCase):
    """V1.4.6：手写姓名把下一栏的字串进来时，必须判为不可信并贴图。"""

    def test_name_with_trailing_label_char_is_suspect(self):
        from pdfrenamer.rules import suspect_field_value
        # 真实样本：手写「张光明」被 OCR 认成「张气明性」（末字串了「性别」的「性」）
        self.assertTrue(suspect_field_value("乙方", "张气明性"))
        self.assertTrue(suspect_field_value("乙方", "张三签字"))

    def test_legit_four_char_name_not_suspect(self):
        from pdfrenamer.rules import suspect_field_value
        self.assertFalse(suspect_field_value("乙方", "欧阳娜娜"))
        self.assertFalse(suspect_field_value("乙方", "张光明"))


if __name__ == "__main__":
    unittest.main()
