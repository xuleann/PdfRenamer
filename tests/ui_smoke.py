# -*- coding: utf-8 -*-
"""UI 无头冒烟测试：实例化主窗口 → 扫描预览 → 确认执行 → 校验 Excel 与改名。

不依赖任何 GUI 自动化框架；通过 root.update() 驱动事件循环，并屏蔽确认弹窗。
用法（项目根目录执行）：.venv/Scripts/python.exe tests/ui_smoke.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SAMPLES = ROOT / "tests" / "samples"

import pdfrenamer.ui.main_window as mw  # noqa: E402
from pdfrenamer.config import load_config  # noqa: E402
from pdfrenamer.excel import FILE_NAME  # noqa: E402
from pdfrenamer.presets import MODE_CONTRACT  # noqa: E402

# 屏蔽所有阻塞式弹窗，以及本机配置写入。
# V1.1.2：_switch_mode / _on_close 会调 save_config，若不屏蔽会把测试态
# （临时的 last_dir / last_input_mode）写进用户 %APPDATA%/config.json，
# 下次 load_config() 读到 files 模式但没有 selected_files → 扫描拿不到文件。
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


def main() -> int:
    if not list(SAMPLES.glob("*.pdf")):
        from make_samples import main as gen
        gen()

    tmp = Path(tempfile.mkdtemp(prefix="pdfrenamer_ui_"))
    for name in ("02_标准合同.pdf", "07_重名A.pdf", "08_重名B.pdf", "03_扫描件.pdf"):
        shutil.copy2(SAMPLES / name, tmp / name)

    cfg = load_config()
    cfg["remember_mode"] = True
    cfg["last_mode"] = MODE_CONTRACT
    cfg["last_dir"] = str(tmp)
    cfg["excel_strategy"] = "append"
    # 冒烟测试固定走文件夹模式，不依赖上次会话残留的输入方式
    cfg["last_input_mode"] = "folder"

    root = tk.Tk()
    root.withdraw()
    win = mw.MainWindow(root, cfg)
    print("[OK] MainWindow 实例化成功，模式 =", win.mode)

    # 模式选择弹窗可正常构建（150ms 后自动关闭，避免阻塞）
    root.after(150, lambda: [d.destroy() for d in root.winfo_children()
                             if isinstance(d, tk.Toplevel)])
    from pdfrenamer.ui.mode_selector import ask_mode
    _m, _r = ask_mode(root, "", True)
    print("[OK] 模式选择弹窗构建成功")

    # 双模式切换：合同 → 论文 → 合同，字段与模板应随之变化
    win._switch_mode("paper")
    paper_fields = [f["name"] for f in win.editor.get_fields()]
    paper_tpl = win.template_var.get()
    print("[OK] 论文模式字段：", paper_fields, "模板：", paper_tpl)
    assert "论文题目" in paper_fields and "{作者}" in paper_tpl
    win._switch_mode("contract")
    contract_fields = [f["name"] for f in win.editor.get_fields()]
    print("[OK] 合同模式字段：", contract_fields)
    assert "甲方" in contract_fields and "合同名称" in contract_fields

    win._on_scan()
    if not wait_until(lambda: win.preview_data is not None, root):
        print("[FAIL] 扫描预览超时")
        root.destroy()
        return 1
    results, records, snap, warns = win.preview_data
    print(f"[OK] 扫描完成：{len(results)} 个结果，{len(records)} 条改名计划，警告={warns}")

    win._on_execute()
    if not wait_until(lambda: not win.busy, root, timeout=60):
        print("[FAIL] 执行超时")
        root.destroy()
        return 1
    root.update()

    xlsx = tmp / FILE_NAME
    ok = True
    if not xlsx.exists():
        print("[FAIL] Excel 未生成在所选目录")
        ok = False
    else:
        from openpyxl import load_workbook
        wb = load_workbook(xlsx)
        ws = wb["合同汇总"]
        print(f"[OK] Excel 生成：{xlsx}｜sheet={wb.sheetnames}｜数据行={ws.max_row - 1}")
        if ws.max_row != len(results) + 1:
            print("[FAIL] Excel 行数不符")
            ok = False
        wb.close()

    renamed = [p.name for p in tmp.glob("*.pdf") if p.name.startswith("2024年度")]
    print("[OK] 已改名文件示例：", renamed[:2])
    if not renamed:
        print("[FAIL] 没有文件被改名")
        ok = False

    # 验证撤销按钮
    win._on_undo()
    root.update()
    restored = (tmp / "02_标准合同.pdf").exists()
    print("[OK] 撤销后原文件名恢复：", restored)
    if not restored:
        ok = False

    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    print("[PASS] UI 冒烟测试通过" if ok else "[FAIL] UI 冒烟测试存在失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
