# -*- coding: utf-8 -*-
"""生成带中文文本层的测试 PDF（PyMuPDF 内置 china-s 字体，无需外部字体文件）。

V1.1.2：新增 3 份「财政支出绩效评价报告」合成负样本。用户已把真实报告样本
从 samples/user/ 删除，若不做等价替代，test_negative.py 的负样本用例会静默 skip。
合成样本可复现、无隐私、与真实报告版式一致（项目单位/委托单位/评价机构/成文年月）。

用法（项目根目录执行）：.venv/Scripts/python.exe tests/make_samples.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pymupdf  # noqa: E402

OUT = ROOT / "tests" / "samples"


def write_pdf(name: str, lines: list[str], encrypt: bool = False,
              image_only: bool = False) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    doc = pymupdf.open()
    page = doc.new_page()
    if image_only:
        # 只画图形，不写任何文字 → 无文本层，模拟扫描件
        page.draw_rect(pymupdf.Rect(60, 60, 500, 400), color=(0.2, 0.4, 0.8), width=3)
        page.draw_line(pymupdf.Point(60, 200), pymupdf.Point(500, 200), color=(0.7, 0.3, 0.3))
    else:
        y = 72
        for i, line in enumerate(lines):
            size = 15 if i == 0 else 11.5
            page.insert_text((60, y), line, fontname="china-s", fontsize=size)
            y += 26 if i == 0 else 22
    if encrypt:
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                 owner_pw="owner123", user_pw="secret123", garbage=3)
    else:
        doc.save(path, garbage=3)
    doc.close()
    return path


def main() -> None:
    samples = [
        ("01_标准论文.pdf", [
            "基于深度学习的中文文本分类研究",
            "作者：张三、李四、王五",
            "期刊：计算机学报",
            "发表年份：2023",
            "摘要：本文研究中文文本分类方法。",
        ]),
        ("02_标准合同.pdf", [
            "劳动合同",
            "合同类型：劳动合同",
            "乙方：张三",
            "身份证号：110101199001011234",
            "合同期限：2023年5月30日至2026年5月29日",
            "签订日期：2023年5月30日",
            "用工部门：办公室",
        ]),
        ("04_加密合同.pdf", [
            "保密协议", "合同名称：技术服务保密协议",
            "甲方：甲公司", "供方：乙公司", "签订日期：2022-11-08",
        ], True),
        ("05_字段缺失合同.pdf", [
            "劳务合同",
            "合同类型：劳务合同",
            "乙方：李四",
            "根据双方协商一致，订立本劳务合同。",
            "乙方应当按照约定完成劳务工作。",
        ]),
        ("06_非法字符长名称.pdf", [
            "合同类型：A/B*C:D?E\"F<G>H|I 超长名称" + "测试" * 60,
            "乙方：王五",
            "身份证号：110101199001011234",
            "签订日期：2021/7/9",
            "用工部门：交通",
        ]),
        ("07_重名A.pdf", [
            "劳动合同",
            "合同类型：劳动合同", "乙方：同一人", "签订日期：2020-01-01",
        ]),
        ("08_重名B.pdf", [
            "劳动合同",
            "合同类型：劳动合同", "乙方：同一人", "签订日期：2020-01-01",
        ]),
        ("09_全角标签独占行.pdf", [
            "劳动合同",
            "合同类型：", "劳动合同",
            "乙方：", "赵六",
            "身份证号：", "110101199001011234",
            "签订日期：", "2023年12月18日",
            "用工部门：", "财务室",
        ]),
        ("10_备用论文.pdf", [
            "题   目：多模态知识图谱构建方法综述",
            "作   者：赵六, 钱七",
            "刊   名：软件学报",
            "出版年份：2021年",
        ]),
        # V1.1.2：等价替代已删除的 3 份真实绩效评价报告，保持负样本回归覆盖
        # （机构与项目名均为虚构，与真实单位无关）
        ("11_绩效评价报告A.pdf", [
            "某市财政支出绩效评价报告",
            "项目名称：2017年度某区养老机构消防改造项目",
            "项目单位：某区社区服务中心",
            "主管单位：某区民政局",
            "委托单位：某区财政局",
            "评价机构：某某税务师事务所",
            "评价类型：事后评价",
            "评价方式：现场评价与资料核查相结合",
            "成文年月：二〇一八年十一月",
            "一、项目基本情况",
            "本项目为财政资金安排的养老机构消防设施改造工程。",
            "二、绩效目标与评价指标",
            "评价指标体系包含产出、效益与满意度三类。",
            "三、评价结论",
            "经评价，项目总体绩效良好，预算执行率符合预期。",
        ]),
        ("12_绩效评价报告B.pdf", [
            "某市财政支出",
            "绩效评价报告",
            "项目名称：2018年某公路日常养护项目",
            "项目单位：某市公路管理部门",
            "主管部门：某市交通主管部门",
            "委托部门：某市交通主管部门",
            "评价机构：某某税务师事务所有限公司",
            "评价时段：2018年1月至2018年12月",
            "成文年月：二〇一九年六月",
            "一、评价工作方案",
            "评价方法采用比较法与因素分析法。",
            "二、自评报告摘要",
            "项目单位已提交绩效自评报告及相关台账。",
            "三、评价结论",
            "绩效跟踪结果显示，主要指标完成情况良好。",
        ]),
        ("13_绩效评价工作方案.pdf", [
            "某区社区智能安防系统项目绩效评价报告",
            "预算单位：某区平安街道办事处、",
            "某区向阳街道办事处、某区望湖街道办事处",
            "委托单位：某区财政局",
            "评价机构：某某会计师事务所有限公司",
            "评价方式：第三方独立评价",
            "评价方法：成本效益分析法",
            "评价指标：覆盖率、在线率、响应时效",
            "2023年7月",
            "一、绩效目标",
            "提升社区智能安防系统运行维护水平。",
            "二、评价结论与建议",
            "建议进一步加强运维考核与资金绩效管理。",
        ]),
    ]
    for item in samples:
        name, lines = item[0], item[1]
        enc = len(item) > 2 and item[2]
        write_pdf(name, lines, encrypt=bool(enc))
        print("created", name)

    write_pdf("03_扫描件.pdf", [], image_only=True)
    print("created 03_扫描件.pdf")
    probe = OUT / "_cjk_probe.pdf"
    if probe.exists():
        probe.unlink()
    print("total:", len(list(OUT.glob("*.pdf"))), "PDF files")


if __name__ == "__main__":
    main()
