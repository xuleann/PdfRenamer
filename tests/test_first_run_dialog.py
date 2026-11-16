# -*- coding: utf-8 -*-
"""首次启动（无 last_mode）模式选择对话框可见性回归。

历史 bug：app.py 先 root.withdraw()，ask_mode() 又对隐藏父窗口做
dlg.transient(parent)，在部分 Windows/Tk 版本下对话框被连带隐藏，
wait_window() 永久阻塞 —— 表现为「双击后进程在、无任何界面」。
本机因已记住模式从不走此路径，故必须用测试覆盖首次启动。
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.ui import mode_selector as ms  # noqa: E402


class FirstRunDialogTests(unittest.TestCase):
    def test_dialog_is_visible_on_hidden_parent(self):
        """隐藏父窗口下，模式选择对话框必须可见且可正常返回。"""
        root = tk.Tk()
        root.withdraw()  # 复现 app.py 的启动状态

        seen: dict[str, object] = {}

        def inspect_and_close():
            children = [w for w in root.winfo_children()
                        if isinstance(w, tk.Toplevel)]
            self.assertEqual(len(children), 1, "应恰好弹出一个模式选择对话框")
            dlg = children[0]
            seen["state"] = dlg.state()
            seen["viewable"] = bool(dlg.winfo_viewable())
            dlg.destroy()

        root.after(200, inspect_and_close)
        try:
            mode, remember = ms.ask_mode(root, "", True)
        finally:
            root.destroy()

        self.assertEqual(seen.get("state"), "normal", "对话框不能是 withdrawn")
        self.assertTrue(seen.get("viewable"), "对话框必须可见")
        self.assertIsNone(mode, "用例中对话框被关闭，应返回 None 而非死等")

    def test_dialog_fits_content_and_card_is_clickable(self):
        """高 DPI/大字体下按钮不被裁，且整张卡片可点击（不只靠按钮）。"""
        from pdfrenamer.ui import theme

        orig = (theme.FONT_UI, theme.FONT_BOLD, theme.FONT_SMALL)
        theme.FONT_UI = ("Microsoft YaHei UI", 15)
        theme.FONT_BOLD = ("Microsoft YaHei UI", 16, "bold")
        theme.FONT_SMALL = ("Microsoft YaHei UI", 13)
        try:
            root = tk.Tk()
            root.withdraw()
            seen: dict[str, object] = {}

            def probe():
                dlg = [w for w in root.winfo_children()
                       if isinstance(w, tk.Toplevel)][0]
                dlg.update_idletasks()
                geo = dlg.geometry().split("+")[0]
                w, h = (int(x) for x in geo.split("x"))
                seen["size"] = (w, h)
                seen["req_h"] = dlg.winfo_reqheight()
                # 卡片标题点击后应选中论文模式
                labels: list[tk.Widget] = []

                def walk(x):
                    for c in x.winfo_children():
                        try:
                            if c.cget("text") in ("论文", "合同"):
                                labels.append(c)
                        except Exception:
                            pass
                        walk(c)
                walk(dlg)
                card = [l for l in labels if l.cget("text") == "论文"]
                if not card:
                    seen["click_error"] = "未找到论文卡片"
                    if dlg.winfo_exists():
                        dlg.destroy()
                    return
                card[0].event_generate("<Button-1>")

            root.after(400, probe)
            try:
                mode, _ = ms.ask_mode(root, "", True)
            finally:
                root.destroy()
            self.assertNotIn("click_error", seen, seen.get("click_error", ""))
            self.assertEqual(mode, "paper", "点击卡片标题应选中论文模式")
            w, h = seen["size"]
            self.assertGreaterEqual(h, seen["req_h"],
                                    "窗口高度必须容得下内容，否则按钮被裁")
        finally:
            theme.FONT_UI, theme.FONT_BOLD, theme.FONT_SMALL = orig

    def test_no_transient_binding_to_parent(self):
        """静态约束：对话框不得 transient 绑定到可能隐藏的父窗口。"""
        src = (ROOT / "src" / "pdfrenamer" / "ui" / "mode_selector.py").read_text(
            encoding="utf-8")
        body = src.split("def ask_mode", 1)[-1]
        # 只看实际调用，忽略注释里对历史 bug 的说明
        calls = [ln.strip() for ln in body.splitlines()
                 if ln.strip().startswith("dlg.transient(")]
        self.assertEqual(calls, [],
                         "不可对隐藏父窗口调用 transient()，否则对话框会被连带隐藏")
        self.assertIn("_force_show(dlg)", body,
                      "应显式强制显示对话框保证映射")
        self.assertIn("_fit_and_center(dlg)", body, "应按内容自适应几何，不写死尺寸")


if __name__ == "__main__":
    unittest.main(verbosity=2)
