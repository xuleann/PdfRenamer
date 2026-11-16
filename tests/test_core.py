# -*- coding: utf-8 -*-
"""核心链路单元测试（stdlib unittest，无第三方测试框架）。

用法（项目根目录执行）：.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfrenamer.config import load_config  # noqa: E402
from pdfrenamer.engine import ExtractEngine, list_pdfs  # noqa: E402
from pdfrenamer.excel import FILE_NAME, ExcelWriter, has_recoverable_rows, recover_rows  # noqa: E402
from pdfrenamer.models import DOC_ENCRYPTED, DOC_NO_TEXT, ST_HEURISTIC  # noqa: E402
from pdfrenamer.presets import MODES  # noqa: E402
from pdfrenamer.renamer import RenameEngine  # noqa: E402
from pdfrenamer.rules import (  # noqa: E402
    first_author, normalize_date, normalize_money, sanitize_filename, unique_name,
)
from pdfrenamer.undo import UndoManager  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"


class RuleTests(unittest.TestCase):
    def test_date(self):
        self.assertEqual(normalize_date("2024年3月5日"), "2024-03-05")
        self.assertEqual(normalize_date("2024/3/5"), "2024-03-05")
        self.assertEqual(normalize_date("2024-03-05"), "2024-03-05")
        self.assertEqual(normalize_date("2023年"), "2023")

    def test_money(self):
        self.assertEqual(normalize_money("¥1,200,000.00元"), "1200000.00元")
        self.assertEqual(normalize_money("120万元"), "1200000元")
        self.assertEqual(normalize_money("8500元"), "8500元")
        self.assertNotIn("e+", normalize_money("¥1,200,000.00元"))

    def test_filename(self):
        self.assertEqual(sanitize_filename('A/B*C:D?E"F<G>H|I.pdf'), "A_B_C_D_E_F_G_H_I.pdf")
        self.assertNotIn("..", sanitize_filename("...test....pdf"))
        self.assertTrue(sanitize_filename("CON.pdf").startswith("_"))
        self.assertLessEqual(len(sanitize_filename("长" * 300 + ".pdf", 120)), 120)

    def test_unique(self):
        used = {"a.pdf"}
        self.assertEqual(unique_name("a.pdf", used), "a_2.pdf")
        self.assertEqual(unique_name("a.pdf", used), "a_3.pdf")
        self.assertEqual(unique_name("A.PDF", {"a.pdf"}), "A_2.PDF")

    def test_first_author(self):
        self.assertEqual(first_author("张三、李四、王五"), "张三")
        self.assertEqual(first_author("张三, 李四"), "张三")


class ExtractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not list(SAMPLES.glob("*.pdf")):
            from make_samples import main
            main()

    def test_contract_fields(self):
        e = ExtractEngine("contract", MODES["contract"])
        r = e.extract_file(SAMPLES / "02_标准合同.pdf")
        self.assertEqual(r.doc_status, "ok")
        self.assertEqual(r.fields["合同名称"].value, "2024年度服务器设备采购合同")
        self.assertEqual(r.fields["甲方"].value, "华东某某科技有限公司")
        self.assertEqual(r.fields["供方"].value, "北京某某信息技术有限公司")
        self.assertEqual(r.fields["时间"].value, "2024-03-05")
        self.assertEqual(r.fields["金额"].value, "1200000.00元")

    def test_paper_fields(self):
        e = ExtractEngine("paper", MODES["paper"])
        r = e.extract_file(SAMPLES / "01_标准论文.pdf")
        self.assertEqual(r.fields["作者"].value, "张三、李四、王五")
        self.assertEqual(r.fields["作者"].file_value, "张三")
        self.assertEqual(r.fields["期刊"].value, "计算机学报")
        self.assertEqual(r.fields["发表年份"].value, "2023")
        self.assertEqual(r.fields["论文题目"].status, ST_HEURISTIC)

    def test_fullwidth_label_on_own_line(self):
        e = ExtractEngine("contract", MODES["contract"])
        r = e.extract_file(SAMPLES / "09_全角标签独占行.pdf")
        self.assertEqual(r.fields["合同名称"].value, "智慧城市平台运维服务合同")
        self.assertEqual(r.fields["甲方"].value, "华东某某科技有限公司")
        self.assertEqual(r.fields["时间"].value, "2023-12-18")

    def test_scanned_pdf(self):
        e = ExtractEngine("contract", MODES["contract"])
        r = e.extract_file(SAMPLES / "03_扫描件.pdf")
        self.assertEqual(r.doc_status, DOC_NO_TEXT)
        self.assertIn("人工", r.skip_reason)

    def test_encrypted_pdf(self):
        e = ExtractEngine("contract", MODES["contract"])
        r = e.extract_file(SAMPLES / "04_加密合同.pdf")
        self.assertEqual(r.doc_status, DOC_ENCRYPTED)

    def test_missing_fields(self):
        e = ExtractEngine("contract", MODES["contract"])
        r = e.extract_file(SAMPLES / "05_字段缺失合同.pdf")
        self.assertEqual(r.doc_status, "partial")
        self.assertIn("供方", r.missing_names())


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not list(SAMPLES.glob("*.pdf")):
            from make_samples import main
            main()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pdfrenamer_"))
        for p in ("02_标准合同.pdf", "07_重名A.pdf", "08_重名B.pdf",
                  "03_扫描件.pdf", "06_非法字符长名称.pdf"):
            shutil.copy2(SAMPLES / p, self.tmp / p)
        self.cfg = load_config()
        self.originals = sorted(p.name for p in self.tmp.glob("*.pdf"))
        self.rid = datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, strategy="append"):
        mode = "contract"
        mc = MODES[mode]
        files = list_pdfs(self.tmp)
        engine = ExtractEngine(mode, mc)
        results = engine.extract_many(files)
        names = [f.name for f in engine.fields]
        renamer = RenameEngine(mc["template"], "未知", 120)
        records = renamer.plan(results, self.tmp)
        undo = UndoManager(self.tmp / "_plans")
        undo.save_plan(self.tmp, mode, records, self.rid)
        renamer.execute(records)
        undo.save_plan(self.tmp, mode, records, self.rid)
        w = ExcelWriter(self.tmp, mode, mc["sheet"], mc["label"], names, "未知", strategy)
        w.prepare()
        for r, rec in zip(results, records):
            w.append_row(w.build_row(r, rec))
        w.finish()
        return results, records, undo, w

    def test_rename_and_excel(self):
        results, records, _, w = self._run()
        done = [r for r in records if r.status == "done"]
        skipped = [r for r in records if r.status == "skipped"]
        self.assertGreaterEqual(len(done), 3)
        self.assertTrue(any(r.reason for r in skipped))
        # 扫描件不改名
        scan = next(r for r in records if r.original == "03_扫描件.pdf")
        self.assertEqual(scan.status, "skipped")
        self.assertTrue((self.tmp / "03_扫描件.pdf").exists())
        # 重名冲突加序号
        new_names = [r.new_name for r in done]
        self.assertEqual(len(new_names), len(set(n.lower() for n in new_names)))
        self.assertTrue(any("_2" in n for n in new_names))
        # Excel 位置与内容
        xlsx = self.tmp / FILE_NAME
        self.assertTrue(xlsx.exists(), "Excel 必须在所选目录下")
        from openpyxl import load_workbook
        wb = load_workbook(xlsx)
        self.assertIn("合同汇总", wb.sheetnames)
        ws = wb["合同汇总"]
        self.assertEqual(ws.max_row, len(results) + 1)
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertEqual(ws["A1"].value, "模式")
        self.assertIsNotNone(ws.auto_filter.ref)
        # V1.1.1：末尾「PDF 类型」标签列 + 类型配色，A 列「模式」保持兼容
        headers = [c.value for c in ws[1]]
        self.assertEqual(headers[-1], "PDF 类型")
        self.assertEqual(ws.cell(row=2, column=len(headers)).value, "合同")
        self.assertEqual(ws["A2"].value, "合同")
        self.assertIsNotNone(ws.cell(row=2, column=len(headers)).fill.fgColor.rgb)
        wb.close()
        # 非法字符不出现
        for n in new_names:
            self.assertFalse(any(c in n for c in '\\/:*?"<>|'))

    def test_undo_restores_all(self):
        _, records, undo, _ = self._run()
        out = undo.undo(self.tmp)
        self.assertTrue(out["ok"])
        self.assertGreater(out["restored"], 0)
        after = sorted(p.name for p in self.tmp.glob("*.pdf"))
        self.assertEqual(after, self.originals, "撤销后文件集合必须与执行前一致")
        for rec in records:
            if rec.status == "done":
                self.assertTrue(Path(rec.src).exists())
                self.assertFalse(Path(rec.dst).exists())

    def test_excel_append_preserves_old_rows(self):
        self._run("append")
        from openpyxl import load_workbook
        wb = load_workbook(self.tmp / FILE_NAME)
        n1 = wb["合同汇总"].max_row
        wb.close()
        # 第二轮用不同 run_id 再跑一次（此时源文件已被改名，仍可提取）
        self.rid = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "b"
        self._run("append")
        wb = load_workbook(self.tmp / FILE_NAME)
        n2 = wb["合同汇总"].max_row
        wb.close()
        self.assertGreater(n2, n1, "追加模式必须保留旧数据")

    def test_excel_upgrade_adds_type_column(self):
        """旧表（末尾为「备注」）应无损升列：不备份重建、不丢历史行。"""
        import pdfrenamer.excel as xm
        from openpyxl import load_workbook
        old_tail = xm.HEADER_TAIL
        try:
            xm.HEADER_TAIL = ["提取状态", "缺失字段", "处理时间", "备注"]
            self._run("append")
            wb = load_workbook(self.tmp / FILE_NAME)
            ws = wb["合同汇总"]
            self.assertEqual([c.value for c in ws[1]][-1], "备注")
            old_rows = ws.max_row
            wb.close()
        finally:
            xm.HEADER_TAIL = old_tail
        # 用新表头再打开 → 触发无损升列
        names = [f["name"] for f in MODES["contract"]["fields"]]
        w2 = ExcelWriter(self.tmp, "contract", "合同汇总", "合同", names, "未知", "append")
        w2.prepare()
        w2.finish()
        wb = load_workbook(self.tmp / FILE_NAME)
        ws = wb["合同汇总"]
        headers = [c.value for c in ws[1]]
        self.assertEqual(headers[-1], "PDF 类型")
        self.assertEqual(ws.max_row, old_rows, "历史行必须完整保留")
        self.assertEqual(ws.cell(row=2, column=len(headers)).value, "合同")
        self.assertEqual(ws["A1"].value, "模式")
        wb.close()
        self.assertEqual(list(self.tmp.glob("信息汇总_备份_*.xlsx")), [],
                         "升列不应产生备份重建")

    def test_rows_jsonl_recovery(self):
        self._run("append")
        self.assertTrue(has_recoverable_rows(self.tmp))
        mc = MODES["contract"]
        names = [f["name"] for f in mc["fields"]]
        n = recover_rows(self.tmp, "contract", mc["sheet"], mc["label"], names, "未知")
        self.assertGreater(n, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
