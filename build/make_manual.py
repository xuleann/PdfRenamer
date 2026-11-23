# -*- coding: utf-8 -*-
"""生成《PdfRenamer 使用说明手册》Word 版（面向最终使用者，非开发文档）。

用法：D:/python/python.exe build/make_manual.py
输出：docs/PdfRenamer使用说明手册_v1.4.8.docx
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "PdfRenamer使用说明手册_v1.4.8.docx"
VERSION = "1.4.8"
TODAY = date.today().strftime("%Y 年 %m 月 %d 日")

BLUE = RGBColor(0x1F, 0x4E, 0x79)
DARK = RGBColor(0x22, 0x28, 0x31)
GREY = RGBColor(0x5A, 0x64, 0x72)


# ---------- 基础排版工具 ----------
def set_font(run, name="微软雅黑", size=10.5, bold=False, color=DARK):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def shade(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:fill"), hex_color)
    tcPr.append(el)


def cell_text(cell, text, bold=False, size=9.5, color=DARK, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    set_font(p.add_run(text), size=size, bold=bold, color=color)


def para(doc, text, size=10.5, bold=False, color=DARK, indent=True,
         space_after=6, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = 1.45
    if indent:
        pf.first_line_indent = Pt(21)
    set_font(p.add_run(text), size=size, bold=bold, color=color)
    return p


def h1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.keep_with_next = True
    set_font(p.add_run(text), size=15, bold=True, color=BLUE)
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "3")
    bottom.set(qn("w:color"), "1F4E79")
    bdr.append(bottom)
    pPr.append(bdr)
    return p


def h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    set_font(p.add_run(text), size=11.5, bold=True, color=RGBColor(0x23, 0x52, 0x7C))
    return p


def bullet(doc, text, bold_prefix=""):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Pt(24)
    pf.first_line_indent = Pt(-12)
    pf.space_after = Pt(3)
    pf.line_spacing = 1.4
    set_font(p.add_run("· "), size=10.5, bold=True, color=BLUE)
    if bold_prefix:
        set_font(p.add_run(bold_prefix), size=10.5, bold=True)
    set_font(p.add_run(text))
    return p


def note(doc, text, kind="info"):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fix_table(table, [16.2])
    cell = table.rows[0].cells[0]
    shade(cell, "EEF4FB" if kind == "info" else "FFF4E5")
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.35
    set_font(p.add_run(text), size=9.5,
             color=RGBColor(0x1F, 0x4E, 0x79) if kind == "info" else RGBColor(0x8A, 0x5A, 0x00))
    return table



def _fix_table(table, widths):
    """固定列宽（cm），并禁止行跨页断开。"""
    table.autofit = False
    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    for row in table.rows:
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trPr.append(cant)
        for i, c in enumerate(row.cells):
            if i < len(widths):
                c.width = Cm(widths[i])
    for i, g in enumerate(table._tbl.tblGrid.findall(qn("w:gridCol"))):
        if i < len(widths):
            g.set(qn("w:w"), str(int(widths[i] * 567)))


def make_table(doc, header, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, t in enumerate(header):
        shade(hdr[i], "DCE6F1")
        cell_text(hdr[i], t, bold=True, size=9.5, color=BLUE)
    for r in rows:
        cells = table.add_row().cells
        for i, v in enumerate(r):
            cell_text(cells[i], v, size=9.5)
    if widths:
        _fix_table(table, widths)
    return table


def add_page_number_footer(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("PdfRenamer 使用说明手册  v" + VERSION + "    第 ")
    set_font(run, size=8.5, color=GREY)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "17")
    rPr.append(sz)
    r.append(rPr)
    fld.append(r)
    p._p.append(fld)
    run2 = p.add_run(" 页")
    set_font(run2, size=8.5, color=GREY)


# ---------- 文档正文 ----------
def build():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin = Cm(2.4)
    sec.right_margin = Cm(2.2)
    add_page_number_footer(sec)

    normal = doc.styles["Normal"]
    normal.font.name = "微软雅黑"
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")

    # ===== 封面 =====
    for _ in range(5):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run("PdfRenamer"), size=30, bold=True, color=BLUE)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run("劳动合同 / 劳务合同  批量信息提取与更名工具"), size=15, color=DARK)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(30)
    set_font(p.add_run("使 用 说 明 手 册"), size=24, bold=True, color=RGBColor(0x23, 0x52, 0x7C))
    for _ in range(6):
        doc.add_paragraph()
    for line in [f"版本号：v{VERSION}", "适用系统：Windows 10 / 11（64 位）", f"编写日期：{TODAY}"]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(p.add_run(line), size=10.5, color=GREY)
    doc.add_page_break()

    # ===== 1 概述 =====
    h1(doc, "一、软件是做什么的")
    para(doc, "PdfRenamer 是一款运行在 Windows 上的桌面小工具，用于把一整个文件夹里的"
              "劳动合同、劳务合同 PDF 批量改名，并把每份合同的关键信息汇总成一张 Excel 表。")
    para(doc, "以往一份一份打开、抄姓名、抄身份证、抄日期，几十份合同要花半天；"
              "用本软件点两次按钮，全部处理完，并生成可直接核对的《信息汇总.xlsx》。")
    h2(doc, "1.1 提取的信息")
    make_table(doc,
               ["信息项", "说明", "示例"],
               [["合同类型", "自动判断是「劳动合同」还是「劳务合同」", "劳动合同"],
                ["乙方", "员工本人姓名，只取姓名，不含公司名", "张三"],
                ["身份证号", "15 / 18 位公民身份号码", "3201**********1234"],
                ["开始日期", "合同期限起始日", "2023-05-30"],
                ["结束日期", "合同期限终止日", "2026-05-29"],
                ["签订日期", "双方签字日期，用于生成文件名里的年份", "2023-05-30"],
                ["用工部门", "七选一：办公室 / 财务室 / 交通 / 物业 / 服务一部 / 服务二部 / 资产",
                 "财务室"]],
               widths=[3.0, 9.6, 3.6])

    h2(doc, "1.2 改名规则")
    para(doc, "默认命名模板为：")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    set_font(p.add_run("合同类型 _ 年份 _ 序号 _ 乙方姓名 .pdf"), size=11.5, bold=True, color=BLUE)
    para(doc, "例如：劳动合同_2023_001_张三.pdf。序号按处理顺序自动累加，不会重复覆盖。")

    h2(doc, "1.3 三点重要特性")
    bullet(doc, "所有识别都在本机完成，不联网、不上传任何合同内容。", "纯本地：")
    bullet(doc, "软件只读原件内容；确认执行后才改名，Excel 汇总表写在 PDF 所在目录。", "不改内容：")
    bullet(doc, "改错了点「撤销」即可全部还原为原文件名。", "可撤销：")

    # ===== 2 运行环境 =====
    h1(doc, "二、安装与启动")
    h2(doc, "2.1 运行环境")
    make_table(doc,
               ["项目", "要求"],
               [["操作系统", "Windows 10 / Windows 11，64 位"],
                ["内存", "建议 4 GB 以上"],
                ["磁盘", "软件本体约 300 MB，另需少量空间存放 Excel 与截图"],
                ["网络", "不需要联网；首次运行也不需要下载任何组件"],
                ["其他软件", "无需安装 Office；但查看汇总表需有 Excel 或 WPS"]],
               widths=[3.4, 12.8])

    h2(doc, "2.2 启动方式（绿色版，免安装）")
    para(doc, "1）把 PdfRenamer.exe 复制到电脑任意位置，例如 D:\\工具\\PdfRenamer\\；")
    para(doc, "2）双击 PdfRenamer.exe 即可启动，不写注册表、不弹广告、不留后台进程；")
    para(doc, "3）首次启动会询问使用「论文」还是「合同」模式，请选择「合同」，"
              "并勾选「记住本次选择」，以后打开直接进入合同模式。")
    note(doc, "提示：首次双击若出现蓝色的「Windows 已保护你的电脑」窗口，"
              "请点「更多信息」→「仍要运行」。这是因为软件未购买数字签名证书，"
              "并非病毒；也可请 IT 同事将 exe 加入白名单。")
    para(doc, "首次启动约需 10～30 秒（单文件程序需要把自己解压到临时目录），"
              "之后每次启动约 5～10 秒，属正常现象。")

    # ===== 3 操作步骤 =====
    h1(doc, "三、四步完成批量处理")
    para(doc, "界面从上到下依次是「1. 选择要处理的 PDF」「2. 重命名规则」「3. 扫描预览」三块，"
              "底部是运行日志与状态栏。整个流程只需点两次主按钮。")

    h2(doc, "第 1 步：选择要处理的 PDF")
    para(doc, "点「浏览…」选择存放合同的文件夹。软件会显示该文件夹下直接包含的 PDF 数量"
              "（不进入子文件夹）。若只想处理其中几份，可切换到「选择 PDF 文件（同目录）」逐个勾选，"
              "注意所选文件必须在同一个文件夹内。")
    note(doc, "建议：处理前先把待处理的合同单独放一个文件夹，处理完再归档，避免和其它 PDF 混在一起。",
         kind="warn")

    h2(doc, "第 2 步：确认重命名规则（一般不用改）")
    para(doc, "右侧显示命名模板，合同模式默认已配置好：{合同类型}_{签订年份}_{序号}_{乙方}。"
              "如需调整，可直接修改模板文字，或点「恢复默认」还原。")
    para(doc, "「处理选项」中保持默认即可，其中两项建议保留勾选：")
    bullet(doc, "自动跳过明显不是合同的 PDF（如绩效报告、通知），避免误改名。", "合同类型校验：")
    bullet(doc, "遇到扫描件时调用系统本地 OCR 与手写识别，提高手写字段识别率。", "扫描件 OCR：")

    h2(doc, "第 3 步：① 扫描并预览")
    para(doc, "点「① 扫描并预览」，软件逐份读取，只在表格里生成改名方案，"
              "此时不会改动任何文件。表格各列含义如下：")
    make_table(doc,
               ["列名", "含义"],
               [["原文件名", "当前 PDF 的实际文件名"],
                ["新文件名", "即将改成的名字"],
                ["状态", "成功 / 缺失 / 待核对 等，绿色为正常"],
                ["缺失字段", "哪些信息没识别出来，需人工看一眼"],
                ["备注", "软件对该文件的判断说明"]],
               widths=[3.4, 12.8])
    para(doc, "扫描耗时与合同页数、是否扫描件有关。纯电子版合同每份约 1～2 秒；"
              "扫描件（需要图像识别）每份约 5～15 秒，请耐心等待进度走完。")

    h2(doc, "第 4 步：② 确认执行")
    para(doc, "核对预览表无误后，点「② 确认执行（改名 + 导出 Excel）」，"
              "软件会弹出二次确认，确认后开始原地改名，并在同一文件夹生成《信息汇总.xlsx》。")
    para(doc, "处理完成后会提示成功份数。若有文件因加密、损坏或不是合同被跳过，"
              "Excel 中会标红并注明「需人工处理」，原件保持原名不变。")

    # ===== 4 结果说明 =====
    h1(doc, "四、结果怎么核对")
    h2(doc, "4.1 汇总表结构")
    para(doc, "《信息汇总.xlsx》每个工作表一行对应一份合同，包含：序号、原文件名、新文件名、"
              "合同类型、乙方、身份证号、开始日期、结束日期、签订日期、用工部门、状态、备注等列。")
    para(doc, "文字列里显示的是软件识别结果。识别可靠的字段直接显示文字，方便直接抄用；"
              "识别不可靠的字段，软件会在该单元格内嵌入一小块合同原图，供人工比对。")

    h2(doc, "4.2 单元格里的截图是什么")
    para(doc, "手写体（姓名、身份证号、日期、部门）机器识别难免有偏差。为保证不把错的信息当对的用，"
              "软件采取「识别不准就贴原图」的做法：")
    bullet(doc, "该字段识别可靠 → 单元格只显示文字，表格干净、便于复制。", "准的：")
    bullet(doc, "该字段识别不到或存疑 → 单元格内嵌入该处的手写原图（已裁到关键字附近，尺寸经过压缩），"
                "人工一眼就能核对并手工填入。", "不准的：")
    bullet(doc, "手写姓名若串了相邻栏的字（例如手写「张光明」被认成「张气明性」），"
                "程序会判定该值不可信并贴原图；识别可靠的字段不贴图，表格保持干净。", "串字：")
    para(doc, "因此，看到单元格里是一小块图片时，说明这一项需要人工确认；"
              "这属于软件的正常设计，不是出错。")

    h2(doc, "4.3 人工补录与撤销")
    bullet(doc, "在预览表里双击某一行，可手动填写/修正该份合同的字段，改完再执行，"
                "新值会同时用于改名和 Excel。", "补录：")
    bullet(doc, "点「撤销」可把上一次改名的文件全部还原为原名（Excel 保留，可自行删除）。", "撤销：")
    bullet(doc, "若执行时 Excel 正被打开导致写入失败，关闭 Excel 后点「恢复」，"
                "软件会从日志把结果补写进表格，无需重新扫描。", "恢复：")

    # ===== 5 常见问题 =====
    h1(doc, "五、常见问题")
    faq = [
        ("双击没反应 / 启动很慢？",
         "单文件程序首次启动需解压，等待 10～30 秒。若超过 1 分钟仍无窗口，"
         "请确认是 64 位 Windows，并检查杀毒软件是否拦截（加入白名单后重试）。"),
        ("提示「Windows 已保护你的电脑」？",
         "点「更多信息」→「仍要运行」。软件未做数字签名，属正常提示。"),
        ("某些合同没被改名？",
         "多数是被「合同类型校验」判为非合同（如绩效评价、通知），或文件加密/损坏。"
         "Excel 中会标注原因，可人工处理或关闭校验后重扫。"),
        ("乙方识别成了公司名或一句话？",
         "手写姓名识别难度最高。软件已限定只取 2～4 字纯姓名，识别不出时宁可不填并在 Excel 贴图，"
         "不会硬填错误内容。此时请按截图手工补录。"),
        ("用工部门识别为空？",
         "部门为七选一：办公室、财务室、交通、物业、服务一部、服务二部、资产。"
         "软件重点看合同「第二条第二点」；整页没认出时，会把手写区单独裁出放大、"
         "二值化再认一次，仍认不出才贴图供核对。"),
        ("日期识别错位（开始 / 结束 / 签订相同）？",
         "扫描件的年月日常被识别混淆。请以 Excel 中截图为准手工修正，或在预览表双击补录。"),
        ("Excel 打不开或提示被占用？",
         "先关闭已打开的《信息汇总.xlsx》再执行；若已失败，关闭后点「恢复」即可补写。"),
        ("处理速度慢？",
         "扫描件需要逐页做图像识别，属正常。可只处理前几页（软件默认只读关键页与末页签章页），"
         "或把电子版合同与扫描件分两批处理。"),
        ("会不会把原合同内容改坏？",
         "不会。软件只读取 PDF 内容并修改文件名，不修改 PDF 内部内容；改名可一键撤销。"),
        ("合同内容会上传到网上吗？",
         "不会。全部识别在本机离线完成，软件不发起任何网络请求。"),
    ]
    for q, a in faq:
        h2(doc, "Q：" + q)
        para(doc, a)

    # ===== 6 注意事项 =====
    h1(doc, "六、使用注意事项")
    bullet(doc, "首次使用前，请先备份一份合同原件（复制到另一个文件夹），确认效果后再批量处理正式文件。",
           "先备份：")
    bullet(doc, "软件只处理所选文件夹「直属」的 PDF，不会递归子文件夹，也不会动 Word、图片等其它文件。",
           "处理范围：")
    bullet(doc, "同一文件夹重复执行会继续累加序号，不会覆盖已有文件；如需重新编号，请先把旧汇总表移走。",
           "序号规则：")
    bullet(doc, "汇总表固定生成在 PDF 所在目录，文件名为《信息汇总.xlsx》，多次执行默认追加行。",
           "输出位置：")
    bullet(doc, "涉密合同请在涉密或内网电脑上使用；软件虽不联网，仍建议遵守单位保密规定。",
           "保密要求：")

    # ===== 7 附录 =====
    h1(doc, "七、附录：一页速查")
    make_table(doc,
               ["操作", "按钮 / 位置", "说明"],
               [["选文件夹", "1. 选择要处理的 PDF → 浏览…", "只处理该文件夹直属 PDF"],
                ["选单份文件", "切换到「选择 PDF 文件（同目录）」", "需同一文件夹"],
                ["生成方案", "① 扫描并预览", "不改文件，仅预览"],
                ["正式改名", "② 确认执行", "改名并生成信息汇总.xlsx"],
                ["改错还原", "撤销", "还原上次改名"],
                ["补写表格", "恢复", "Excel 被占用后补写"],
                ["修正字段", "预览表双击某行", "手工补录后重新执行"],
                ["切换模式", "菜单「模式」", "论文 / 合同"]],
               widths=[3.2, 6.8, 6.2])

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run("— 本手册完 —"), size=10, color=GREY)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print("OK ->", OUT)


if __name__ == "__main__":
    build()
