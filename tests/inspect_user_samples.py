# -*- coding: utf-8 -*-
"""只读探查：列出 samples/user 下真实样本的文本版式特征。

不修改任何样本文件，不联网，只在本机打印文本片段供规则校准。
用法：python tests/inspect_user_samples.py [每篇打印字符数]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pymupdf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
USER = ROOT / "samples" / "user"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 1600


def pdf_head(path: Path, limit: int) -> str:
    with pymupdf.open(path) as doc:
        pages = min(2, doc.page_count)
        chunks = [doc[i].get_text("text") for i in range(pages)]
        return "\n".join(chunks)[:limit]


def main() -> None:
    pdfs = sorted(p for p in USER.glob("*.pdf"))
    print(f"PDF 数量：{len(pdfs)}  目录：{USER}")
    for p in pdfs:
        print("\n" + "=" * 78)
        print(f"### {p.name}  ({p.stat().st_size / 1024:.0f} KB)")
        try:
            with pymupdf.open(p) as d:
                print(f"    页数={d.page_count}  元数据={d.metadata.get('title', '')!r} / {d.metadata.get('author', '')!r}")
        except Exception as exc:
            print("    打开失败：", exc)
            continue
        txt = pdf_head(p, LIMIT)
        print("-" * 78)
        print(txt)
        print("-" * 78)

    for w in sorted(list(USER.glob("*.docx")) + list(USER.glob("*.doc"))):
        print("\n" + "=" * 78)
        print(f"### {w.name}  ({w.stat().st_size / 1024:.0f} KB)")
        if w.suffix.lower() == ".docx":
            try:
                from docx import Document
                d = Document(w)
                lines = [x.text for x in d.paragraphs if x.text.strip()]
                for t in d.tables:
                    for row in t.rows:
                        lines.append(" | ".join(c.text.strip() for c in row.cells))
                print("\n".join(lines)[:LIMIT * 2])
            except Exception as exc:
                print("    docx 读取失败：", exc)
        else:
            print("    [旧版 .doc 二进制，单独处理]")


if __name__ == "__main__":
    main()
