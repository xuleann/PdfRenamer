# -*- coding: utf-8 -*-
"""V1.1.2 离线 OCR 模块单测：全部 mock subprocess，不依赖真实 OCR。"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.extractor import ocr_winrt as ocr  # noqa: E402
from pdfrenamer.extractor.base import TextDoc  # noqa: E402
from pdfrenamer.models import DOC_NO_TEXT, DOC_OK  # noqa: E402


def _ps_out(text: str) -> bytes:
    return base64.b64encode(text.encode("utf-8")) + b"\r\n"


class SpacingTests(unittest.TestCase):
    def test_normalize_chinese_spacing(self):
        self.assertEqual(ocr.normalize_ocr_line("合 同 书"), "合同书")
        self.assertEqual(ocr.normalize_ocr_line("甲 方 ： 国 家 税 务 总 局"),
                         "甲方：国家税务总局")
        self.assertEqual(ocr.normalize_ocr_line("2024 年 3 月 5 日"), "2024年3月5日")

    def test_preserve_ascii_word_space(self):
        self.assertEqual(ocr.normalize_ocr_line("Hello World 2024"), "Hello World 2024")
        self.assertEqual(ocr.normalize_ocr_line("G B · 2024 · 01026"), "G B · 2024 · 01026")

    def test_normalize_ocr_text_splits_head(self):
        raw = "甲 方 ： A 公 司\f第 二 页 内 容"
        text, head = ocr.normalize_ocr_text(raw)
        # clean_pdf_text 做 NFKC，全角冒号会变半角；规则里的 [：:] 兼容两者
        self.assertIn("甲方:A公司", text)
        self.assertIn("第二页内容", text)
        self.assertEqual(head, "甲方:A公司")


class PageIndicesTests(unittest.TestCase):
    def test_first_pages_and_last(self):
        self.assertEqual(ocr.page_indices(25, 2, True), [0, 1, 24])
        self.assertEqual(ocr.page_indices(5, 2, False), [0, 1])
        self.assertEqual(ocr.page_indices(1, 3, True), [0])
        self.assertEqual(ocr.page_indices(0, 2, True), [])
        self.assertEqual(ocr.page_indices(2, 3, True), [0, 1])


class ProbeTests(unittest.TestCase):
    def setUp(self):
        ocr._PROBE_CACHE = None

    def tearDown(self):
        ocr._PROBE_CACHE = None

    def test_probe_success_and_cached(self):
        payload = base64.b64encode(json.dumps(
            {"available": True, "lang": "zh-Hans-CN", "max_dim": 10000}
        ).encode("utf-8"))
        with mock.patch.object(ocr, "_run_powershell", return_value=payload.decode()) as run:
            a = ocr.probe_ocr()
            b = ocr.probe_ocr()
        self.assertTrue(a["available"])
        self.assertEqual(a["lang"], "zh-Hans-CN")
        self.assertEqual(a["max_dim"], 10000)
        self.assertEqual(a, b)
        self.assertEqual(run.call_count, 1)  # 结果被缓存

    def test_probe_failure_is_safe(self):
        with mock.patch.object(ocr, "_run_powershell", return_value=""):
            info = ocr.probe_ocr()
        self.assertFalse(info["available"])
        self.assertTrue(info["reason"])


class RunPowerShellTests(unittest.TestCase):
    def test_create_no_window_flag(self):
        fake = mock.Mock(returncode=0, stdout=_ps_out("x"), stderr=b"")
        with mock.patch.object(ocr.subprocess, "run", return_value=fake) as run:
            ocr._run_powershell("$x=1", 10)
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["creationflags"], 0x08000000)
        args = run.call_args.args[0]
        self.assertEqual(args[0], "powershell.exe")
        self.assertIn("-STA", args)
        self.assertIn("-EncodedCommand", args)

    def test_nonzero_returncode_returns_empty(self):
        fake = mock.Mock(returncode=2, stdout=b"", stderr=b"NO_OCR_ENGINE")
        with mock.patch.object(ocr.subprocess, "run", return_value=fake):
            self.assertEqual(ocr._run_powershell("x", 10), "")

    def test_timeout_returns_empty(self):
        import subprocess
        with mock.patch.object(ocr.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("powershell", 1)):
            self.assertEqual(ocr._run_powershell("x", 10), "")


class OcrTextTests(unittest.TestCase):
    def _scanned(self) -> Path:
        p = ROOT / "samples" / "user" / "1733213561774078181.pdf"
        if not p.exists():
            self.skipTest("真实扫描样本不可用")
        return p

    def test_ocr_text_decodes_and_normalizes(self):
        raw = "合 同 书\r\n甲 方 ： A 公 司\f乙 方 ： B 公 司"
        b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        with mock.patch.object(ocr, "_run_powershell", return_value=b64):
            text = ocr.ocr_pdf_text(self._scanned())
        self.assertIn("合同书", text)
        self.assertIn("甲方:A公司", text)
        self.assertIn("乙方:B公司", text)

    def test_ocr_failure_returns_empty(self):
        with mock.patch.object(ocr, "_run_powershell", return_value=""):
            self.assertEqual(ocr.ocr_pdf_text(self._scanned()), "")

    def test_temp_png_cleaned(self):
        b64 = base64.b64encode("测 试".encode("utf-8")).decode("ascii")
        before = set(Path(tempfile.gettempdir()).glob("pdfrenamer_ocr_*"))
        with mock.patch.object(ocr, "_run_powershell", return_value=b64):
            ocr.ocr_pdf_text(self._scanned())
        after = set(Path(tempfile.gettempdir()).glob("pdfrenamer_ocr_*"))
        self.assertEqual(before, after, "临时目录必须被清理")

    def test_png_list_uses_native_backslash(self):
        seen: dict[str, str] = {}

        def fake_run(script: str, timeout: int) -> str:
            # 从脚本里抽出 png_list 路径并读取内容
            line = next(l for l in script.splitlines() if "Get-Content" in l)
            p = line.split("'")[1]
            seen["listing"] = Path(p).read_text(encoding="utf-8")
            return ""

        with mock.patch.object(ocr, "_run_powershell", side_effect=fake_run):
            ocr.ocr_pdf_text(self._scanned())
        self.assertIn("\\", seen["listing"], "PNG 路径必须是原生反斜杠")
        self.assertNotIn("/", seen["listing"].split("\n")[0].replace(":\\", ""))


class SupplementTests(unittest.TestCase):
    def test_supplement_ok(self):
        doc = TextDoc("", DOC_NO_TEXT, 0, 5, "无文本层", {}, "")
        raw = ("合 同 书\r\n甲 方 ： 国 家 税 务 总 局 吕 梁 市 税 务 局\r\n"
               "乙 方 ： 吕 梁 玮 嘉 房 地 产 评 估 有 限 公 司\r\n"
               "日 期 ： 2024 年 3 月 5 日\f第 二 页 合 同 条 款 内 容 很 长")
        with mock.patch.object(ocr, "_ocr_raw", return_value=raw):
            out = ocr.supplement_textdoc("dummy.pdf", doc)
        self.assertIsNotNone(out)
        self.assertEqual(out.status, DOC_OK)
        self.assertIn("甲方:", out.text)
        self.assertEqual(out.metadata, {}, "扫描件元数据必须清空，避免扫描时间被当成日期")
        self.assertIn("合同书", out.head_text)
        self.assertIn("系统离线 OCR", out.note)
        self.assertEqual(out.pages, 5)

    def test_supplement_degrades_on_empty(self):
        doc = TextDoc("", DOC_NO_TEXT, 0, 5, "无文本层", {}, "")
        with mock.patch.object(ocr, "_ocr_raw", return_value=""):
            self.assertIsNone(ocr.supplement_textdoc("dummy.pdf", doc))

    def test_supplement_skips_non_no_text(self):
        doc = TextDoc("已有文本层内容", DOC_OK, 8, 2, "", {}, "已有文本层内容")
        with mock.patch.object(ocr, "_ocr_raw") as run:
            self.assertIsNone(ocr.supplement_textdoc("dummy.pdf", doc))
        run.assert_not_called()

    def test_supplement_rejects_ocr_noise(self):
        doc = TextDoc("", DOC_NO_TEXT, 0, 5, "无文本层", {}, "")
        with mock.patch.object(ocr, "_ocr_raw", return_value="\ufffd" * 30):
            self.assertIsNone(ocr.supplement_textdoc("dummy.pdf", doc))


if __name__ == "__main__":
    unittest.main(verbosity=2)
