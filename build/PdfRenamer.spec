# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile 配置（全 ASCII 构建路径，避免中文路径兼容问题）。"""
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821  SPECPATH 由 PyInstaller 注入
SRC = ROOT / "src"

datas = [
    (str(ROOT / "config" / "default_config.json"), "config"),
    (str(ROOT / "assets" / "app.ico"), "assets"),
]

hiddenimports = [
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox",
    "tkinter.scrolledtext",
    "pymupdf", "openpyxl", "pypdf", "pdfplumber",
    "pdfminer", "PIL", "charset_normalizer",
]

a = Analysis(  # noqa: F821
    [str(SRC / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "onnxruntime", "torch", "transformers", "matplotlib"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PdfRenamer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # 避免 PyMuPDF 扩展 DLL 被 UPX 破坏 / 杀软误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,             # GUI 程序，不弹控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico"),
    version=None,
)
