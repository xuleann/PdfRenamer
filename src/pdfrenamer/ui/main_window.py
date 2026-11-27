# -*- coding: utf-8 -*-
"""主窗口：选文件夹 → 配置字段/模板 → 扫描预览 → 确认执行 → 导出 Excel / 撤销。

所有耗时操作在后台线程执行，通过 queue.Queue + root.after 回灌 UI，界面不会卡死。
"""
from __future__ import annotations

import queue
import threading
import traceback
import webbrowser
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
import tkinter as tk

from .. import __version__
from ..config import appdata_dir, load_config, resource_path, save_config
from ..engine import ExtractEngine, list_pdfs, check_same_parent, normalize_pdf_paths
from ..excel import (ExcelBusyError, ExcelWriter, load_rows_from_log, recover_rows,
                     result_col_name)
from ..extractor import available_backends
from ..models import (DOC_NOT_CONTRACT, DOC_OK, DOC_PARTIAL, ExtractResult, FieldResult,
                      SKIP_DOC_STATUSES, ST_MANUAL, ST_MISSING, ST_HEURISTIC, ST_OK)
from ..presets import MODES, MODE_CONTRACT, MODE_PAPER
from ..renamer import RenameEngine
from ..review import assign_review_codes
from ..rules import clean_value, normalize_by_type, to_filename_value
from ..undo import UndoManager
from . import theme
from .field_editor import FieldEditor
from .mode_selector import ask_mode

STATUS_CN = {
    "planned": "待改名", "done": "已改名", "skipped": "跳过",
    "failed": "失败", "unchanged": "无需改名",
}
DOC_CN = {
    "ok": "完整", "partial": "部分缺失", "no_text_layer": "需人工处理",
    "garbled": "需人工处理", "encrypted": "需人工处理", "error": "需人工处理",
    "not_contract": "非合同文档",
}


class MainWindow:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.root = root
        self.cfg = cfg
        self.mode = cfg.get("last_mode") or MODE_PAPER
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.preview_data = None          # (results, records, snapshot, warnings)
        self.snapshot: dict | None = None
        self._after_id: str | None = None  # _drain 的定时器句柄，关闭窗口时取消
        # V1.1.2 人工补录：key = 规范化绝对路径；不持久化，清空预览时一并清除
        self.manual_overrides: dict[str, dict[str, str]] = {}

        self.dir_var = tk.StringVar(value=cfg.get("last_dir", ""))
        self.template_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=self.mode)
        self.backend_var = tk.StringVar(value=cfg.get("backend", "pymupdf"))
        self.strategy_var = tk.StringVar(value=cfg.get("excel_strategy", "append"))
        self.missing_var = tk.StringVar(value=cfg.get("missing_value", "未知"))
        self.first_var = tk.StringVar(value=str(cfg.get("first_pages", 3)))
        self.maxlen_var = tk.StringVar(value=str(cfg.get("max_filename_len", 120)))
        self.count_var = tk.StringVar(value="尚未选择文件夹")
        self.mode_title_var = tk.StringVar()
        self.tpl_warn_var = tk.StringVar()
        # V1.1.1：输入方式（文件夹 / 多选文件）、状态栏、合同类型闸门开关
        self.input_mode_var = tk.StringVar(value=cfg.get("last_input_mode") or "folder")
        self.selected_files: list[Path] = []
        self.status_var = tk.StringVar(value="就绪")
        self.gate_var = tk.BooleanVar(value=bool(cfg.get("contract_type_gate", True)))
        self.gate_threshold_var = tk.StringVar(
            value=str(cfg.get("contract_gate_threshold", 2) or 2))

        # V1.1.1 现代浅色主题（幂等）与窗口图标
        theme.apply_theme(root)
        try:
            root.iconbitmap(str(resource_path("assets/app.ico")))
        except Exception:
            pass
        root.title(f"PdfRenamer  PDF 信息提取与批量更名  v{__version__}")
        # V1.1.2 排版精简：整体高度下调，避免 1366×768 屏上状态栏被挤出可视区。
        # 修复：按屏幕实际尺寸安全居中，窗口不超过可视区，避免高 DPI / 小屏 /
        # 多显示器场景下窗口出现在屏幕外导致「进程在、看不到界面」。
        self._safe_geometry(root, 1180, 760)
        try:
            root.minsize(min(1040, root.winfo_screenwidth()),
                         min(680, root.winfo_screenheight()))
        except Exception:
            pass
        self._build_menu()
        self._build_ui()
        self._load_mode()
        self._refresh_count()
        self._after_id = root.after(80, self._drain)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        # V1.4.5：后台预热本地 OCR 模型（首次加载约 3 秒）。
        # 放在窗口显示之后跑，用户选目录/看选项的时间就把模型加载完了，
        # 第一次点「扫描」不用再等这 3 秒。
        threading.Thread(target=self._warm_ocr, daemon=True).start()

    @staticmethod
    def _warm_ocr() -> None:
        """预热 RapidOCR（失败静默，绝不打扰用户）。"""
        try:
            from ..extractor.ocr_rapid import _get_engine, rapid_available
            if rapid_available():
                _get_engine()
        except Exception:
            pass

    @staticmethod
    def _safe_geometry(root: tk.Tk, width: int, height: int) -> None:
        """把主窗口限制在屏幕可视区内并居中；失败时退化为普通 geometry。"""
        try:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w, h = min(width, max(320, sw - 40)), min(height, max(240, sh - 80))
            x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20)
            root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            try:
                root.geometry(f"{width}x{height}")
            except Exception:
                pass

    # ------------------------------------------------------------------ 菜单
    def _build_menu(self):
        mb = tk.Menu(self.root)
        m_mode = tk.Menu(mb, tearoff=0)
        for mode, cfg in MODES.items():
            m_mode.add_radiobutton(label=f"{cfg['label']}模式", value=mode,
                                  variable=self.mode_var, command=self._on_mode_radio)
        m_mode.add_separator()
        m_mode.add_command(label="切换模式…", command=self._switch_dialog)
        mb.add_cascade(label="模式", menu=m_mode)

        m_help = tk.Menu(mb, tearoff=0)
        m_help.add_command(label="处理规则说明", command=self._show_rules)
        m_help.add_command(label="打开配置目录", command=self._open_config_dir)
        m_help.add_command(label="关于", command=self._about)
        mb.add_cascade(label="帮助", menu=m_help)
        self.root.config(menu=mb)

    def _show_rules(self):
        """把界面上精简掉的完整规则说明集中在这里，不占主窗口空间。"""
        messagebox.showinfo(
            "处理规则说明",
            "Excel 策略：append=按模式分表追加 / backup=备份后重建 / overwrite=直接覆盖。\n\n"
            "跳过规则：扫描件、加密件、乱码件、非合同文档不会改名，Excel 标「需人工处理」。\n"
            "扫描件使用 Windows 系统内置离线 OCR 取得文字；缺中文语言包或识别不足时保持原名，"
            "可在预览表双击该行手动补录字段后重新生成文件名。\n\n"
            "取值优先级：结构化来源 → 正则 → 标签关键词 → 按类型启发式 → 缺失填「未知」。\n"
            "所有处理均在本地完成，零联网；软件不含大模型 / 云端 API / 推理库。",
            parent=self.root)

    def _on_mode_radio(self):
        self._switch_mode(self.mode_var.get())

    def _switch_dialog(self):
        m, remember = ask_mode(self.root, self.mode, self.cfg.get("remember_mode", True))
        if not m:
            return
        self.cfg["remember_mode"] = bool(remember)
        self._switch_mode(m)

    def _open_config_dir(self):
        webbrowser.open(str(appdata_dir()))

    def _about(self):
        messagebox.showinfo("关于 PdfRenamer",
                            f"PdfRenamer v{__version__}\n\n"
                            "纯本地工具：选文件夹 → 提取 PDF 信息 → 批量更名 → Excel 汇总。\n\n"
                            "不含大模型 / 云端 API / 推理库，零联网。扫描件仅调用 Windows 系统内置"
                            "离线 OCR 转为本地文本，再交给关键词与正则处理。\n\n"
                            "论文 / 合同双模式，字段与模板可自定义，支持一键撤销。",
                            parent=self.root)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        # 顶部：模式 + 输入方式 + 路径
        top = ttk.LabelFrame(outer, text=" 1. 选择要处理的 PDF ", padding=8)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, textvariable=self.mode_title_var, style="Title.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        mode_box = ttk.Frame(top)
        mode_box.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Radiobutton(mode_box, text="文件夹", value="folder",
                        variable=self.input_mode_var,
                        command=self._on_input_mode_change).pack(side="left")
        ttk.Radiobutton(mode_box, text="选择 PDF 文件（同目录）", value="files",
                        variable=self.input_mode_var,
                        command=self._on_input_mode_change).pack(side="left", padx=(14, 0))
        ttk.Label(top, text="路径：").grid(row=2, column=0, sticky="w")
        self.dir_entry = ttk.Entry(top, textvariable=self.dir_var)
        self.dir_entry.grid(row=2, column=1, sticky="ew", padx=6)
        self.btn_pick = ttk.Button(top, text="浏览…", command=self._choose_dir)
        self.btn_pick.grid(row=2, column=2)
        self.btn_clear = ttk.Button(top, text="清空", command=self._clear_files)
        self.btn_clear.grid(row=2, column=3, padx=(6, 0))
        ttk.Label(top, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=3, column=1, columnspan=3, sticky="w", padx=6, pady=(4, 0))

        # 中部：字段 + 模板/选项
        mid = ttk.Frame(outer)
        mid.grid(row=1, column=0, sticky="nsew")
        outer.rowconfigure(1, weight=2)
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=2)
        mid.rowconfigure(0, weight=1)

        self.editor = FieldEditor(mid, on_change=self._validate_template)
        self.editor.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = ttk.Frame(mid)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        tpl = ttk.LabelFrame(right, text=" 2. 重命名规则 ", padding=8)
        tpl.pack(fill="x", pady=(0, 8))
        tpl.columnconfigure(0, weight=1)
        ttk.Label(tpl, text="命名模板（用 {字段名} 作占位符）：").grid(row=0, column=0, sticky="w")
        ttk.Entry(tpl, textvariable=self.template_var).grid(row=1, column=0, sticky="ew", pady=(4, 2))
        self.ph_label = ttk.Label(tpl, text="", wraplength=300,
                                  style="Muted.TLabel", justify="left")
        self.ph_label.grid(row=2, column=0, sticky="w")
        ttk.Label(tpl, textvariable=self.tpl_warn_var, wraplength=300,
                  foreground=theme.WARN, font=theme.FONT_UI).grid(row=3, column=0, sticky="w")
        ttk.Button(tpl, text="恢复默认", command=self._reset_template).grid(
            row=4, column=0, sticky="w", pady=(6, 0))
        self.template_var.trace_add("write", lambda *_: self._validate_template())

        opt = ttk.LabelFrame(right, text=" 处理选项 ", padding=8)
        opt.pack(fill="both", expand=True)
        opt.columnconfigure(1, weight=1)
        rows = [
            ("PDF 解析后端", self.backend_var,
             ttk.Combobox(opt, textvariable=self.backend_var, values=available_backends(),
                          state="readonly", width=16)),
            ("Excel 已存在时", self.strategy_var,
             ttk.Combobox(opt, textvariable=self.strategy_var,
                          values=["append", "backup", "overwrite"], state="readonly", width=16)),
            ("读取前 N 页", self.first_var, ttk.Entry(opt, textvariable=self.first_var, width=8)),
            ("缺失值占位", self.missing_var, ttk.Entry(opt, textvariable=self.missing_var, width=8)),
            ("文件名长度上限", self.maxlen_var, ttk.Entry(opt, textvariable=self.maxlen_var, width=8)),
        ]
        for i, (label, _, widget) in enumerate(rows):
            ttk.Label(opt, text=label).grid(row=i, column=0, sticky="w", pady=3)
            widget.grid(row=i, column=1, sticky="w", padx=8, pady=3)
        # V1.1.1 合同文档类型闸门：可关闭，阈值可配（真实合同到位后便于复核）
        gate_box = ttk.Frame(opt)
        gate_box.grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(gate_box, text="合同类型校验（拦截非合同文档）",
                        variable=self.gate_var).pack(side="left")
        ttk.Label(gate_box, text="阈值").pack(side="left", padx=(10, 2))
        ttk.Spinbox(gate_box, from_=1, to=9, width=4,
                    textvariable=self.gate_threshold_var).pack(side="left")
        # V1.1.2：两条长说明压短合并；完整规则收进「帮助 → 处理规则说明」
        ttk.Label(opt, text="策略：追加 / 备份重建 / 覆盖。扫描件用系统离线 OCR，双击预览行可补录。",
                  foreground=theme.SUBTLE, font=theme.FONT_SMALL, wraplength=290).grid(
            row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(opt, text="缺中文 OCR 语言包时保持原名，Excel 标「需人工处理」。",
                  foreground=theme.SUBTLE, font=theme.FONT_SMALL, wraplength=290).grid(
            row=len(rows) + 2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # 预览表
        pv = ttk.LabelFrame(outer, text=" 3. 扫描预览（确认后才会真正改名） ", padding=8)
        pv.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        outer.rowconfigure(2, weight=2)
        pv.columnconfigure(0, weight=1)
        pv.rowconfigure(0, weight=1)
        cols = ("old", "new", "state", "doc", "missing", "note")
        self.pv_tree = ttk.Treeview(pv, columns=cols, show="headings", height=8)
        for c, title, w in (("old", "原文件名", 210), ("new", "新文件名", 300),
                            ("state", "改名状态", 90), ("doc", "提取状态", 90),
                            ("missing", "缺失字段", 150), ("note", "备注", 220)):
            self.pv_tree.heading(c, text=title)
            self.pv_tree.column(c, width=w, anchor="w")
        self.pv_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(pv, orient="vertical", command=self.pv_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.pv_tree.configure(yscrollcommand=vsb.set)
        theme.configure_tree_tags(self.pv_tree)
        # V1.1.2：双击预览行可手动补录字段（主窗口不新增常驻控件）
        self.pv_tree.bind("<Double-1>", self._on_edit_row)

        # 底部：按钮 / 进度 / 日志
        bottom = ttk.Frame(outer)
        bottom.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.btn_scan = ttk.Button(bottom, text="① 扫描并导出复核表", command=self._on_scan,
                                   style="Accent.TButton")
        self.btn_scan.pack(side="left")
        self.btn_exec = ttk.Button(bottom, text="② 按复核表改名",
                                   command=self._on_execute, state="disabled",
                                   style="Accent.TButton")
        self.btn_exec.pack(side="left", padx=6)
        self.btn_undo = ttk.Button(bottom, text="撤销", command=self._on_undo)
        self.btn_undo.pack(side="left", padx=4)
        self.btn_recover = ttk.Button(bottom, text="恢复", command=self._on_recover)
        self.btn_recover.pack(side="left", padx=4)
        self.pb = ttk.Progressbar(bottom, mode="determinate", maximum=100, length=180)
        self.pb.pack(side="right", padx=(6, 0))

        logf = ttk.LabelFrame(outer, text=" 运行日志 ", padding=4)
        logf.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.log = scrolledtext.ScrolledText(logf, height=5, font=theme.FONT_MONO)
        self.log.pack(fill="x")
        self._log(f"欢迎使用 PdfRenamer v{__version__}｜当前模式：{MODES[self.mode]['label']}")

        # V1.1.1 底部状态栏（模式 / 输入方式 / 运行状态 / 版本）
        status = ttk.Frame(outer)
        status.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(status, textvariable=self.status_var, anchor="w", relief="sunken",
                  padding=(6, 2)).pack(side="left", fill="x", expand=True)
        ttk.Label(status, text=f"v{__version__}", anchor="e",
                  padding=(6, 2)).pack(side="right")
        # 所有控件就绪后再按输入方式初始化按钮/Entry 状态
        self._on_input_mode_change()

    # ------------------------------------------------------------------ 基础操作
    def _log(self, text: str):
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n")
        self.log.see("end")

    # ------------------------------------------------------------------ V1.1.1 多选 PDF
    def _pick_pdf_files(self) -> tuple[str, ...]:
        """唯一调用文件选择对话框的方法，供无头测试 monkeypatch 替换。"""
        return filedialog.askopenfilenames(
            title="选择 PDF 文件（可多选，须位于同一目录）",
            filetypes=[("PDF 文件", "*.pdf")],
            initialdir=self.dir_var.get() or None, parent=self.root) or ()

    def _choose_files(self):
        paths = self._pick_pdf_files()
        if not paths:
            return
        ok, common = check_same_parent(paths)
        if not ok:
            n = len({str(Path(p).parent.resolve()) for p in paths})
            messagebox.showwarning(
                "请按目录分批处理",
                f"所选 {len(paths)} 个 PDF 来自 {n} 个不同目录。\n\n"
                "为保证「信息汇总.xlsx」固定输出到该目录、原地改名与撤销一致，"
                "请按目录分批处理（一次只选同一文件夹里的文件）。",
                parent=self.root)
            return
        picked = normalize_pdf_paths(paths)
        if not picked:
            messagebox.showinfo("没有 PDF", "所选文件里没有有效的 PDF。", parent=self.root)
            return
        self.selected_files = picked
        self.dir_var.set(str(common))     # 关键：共同父目录写回唯一 directory 锚点
        self._refresh_count()
        self._clear_preview()
        self._log(f"已选择 {len(picked)} 个 PDF 文件（目录：{common}）。")

    def _clear_files(self):
        self.selected_files = []
        self._refresh_count()
        self._clear_preview()

    def _on_input_mode_change(self):
        files_mode = (self.input_mode_var.get() == "files")
        if hasattr(self, "btn_pick"):
            self.btn_pick.config(
                text="添加 PDF 文件…" if files_mode else "浏览…",
                command=self._choose_files if files_mode else self._choose_dir)
        if hasattr(self, "dir_entry"):
            self.dir_entry.config(state="readonly" if files_mode else "normal")
        self._refresh_count()
        if hasattr(self, "pv_tree"):
            self._clear_preview()

    def _resolve_input(self) -> tuple[str, list[Path]]:
        """把界面输入统一映射为 (目录, PDF 列表)，保持下游 directory 语义不变。"""
        d = self.dir_var.get().strip()
        if self.input_mode_var.get() == "files":
            ok, common = check_same_parent(self.selected_files)
            if not ok or not self.selected_files or common is None:
                return d, []
            return str(common), list(self.selected_files)
        return d, list_pdfs(d)

    def _current_dir(self) -> str:
        """撤销/恢复优先使用上次扫描的目录锚点，避免预览后手改路径导致不一致。"""
        if self.preview_data and len(self.preview_data) > 2:
            d = (self.preview_data[2] or {}).get("output_dir", "")
            if d:
                return d
        return self.dir_var.get().strip()

    def _safe_threshold(self) -> int:
        try:
            return max(1, min(9, int(self.gate_threshold_var.get() or 2)))
        except (ValueError, TypeError):
            return 2

    def _choose_dir(self):
        d = filedialog.askdirectory(title="选择包含 PDF 文件的文件夹",
                                    initialdir=self.dir_var.get() or None, parent=self.root)
        if d:
            self.dir_var.set(d)
            self._refresh_count()
            self._clear_preview()

    def _refresh_count(self):
        d = self.dir_var.get().strip()
        mode_label = MODES[self.mode]["label"]
        if self.input_mode_var.get() == "files":
            n = len(self.selected_files)
            if n:
                self.count_var.set(f"已选 {n} 个 PDF｜Excel 输出到该目录")
            else:
                self.count_var.set("尚未选择 PDF 文件｜点「添加 PDF 文件…」可多选（须同一目录）")
            self.status_var.set(f"{mode_label}｜文件选择")
            return
        if not d or not Path(d).is_dir():
            self.count_var.set("尚未选择有效文件夹")
            self.status_var.set(f"{mode_label}｜文件夹")
            return
        n = len(list_pdfs(d))
        self.count_var.set(f"{n} 个直属 PDF（不递归）｜Excel 输出到本目录")
        self.status_var.set(f"{mode_label}｜文件夹")

    def _clear_preview(self):
        self.preview_data = None
        self.manual_overrides = {}
        self.pv_tree.delete(*self.pv_tree.get_children())
        self.btn_exec.config(state="disabled")
        self.pb["value"] = 0

    def _load_mode(self):
        mc = self.cfg["modes"][self.mode]
        self.mode_var.set(self.mode)
        self.mode_title_var.set(f"当前模式：{mc['label']}　|　{mc['description']}")
        self.editor.set_fields(mc.get("fields", []), self.mode)
        self.template_var.set(mc.get("template", ""))
        self._validate_template()

    def _reset_template(self):
        self.template_var.set(MODES[self.mode]["template"])
        self._log(f"已恢复 {MODES[self.mode]['label']} 模式默认命名模板。")

    def _validate_template(self):
        engine = RenameEngine(self.template_var.get(), "未知", 120)
        names = [f.get("name", "") for f in self.editor.get_fields()]
        unknown = engine.unknown_placeholders(names)
        if unknown:
            self.tpl_warn_var.set("⚠ 模板中存在未知字段：" + "、".join(sorted(set(unknown))))
        elif not engine.placeholders():
            self.tpl_warn_var.set("⚠ 模板中没有 {字段名} 占位符，所有文件会得到相同名称")
        else:
            self.tpl_warn_var.set("")
        # V1.1.2：字段清单已完整列在左侧编辑器里，此处仅在模板有未知占位符时才提示，
        # 避免常驻一整行重复说明。（ph_label 对象保留，布局不变）
        self.ph_label.config(text=("可用字段：" + "、".join("{" + n + "}" for n in names))
                            if (unknown or not engine.placeholders()) else "")

    def _collect_config(self) -> dict:
        """把界面当前状态收拢进 cfg 并持久化。"""
        mc = self.cfg["modes"][self.mode]
        mc["fields"] = self.editor.get_fields()
        mc["template"] = self.template_var.get().strip()
        self.cfg.update({
            "last_mode": self.mode, "last_dir": self.dir_var.get().strip(),
            "backend": self.backend_var.get(), "excel_strategy": self.strategy_var.get(),
            "missing_value": self.missing_var.get().strip() or "未知",
            "first_pages": max(1, min(20, int(self.first_var.get() or 3))),
            "max_filename_len": max(20, min(200, int(self.maxlen_var.get() or 120))),
            "last_input_mode": self.input_mode_var.get(),
            "contract_type_gate": bool(self.gate_var.get()),
            "contract_gate_threshold": self._safe_threshold(),
        })
        save_config(self.cfg)
        return self.cfg

    def _switch_mode(self, new_mode: str):
        if new_mode not in MODES or new_mode == self.mode:
            return
        self._collect_config()
        self.mode = new_mode
        self.cfg["last_mode"] = new_mode
        self._load_mode()
        self._clear_preview()
        self._log(f"已切换到「{MODES[new_mode]['label']}」模式。")

    def _on_close(self):
        try:
            self._collect_config()
        except Exception:
            pass
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self.root.destroy()

    def _snapshot(self, output_dir: str = "") -> dict:
        cfg = self._collect_config()
        mc = deepcopy(cfg["modes"][self.mode])
        return {
            "mode": self.mode, "mode_cfg": mc,
            "template": mc.get("template", ""),
            "backend": cfg["backend"], "first_pages": cfg["first_pages"],
            "last_pages": cfg.get("last_pages", 0),
            "missing_value": cfg["missing_value"],
            "max_len": cfg["max_filename_len"],
            "strategy": cfg["excel_strategy"],
            # 扫描时的目录锚点：执行/撤销/恢复统一使用，避免预览后手改路径导致错位
            "output_dir": output_dir or self.dir_var.get().strip(),
            "contract_type_gate": bool(cfg.get("contract_type_gate", True)),
            "contract_gate_threshold": int(cfg.get("contract_gate_threshold", 2) or 2),
            # V1.1.2 扫描件离线 OCR 参数（由 config v5 提供，界面不新增控件）
            "scan_ocr_enabled": bool(cfg.get("scan_ocr_enabled", True)),
            "scan_ocr_max_pages": cfg.get("scan_ocr_max_pages", 2),
            "scan_ocr_include_last_page": bool(cfg.get("scan_ocr_include_last_page", True)),
            "scan_ocr_dpi": cfg.get("scan_ocr_dpi", 200),
            "scan_ocr_max_side": cfg.get("scan_ocr_max_side", 2400),
            "scan_ocr_timeout": cfg.get("scan_ocr_timeout", 60),
            "scan_ocr_lang": cfg.get("scan_ocr_lang", "auto"),
            # V1.2.0：RapidOCR 手写识别开关
            "scan_rapid_enabled": bool(cfg.get("scan_rapid_enabled", True)),
            # V1.5.0：序号每批都从 01 开始（不再跨批全局递增）
            "sequence_counter": 1,
            # V1.3.0：手写字段截图嵌入 Excel 开关
            "capture_field_images": bool(cfg.get("capture_field_images", True)),
        }

    # ------------------------------------------------------------------ 扫描
    def _set_busy(self, busy: bool):
        self.busy = busy
        if busy:
            self.status_var.set("处理中，请稍候…")
        state = "disabled" if busy else "normal"
        self.btn_scan.config(state=state)
        self.btn_undo.config(state=state)
        self.btn_recover.config(state=state)
        self.btn_exec.config(state="disabled" if busy else ("normal" if self.preview_data else "disabled"))

    def _on_scan(self):
        if self.busy:
            return
        d, files = self._resolve_input()
        if not d or not Path(d).is_dir():
            messagebox.showwarning("未选择 PDF", "请先选择文件夹，或添加同一目录下的 PDF 文件。", parent=self.root)
            return
        if not files:
            messagebox.showinfo("没有 PDF", "没有找到可处理的 PDF 文件。", parent=self.root)
            return
        warn = self.tpl_warn_var.get()
        if warn and not messagebox.askyesno("模板提示", warn + "\n\n仍要继续扫描吗？", parent=self.root):
            return
        try:
            snap = self._snapshot(d)
        except ValueError:
            messagebox.showwarning("格式错误", "「读取前 N 页」「文件名长度上限」必须是数字。", parent=self.root)
            return
        self._clear_preview()
        self._set_busy(True)
        self._log(f"开始扫描 {len(files)} 个 PDF（{MODES[snap['mode']]['label']}模式，后端 {snap['backend']}）…")
        threading.Thread(target=self._scan_worker, args=(d, files, snap), daemon=True).start()

    def _scan_worker(self, directory: str, files: list[Path], snap: dict):
        try:
            engine = ExtractEngine(
                snap["mode"], snap["mode_cfg"], snap["backend"],
                snap["first_pages"], snap["last_pages"], snap["missing_value"],
                contract_gate=snap["contract_type_gate"],
                gate_threshold=snap["contract_gate_threshold"],
                scan_ocr_enabled=snap["scan_ocr_enabled"],
                scan_ocr_max_pages=snap["scan_ocr_max_pages"],
                scan_ocr_include_last_page=snap["scan_ocr_include_last_page"],
                scan_ocr_dpi=snap["scan_ocr_dpi"],
                scan_ocr_max_side=snap["scan_ocr_max_side"],
                scan_ocr_timeout=snap["scan_ocr_timeout"],
                scan_ocr_lang=snap["scan_ocr_lang"],
                scan_rapid_enabled=snap["scan_rapid_enabled"],
                capture_field_images=snap.get("capture_field_images", True),
            )
            results = engine.extract_many(
                files, progress=lambda i, t, n: self.q.put(("progress", i, t, f"提取 {n}")))
            # V1.4.9：合同模式下为不可信的乙方分配 xx1/xx2 核对占位符。
            if snap["mode"] == MODE_CONTRACT:
                try:
                    assign_review_codes(results)
                except Exception:
                    pass
            renamer = RenameEngine(snap["template"], snap["missing_value"], snap["max_len"],
                                   sequence_start=snap["sequence_counter"])
            names = [f["name"] for f in snap["mode_cfg"]["fields"] if f.get("enabled", True)]
            records = renamer.plan(results, directory)

            # V1.6.0：扫描阶段就把识别结果 + 六字段截图写进复核表（此时改名未发生，
            # 原路径有效），人工直接在 Excel 结果列复核修改。
            mc = snap["mode_cfg"]
            writer = ExcelWriter(directory, snap["mode"], mc["sheet"], mc["label"], names,
                                 snap["missing_value"], snap["strategy"])
            writer.prepare()
            image_fields = tuple(writer.image_fields)
            total = max(1, len(results))
            excel_busy = False
            for i, (r, rec) in enumerate(zip(results, records), 1):
                imgs = self._capture_one(r, snap, names) if r.doc_status not in SKIP_DOC_STATUSES else {}
                # 逐行 save：实测带图场景比攒到最后一次 save 更快
                # （openpyxl 逐次固化已写图片，避免末尾一次性序列化全部图片）
                row = writer.build_row(r, rec)
                if excel_busy:
                    writer.append_row(row, imgs, save=False)   # 只进增量日志
                else:
                    try:
                        writer.append_row(row, imgs)
                    except ExcelBusyError:
                        # V1.6.6：这一行已进内存表与增量日志，只是落盘失败。
                        # 不打断扫描——否则关掉 Excel 后用户还得从头再扫一遍。
                        excel_busy = True
                        self.q.put(("log", "Excel 正被打开：复核表暂未写入，"
                                           "关闭 Excel 后点「恢复」即可补写，不必重新扫描。"))
                self.q.put(("progress", i, total, f"写复核表 {r.original_name}"))
            if not excel_busy:
                try:
                    writer.finish()
                except ExcelBusyError:
                    excel_busy = True
                    self.q.put(("log", "Excel 正被打开：复核表未保存。"
                                       "关闭 Excel 后点「恢复」即可补写，不必重新扫描。"))
            else:
                writer._cleanup_images()

            snap["image_fields"] = image_fields
            snap["excel_busy"] = excel_busy
            self.q.put(("preview", results, records, renamer.unknown_placeholders(names),
                        snap, renamer.next_sequence))
            if excel_busy:
                self.q.put(("log", "扫描已完成，但复核表还没写进 Excel：请先关闭 Excel，"
                                   "点「恢复」补写后再执行改名。"))
        except ExcelBusyError as exc:
            self.q.put(("excel_busy", str(exc)))
        except Exception:
            self.q.put(("error", traceback.format_exc()))

    def _capture_images(self, results: list, snap: dict, names: list[str]) -> dict[str, dict]:
        """批量截图（供其它入口复用）：{规范化路径: {字段: 图片字节}}。"""
        out: dict[str, dict] = {}
        for r in results:
            if r.doc_status in SKIP_DOC_STATUSES:
                continue
            imgs = self._capture_one(r, snap, names)
            if imgs:
                out[str(r.path)] = imgs
        return out

    def _capture_one(self, r, snap: dict, names: list[str]) -> dict[str, bytes]:
        """对单个 PDF 截图：V1.6.0 起六字段都截（放进各自原件图列），
        乙方固定首页、用工部门按锚点；自检失败静默跳过，绝不影响扫描。"""
        if not snap.get("capture_field_images", True) or snap["mode"] != MODE_CONTRACT:
            return {}
        try:
            from ..extractor.field_crop import FIELD_ANCHORS, crop_field_images
            targets = [n for n in names if n in FIELD_ANCHORS]
            if not targets:
                return {}
            # V1.6.1：乙方固定第 1 页、签订日期固定末页（-1）签章区；
            # 开始/结束日期按日期数字定位（不限页）。
            page_map: dict[str, list[int]] = {}
            if "乙方" in targets:
                page_map["乙方"] = [0]
            if "签订日期" in targets:
                page_map["签订日期"] = [-1]
            return crop_field_images(r.path, targets, field_pages=page_map or None)
        except Exception:
            return {}

    def _fill_preview(self, results, records, warnings, snap, next_sequence=None):
        self.pv_tree.delete(*self.pv_tree.get_children())
        for i, (r, rec) in enumerate(zip(results, records)):
            new_name = rec.new_name if rec.status in ("planned", "done", "unchanged") else "（未改名）"
            # 斑马纹 tag 与状态前景 tag 使用不同属性，可叠加
            tags = ["odd" if i % 2 == 0 else "even"]
            if rec.status == "skipped":
                tags.append("skip")
            elif rec.status == "failed" or r.fields and any(
                    f.status == "heuristic" for f in r.fields.values()):
                tags.append("warn")
            self.pv_tree.insert("", "end", values=(
                r.original_name, new_name, STATUS_CN.get(rec.status, rec.status),
                DOC_CN.get(r.doc_status, r.doc_status),
                "、".join(r.missing_names()),
                (r.skip_reason or rec.reason or r.note or "")[:120],
            ), tags=tuple(tags))
        self.preview_data = (results, records, snap, warnings, next_sequence)
        if (snap or {}).get("excel_busy"):
            # 复核表没写进 Excel 时不允许执行改名：否则读回复核值会读到旧表
            self.btn_exec.config(state="disabled")
            self.status_var.set("复核表未写入 Excel：关闭 Excel 后点「恢复」再执行")
        else:
            self.btn_exec.config(state="normal")
        self._log(f"复核表已生成：{len(results)} 行，"
                  f"待改名 {sum(1 for x in records if x.status == 'planned')} 个，"
                  f"跳过 {sum(1 for x in records if x.status == 'skipped')} 个"
                  "｜请打开 Excel 核对结果列，改完点「② 按复核表改名」。")
        if warnings:
            self._log("警告：模板存在未知字段 " + "、".join(sorted(set(warnings))))

    # ------------------------------------------------------------------ V1.1.2 人工补录
    @staticmethod
    def _result_key(path: str) -> str:
        return str(Path(path).resolve()).lower()

    def _on_edit_row(self, event=None):
        """双击预览行 → 弹出按需创建的补录对话框（主窗口不新增常驻控件）。"""
        if self.busy or not self.preview_data:
            return
        # 双击时 focus 可能还没跟上鼠标位置，优先用 y 坐标定位行
        iid = (self.pv_tree.identify_row(event.y) if event is not None else "") \
            or self.pv_tree.focus()
        if not iid:
            return
        try:
            idx = self.pv_tree.index(iid)
            result = self.preview_data[0][idx]
        except (IndexError, tk.TclError, TypeError, ValueError):
            return
        self._open_override_dialog(result)

    def _open_override_dialog(self, result):
        """无头测试可直接覆盖本方法注入值；这里只负责构建 UI。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("补录字段")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        theme.apply_theme(dlg)
        key = self._result_key(result.path)
        saved = self.manual_overrides.get(key, {})
        fields = [f for f in self.cfg["modes"][self.mode]["fields"] if f.get("enabled", True)]
        if not fields:
            dlg.destroy()
            return

        box = ttk.Frame(dlg, padding=12)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=result.original_name, style="Title.TLabel",
                  wraplength=380).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(box, text="留空表示不修改；填写的值会用于改名并写入 Excel。",
                  style="Muted.TLabel", wraplength=380).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        entries: dict[str, tk.StringVar] = {}
        for i, f in enumerate(fields, 2):
            name = str(f.get("name", ""))
            ftype = str(f.get("type", "text"))
            choices = [str(c) for c in (f.get("choices") or [])]
            current = saved.get(name)
            if current is None:
                fr = result.fields.get(name)
                current = "" if (fr is None or fr.is_missing) else fr.value
            ttk.Label(box, text=name + "：").grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(current))
            if ftype == "enum" and choices:
                # V1.2.0：枚举字段（用工部门/合同类型）用下拉点选，不手敲
                cb = ttk.Combobox(box, textvariable=var, values=choices, state="readonly",
                                  width=35)
                cb.grid(row=i, column=1, sticky="ew", pady=3, padx=(6, 0))
            else:
                ttk.Entry(box, textvariable=var, width=38).grid(
                    row=i, column=1, sticky="ew", pady=3, padx=(6, 0))
            entries[name] = var
            # V1.2.0：日期字段加格式提示
            if ftype == "date":
                ttk.Label(box, text="格式 YYYY-MM-DD",
                          style="Muted.TLabel", font=theme.FONT_SMALL).grid(
                    row=i, column=2, sticky="w", padx=(6, 0))
        box.columnconfigure(1, weight=1)

        def apply():
            values = {n: clean_value(v.get()) for n, v in entries.items()}
            if any(values.values()):
                self.manual_overrides[key] = {n: v for n, v in values.items() if v}
            else:
                self.manual_overrides.pop(key, None)
            dlg.destroy()
            self._apply_overrides()
            self._log(f"已补录字段：{result.original_name}")

        btns = ttk.Frame(box)
        btns.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="确定", command=apply, style="Accent.TButton").pack(side="right")
        dlg.grab_set()
        dlg.wait_window()

    def _apply_overrides(self) -> None:
        """把人工补录值写回结果并重新生成改名计划（原地、不移动文件）。"""
        if not self.preview_data:
            return
        results, _records, snap, warnings, _next = self.preview_data
        if not self.manual_overrides:
            return
        patched: list = []
        for r in results:
            overrides = self.manual_overrides.get(self._result_key(r.path))
            if not overrides:
                patched.append(r)
                continue
            rr = deepcopy(r)
            for name, raw in overrides.items():
                f = next((x for x in self.cfg["modes"][self.mode]["fields"]
                          if str(x.get("name")) == name), None)
                ftype = str((f or {}).get("type", "text"))
                max_len = int((f or {}).get("max_len", 0) or 0)
                choices = [str(c) for c in ((f or {}).get("choices") or [])]
                display = normalize_by_type(raw, ftype, choices) or clean_value(raw)
                rr.fields[name] = FieldResult(
                    name, display,
                    to_filename_value(display, ftype, max_len) or snap["missing_value"],
                    ST_MANUAL, "人工补录")
            # 脱离 SKIP_DOC_STATUSES，否则 renamer.plan 仍会跳过
            if rr.doc_status in SKIP_DOC_STATUSES:
                rr.doc_status = DOC_PARTIAL if rr.missing_names() else DOC_OK
            patched.append(rr)
        renamer = RenameEngine(snap["template"], snap["missing_value"], snap["max_len"],
                               sequence_start=snap.get("sequence_counter", 1))
        records = renamer.plan(patched, snap.get("output_dir") or self.dir_var.get().strip())
        for rec in records:
            if rec.status == "planned" and self._result_key(rec.src) in self.manual_overrides:
                rec.reason = (rec.reason + "；" if rec.reason else "") + "人工补录"
        self.preview_data = (patched, records, snap, warnings, renamer.next_sequence)
        self._fill_preview(patched, records, warnings, snap, renamer.next_sequence)

    # ------------------------------------------------------------------ 执行
    def _on_execute(self):
        if self.busy or not self.preview_data:
            return
        if (self.preview_data[2] or {}).get("excel_busy"):
            messagebox.showwarning(
                "复核表还没写进 Excel",
                "本轮复核表写入失败（Excel 正被打开）。\n\n"
                "请先关闭「信息汇总.xlsx」，点下方「恢复」补写，再执行改名。\n"
                "不需要重新扫描。", parent=self.root)
            return
        results, records, snap, _, next_seq = self.preview_data
        d = snap.get("output_dir") or self.dir_var.get().strip()
        xlsx = Path(d) / "信息汇总.xlsx"
        if not xlsx.exists():
            messagebox.showwarning(
                "找不到复核表",
                f"未找到复核表：\n{xlsx}\n\n请先点「① 扫描并导出复核表」。",
                parent=self.root)
            return
        if not messagebox.askyesno(
                "按复核表改名",
                f"将读取你复核后的表格：\n{xlsx}\n\n"
                "按表中「乙方 / 身份证号 / 日期 / 用工部门」等结果列的值改名，\n"
                "并只更新表里的「新文件名」列（不会覆盖你改过的字段值）。\n\n"
                "确认已保存并关闭 Excel，继续改名？",
                parent=self.root):
            return
        self._set_busy(True)
        self._log("开始按复核表改名：读取 Excel → 重新生成改名计划 → 重命名 → 更新新文件名列…")
        # 预览表双击补录的值优先级高于 Excel（两者通常不会同时改同一字段）
        snap["manual_overrides"] = deepcopy(self.manual_overrides)
        rid = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        threading.Thread(target=self._execute_worker, args=(d, results, snap, rid),
                         daemon=True).start()

    def _execute_worker(self, directory, results, snap, rid):
        """V1.6.0：按人工复核后的 Excel 值改名（不再截图、不再重写整表）。"""
        try:
            from ..excel import read_reviewed_values, update_excel_after_rename

            # 1) 读回人工复核值，覆盖识别结果（只覆盖表中非空的字段）
            mc = snap["mode_cfg"]
            names = [f["name"] for f in mc["fields"] if f.get("enabled", True)]
            xlsx = Path(directory) / "信息汇总.xlsx"
            reviewed = read_reviewed_values(xlsx, mc["sheet"], names)
            applied = 0
            field_types = {f["name"]: str(f.get("type", "text")) for f in mc["fields"]}
            field_maxlen = {f["name"]: int(f.get("max_len", 0) or 0) for f in mc["fields"]}
            for r in results:
                vals = reviewed.get(r.original_name)
                if not vals:
                    continue
                for fname, raw in vals.items():
                    if not raw or fname not in field_types:
                        continue
                    # 复核表里 xxN 占位符是"未核对"，保留原占位不覆盖
                    if raw.startswith("xx") and raw[2:].isdigit():
                        continue
                    ftype = field_types[fname]
                    display = normalize_by_type(raw, ftype) or clean_value(raw)
                    if not display:
                        continue
                    r.fields[fname] = FieldResult(
                        fname, display,
                        to_filename_value(display, ftype, field_maxlen.get(fname, 0))
                        or snap["missing_value"],
                        ST_MANUAL, "人工复核")
                    applied += 1

            # 预览表双击补录的值优先级最高（覆盖 Excel 同名字段）
            overrides = snap.get("manual_overrides") or {}
            for r in results:
                key = str(Path(r.path).resolve()).lower()
                ov = overrides.get(key)
                if not ov:
                    continue
                for fname, raw in ov.items():
                    if not raw or fname not in field_types:
                        continue
                    ftype = field_types[fname]
                    display = normalize_by_type(raw, ftype) or clean_value(raw)
                    if not display:
                        continue
                    r.fields[fname] = FieldResult(
                        fname, display,
                        to_filename_value(display, ftype, field_maxlen.get(fname, 0))
                        or snap["missing_value"],
                        ST_MANUAL, "人工补录")
                    applied += 1
            self.q.put(("log", f"已从复核表/补录应用 {applied} 处人工修改"))

            # 2) 用复核后的结果重新生成改名计划
            renamer = RenameEngine(snap["template"], snap["missing_value"], snap["max_len"],
                                   sequence_start=snap.get("sequence_counter", 1))
            records = renamer.plan(results, directory)

            # 3) 改名前写还原日志 → 执行改名 → 更新日志状态
            undo = UndoManager()
            undo.save_plan(directory, snap["mode"], records, rid)
            renamer.execute(
                records, progress=lambda i, t, n: self.q.put(("progress", i, t, f"改名 {n}")))
            undo.save_plan(directory, snap["mode"], records, rid)

            # 4) 只更新 Excel 的「新文件名」列，保留人工复核值与截图
            final_names = {
                rec.original: rec.new_name for rec in records
                if rec.status in ("planned", "done", "unchanged")
            }
            try:
                update_excel_after_rename(xlsx, mc["sheet"], final_names)
            except Exception:
                pass   # 改名已完成，Excel 列更新失败不影响改名结果

            done = sum(1 for x in records if x.status == "done")
            failed = sum(1 for x in records if x.status == "failed")
            skipped = sum(1 for x in records if x.status == "skipped")
            self.q.put(("done",
                        f"完成：改名 {done} 个，跳过 {skipped} 个，失败 {failed} 个；"
                        f"复核表已更新新文件名：{xlsx}"))
        except Exception:
            self.q.put(("error", traceback.format_exc()))

    # ------------------------------------------------------------------ 撤销 / 恢复
    def _on_undo(self):
        if self.busy:
            return
        d = self._current_dir()
        if not d or not Path(d).is_dir():
            messagebox.showwarning("未选择文件夹", "请先选择之前处理过的文件夹。", parent=self.root)
            return
        out = UndoManager().undo(d)
        self._log("撤销结果：" + out["message"])
        for x in out["details"][:10]:
            self._log("  " + x)
        messagebox.showinfo("撤销完成", out["message"], parent=self.root)
        self._refresh_count()
        self._clear_preview()

    def _on_recover(self):
        if self.busy:
            return
        d = self._current_dir()
        if not d or not Path(d).is_dir():
            return
        snap = self._snapshot(d)
        mc = snap["mode_cfg"]
        names = [f["name"] for f in mc["fields"] if f.get("enabled", True)]

        # V1.6.6：先读增量日志。若扫描没走完（预览为空），用日志把结果重建回界面，
        # 让用户恢复后可以直接执行改名，而不是被迫重扫。
        try:
            rows = load_rows_from_log(d, snap["mode"])
        except Exception:
            rows = []
        rebuilt = False
        if not self.preview_data and rows:
            rebuilt = self._restore_preview_from_rows(d, snap, rows, names)

        # 恢复也要处理「Excel 还没关」——明确提示，而不是静默失败。
        try:
            n = recover_rows(d, snap["mode"], mc["sheet"], mc["label"], names,
                             snap["missing_value"])
        except ExcelBusyError as exc:
            self._log("恢复失败：Excel 仍被占用。")
            messagebox.showwarning("Excel 仍被占用", str(exc), parent=self.root)
            return
        except Exception:
            detail = traceback.format_exc()
            self._log("恢复出错：\n" + detail)
            messagebox.showerror("恢复失败", detail[-1500:], parent=self.root)
            return

        # 补写成功后解除「不许执行」的锁
        if self.preview_data and len(self.preview_data) > 2:
            self.preview_data[2]["excel_busy"] = False
            self.btn_exec.config(state="normal")
            self.status_var.set("复核表已补写，可以执行改名")

        if n:
            self._log(f"已从增量日志补写 {n} 行到 Excel（含手写截图）。")
            extra = "\n预览也已恢复，可直接点「按复核表改名」。" if rebuilt else ""
            messagebox.showinfo("恢复完成",
                                f"已把上次未写入的 {n} 条结果补进「信息汇总.xlsx」，"
                                f"无需重新扫描。{extra}", parent=self.root)
        elif rebuilt:
            self._log("已从增量日志恢复预览，可继续执行改名。")
            messagebox.showinfo("已恢复",
                                "结果已在表格里，预览也已重建，可直接点「按复核表改名」。",
                                parent=self.root)
        else:
            self._log("没有可恢复的记录（上次已成功写入，或日志已过期）。")
            messagebox.showinfo("没有可恢复的记录",
                                "没有找到待补写的记录。\n"
                                "如果表格里确实缺数据，请重新扫描一次。", parent=self.root)

    def _restore_preview_from_rows(self, directory: str, snap: dict, rows: list[dict],
                                   names: list[str]) -> bool:
        """用增量日志重建预览（扫描中途失败、window 里没有结果时用）。

        只能还原表格里已有的值，无法还原被判定为「非合同」等细节状态——
        因此对原本「未改名」的行按跳过处理，避免恢复后被误改名。
        """
        cfg_by_name = {f["name"]: f for f in snap["mode_cfg"]["fields"]
                       if f.get("enabled", True)}
        base = Path(directory)
        results: list[ExtractResult] = []
        for row in rows:
            path = base / str(row.get("原文件名") or "")
            if not path.exists():
                alt = str(row.get("新文件名") or "").strip()
                if alt and alt != "（未改名）":
                    path = base / alt
            if not path.exists():
                continue
            skipped = str(row.get("新文件名") or "").strip() in ("（未改名）", "")
            fields: dict[str, FieldResult] = {}
            for fname in names:
                cfg = cfg_by_name.get(fname, {})
                raw = row.get(result_col_name(fname), row.get(fname, ""))
                val = str(raw or "").strip()
                missing = (not val) or val == snap["missing_value"]
                file_val = "" if missing else to_filename_value(
                    val, str(cfg.get("type", "text")), int(cfg.get("max_len", 0) or 0))
                fields[fname] = FieldResult(
                    fname,
                    snap["missing_value"] if missing else val,
                    file_val or snap["missing_value"],
                    ST_MISSING if missing else ST_OK,
                    "从增量日志恢复")
            results.append(ExtractResult(
                path=str(path), original_name=path.name, mode=snap["mode"],
                fields=fields,
                doc_status=DOC_NOT_CONTRACT if skipped else DOC_OK,
                note="从增量日志恢复（未重新扫描）"))
        if not results:
            return False
        renamer = RenameEngine(snap["template"], snap["missing_value"], snap["max_len"],
                               sequence_start=snap["sequence_counter"])
        records = renamer.plan(results, directory)
        self._fill_preview(results, records, [], snap, renamer.next_sequence)
        return True

    # ------------------------------------------------------------------ 队列回灌
    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1])
                elif kind == "progress":
                    _, i, total, text = msg
                    self.pb["value"] = (i / max(1, total)) * 100
                    if i == total or i % 5 == 0:
                        self._log(f"  {i}/{total} {text}")
                elif kind == "preview":
                    self._fill_preview(msg[1], msg[2], msg[3], msg[4], msg[5] if len(msg) > 5 else None)
                    self._set_busy(False)
                    self.status_var.set("复核表已生成，请打开 Excel 复核，改完保存关闭后点「② 按复核表改名」")
                    messagebox.showinfo(
                        "请人工复核",
                        "扫描完成！已生成《信息汇总.xlsx》复核表。\n\n"
                        "请打开该表格，逐行核对并直接修改结果列\n"
                        "（乙方 / 身份证号 / 开始日期 / 结束日期 / 签订日期 / 用工部门），\n"
                        "右侧图片列是该字段的原件截图供对照。\n\n"
                        "改完保存并关闭 Excel 后，回到软件点\n"
                        "「② 按复核表改名」即可按你改过的内容改名。",
                        parent=self.root)
                elif kind == "done":
                    self.pb["value"] = 100
                    self._log(msg[1])
                    self._set_busy(False)
                    self._refresh_count()
                    self.status_var.set("处理完成")
                    messagebox.showinfo("处理完成", msg[1], parent=self.root)
                elif kind == "excel_busy":
                    self._log("Excel 写入失败：" + msg[1])
                    self._set_busy(False)
                    messagebox.showwarning("Excel 被占用", msg[1], parent=self.root)
                elif kind == "error":
                    self._log("发生错误：\n" + msg[1])
                    self._set_busy(False)
                    messagebox.showerror("运行错误", msg[1][-1500:], parent=self.root)
        except queue.Empty:
            pass
        try:
            self._after_id = self.root.after(80, self._drain)
        except tk.TclError:      # 窗口已销毁
            self._after_id = None
