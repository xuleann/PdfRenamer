# -*- coding: utf-8 -*-
"""V1.1.2 真实合同扫描件正向校准（Windows 系统内置离线 OCR）。

样本：samples/user/ 下 4 份真实合同扫描件（CamScanner / Sharp，无文本层）。
期望值：tests/scanned_expect.json，由人工逐页目视核对抄录。
格式模板：tests/scanned_expect.example.json（虚构内容，仅说明结构）。

跨机说明：真实样本与真实期望值均不入 Git（见 .gitignore）。本脚本在
「samples/user/ 缺失或为空」或「缺少 scanned_expect.json」时输出 [SKIP]
并返回 0（不视为失败），也不会拿 example 文件冒充真实期望值。

PASS 判据（硬门禁）：
  4/4 OCR 出文本（doc_status != no_text_layer 且 text_chars >= 20）
  4/4 判为合同（doc_status != not_contract）
  0 个「垃圾改名」（不是全「未知」占位名、也不是被误判跳过）

字段命中率仅作统计（不做硬门禁）：OCR 默认只读前 2 页 + 末页，
正文中间页的金额/签订日期通常取不到，属已知限制，由预览表人工补录兜底。

纯只读：不创建/复制/修改 samples/user/ 下的任何样本文件。
用法（项目根目录执行）：.venv/Scripts/python.exe tests/calibrate_scanned.py [--json output/calibration_scanned.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.config import load_config  # noqa: E402
from pdfrenamer.engine import ExtractEngine  # noqa: E402
from pdfrenamer.models import DOC_NO_TEXT, DOC_NOT_CONTRACT  # noqa: E402
from pdfrenamer.presets import MODES  # noqa: E402
from pdfrenamer.renamer import RenameEngine  # noqa: E402

USER = ROOT / "samples" / "user"
EXPECT_FILE = ROOT / "tests" / "scanned_expect.json"
FIELDS = ["合同名称", "甲方", "供方", "时间", "金额"]

_PUNCT = re.compile(r"[\s,，.。:：;；()（）¥￥%／/\\-]+")


def norm(v: str) -> str:
    return _PUNCT.sub("", str(v or "")).lower()


def hit(actual: str, expected: str, field: str) -> bool:
    """宽松比对：OCR 有截断/误字/大写金额，完全相同过于苛刻。"""
    a, e = norm(actual), norm(expected)
    if not a or not e:
        return False
    if a == e:
        return True
    if field == "时间":
        nums_a = re.sub(r"\D", "", a)
        nums_e = re.sub(r"\D", "", e)
        return len(nums_a) >= 4 and (nums_a in nums_e or nums_e in nums_a)
    if field == "金额":
        m_a = re.search(r"\d+(?:\.\d+)?", a)
        m_e = re.search(r"\d+(?:\.\d+)?", e)
        return bool(m_a and m_e and
                    (m_a.group(0) in m_e.group(0) or m_e.group(0) in m_a.group(0)))
    if len(a) >= 4 and len(e) >= 4:
        return a in e or e in a
    return False


def _skip(reason: str) -> int:
    print("=" * 104)
    print(f"[SKIP] {reason}")
    print("  本脚本依赖仅存于本机的真实扫描样本与期望值（均不入 Git）。")
    print("  如需在本机启用：把真实合同扫描件放入 samples/user/，")
    print("  按 tests/scanned_expect.example.json 的格式抄录生成 tests/scanned_expect.json。")
    print("=" * 104)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    if not USER.is_dir() or not any(USER.glob("*.pdf")):
        return _skip("缺少真实扫描样本目录 samples/user/（或其中没有 PDF）")
    if not EXPECT_FILE.exists():
        return _skip("缺少真实期望值文件 tests/scanned_expect.json")

    expect = json.loads(EXPECT_FILE.read_text(encoding="utf-8"))["samples"]
    if not any((USER / n).exists() for n in expect):
        return _skip("samples/user/ 中没有期望值清单里的任何样本文件")
    cfg = load_config()
    engine = ExtractEngine(
        "contract", MODES["contract"],
        contract_gate=True,
        gate_threshold=cfg.get("contract_gate_threshold", 2),
        scan_ocr_enabled=bool(cfg.get("scan_ocr_enabled", True)),
        scan_ocr_max_pages=cfg.get("scan_ocr_max_pages", 2),
        scan_ocr_include_last_page=bool(cfg.get("scan_ocr_include_last_page", True)),
        scan_ocr_dpi=cfg.get("scan_ocr_dpi", 200),
        scan_ocr_max_side=cfg.get("scan_ocr_max_side", 2400),
        scan_ocr_timeout=cfg.get("scan_ocr_timeout", 60),
        scan_ocr_lang=cfg.get("scan_ocr_lang", "auto"),
    )
    renamer = RenameEngine(MODES["contract"]["template"], "未知", 120)

    print("=" * 104)
    print(f"V1.1.2 真实合同扫描件正向校准  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("期望：4/4 OCR 出文本、4/4 判为合同、0 垃圾改名；字段命中率单列统计（非硬门禁）")
    print("=" * 104)

    rows: list[dict] = []
    n_docs = n_text = n_contract = n_good_name = 0
    n_fields = n_hits = 0

    for name, exp in expect.items():
        p = USER / name
        if not p.exists():
            print(f"[SKIP] 缺少样本 {name}")
            continue
        r = engine.extract_file(p)
        rec = renamer.plan([r], p.parent)[0]

        has_text = (r.doc_status != DOC_NO_TEXT and r.text_chars >= 20)
        is_contract = (r.doc_status != DOC_NOT_CONTRACT)
        new_name = rec.new_name or ""
        good_name = (rec.status != "skipped" and not
                     all(x in new_name for x in ("未知_未知", "未知_未知_未知")))

        n_docs += 1
        n_text += int(has_text)
        n_contract += int(is_contract)
        n_good_name += int(good_name)

        values, matched = {}, {}
        for f in FIELDS:
            actual = r.fields[f].value if f in r.fields else ""
            values[f] = actual
            matched[f] = bool(hit(actual, exp.get(f, ""), f))
            n_fields += 1
            n_hits += int(matched[f])

        rows.append({
            "file": name, "doc_status": r.doc_status, "text_chars": r.text_chars,
            "has_text": has_text, "is_contract": is_contract,
            "rename_status": rec.status, "new_name": new_name,
            "good_name": good_name, "values": values, "matched": matched,
            "note": r.note,
        })
        print(f"\n■ {name}")
        print(f"  [{'OK ' if has_text else 'BAD'}] OCR 文本 = {r.text_chars} 字符｜状态 {r.doc_status}")
        print(f"  [{'OK ' if is_contract else 'BAD'}] 文档类型 = 合同")
        print(f"  [{'OK ' if good_name else 'BAD'}] 改名计划 = {rec.status} → {new_name[:70]}")
        for f in FIELDS:
            mark = "hit " if matched[f] else "miss"
            print(f"    [{mark}] {f:<6} 实际={values[f][:38]!r:<40} 期望={exp.get(f, '')[:32]}")
        if r.note:
            print(f"       备注: {r.note[:100]}")

    overall = (n_docs == len(expect) and n_text == n_docs
               and n_contract == n_docs and n_good_name == n_docs)
    print("\n" + "=" * 104)
    print(f"结果: OCR 出文本 {n_text}/{n_docs}｜判为合同 {n_contract}/{n_docs}｜"
          f"正常改名 {n_good_name}/{n_docs}｜字段命中 {n_hits}/{n_fields} "
          f"= {n_hits / max(1, n_fields) * 100:.1f}%｜{'PASS' if overall else 'FAIL'}")
    print("说明：金额/日期多在正文中间页，默认只读前 2 页 + 末页，未命中属已知限制；"
          "可在预览表双击补录。")
    print("=" * 104)

    if args.json:
        out = ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "time": datetime.now().isoformat(timespec="seconds"),
            "documents": n_docs, "ocr_text": n_text, "contracts": n_contract,
            "good_names": n_good_name, "fields": n_fields, "field_hits": n_hits,
            "field_hit_rate": round(n_hits / max(1, n_fields), 4),
            "pass": overall, "rows": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("报告:", out)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
