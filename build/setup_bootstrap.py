# -*- coding: utf-8 -*-
"""离线兜底安装向导（仅当 Inno Setup 无法下载/安装时使用）。

用 PyInstaller 打包时把 PdfRenamer.exe 作为数据文件嵌入。
从项目根目录执行：
  .venv\Scripts\python.exe -m PyInstaller --onefile --noconsole ^
      --name PdfRenamer_setup --distpath dist --workpath build\work ^
      --add-data "dist\PdfRenamer.exe;." ^
      --add-data "docs\*.docx;docs" ^
      --add-data "README.md;." ^
      build\setup_bootstrap.py

仅使用标准库（tkinter / shutil / winreg / subprocess），无网络、无 AI。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP = "PdfRenamer"
PAYLOAD = "PdfRenamer.exe"


def bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def default_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / APP


def make_shortcut(target: Path, lnk: Path) -> bool:
    """用 Windows 自带 WScript.Shell 创建 .lnk，不依赖第三方库。"""
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        f"'{str(lnk)}');$s.TargetPath='{str(target)}';$s.WorkingDirectory='{str(target.parent)}';"
        "$s.Description='PdfRenamer';$s.Save()"
    )
    try:
        return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                              check=False, timeout=30, capture_output=True).returncode == 0
    except Exception:
        return False


def write_uninstall(target: Path) -> None:
    """写 HKCU 卸载项 + 一个纯 bat 卸载脚本（不依赖 Python）。"""
    bat = target / "uninstall.bat"
    bat.write_text(
        "@echo off\r\n"
        f'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP}" /f >nul 2>&1\r\n'
        f'if exist "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP}.lnk" del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP}.lnk"\r\n'
        f'if exist "%USERPROFILE%\\Desktop\\{APP}.lnk" del "%USERPROFILE%\\Desktop\\{APP}.lnk"\r\n'
        f'echo Uninstalled. Files in "{target}" were kept for safety.\r\n',
        encoding="mbcs", errors="replace",
    )
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP}")
        for name, value in (("DisplayName", APP), ("DisplayVersion", "1.1.2"),
                            ("Publisher", "Local Desktop Tool"),
                            ("InstallLocation", str(target)),
                            ("DisplayIcon", str(target / PAYLOAD)),
                            ("UninstallString", f'cmd /c "{bat}"')):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
    except Exception:
        pass  # 注册失败不影响程序本身可用


def install(target: Path, desktop: bool) -> str:
    src = bundle_dir()
    payload = src / PAYLOAD
    if not payload.exists():
        raise FileNotFoundError(f"打包时未嵌入 {PAYLOAD}，请先构建 dist/PdfRenamer.exe")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload, target / PAYLOAD)
    docs = src / "docs"
    if docs.is_dir():
        (target / "docs").mkdir(exist_ok=True)
        for p in docs.glob("*.docx"):
            shutil.copy2(p, target / "docs" / p.name)
    readme = src / "README.md"
    if readme.exists():
        shutil.copy2(readme, target / "README.md")

    shortcuts = 0
    desktop_dir = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    start_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / \
        r"Microsoft\Windows\Start Menu\Programs"
    if desktop and desktop_dir.is_dir() and make_shortcut(target / PAYLOAD, desktop_dir / f"{APP}.lnk"):
        shortcuts += 1
    if start_dir.is_dir() and make_shortcut(target / PAYLOAD, start_dir / f"{APP}.lnk"):
        shortcuts += 1
    write_uninstall(target)
    return f"安装完成：{target}\n已创建 {shortcuts} 个快捷方式。\n卸载请运行目录内的 uninstall.bat。"


def main() -> int:
    root = tk.Tk()
    root.title(f"{APP} 安装向导（离线兜底）")
    root.geometry("560x260")
    root.resizable(False, False)

    frm = ttk.Frame(root, padding=18)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=f"安装 {APP}", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
    ttk.Label(frm, text="纯本地工具，不联网、不写系统目录。", foreground="#5a6472").pack(anchor="w", pady=(2, 14))

    row = ttk.Frame(frm)
    row.pack(fill="x")
    var = tk.StringVar(value=str(default_dir()))
    ttk.Label(row, text="安装目录：").pack(side="left")
    ttk.Entry(row, textvariable=var, width=46).pack(side="left", padx=6)
    ttk.Button(row, text="浏览…", command=lambda: var.set(
        filedialog.askdirectory(initialdir=var.get(), parent=root) or var.get())).pack(side="left")

    desk = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm, text="创建桌面快捷方式", variable=desk).pack(anchor="w", pady=14)

    def do_install():
        try:
            msg = install(Path(var.get()), bool(desk.get()))
        except Exception as exc:
            messagebox.showerror("安装失败", str(exc), parent=root)
            return
        messagebox.showinfo("完成", msg, parent=root)
        root.destroy()

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(10, 0))
    ttk.Button(btns, text="安装", command=do_install).pack(side="right", padx=4)
    ttk.Button(btns, text="取消", command=root.destroy).pack(side="right")
    root.mainloop()
    return 0


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        print("请运行安装目录内的 uninstall.bat")
        sys.exit(0)
    sys.exit(main())
