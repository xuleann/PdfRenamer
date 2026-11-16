# -*- coding: utf-8 -*-
"""V1.1.2 人工补录单测：无头实例化 MainWindow，不弹任何对话框。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pdfrenamer.ui.main_window as mw  # noqa: E402
from pdfrenamer.config import load_config  # noqa: E402
from pdfrenamer.engine import ExtractEngine  # noqa: E402
from pdfrenamer.models import DOC_NO_TEXT, DOC_OK, ST_MANUAL  # noqa: E402
from pdfrenamer.presets import MODES  # noqa: E402
from pdfrenamer.renamer import RenameEngine  # noqa: E402

_ORIG_PICK = mw.MainWindow._pick_pdf_files
_ORIG_DIALOG = mw.MainWindow._open_override_dialog
_ORIG_SAVE = mw.save_config
_ORIG_WARN = mw.messagebox.showwarning
_ORIG_YES = mw.messagebox.askyesno
_ORIG_INFO = mw.messagebox.showinfo


class ManualOverrideTests(unittest.TestCase):
    def setUp(self):
        # 每个用例都重新屏蔽配置写入与阻塞式弹窗：模块级 lambda 可能被其它
        # 测试模块的 tearDown 恢复掉，导致跨模块顺序运行时污染用户配置或弹真对话框。
        mw.save_config = lambda _c: None
        mw.messagebox.askyesno = lambda *a, **k: True
        mw.messagebox.showinfo = lambda *a, **k: None
        mw.messagebox.showwarning = lambda *a, **k: None
        mw.messagebox.showerror = lambda *a, **k: None
        self.tmp = Path(tempfile.mkdtemp(prefix="pdfrenamer_override_"))
        src = ROOT / "tests" / "samples" / "03_扫描件.pdf"
        if src.exists():
            shutil.copy2(src, self.tmp / "03_扫描件.pdf")
        self.root = tk.Tk()
        self.root.withdraw()
        cfg = load_config()
        cfg["last_dir"] = str(self.tmp)
        cfg["last_mode"] = "contract"
        cfg["config_version"] = 5
        cfg["last_input_mode"] = "folder"   # 不依赖用户上次会话的输入方式
        with mock.patch.object(mw, "save_config", lambda _c: None):
            self.win = mw.MainWindow(self.root, cfg)
        self.win.mode = "contract"
        mw.save_config = lambda _c: None
        mw.messagebox.showwarning = lambda *a, **k: None
        mw.messagebox.askyesno = lambda *a, **k: True
        mw.messagebox.showinfo = lambda *a, **k: None
        # 关键：本轮所有测试都不弹补录对话框
        mw.MainWindow._open_override_dialog = lambda self, result: None

    def tearDown(self):
        mw.MainWindow._pick_pdf_files = _ORIG_PICK
        mw.MainWindow._open_override_dialog = _ORIG_DIALOG
        # 不把 save_config / messagebox 恢复成真实函数：其它 UI 测试模块可能
        # 在本模块之后运行，恢复会写用户配置或弹出阻塞对话框。测试进程内
        # 全程保持屏蔽，进程结束时模块全局自然复原，不触及用户数据。
        mw.save_config = lambda _c: None
        mw.messagebox.showwarning = lambda *a, **k: None
        mw.messagebox.askyesno = lambda *a, **k: True
        mw.messagebox.showinfo = lambda *a, **k: None
        mw.messagebox.showerror = lambda *a, **k: None
        if self.win._after_id:
            try:
                self.root.after_cancel(self.win._after_id)
            except tk.TclError:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_preview(self):
        """用真实 ExtractEngine 结果构造一份 skipped 预览（不跑 OCR）。"""
        eng = ExtractEngine("contract", MODES["contract"], scan_ocr_enabled=False)
        results = eng.extract_many([self.tmp / "03_扫描件.pdf"])
        self.assertEqual(results[0].doc_status, DOC_NO_TEXT)
        renamer = RenameEngine(MODES["contract"]["template"], "未知", 120)
        records = renamer.plan(results, self.tmp)
        snap = self.win._snapshot(str(self.tmp))
        self.win.preview_data = (results, records, snap, [])
        self.win._fill_preview(results, records, [], snap)
        return results, records

    def test_override_turns_skipped_into_planned(self):
        results, records = self._fake_preview()
        self.assertEqual(records[0].status, "skipped")
        key = self.win._result_key(results[0].path)
        self.win.manual_overrides[key] = {
            "合同名称": "扫描件采购合同",
            "甲方": "华东某某科技有限公司",
            "供方": "北京某某信息技术有限公司",
            "时间": "2024-03-05",
        }
        self.win._apply_overrides()
        patched, new_records, _, _ = self.win.preview_data
        self.assertEqual(patched[0].doc_status, "partial")
        self.assertEqual(patched[0].fields["甲方"].status, ST_MANUAL)
        self.assertEqual(patched[0].fields["甲方"].note, "人工补录")
        self.assertEqual(new_records[0].status, "planned")
        self.assertTrue(new_records[0].new_name.startswith("扫描件采购合同_"))
        self.assertIn("华东某某科技有限公司", new_records[0].new_name)
        self.assertIn("人工补录", new_records[0].reason)

    def test_override_values_normalized_by_type(self):
        results, _ = self._fake_preview()
        key = self.win._result_key(results[0].path)
        self.win.manual_overrides[key] = {
            "合同名称": "测试合同", "甲方": "甲公司", "供方": "乙公司",
            "时间": "2024年3月5日", "金额": "¥1,200,000.00元",
        }
        self.win._apply_overrides()
        f = self.win.preview_data[0][0].fields
        self.assertEqual(f["时间"].value, "2024-03-05")
        self.assertEqual(f["金额"].value, "1200000.00元")

    def test_clear_preview_drops_overrides(self):
        results, _ = self._fake_preview()
        self.win.manual_overrides[self.win._result_key(results[0].path)] = {"甲方": "甲公司"}
        self.win._clear_preview()
        self.assertEqual(self.win.manual_overrides, {})
        self.assertIsNone(self.win.preview_data)

    def test_snapshot_has_ocr_keys(self):
        snap = self.win._snapshot(str(self.tmp))
        for key in ("scan_ocr_enabled", "scan_ocr_max_pages", "scan_ocr_include_last_page",
                    "scan_ocr_dpi", "scan_ocr_max_side", "scan_ocr_timeout", "scan_ocr_lang"):
            self.assertIn(key, snap)
        self.assertEqual(snap["scan_ocr_max_pages"], 2)
        self.assertTrue(snap["scan_ocr_enabled"])

    def test_double_click_maps_to_result(self):
        results, _, = self._fake_preview()[0], None
        seen = []
        mw.MainWindow._open_override_dialog = lambda self, r: seen.append(r.original_name)
        tree = self.win.pv_tree
        iid = tree.get_children()[0]
        ev = mock.Mock()
        ev.y = 5
        with mock.patch.object(tree, "identify_row", return_value=iid):
            self.win._on_edit_row(ev)
        self.assertEqual(seen, [results[0].original_name])

    def test_no_overrides_is_noop(self):
        results, records = self._fake_preview()
        self.win._apply_overrides()
        self.assertIs(self.win.preview_data[0][0], results[0])
        self.assertIs(self.win.preview_data[1][0], records[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
