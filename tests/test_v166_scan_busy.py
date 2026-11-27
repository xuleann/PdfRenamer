# -*- coding: utf-8 -*-
"""V1.6.6 集成回归：扫描阶段 Excel 正被打开时，不能把整次扫描打断。

旧行为：第一行写表时保存抛 ExcelBusyError → 扫描 worker 直接退出 →
预览没生成、结果没日志 → 用户关掉 Excel 后只能重扫。

现在：这一次保存失败只置 excel_busy 标记，后续行继续写增量日志，扫描照常完成；
关闭 Excel 点「恢复」能补写全部行，预览里也能直接执行改名。
"""
from __future__ import annotations

import queue
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.excel import load_rows_from_log, recover_rows  # noqa: E402
from pdfrenamer.presets import MODES  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"


def make_snap() -> dict:
    mc = MODES["contract"]
    return {
        "mode": "contract", "mode_cfg": mc,
        "template": mc.get("template", ""),
        "backend": "pymupdf", "first_pages": 3, "last_pages": 0,
        "missing_value": "未知", "max_len": 120, "strategy": "append",
        "output_dir": "", "contract_type_gate": True, "contract_gate_threshold": 2,
        "scan_ocr_enabled": False, "scan_ocr_max_pages": 2,
        "scan_ocr_include_last_page": True, "scan_ocr_dpi": 200,
        "scan_ocr_max_side": 2400, "scan_ocr_timeout": 60, "scan_ocr_lang": "auto",
        "scan_rapid_enabled": False, "sequence_counter": 1,
        "capture_field_images": False,
    }


class TestScanSurvivesExcelLock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pdfr_scan_busy_"))
        self.files = []
        for i, src in enumerate(("02_标准合同.pdf",), 1):
            dst = self.tmp / f"合同{i}.pdf"
            shutil.copy(SAMPLES / src, dst)
            self.files.append(dst)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_scan(self, locked: bool) -> tuple[dict, list]:
        from pdfrenamer.ui.main_window import MainWindow
        fake = types.SimpleNamespace(q=queue.Queue(),
                                     _capture_one=lambda *a, **k: {})
        snap = make_snap()
        if locked:
            ctx = patch("openpyxl.workbook.workbook.Workbook.save",
                        side_effect=PermissionError("locked"))
        else:
            ctx = patch("openpyxl.workbook.workbook.Workbook.save")
        with ctx:
            MainWindow._scan_worker(fake, str(self.tmp), self.files, snap)
        msgs = []
        while not fake.q.empty():
            msgs.append(fake.q.get())
        return snap, msgs

    def test_scan_completes_when_excel_locked(self):
        snap, msgs = self._run_scan(locked=True)
        kinds = [m[0] for m in msgs]
        self.assertIn("preview", kinds, "扫描必须照常完成、生成预览")
        self.assertNotIn("excel_busy", kinds, "不应再因第一行失败就整体报错退出")
        self.assertTrue(snap.get("excel_busy"), "需要标记复核表未写入")

    def test_log_keeps_rows_when_excel_locked(self):
        self._run_scan(locked=True)
        rows = load_rows_from_log(self.tmp, "contract")
        self.assertEqual(len(rows), len(self.files), "每份文件都要留在增量日志里")

    def test_recover_after_unlock_writes_rows(self):
        self._run_scan(locked=True)
        n = recover_rows(self.tmp, "contract", MODES["contract"]["sheet"],
                         MODES["contract"]["label"], ["合同类型", "乙方"], "未知")
        self.assertEqual(n, len(self.files))
        from openpyxl import load_workbook
        from pdfrenamer.excel import FILE_NAME
        ws = load_workbook(self.tmp / FILE_NAME)[MODES["contract"]["sheet"]]
        self.assertEqual(ws.max_row, 1 + len(self.files))

    def test_normal_scan_marks_not_busy(self):
        snap, msgs = self._run_scan(locked=False)
        self.assertFalse(snap.get("excel_busy"))
        self.assertIn("preview", [m[0] for m in msgs])


if __name__ == "__main__":
    unittest.main()
