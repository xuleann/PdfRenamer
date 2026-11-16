# -*- coding: utf-8 -*-
"""构建门禁：静态扫描源码，禁止任何 AI / 推理 / 网络客户端依赖进入运行时。

用法（项目根目录执行）：.venv/Scripts/python.exe tests/scan_no_ai.py
退出码 0 = 通过，1 = 发现违规。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

FORBIDDEN_MODULES = {
    "torch", "transformers", "onnxruntime", "openai", "anthropic",
    "langchain", "llama_index", "sentence_transformers", "tensorflow",
    "keras", "sklearn", "cv2", "paddleocr", "easyocr", "pytesseract",
    "requests", "httpx", "aiohttp", "urllib.request", "socket",
    "pymupdf_layout", "pymupdf4llm",
}
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)


def main() -> int:
    violations: list[str] = []
    for py in sorted(SRC.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        for mod in IMPORT_RE.findall(text):
            top = mod.split(".")[0]
            if mod in FORBIDDEN_MODULES or top in FORBIDDEN_MODULES:
                violations.append(f"{py.relative_to(ROOT)}: import {mod}")
    # 运行时依赖白名单之外的第三方库也不允许出现在 requirements.txt
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for pkg in re.findall(r"^\s*([A-Za-z][\w.-]*)\s*==", req, re.MULTILINE):
        if pkg.lower() in FORBIDDEN_MODULES:
            violations.append(f"requirements.txt: {pkg}")

    # venv 里也不应有推理引擎（若存在则提示，但不阻断源码构建）
    try:
        import importlib.util
        for name in ("onnxruntime", "torch", "transformers"):
            if importlib.util.find_spec(name) is not None:
                violations.append(f"venv 中残留推理库：{name}")
    except Exception:
        pass

    if violations:
        print("[FAIL] 检测到 AI / 网络依赖：")
        for v in violations:
            print("  -", v)
        return 1
    print(f"[PASS] 已扫描 {len(list(SRC.rglob('*.py')))} 个源文件，未发现 AI / 推理 / 网络调用依赖。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
