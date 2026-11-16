# -*- coding: utf-8 -*-
"""程序入口：DPI 感知 → 模式选择 → 主窗口。"""
from __future__ import annotations

import os
import sys
import threading
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from . import __version__
from .config import load_config, save_config
from .presets import MODES
from .ui.main_window import MainWindow
from .ui.mode_selector import ask_mode


def _trace(msg: str) -> None:
    """把启动关键阶段写入 %TEMP%/pdfrenamer_startup.log。

    windowed exe（console=False）没有控制台，一旦启动期阻塞或异常，用户只看到
    「进程在、无界面」。留下日志便于定位问题发生在哪一步（ append，不覆盖）。
    """
    try:
        p = Path(os.environ.get("TEMP", ".")) / "pdfrenamer_startup.log"
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  v{__version__}  {msg}\n")
    except Exception:
        pass


def _enable_dpi() -> None:
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            from ctypes import windll
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _selftest() -> int:
    """打包后自检：不弹界面，直接跑一遍「生成 PDF → 提取 → 改名 → Excel → 撤销」。

    结果同时打印并写入 %TEMP%/pdfrenamer_selftest.txt（windowed exe 无控制台时也可读）。
    """
    import shutil
    import tempfile
    from pathlib import Path

    report = Path(tempfile.gettempdir()) / "pdfrenamer_selftest.txt"
    lines: list[str] = []

    def log(s: str) -> None:
        lines.append(s)
        print(s)

    try:
        import pymupdf  # noqa: F401
        import openpyxl  # noqa: F401
        import tkinter  # noqa: F401
        from .config import load_config, resource_path
        from .engine import ExtractEngine, list_pdfs
        from .excel import FILE_NAME, ExcelWriter
        from .presets import MODES
        from .renamer import RenameEngine
        from .undo import UndoManager

        log(f"PdfRenamer {__version__} selftest")
        log(f"frozen={getattr(sys, 'frozen', False)}  _MEIPASS={getattr(sys, '_MEIPASS', '-')}")
        log(f"default_config exists={resource_path('config/default_config.json').exists()}")
        cfg = load_config()
        log(f"config loaded: modes={list(cfg['modes'].keys())} backend={cfg['backend']}")

        tmp = Path(tempfile.mkdtemp(prefix="pdfrenamer_selftest_"))
        try:
            doc = pymupdf.open()
            page = doc.new_page()
            for i, line in enumerate([
                "设备采购合同",
                "合同名称：自检用服务器采购合同",
                "甲方（盖章）：华东某某科技有限公司",
                "供方（盖章）：北京某某信息技术有限公司",
                "签订日期：2024年3月5日",
                "合同金额：¥1,200,000.00元",
            ]):
                page.insert_text((60, 72 + i * 26), line, fontname="china-s", fontsize=12)
            doc.save(tmp / "raw.pdf")
            doc.close()

            mc = MODES["contract"]
            engine = ExtractEngine("contract", mc, cfg["backend"])
            results = engine.extract_many(list_pdfs(tmp))
            r = results[0]
            log(f"extract: doc_status={r.doc_status} 甲方={r.fields['甲方'].value} 金额={r.fields['金额'].value}")
            assert r.fields["甲方"].value == "华东某某科技有限公司", "甲方提取失败"
            assert r.fields["金额"].value == "1200000.00元", "金额归一化失败"

            renamer = RenameEngine(mc["template"], cfg["missing_value"], cfg["max_filename_len"])
            records = renamer.plan(results, tmp)
            undo = UndoManager()
            rid = "selftest"
            undo.save_plan(tmp, "contract", records, rid)
            renamer.execute(records)
            undo.save_plan(tmp, "contract", records, rid)
            log(f"rename: {records[0].status} -> {records[0].new_name}")
            assert (tmp / records[0].new_name).exists(), "改名失败"

            names = [f["name"] for f in mc["fields"]]
            w = ExcelWriter(tmp, "contract", mc["sheet"], mc["label"], names)
            w.prepare()
            w.append_row(w.build_row(r, records[0]))
            w.finish()
            assert (tmp / FILE_NAME).exists(), "Excel 未生成"
            log(f"excel: {(tmp / FILE_NAME).name} 已生成于所选目录")

            out = undo.undo(tmp)
            assert (tmp / "raw.pdf").exists(), "撤销未还原原文件名"
            log(f"undo: {out['message']}")
            log("RESULT: PASS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        log("RESULT: FAIL")
        log(traceback.format_exc())
        report.write_text("\n".join(lines), encoding="utf-8")
        return 1
    report.write_text("\n".join(lines), encoding="utf-8")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    _trace("启动：开始")
    _enable_dpi()
    _trace("DPI 感知已设置")
    # 兜底：确认使用的是带 tkinter 的标准 CPython
    if "tkinter" not in sys.modules:
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print("错误：当前 Python 缺少 tkinter。请使用标准 CPython（py -3.13），"
                  "不要使用缺少 tkinter 的精简/嵌入式解释器。", file=sys.stderr)
            _trace("致命：tkinter 不可用")
            return 2

    root = tk.Tk()
    root.withdraw()
    _trace("Tk 根窗口已创建（初始隐藏）")

    def report(exc_type, exc_value, exc_tb):
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _trace("主线程异常:\n" + detail[-1500:])
        try:
            messagebox.showerror("未处理的异常", detail[-1800:], parent=root)
        except Exception:
            pass

    root.report_callback_exception = report
    threading.excepthook = lambda args: print("worker error:", args.exc_value, file=sys.stderr)

    cfg = load_config()
    _trace("配置已载入")
    mode = cfg.get("last_mode", "") if cfg.get("remember_mode", True) else ""
    if mode not in MODES:
        _trace("首次启动/未记住模式：显示模式选择对话框")
        chosen, remember = ask_mode(root, mode, bool(cfg.get("remember_mode", True)))
        _trace(f"模式选择返回：{chosen!r}")
        if not chosen:
            root.destroy()
            return 0
        cfg["last_mode"] = chosen
        cfg["remember_mode"] = bool(remember)
        save_config(cfg)
        mode = chosen
    cfg["last_mode"] = mode

    root.deiconify()
    _trace("主窗口即将构建")
    try:
        MainWindow(root, cfg)
        _trace("主窗口已构建，进入 mainloop")
        root.mainloop()
        _trace("mainloop 退出")
    except Exception:
        detail = traceback.format_exc()
        _trace("构建主窗口失败:\n" + detail[-1500:])
        try:
            messagebox.showerror("启动失败", detail[-1800:])
        except Exception:
            pass
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
