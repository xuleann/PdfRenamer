# -*- coding: utf-8 -*-
"""真实样本规则校准：对 samples/user 下的论文 PDF 计算字段命中率。

纯本地、只读样本。可反复运行，用于对比规则调整前后的效果。
用法：python tests/calibrate.py [--json output/calibration_report.json]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.engine import ExtractEngine  # noqa: E402
from pdfrenamer.presets import MODES  # noqa: E402

USER = ROOT / "samples" / "user"

# 人工核对真实首页/Metadata 后标注的期望值；仅用于评分，不参与提取
EXPECT: dict[str, dict[str, str]] = {
    "FedOM、FedOMF.pdf": {
        "论文题目": "Personalized Federated Learning in One-Shot: A Method for Heterogeneous Data Scenarios",
        "作者": "Tian Sang",
        "期刊": "IEEE Internet of Things Journal",
        "发表年份": "2025",
    },
    "FedProto.pdf": {
        "论文题目": "FedProto: Federated Prototype Learning across Heterogeneous Clients",
        "作者": "Yue Tan",
        "期刊": "AAAI",
        "发表年份": "2022",
    },
    "FedTED.pdf": {
        "论文题目": "Improving Generalization and Personalization in Model-Heterogeneous Federated Learning",
        "作者": "Xiongtao Zhang",
        "期刊": "IEEE Transactions on Neural Networks and Learning Systems",
        "发表年份": "2025",
    },
    "mcmahan17a.pdf": {
        "论文题目": "Communication-Efficient Learning of Deep Networks from Decentralized Data",
        "作者": "H. Brendan McMahan",
        "期刊": "AISTATS",
        "发表年份": "2017",
    },
    "pFedC.pdf": {
        "论文题目": "Model Decomposition and Reassembly for Purified Knowledge Transfer in Personalized Federated Learning",
        "作者": "Jie Zhang",
        "期刊": "IEEE Transactions on Mobile Computing",
        "发表年份": "2025",
    },
    "pFedKD.pdf": {
        "论文题目": "PFedKD: Personalized Federated Learning via Knowledge Distillation Using Unlabeled Pseudo Data for Internet of Things",
        "作者": "Hanxi Li",
        "期刊": "IEEE Internet of Things Journal",
        "发表年份": "2025",
    },
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (s or "").lower())


def hit(field: str, actual: str, expected: str) -> bool:
    a, e = norm(actual), norm(expected)
    if not a or not e:
        return False
    if field == "发表年份":
        return e in a and len(a) <= 8
    if field == "作者":
        # 命中首位作者姓名（或姓氏）即可
        parts = [norm(p) for p in re.split(r"[,，;；、\s]+", expected) if p.strip()]
        key = parts[-1] if parts else e
        return key in a or e in a
    if field == "期刊":
        return e in a or a in e
    # 题目：允许 PDF 元数据被截断，只要主体一致
    if e in a or a in e:
        return True
    return difflib.SequenceMatcher(None, a, e).ratio() >= 0.72


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    engine = ExtractEngine("paper", MODES["paper"])
    rows: list[dict] = []
    total = good = 0
    print("=" * 108)
    print(f"真实样本规则校准  {datetime.now():%Y-%m-%d %H:%M:%S}   样本目录: {USER}")
    print("=" * 108)
    for name, exp in EXPECT.items():
        p = USER / name
        if not p.exists():
            print(f"[SKIP] 缺少样本 {name}")
            continue
        r = engine.extract_file(p)
        print(f"\n■ {name}   doc_status={r.doc_status}  chars={r.text_chars}")
        for fname, expected in exp.items():
            fr = r.fields.get(fname)
            actual = fr.value if fr else ""
            status = fr.status if fr else "missing"
            ok = hit(fname, actual, expected)
            total += 1
            good += int(ok)
            mark = "HIT " if ok else "MISS"
            rows.append({"file": name, "field": fname, "hit": ok,
                         "actual": actual, "expected": expected, "status": status})
            shown = actual if len(actual) <= 88 else actual[:85] + "…"
            print(f"  [{mark}] {fname:<6} ({status:<9}) {shown}")
            if not ok:
                print(f"         期望: {expected[:96]}")
        if r.note:
            print("  note:", r.note[:100])

    rate = good / total * 100 if total else 0.0
    print("\n" + "=" * 108)
    print(f"命中率: {good}/{total} = {rate:.1f}%")
    per_field: dict[str, list[bool]] = {}
    for x in rows:
        per_field.setdefault(x["field"], []).append(x["hit"])
    for f, v in per_field.items():
        print(f"  {f:<8}: {sum(v)}/{len(v)}")
    print("=" * 108)

    if args.json:
        out = ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "time": datetime.now().isoformat(timespec="seconds"),
            "hit": good, "total": total, "rate": round(rate, 1),
            "rows": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("报告:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
