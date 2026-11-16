# -*- coding: utf-8 -*-
"""V1.1.1「单独选择一个或多个 PDF 文件」的 UI 无头测试。

通过 monkeypatch MainWindow._pick_pdf_files 注入文件选择结果，不弹出系统对话框。
用法（项目根目录执行）：.venv/Scripts/python.exe tests/test_ui_files.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SAMPLES = ROOT / "tests" / "samples"

import pdfrenamer.ui.main_window as mw  # noqa: E402
from pdfrenamer.config import load_config  # noqa: E402
from pdfrenamer.excel import FILE_NAME  # noqa: E402
from pdfrenamer.presets import MODE_CONTRACT  # noqa: E402

_ORIG_PICK = mw.MainWindow._pick_pdf_files
_ORIG_WARN = mw.messagebox.showwarning
_ORIG_SAVE = mw.save_config

# 屏蔽阻塞式弹窗与本机配置写入（测试不得污染用户 %APPDATA%/config.json）
mw.messagebox.askyesno = lambda *a, **k: True
mw.messagebox.showinfo = lambda *a, **k: None
mw.messagebox.showwarning = lambda *a, **k: None
mw.messagebox.showerror = lambda *a, **k: print("ERROR DIALOG:", a[-1] if a else "")
mw.save_config = lambda cfg: None


def wait_until(predicate, root, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.02)
    return False


class FilesModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not list(SAMPLES.glob("*.pdf")):
            from make_samples import main as gen
            gen()

    def setUp(self):
        # 每个用例都重新屏蔽写配置与阻塞式弹窗：模块级 lambda 会被其它测试模块
        # 的 tearDown 恢复掉（尤其 messagebox.askyesno 恢复后会弹真对话框挂住测试）。
        mw.save_config = lambda cfg: None
        mw.messagebox.askyesno = lambda *a, **k: True
        mw.messagebox.showinfo = lambda *a, **k: None
        mw.messagebox.showerror = lambda *a, **k: None
        self.tmp = Path(tempfile.mkdtemp(prefix="pdfrenamer_files_"))
        self.tmp2 = Path(tempfile.mkdtemp(prefix="pdfrenamer_files2_"))
        for name in ("02_标准合同.pdf", "07_重名A.pdf", "08_重名B.pdf"):
            shutil.copy2(SAMPLES / name, self.tmp / name)
        shutil.copy2(SAMPLES / "02_标准合同.pdf", self.tmp2 / "另一个目录的合同.pdf")
        cfg = load_config()
        cfg.update({
            "remember_mode": True, "last_mode": MODE_CONTRACT,
            "last_dir": str(self.tmp), "excel_strategy": "append",
            "last_input_mode": "folder", "contract_type_gate": True,
        })
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = mw.MainWindow(self.root, cfg)
        self.warn_calls: list = []
        mw.messagebox.showwarning = lambda *a, **k: self.warn_calls.append(a)

    def tearDown(self):
        mw.MainWindow._pick_pdf_files = _ORIG_PICK
        # 同 test_manual_override：不恢复真实 messagebox / save_config，
        # 避免跨模块顺序运行时写用户配置或弹阻塞对话框。
        mw.save_config = lambda cfg: None
        mw.messagebox.showwarning = lambda *a, **k: None
        mw.messagebox.askyesno = lambda *a, **k: True
        mw.messagebox.showinfo = lambda *a, **k: None
        mw.messagebox.showerror = lambda *a, **k: None
        if getattr(self.win, "_after_id", None):
            try:
                self.root.after_cancel(self.win._after_id)
            except tk.TclError:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.tmp2, ignore_errors=True)

    def _to_files_mode(self):
        self.win.input_mode_var.set("files")
        self.win._on_input_mode_change()

    def test_same_directory_select_two_and_process(self):
        """选 2 个同目录 PDF：只处理 2 个、Excel 仍在该目录、可撤销。"""
        self.assertEqual(self.win.input_mode_var.get(), "folder", "默认应为文件夹模式")
        self._to_files_mode()
        picked = (str(self.tmp / "02_标准合同.pdf"), str(self.tmp / "07_重名A.pdf"))
        mw.MainWindow._pick_pdf_files = lambda self: picked
        self.win._choose_files()

        self.assertEqual(len(self.win.selected_files), 2)
        self.assertEqual(self.win.dir_var.get(), str(self.tmp.resolve()),
                         "共同父目录必须写回唯一 directory 锚点")

        self.win._on_scan()
        self.assertTrue(wait_until(lambda: self.win.preview_data is not None, self.root),
                        "扫描预览超时")
        results, records, snap, _ = self.win.preview_data
        self.assertEqual(len(results), 2, "只应处理选中的 2 个文件")
        self.assertEqual(snap["output_dir"], str(self.tmp.resolve()))

        self.win._on_execute()
        self.assertTrue(wait_until(lambda: not self.win.busy, self.root, timeout=60),
                        "执行超时")
        self.root.update()
        xlsx = self.tmp / FILE_NAME
        self.assertTrue(xlsx.exists(), "Excel 必须生成在这 2 个文件所在目录")
        from openpyxl import load_workbook
        wb = load_workbook(xlsx)
        self.assertEqual(wb["合同汇总"].max_row - 1, 2)
        wb.close()

        self.win._on_undo()
        self.root.update()
        self.assertTrue((self.tmp / "02_标准合同.pdf").exists(), "撤销应恢复原文件名")

    def test_cross_directory_is_rejected(self):
        """跨目录选择：弹窗提示且无任何改名 / Excel 副作用。"""
        self._to_files_mode()
        before = list(self.win.selected_files)
        picked = (str(self.tmp / "02_标准合同.pdf"),
                  str(self.tmp2 / "另一个目录的合同.pdf"))
        mw.MainWindow._pick_pdf_files = lambda self: picked
        self.win._choose_files()

        self.assertEqual(len(self.warn_calls), 1, "应弹出「请按目录分批处理」")
        self.assertEqual(self.win.selected_files, before, "跨目录选择不得写入已选列表")
        self.assertIsNone(self.win.preview_data)
        self.assertFalse((self.tmp / FILE_NAME).exists())
        self.assertFalse((self.tmp2 / FILE_NAME).exists())
        self.assertTrue((self.tmp2 / "另一个目录的合同.pdf").exists())

    def test_clear_files(self):
        self._to_files_mode()
        one = str(self.tmp / "02_标准合同.pdf")
        mw.MainWindow._pick_pdf_files = lambda _win: (one,)
        self.win._choose_files()
        self.assertEqual(len(self.win.selected_files), 1)
        self.win._clear_files()
        self.assertEqual(self.win.selected_files, [])
        self.assertIn("尚未选择", self.win.count_var.get())


if __name__ == "__main__":
    unittest.main(verbosity=2)
