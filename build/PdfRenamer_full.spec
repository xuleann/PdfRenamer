# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile 配置（V1.4.3 完整版，含本地离线 OCR 手写识别）。

与 PdfRenamer.spec 的区别：
- 不再 excludes numpy / onnxruntime —— V1.2.0 起手写体识别依赖 RapidOCR + ONNXRuntime；
  旧 spec 排除它们会导致 exe 里手写姓名/部门/日期全部识别不出来。
- 用 collect_all('rapidocr') 把 models/*.onnx（PP-OCRv6 检测/识别/方向分类）与
  config.yaml / default_models.yaml 一并打包，保证目标机首次运行不用联网下载模型。
- 仍排除 torch / transformers / pandas 等与运行时无关的重型库，控制体积。
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))  # noqa: F821

datas = []
binaries = []
hiddenimports = []

# RapidOCR：模型 + 配置 + 子模块（推理后端动态导入）
for pkg in ("rapidocr",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 推理链路的动态导入
hiddenimports += collect_submodules("onnxruntime")
hiddenimports += [
    "onnxruntime", "onnxruntime.capi", "onnxruntime.capi._pybind_state",
    "numpy", "cv2", "pyclipper", "shapely", "six", "tqdm", "yaml",
    "omegaconf", "colorlog", "requests", "PIL",
]

# 项目自带资源
datas += [
    (os.path.join(ROOT, "config", "default_config.json"), "config"),
    (os.path.join(ROOT, "assets", "app.ico"), "assets"),
]

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "src", "launcher.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch", "torchvision", "transformers", "tensorflow", "matplotlib",
        "pandas", "scipy", "notebook", "IPython", "pytest", "tkinter.test",
        "PyQt5", "PySide6", "paddle", "paddleocr",
    ],
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
    upx=False,                 # 避免 PyMuPDF / onnxruntime DLL 被 UPX 破坏或引发杀软误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,             # GUI 程序，不弹控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "app.ico"),
    version=None,
)
