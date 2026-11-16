# -*- coding: utf-8 -*-
"""启动时的模式选择卡片：论文 / 合同。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..presets import MODES, MODE_CONTRACT, MODE_PAPER
from . import theme


def _fit_and_center(win: tk.Misc, min_w: int = 680, min_h: int = 500) -> None:
    """按内容自然尺寸设置窗口并居中（必须在控件 pack 完之后调用）。

    历史 bug：窗口写死 600x400，在高 DPI / 大字体 / 中文字体回退的机器上，
    卡片按钮与底部「取消」被裁到可视区外，用户看不到按钮、点卡片文字又无
    响应，等于卡死在首启界面。改为读取 winfo_reqwidth/reqheight 自适应，
    并夹在屏幕可视范围内；任何异常都退化为保守的大尺寸，绝不阻断启动。
    """
    try:
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        w = min(max(win.winfo_reqwidth() + 20, min_w), max(320, sw - 40))
        h = min(max(win.winfo_reqheight() + 20, min_h), max(240, sh - 80))
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        try:
            win.geometry("680x560+100+80")
        except Exception:
            pass


def _force_show(win: tk.Misc) -> None:
    """强制映射并置顶窗口，避免隐藏父窗口导致对话框不可见。"""
    for fn in (getattr(win, "deiconify", None), getattr(win, "lift", None),
               getattr(win, "focus_force", None)):
        if fn is None:
            continue
        try:
            fn()
        except Exception:
            pass


def ask_mode(parent: tk.Misc, last_mode: str = "", remember: bool = True):
    """返回 (mode, remember_choice)；取消返回 (None, remember)。"""
    dlg = tk.Toplevel(parent)
    dlg.title("PdfRenamer — 选择工作模式")
    # 对话框必须显式定位并强制显示：启动时父窗口是 withdraw() 隐藏状态，
    # 若把本窗口 transient 绑定到隐藏父窗口，部分 Windows/Tk 版本会连带隐藏
    # 本对话框，而 wait_window() 将永久阻塞 —— 表现为「进程在、无界面」。
    # 因此这里不做 transient 绑定，改为 deiconify/lift/focus_force。
    # 尺寸在控件构建完后由 _fit_and_center() 按内容自适应，不写死 600x400。
    dlg.resizable(True, True)   # 允许拉伸，极小屏/超大字体时用户也能看到全部内容
    dlg.grab_set()
    # 与 MainWindow 共用同一套 ttk 样式（Style 是 master 级单例）
    theme.apply_theme(dlg)
    dlg.configure(background=theme.BG)
    try:
        dlg.iconbitmap(default="")  # 无图标时安全忽略
    except tk.TclError:
        pass
    _force_show(dlg)

    result = {"mode": None, "remember": bool(remember)}
    remember_var = tk.BooleanVar(value=bool(remember))

    head = ttk.Frame(dlg, padding=(20, 14, 20, 4))
    head.pack(fill="x")
    ttk.Label(head, text="请选择本次要处理的资料类型",
              foreground=theme.PRIMARY,
              font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
    ttk.Label(head, text="两种模式使用不同规则，之后可随时从「模式」菜单切换。",
              foreground=theme.MUTED, wraplength=560).pack(anchor="w", pady=(4, 0))

    cards = ttk.Frame(dlg, padding=(20, 8))
    cards.pack(fill="both", expand=True)
    cards.columnconfigure(0, weight=1)
    cards.columnconfigure(1, weight=1)
    cards.rowconfigure(0, weight=1)

    def choose(mode: str) -> None:
        result["mode"] = mode
        result["remember"] = remember_var.get()
        dlg.destroy()

    for col, mode in ((0, MODE_PAPER), (1, MODE_CONTRACT)):
        cfg = MODES[mode]
        card = ttk.Frame(cards, style="Card.TFrame", padding=14)
        card.grid(row=0, column=col, padx=(0, 8) if col == 0 else (8, 0), sticky="nsew")

        def on_card_click(event, m=mode):
            # 整张卡片可点：即便按钮因 DPI/字体问题被挤出可视区，点文字也能进入
            choose(m)

        for w in (card, *card.winfo_children()):
            try:
                w.bind("<Button-1>", on_card_click)
            except Exception:
                pass
        title_lbl = ttk.Label(card, text=cfg["label"], foreground=theme.PRIMARY,
                              font=("Microsoft YaHei UI", 18, "bold"))
        title_lbl.pack(pady=(2, 2))
        desc_lbl = ttk.Label(card, text=cfg["description"], wraplength=240, justify="center",
                             foreground=theme.MUTED)
        desc_lbl.pack(pady=(0, 8))
        tpl_lbl = ttk.Label(card, text="默认命名：\n" + cfg["template"], wraplength=240,
                            justify="center", font=theme.FONT_MONO)
        tpl_lbl.pack(pady=(0, 10))
        btn = ttk.Button(card, text=f"进入「{cfg['label']}」模式",
                         command=lambda m=mode: choose(m), style="Accent.TButton")
        btn.pack(fill="x", pady=(0, 4))
        for w in (title_lbl, desc_lbl, tpl_lbl):
            try:
                w.bind("<Button-1>", on_card_click)
            except Exception:
                pass
        if mode == last_mode:
            btn.focus_set()

    bottom = ttk.Frame(dlg, padding=(24, 6, 24, 20))
    bottom.pack(fill="x")
    ttk.Checkbutton(bottom, text="记住本次选择，下次启动直接进入",
                    variable=remember_var).pack(side="left")
    ttk.Button(bottom, text="取消", command=dlg.destroy).pack(side="right")

    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
    # 控件全部构建完后再按内容自适应几何并强制显示
    _fit_and_center(dlg)
    _force_show(dlg)
    parent.wait_window(dlg)
    return result["mode"], result["remember"]
