# -*- coding: utf-8 -*-
"""字段编辑器：从界面添加 / 修改 / 删除「需要自动提取的信息」。"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, ttk
from copy import deepcopy

from ..models import FIELD_TYPES
from ..presets import MODES
from ..structured import SOURCE_LABELS
from . import theme

TYPE_LABELS = [
    ("文本", "text"), ("作者/多人列表", "list"), ("年份", "year"),
    ("公司/机构", "company"), ("日期", "date"), ("金额", "money"),
]
LABEL_TO_TYPE = {label: value for label, value in TYPE_LABELS}
TYPE_TO_LABEL = {value: label for label, value in TYPE_LABELS}
LABEL_TO_SOURCE = {label: value for label, value in SOURCE_LABELS}
SOURCE_TO_LABEL = {value: label for label, value in SOURCE_LABELS}


def parse_keywords(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,，;；\n]+", text or "") if p.strip()]


class FieldEditor(ttk.LabelFrame):
    """左侧字段面板：Treeview + 编辑表单 + 增删改排序。"""

    def __init__(self, master, on_change=None):
        super().__init__(master, text=" 需要提取的信息（可自由添加） ", padding=8,
                         style="Card.TLabelframe")
        self.on_change = on_change
        self.fields: list[dict] = []
        self._selected: int | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_tree()
        self._build_form()
        self._build_buttons()

    # ---------------- Treeview ----------------
    def _build_tree(self):
        box = ttk.Frame(self)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        cols = ("name", "keywords", "regex", "type", "source", "enabled")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=9, selectmode="browse")
        for col, title, width in (
            ("name", "字段名", 100), ("keywords", "标签关键词", 165),
            ("regex", "正则表达式", 150), ("type", "类型", 90),
            ("source", "结构化来源", 100), ("enabled", "启用", 50),
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w" if col != "enabled" else "center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        theme.configure_tree_tags(self.tree)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    # ---------------- 表单 ----------------
    def _build_form(self):
        f = ttk.Frame(self, padding=(0, 8, 0, 4))
        f.grid(row=1, column=0, sticky="ew")
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)

        self.v_name = tk.StringVar()
        self.v_keywords = tk.StringVar()
        self.v_regex = tk.StringVar()
        self.v_source = tk.StringVar(value=SOURCE_LABELS[0][0])
        self.v_type = tk.StringVar(value="文本")
        self.v_max = tk.StringVar(value="0")
        self.v_enabled = tk.BooleanVar(value=True)
        self.v_required = tk.BooleanVar(value=False)

        ttk.Label(f, text="字段名").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Entry(f, textvariable=self.v_name).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(f, text="类型").grid(row=0, column=2, sticky="w", padx=(12, 6))
        ttk.Combobox(f, textvariable=self.v_type, values=[x[0] for x in TYPE_LABELS],
                     state="readonly", width=16).grid(row=0, column=3, sticky="ew", pady=2)

        ttk.Label(f, text="标签关键词").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Entry(f, textvariable=self.v_keywords).grid(row=1, column=1, columnspan=3, sticky="ew", pady=2)
        ttk.Label(f, text="逗号分隔，如：甲方, 需方",
                  foreground=theme.SUBTLE, font=theme.FONT_SMALL).grid(
            row=2, column=1, columnspan=3, sticky="w")

        ttk.Label(f, text="正则表达式").grid(row=3, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Entry(f, textvariable=self.v_regex).grid(row=3, column=1, columnspan=3, sticky="ew", pady=2)
        ttk.Label(f, text="可选，优先取第 1 个捕获组",
                  foreground=theme.SUBTLE, font=theme.FONT_SMALL).grid(
            row=4, column=1, columnspan=3, sticky="w")

        ttk.Label(f, text="结构化来源").grid(row=5, column=0, sticky="w", padx=(0, 6), pady=(6, 2))
        ttk.Combobox(f, textvariable=self.v_source,
                     values=[x[0] for x in SOURCE_LABELS], state="readonly",
                     width=24).grid(row=5, column=1, sticky="w", pady=(6, 2))
        self.hint_src = ttk.Label(f, text="论文元数据/版式解析，优先于关键词与正则",
                                  foreground=theme.SUBTLE, font=theme.FONT_SMALL)
        self.hint_src.grid(row=6, column=1, columnspan=3, sticky="w")

        opts = ttk.Frame(f)
        opts.grid(row=7, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="启用", variable=self.v_enabled).pack(side="left")
        ttk.Checkbutton(opts, text="必填", variable=self.v_required).pack(side="left", padx=(14, 0))
        ttk.Label(opts, text="文件名最大长度").pack(side="left", padx=(14, 4))
        ttk.Entry(opts, textvariable=self.v_max, width=6).pack(side="left")

    def _build_buttons(self):
        b = ttk.Frame(self)
        b.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        for text, cmd in (
            ("新增字段", self.add_field), ("应用修改", self.apply_field),
            ("删除", self.delete_field), ("上移", lambda: self.move(-1)),
            ("下移", lambda: self.move(1)), ("恢复出厂预设", self.reset_preset),
        ):
            ttk.Button(b, text=text, command=cmd).pack(side="left", padx=(0, 6))

    # ---------------- 数据 ----------------
    def set_fields(self, fields: list[dict], mode: str = "") -> None:
        self.fields = deepcopy(fields)
        self._mode = mode
        self._refresh()
        self._clear_form()
        # V1.1.2：结构化来源是论文模式专用，合同模式隐藏以免常驻无关说明
        if hasattr(self, "hint_src"):
            if mode == "contract":
                self.hint_src.grid_remove()
            else:
                self.hint_src.grid()

    def get_fields(self) -> list[dict]:
        return deepcopy(self.fields)

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, d in enumerate(self.fields):
            self.tree.insert("", "end", iid=str(i), values=(
                d.get("name", ""),
                ", ".join(d.get("keywords", [])),
                d.get("regex", ""),
                TYPE_TO_LABEL.get(d.get("type", "text"), "文本"),
                SOURCE_TO_LABEL.get(d.get("source", ""), "不使用"),
                "是" if d.get("enabled", True) else "否",
            ), tags=("odd" if i % 2 == 0 else "even",))

    def _clear_form(self):
        self._selected = None
        for v in (self.v_name, self.v_keywords, self.v_regex):
            v.set("")
        self.v_type.set("文本")
        self.v_source.set(SOURCE_LABELS[0][0])
        self.v_max.set("0")
        self.v_enabled.set(True)
        self.v_required.set(False)
        self.tree.selection_remove(*self.tree.selection())

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        self._selected = i
        d = self.fields[i]
        self.v_name.set(d.get("name", ""))
        self.v_keywords.set(", ".join(d.get("keywords", [])))
        self.v_regex.set(d.get("regex", ""))
        self.v_source.set(SOURCE_TO_LABEL.get(d.get("source", ""), SOURCE_LABELS[0][0]))
        self.v_type.set(TYPE_TO_LABEL.get(d.get("type", "text"), "文本"))
        self.v_max.set(str(d.get("max_len", 0) or 0))
        self.v_enabled.set(bool(d.get("enabled", True)))
        self.v_required.set(bool(d.get("required", False)))

    def _form_to_dict(self) -> dict | None:
        name = self.v_name.get().strip()
        if not name:
            messagebox.showwarning("字段名为空", "请填写字段名，例如「甲方」「期刊」。", parent=self)
            return None
        try:
            mx = int(self.v_max.get().strip() or "0")
        except ValueError:
            messagebox.showwarning("格式错误", "文件名最大长度必须是数字。", parent=self)
            return None
        rx = self.v_regex.get().strip()
        if rx:
            try:
                re.compile(rx)
            except re.error as exc:
                messagebox.showwarning("正则无效", f"正则表达式无法编译：\n{exc}", parent=self)
                return None
        return {
            "name": name,
            "keywords": parse_keywords(self.v_keywords.get()),
            "regex": rx,
            "enabled": bool(self.v_enabled.get()),
            "required": bool(self.v_required.get()),
            "type": LABEL_TO_TYPE.get(self.v_type.get(), "text"),
            "max_len": max(0, mx),
            "source": LABEL_TO_SOURCE.get(self.v_source.get(), ""),
        }

    def _changed(self):
        if self.on_change:
            self.on_change()

    def add_field(self):
        d = self._form_to_dict()
        if d is None:
            return
        if any(x.get("name") == d["name"] for x in self.fields):
            messagebox.showwarning("重名", f"字段「{d['name']}」已存在，请用「应用修改」。", parent=self)
            return
        self.fields.append(d)
        self._refresh()
        self._clear_form()
        self._changed()

    def apply_field(self):
        if self._selected is None:
            messagebox.showinfo("未选中", "请先在上方列表选中一个字段。", parent=self)
            return
        d = self._form_to_dict()
        if d is None:
            return
        old = self.fields[self._selected].get("name")
        if old != d["name"] and any(x.get("name") == d["name"] for x in self.fields):
            messagebox.showwarning("重名", f"字段「{d['name']}」已存在。", parent=self)
            return
        self.fields[self._selected] = d
        self._refresh()
        self._clear_form()
        self._changed()

    def delete_field(self):
        if self._selected is None:
            messagebox.showinfo("未选中", "请先选中要删除的字段。", parent=self)
            return
        name = self.fields[self._selected].get("name")
        if not messagebox.askyesno("确认删除", f"删除字段「{name}」？", parent=self):
            return
        del self.fields[self._selected]
        self._refresh()
        self._clear_form()
        self._changed()

    def move(self, delta: int):
        if self._selected is None:
            return
        j = self._selected + delta
        if j < 0 or j >= len(self.fields):
            return
        self.fields[self._selected], self.fields[j] = self.fields[j], self.fields[self._selected]
        self._refresh()
        self.tree.selection_set(str(j))
        self._selected = j
        self._changed()

    def reset_preset(self):
        if not messagebox.askyesno("恢复预设", "将丢弃当前模式下所有自定义字段，恢复出厂预设。继续？", parent=self):
            return
        self.fields = deepcopy(MODES.get(getattr(self, "_mode", "paper"), MODES["paper"])["fields"])
        self._refresh()
        self._clear_form()
        self._changed()
        return True
