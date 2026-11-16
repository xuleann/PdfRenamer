# -*- coding: utf-8 -*-
"""现代浅色主题（V1.1.1，纯标准库 ttk，零第三方 GUI 依赖）。

设计约束：
- 顶层**只定义常量与函数，绝不创建 ttk.Style()**。`app.py` 在模块顶层 import
  main_window，而 `--selftest` 会在创建 tk.Tk() 之前 return；顶层建 Style 会抛 TclError。
- `apply_theme(root)` 幂等，由 MainWindow.__init__ 调用；`ui_smoke` 直接实例化
  MainWindow 时同样生效；`--selftest` 完全不碰 Tk。
- 不引入 PIL.ImageTk / ttkbootstrap / customtkinter，`requirements.txt` 与
  PyInstaller spec 的 datas / hiddenimports / excludes 均无需改动。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# 主色与中性色
PRIMARY = "#1f4e79"
PRIMARY_DARK = "#163d5f"
ACCENT = "#2f6fb0"
BG = "#f5f7fa"
CARD_BG = "#ffffff"
TEXT = "#1f2933"
MUTED = "#5a6472"
SUBTLE = "#7a8492"
WARN = "#c0392b"
BORDER = "#d7dee8"

TREE_ODD = "#ffffff"
TREE_EVEN = "#f4f7fb"
TREE_SELECT = "#cfe2f3"
HEADER_BG = "#e8eef6"
SKIP_FG = "#b03a2e"
WARN_FG = "#b9770e"

FONT_UI = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 11, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 8)
FONT_MONO = ("Consolas", 9)


def apply_theme(root: tk.Misc) -> ttk.Style:
    """应用主题；同一 root 重复调用直接返回（幂等）。"""
    if getattr(root, "_pdfrenamer_themed", False):
        return ttk.Style(root)
    style = ttk.Style(root)
    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", font=FONT_UI, background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD_BG, relief="solid", borderwidth=1)
    style.configure("TLabel", background=BG, foreground=TEXT, font=FONT_UI)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
    style.configure("Title.TLabel", background=BG, foreground=PRIMARY, font=FONT_BOLD)

    # 卡片式分区：默认 TLabelframe 即卡片，另留 Card.* 别名备用
    for name in ("TLabelframe", "Card.TLabelframe"):
        style.configure(name, background=CARD_BG, relief="solid", borderwidth=1)
    for name in ("TLabelframe.Label", "Card.TLabelframe.Label"):
        style.configure(name, background=BG, foreground=PRIMARY, font=FONT_BOLD)

    style.configure("TButton", font=FONT_UI, padding=(10, 5))
    style.map("TButton", background=[("active", "#e3ecf7")],
              foreground=[("disabled", SUBTLE)])
    style.configure("Accent.TButton", background=PRIMARY, foreground="#ffffff",
                    font=FONT_BOLD, padding=(12, 6), borderwidth=0)
    style.map("Accent.TButton",
              background=[("active", ACCENT), ("disabled", BORDER)],
              foreground=[("disabled", SUBTLE)])

    style.configure("TEntry", fieldbackground=CARD_BG, foreground=TEXT, padding=4)
    style.configure("TCombobox", fieldbackground=CARD_BG, padding=3)
    style.configure("TSpinbox", fieldbackground=CARD_BG, padding=3)
    style.configure("TCheckbutton", background=BG, foreground=TEXT, font=FONT_UI)
    style.configure("TRadiobutton", background=BG, foreground=TEXT, font=FONT_UI)
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(12, 5), font=FONT_UI)
    style.configure("TProgressbar", background=PRIMARY, troughcolor=BG)

    style.configure("Treeview", background=CARD_BG, fieldbackground=CARD_BG,
                    foreground=TEXT, rowheight=26, borderwidth=0, font=FONT_UI)
    style.configure("Treeview.Heading", background=HEADER_BG, foreground=PRIMARY,
                    font=FONT_BOLD, padding=5)
    style.map("Treeview", background=[("selected", TREE_SELECT)],
              foreground=[("selected", TEXT)])

    try:
        style.configure("Horizontal.TProgressbar", background=PRIMARY, troughcolor=BG)
    except tk.TclError:
        pass

    root._pdfrenamer_themed = True  # type: ignore[attr-defined]
    return style


def configure_tree_tags(tree: ttk.Treeview) -> None:
    """斑马纹 + 状态前景色（两者属性不同，可叠加在同一行上）。"""
    tree.tag_configure("odd", background=TREE_ODD)
    tree.tag_configure("even", background=TREE_EVEN)
    tree.tag_configure("skip", foreground=SKIP_FG)
    tree.tag_configure("warn", foreground=WARN_FG)
