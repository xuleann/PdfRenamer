# -*- coding: utf-8 -*-
"""只读版式诊断：为规则校准打印论文 PDF 的元数据、首页行结构与年份上下文。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

USER = Path(__file__).resolve().parents[1] / "samples" / "user"
YEAR = re.compile(r"\b((?:19|20)\d{2})\b")

for p in sorted(USER.glob("*.pdf")):
    print("\n" + "=" * 76)
    print(f"### {p.name}")
    with pymupdf.open(p) as d:
        md = {k: v for k, v in d.metadata.items() if v}
        print("  metadata:", {k: (v[:90] if isinstance(v, str) else v) for k, v in md.items()})
        first = d[0].get_text("text")
        lines = [x.rstrip() for x in first.splitlines()]
        print("  --- 首页前 22 行（行号|内容）---")
        for i, ln in enumerate(lines[:22]):
            if ln.strip():
                print(f"  {i:>2}| {ln[:110]}")
        full = "\n".join(d[i].get_text("text") for i in range(min(3, d.page_count)))
        print("  --- 年份出现上下文（前 3 页，最多 6 处）---")
        for m in list(YEAR.finditer(full))[:6]:
            s = max(0, m.start() - 55)
            ctx = full[s:m.end() + 35].replace("\n", " ")
            print(f"     ...{ctx}...")
        print("  --- 页眉/会议候选行 ---")
        for ln in lines[:12]:
            if re.search(r"IEEE|TRANSACTIONS|JOURNAL|PROCEEDINGS|AAAI|NeurIPS|ICLR|ACM|Conference|arXiv|VOL\.", ln, re.I):
                print("     ", ln[:110])
        last = d[-1].get_text("text")
        tail = [x for x in last.splitlines() if x.strip()][-8:]
        print("  --- 末页尾部 8 行 ---")
        for ln in tail:
            print("     ", ln[:110])
