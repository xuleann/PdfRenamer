# -*- coding: utf-8 -*-
"""PyInstaller 入口：必须用绝对导入，因为 frozen 时 app.py 会被当作顶层脚本。"""
from pdfrenamer.app import main

if __name__ == "__main__":
    raise SystemExit(main())
