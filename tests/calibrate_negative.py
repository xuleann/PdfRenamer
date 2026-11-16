# -*- coding: utf-8 -*-
"""合同模式负样本校准：验证「非合同文档」不被误提取、不被改名。

V1.1.1 的 3 份真实样本经逐页核对是**财政支出绩效评价报告 / 工作方案**，
不是合同、也不是空白范本：封面标签为 项目名称/项目单位/委托单位/评价机构/成文年月，
全文没有甲乙双方、签订日期、合同金额的标签-值对。

V1.1.2：用户已把这 3 份真实报告从 samples/user/ 删除。为避免回归用例静默 skip，
改由 tests/make_samples.py 生成 3 份版式等价的合成负样本（tests/samples/）。
这样既不要求用户补回原文件，也不含任何真实业务数据。

因此合同模式下的正确结果是：判为 not_contract、5 个字段全部缺失、**不参与改名**。
切勿把「项目名称」当成合同名称的正向期望值，否则会污染校准。

纯只读：不创建/复制/修改 samples/user/ 下的任何样本文件。
用法：python tests/calibrate_negative.py [--json output/calibration_negative.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.engine import ExtractEngine  # noqa: E402
from pdfrenamer.models import DOC_NOT_CONTRACT  # noqa: E402
from pdfrenamer.presets import MODES  # noqa: E402
from pdfrenamer.renamer import RenameEngine  # noqa: E402

USER = ROOT / "tests" / "samples"   # V1.1.2：改用合成负样本，不再依赖用户样本目录
NEGATIVE_FILES = [
    "11_绩效评价报告A.pdf",
    "12_绩效评价报告B.pdf",
    "13_绩效评价工作方案.pdf",
]
CONTRACT_FIELDS = ["合同名称", "甲方", "供方", "时间", "金额"]
# None = 该字段必须为「缺失/未知」
NEGATIVE_EXPECT: dict[str, dict[str, None]] = {
    name: {f: None for f in CONTRACT_FIELDS} for name in NEGATIVE_FILES
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    engine = ExtractEngine("contract", MODES["contract"])
    renamer = RenameEngine(MODES["contract"]["template"], "未知", 120)
    rows: list[dict] = []
    docs = good_docs = fields = good_fields = renamed = 0

    print("=" * 100)
    print(f"合同模式负样本校准  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("期望：3 份绩效评价报告全部判 not_contract、15/15 字段缺失、0 改名")
    print("=" * 100)
    for name in NEGATIVE_FILES:
        p = USER / name
        if not p.exists():
            print(f"[SKIP] 缺少样本 {name}")
            continue
        r = engine.extract_file(p)
        rec = renamer.plan([r], p.parent)[0]
        ok_doc = (r.doc_status == DOC_NOT_CONTRACT)
        missing = {f: r.fields[f].is_missing for f in CONTRACT_FIELDS
                   if f in r.fields}
        ok_field = sum(missing.values())
        no_rename = rec.status == "skipped"
        docs += 1
        good_docs += int(ok_doc)
        fields += len(missing)
        good_fields += ok_field
        renamed += int(not no_rename)
        rows.append({
            "file": name, "doc_status": r.doc_status,
            "doc_ok": ok_doc, "missing": missing,
            "rename_status": rec.status, "no_rename": no_rename,
            "contract_name": r.fields["合同名称"].value,
            "note": r.note,
        })
        print(f"\n■ {name}")
        print(f"  [{'OK ' if ok_doc else 'BAD'}] 文档类型 = {r.doc_status}")
        print(f"  [{'OK ' if ok_field == len(missing) else 'BAD'}] 字段缺失 = "
              f"{ok_field}/{len(missing)}  {missing}")
        print(f"  [{'OK ' if no_rename else 'BAD'}] 改名计划 = {rec.status}（期望 skipped）")
        if r.note:
            print(f"       备注: {r.note[:100]}")

    overall = (docs == len(NEGATIVE_FILES) and good_docs == docs
               and good_fields == fields and renamed == 0)
    print("\n" + "=" * 100)
    print(f"结果: 非合同判定 {good_docs}/{docs}｜字段正确缺失 {good_fields}/{fields}｜"
          f"误改名 {renamed}｜{'PASS' if overall else 'FAIL'}")
    print("=" * 100)

    if args.json:
        out = ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "time": datetime.now().isoformat(timespec="seconds"),
            "documents": docs, "not_contract": good_docs,
            "fields": fields, "missing_fields": good_fields,
            "renamed": renamed, "pass": overall, "rows": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("报告:", out)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
