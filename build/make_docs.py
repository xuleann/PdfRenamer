# -*- coding: utf-8 -*-
"""生成《需求分析说明书》与《PRD产品需求文档》的排版 HTML（供 html-to-doc 转换）。

内容直接读取 src/pdfrenamer/presets.py 的出厂预设，保证文档与实现一致。
用法：从项目根目录执行 .venv/Scripts/python.exe build/make_docs.py
"""
from __future__ import annotations

import html
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfrenamer.presets import DEFAULT_CONFIG, MODES  # noqa: E402

OUT = ROOT / "output" / "html"
OUT.mkdir(parents=True, exist_ok=True)
TODAY = date.today().strftime("%Y-%m-%d")
VERSION = "1.1.2"

CSS = """
<style>
@page { size: A4; margin: 2.2cm 2.0cm 2.0cm 2.0cm; }
body { font-family: "Microsoft YaHei", "SimSun", sans-serif; font-size: 10.5pt;
       color: #222831; line-height: 1.75; }
h1 { font-size: 20pt; color: #1f4e79; border-bottom: 2px solid #1f4e79;
     padding-bottom: 6px; margin-top: 26px; margin-bottom: 14px; }
h2 { font-size: 14pt; color: #23527c; margin-top: 20px; margin-bottom: 8px; }
h3 { font-size: 11.5pt; color: #34495e; margin-top: 14px; margin-bottom: 6px; }
p { margin: 6px 0; text-align: justify; }
ul, ol { margin: 6px 0 10px 0; padding-left: 22px; }
li { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 16px 0; font-size: 9pt; }
th { background-color: #dce6f1; color: #1f4e79; border: 1px solid #9fb6cd;
     padding: 5px 6px; text-align: left; font-weight: bold; }
td { border: 1px solid #c3d0de; padding: 5px 6px; vertical-align: top; }
tr:nth-child(even) td { background-color: #f6f9fc; }
code { font-family: Consolas, monospace; background: #f2f4f7; padding: 1px 3px;
       font-size: 9pt; color: #a0392b; }
.cover { text-align: center; padding-top: 150px; page-break-after: always; }
.cover .kicker { font-size: 11pt; color: #6b7a8f; letter-spacing: 3px; }
.cover h1 { font-size: 30pt; border: none; color: #1f4e79; margin: 26px 0 10px 0; }
.cover .sub { font-size: 14pt; color: #4a5b6d; margin-bottom: 60px; }
.cover .meta { font-size: 10.5pt; color: #334; line-height: 2.1; }
.note { background: #eef4fb; border-left: 4px solid #1f4e79; padding: 8px 12px;
        margin: 10px 0; }
.warn { background: #fff4e5; border-left: 4px solid #d68910; padding: 8px 12px;
        margin: 10px 0; }
.doc-toc { background: #f7f9fc; border: 1px solid #d6e0ec; padding: 12px 20px;
           margin: 14px 0; }
.small { font-size: 9pt; color: #5a6472; }
</style>
"""


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def cover(title: str, subtitle: str, rows: list[tuple[str, str]]) -> str:
    meta = "".join(f"<div>{esc(k)}：{esc(v)}</div>" for k, v in rows)
    return (f'<div class="cover"><div class="kicker">LOCAL DESKTOP TOOL · 内部自用</div>'
            f"<h1>{esc(title)}</h1><div class=\"sub\">{esc(subtitle)}</div>"
            f'<div class="meta">{meta}</div></div>')


def doc(title: str, body: str) -> str:
    return ("<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{esc(title)}</title>{CSS}</head><body>{body}</body></html>")


def toc(items: list[str]) -> str:
    return '<div class="doc-toc"><strong>目录</strong><ol>' + "".join(
        f"<li>{esc(x)}</li>" for x in items) + "</ol></div>"


def table(headers: list[str], rows: list[list]) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def field_rows() -> list[list]:
    rows = []
    for mode, mc in MODES.items():
        for f in mc["fields"]:
            rows.append([
                mc["label"], f["name"], f["type"], "、".join(f["keywords"]),
                f["regex"] or "（空，仅用关键词）",
                f.get("source", "") or "—",
                "是" if f["required"] else "否", str(f["max_len"]),
                mc["template"],
            ])
    return rows


FIELD_HEADERS = ["模式", "字段名", "类型", "标签关键词", "默认正则", "结构化来源",
                 "必填", "文件名长度", "所属模板"]


def build_analysis() -> str:
    b = []
    b.append(cover("需求分析说明书", "PdfRenamer — 本地 PDF 信息提取与批量更名软件", [
        ("文档版本", f"V{VERSION}"), ("编制日期", TODAY),
        ("产品形态", "Windows 本地桌面软件（绿色 exe + 安装向导）"),
        ("适用读者", "需求方、开发、测试、评审"),
        ("文档状态", "评审稿"),
    ]))
    b.append("<h1>1. 引言</h1>")
    b.append("<h2>1.1 编写目的</h2>")
    b.append("<p>本文档对「利用 AI 编程实现 PDF 批量信息提取、按规则重命名、并汇总到 Excel」的原始需求进行结构化分析，"
             "明确建设目标、功能边界、非功能约束、环境依赖与风险，作为后续 PRD、开发实现与验收测试的基准。</p>")
    b.append("<h2>1.2 术语与缩略语</h2>")
    b.append(table(["术语", "说明"], [
        ["PDF 文本层", "PDF 内嵌的可复制文字。软件只读既有文本层，不做 OCR、不做图像识别。"],
        ["标签关键词", "如「甲方（盖章）：」中的「甲方」，用于定位并取其后同行的值。"],
        ["正则表达式", "用户为每个字段配置的更精确的取值规则，引擎优先取第 1 个捕获组。"],
        ["结构化来源", "论文字段可选来源：从 PDF 元数据（title/author/subject/creationDate）与首页版式（页眉期刊行、跨行标题、作者区、Abstract 分界）确定性解析题目/作者/期刊/年份；仍是纯规则，不含模型推理。"],
        ["模式", "论文 / 合同两套独立的字段集、命名模板与 Excel 工作表。"],
        ["dry-run 预览", "只生成改名计划、不动文件；用户确认后才执行。"],
        ["还原日志 plan.json", "记录 原路径→新路径 的本地 JSON，用于一键撤销与崩溃对账。"],
        ["扫描件", "无文本层的图片型 PDF，本期不改名并在 Excel 标记「需人工处理」。"],
    ]))
    b.append("<h2>1.3 需求来源与确认结论</h2>")
    b.append("<p>原始需求共 8 条（其中第 4、6 条关于 Excel 汇总重复，第 6 条补充「Excel 必须放在所选目录下」）。"
             "经与需求方确认，形成以下不可变更决策：</p>")
    b.append(table(["决策项", "结论"], [
        ["交付位置", "在本地新建全 ASCII 项目目录，工程与全部成品放入其中；仓库可克隆到任意路径"],
        ["字段配置", "内置预设 + 界面可新增/删除字段 + 每字段可填标签关键词与可选正则，规则持久化"],
        ["重命名", "模板可编辑；缺失填「未知」、重名加序号、非法字符替换；原地改名 + 还原日志 + 一键撤销"],
        ["安装包", "PyInstaller 单文件绿色 exe + Inno Setup 安装向导 setup.exe，两者都交付"],
        ["文档", "《需求分析说明书.docx》+《PRD产品需求文档.docx》两份 Word"],
        ["PDF 引擎", "仅个人/内部自用 → PyMuPDF 1.26.x（AGPL，源码随项目交付）"],
        ["样例", "需求方已提供 6 篇真实英文论文 PDF 与 4 份真实合同扫描件；V1.1.0 论文校准 24/24，V1.1.1 以绩效评价报告作负样本，V1.1.2 完成扫描件 4/4 正向校准"],
        ["多选文件", "V1.1.1 界面可单独选择一个或多个 PDF 文件并提取；限制同一目录，跨目录提示分批处理；Excel 仍固定输出到该目录"],
        ["界面风格", "V1.1.1 现代浅色纯 ttk（clam + 主蓝 + 卡片 + 斑马纹 + 状态栏），不引入第三方 GUI 依赖；V1.1.2 文案级精简、窗口高度下调"],
        ["Excel 类型标签", "V1.1.1 表头末尾追加「PDF 类型」列并配色，A 列「模式」保留兼容旧表；旧表无损升列回填历史行"],
        ["扫描件", "V1.1.2：调用 Windows 10/11 操作系统内置离线 OCR（Windows.Media.Ocr）把无文本层扫描件转为本地文本再走规则链；缺中文语言包时优雅降级为「保持原名 + Excel 标需人工处理」；识别不全可在预览表双击人工补录"],
        ["OCR 边界", "仅使用操作系统随附的传统 OCR 组件；不含大模型 / 云端 API / 推理库，零联网、零新增 Python 依赖；物理层异常优先于合同类型闸门"],
        ["Excel 已存在", "按模式分 sheet 追加（论文汇总 / 合同汇总），旧数据不丢"],
        ["软件形态", "本地 Windows 桌面软件，不是微信小程序；与「本地 + 可执行安装包」要求一致"],
    ]))

    b.append("<h1>2. 背景与痛点</h1>")
    b.append("<p>论文与合同资料常以「扫描件_001.pdf」「合同 (3).pdf」这类无语义文件名堆积在文件夹中，"
             "人工逐份打开、复制字段、手工改名、再录入台账，重复且易错。现有方案要么依赖云端大模型（数据出域、需联网、结果不稳定），"
             "要么是纯手工。本项目的定位是<strong>完全本地、确定性、可复现、可撤销</strong>的轻量工具。</p>")
    b.append("<h1>3. 建设目标</h1>")
    b.append("<ol><li>选一个文件夹即可批量处理其中直属 PDF，无需逐份操作。</li>"
             "<li>两种可选模式（论文 / 合同）对应不同字段集与命名规则，字段可在界面自由增删改。</li>"
             "<li>按用户可编辑的模板批量重命名，并在所选目录生成「信息汇总.xlsx」台账。</li>"
             "<li>软件纯本地运行，内部不嵌任何 AI / 大模型 / 云端 API；提供绿色 exe 与带安装向导的 setup.exe。</li></ol>")
    b.append("<h1>4. 用户角色与典型场景</h1>")
    b.append(table(["角色", "场景", "操作步骤", "期望结果"], [
        ["科研/教务人员", "整理一批已下载的期刊论文", "选论文模式 → 选文件夹 → 扫描预览 → 确认执行",
         "文件名为「题目_第一作者_年份.pdf」，论文汇总表可检索"],
        ["行政/采购/法务", "归档一批已签合同", "选合同模式 → 核对甲方/供方/金额 → 确认执行",
         "文件名为「合同名称_甲方_供方_时间.pdf」，合同汇总表含金额"],
        ["任一用户", "发现改名结果不理想", "点「撤销上次重命名」", "所有文件名还原，零文件丢失"],
    ]))
    b.append("<h1>5. 功能需求</h1>")
    b.append(table(["编号", "功能", "说明", "优先级"], [
        ["FR-01", "模式选择", "启动时卡片式选择论文/合同；可记住选择，主窗口菜单可随时切换", "P0"],
        ["FR-02", "选择文件夹", "文件夹选择对话框，显示直属 PDF 数量；不递归子目录", "P0"],
        ["FR-03", "字段配置", "预设字段的增删改、排序、启用/必填、类型；每字段可填标签关键词、正则与结构化来源下拉；正则编译校验", "P0"],
        ["FR-04", "命名模板", "可编辑模板，{字段名} 占位符；未知占位符红字提示；可一键恢复默认", "P0"],
        ["FR-05", "本地文本提取", "PyMuPDF 读前 N 页文本层 + 首页未重排原文 + PDF 元数据；NFKC 归一化；乱码/无文本层/加密判定", "P0"],
        ["FR-06", "规则取值", "结构化来源 → 正则 → 关键词回退 → 按类型启发式 → 缺失；记录 ok/fallback/heuristic/missing；空白范本占位判缺失", "P0"],
        ["FR-07", "值清洗", "日期、金额、公司名、多作者、年份归一化；去控制字符与盖章装饰", "P0"],
        ["FR-08", "dry-run 预览", "扫描后先出预览表（原文件名/新文件名/状态/缺失字段/备注），不改动任何文件", "P0"],
        ["FR-09", "批量重命名", "确认后原地改名；非法字符替换、长度上限、大小写不敏感重名加序号", "P0"],
        ["FR-10", "Excel 汇总", "所选目录下固定生成「信息汇总.xlsx」；按模式分 sheet 追加；动态表头、冻结首行、自动筛选、状态着色；V1.1.1 末尾「PDF 类型」标签列与配色，旧表无损升列", "P0"],
        ["FR-11", "一键撤销", "基于 plan.json 逆序还原；冲突/缺失只跳过，绝不删除文件；断点续做", "P0"],
        ["FR-12", "配置持久化", "%APPDATA%/PdfRenamer/config.json；版本迁移 + 原子写；重启自动载入", "P1"],
        ["FR-13", "日志与进度", "运行日志区 + 进度条；后台线程处理，界面不卡死", "P1"],
        ["FR-14", "结果恢复", "每文件增量写 rows.jsonl；Excel 被占用时提供「恢复上次结果」", "P1"],
        ["FR-15", "打包交付", "绿色单文件 exe + 安装向导 setup.exe（可卸载、桌面快捷方式）", "P0"],
        ["FR-16", "多选 PDF 文件", "界面可单独选择一个或多个 PDF 文件并提取；同目录校验；共同父目录写回唯一 directory 锚点，撤销/重名检测/Excel 全部保持原语义", "P0"],
        ["FR-17", "合同类型闸门", "合同模式以纯规则判定是否为合同文档；非合同文档不改名、Excel/预览标记；开关与阈值可在「处理选项」配置", "P0"],
        ["FR-18", "规则通用性", "中文合同别称、中文数字/年月日期、叙述式与表头金额、跨行标签值；去掉「项目名称」误取同义词", "P1"],
        ["FR-19", "现代浅色主题", "clam 主题 + 主蓝配色、卡片分区、Treeview 斑马纹与选中色、强调按钮、底部状态栏、窗口图标；零第三方 GUI 依赖", "P1"],
        ["FR-20", "扫描件离线 OCR", "无文本层 PDF 自动渲染前 2 页 + 末页，调用 Windows 系统内置离线 OCR 转本地文本再走既有规则链；语言包缺失/超时优雅降级；零新增 Python 依赖", "P0"],
        ["FR-21", "人工补录", "预览表双击行弹出按需创建的补录弹窗，可手动填写 5 字段并重新生成文件名、写入 Excel 与还原日志；主窗口不新增常驻控件", "P0"],
        ["FR-22", "UI 排版精简", "收敛重复说明与冗余文案、窗口高度下调适配 1366×768、完整规则收进「帮助 → 处理规则说明」；不删控件、不改变量名", "P2"],
    ]))
    b.append("<h1>6. 非功能需求</h1>")
    b.append(table(["编号", "类别", "要求"], [
        ["NFR-01", "本地性", "运行时零网络请求；不调用任何大模型、云 API、在线服务或推理库；扫描件仅调用操作系统随附的传统离线 OCR 组件；静态扫描门禁禁止 torch/onnxruntime/requests 等（25 个源文件 PASS）"],
        ["NFR-02", "隐私", "PDF 内容不离开本机；除所选目录下的 Excel 外，配置与日志只写 %APPDATA%/PdfRenamer/"],
        ["NFR-03", "兼容性", "Windows 10 22H2 及以上；中文路径与中文文件名；GUI 使用标准库 tkinter"],
        ["NFR-04", "可靠性", "改名前先落盘完整 plan；每改名成功原子更新；中途崩溃可对账并恢复结果"],
        ["NFR-05", "安全性", "任何异常路径都不删除用户文件；撤销遇冲突跳过而非覆盖"],
        ["NFR-06", "易用性", "两步式操作（扫描预览 → 确认执行）；预览中可发现误提取并取消"],
        ["NFR-07", "可维护性", "UI / 提取 / 重命名 / Excel / 配置 / 撤销 分层，可独立单测；PDF 后端可切换"],
        ["NFR-08", "可分发", "安装包可卸载、创建快捷方式；卸载保留用户配置与还原日志"],
        ["NFR-09", "性能", "单份常规合同/论文提取在百毫秒量级；批量处理有进度反馈"],
    ]))
    b.append("<h1>7. 约束与假设</h1>")
    b.append("<div class=\"warn\"><strong>关键约束：</strong>「利用 AI 编程」指开发方式；软件<strong>内部不得嵌入任何大模型 / 云端 API / 推理库</strong>。"
             "信息提取依赖 PDF 既有文本层、PDF 元数据 + 确定性版式解析 + 关键词 + 正则，结果可复现。"
             "V1.1.2 起对无文本层的扫描件，仅调用 Windows 10/11 <strong>操作系统内置的传统离线 OCR</strong>"
             "（Windows.Media.Ocr）把图片文字转为本地文本，再交给同一套规则处理；全程零联网、零新增 Python 依赖，"
             "不含模型推理。目标机缺中文 OCR 语言包时优雅降级为「保持原名 + Excel 标需人工处理」。</div>")
    b.append("<ul><li>只处理所选目录直属 *.pdf，不递归子目录（界面可配）。</li>"
             "<li>无文本层扫描件先走系统离线 OCR；OCR 失败、缺语言包、加密件与乱码件不改名并标记。</li>"
             "<li>不修改 PDF 内容，只改文件名；金额只进入 Excel，不进合同默认命名模板。</li>"
             "<li>规则命中率依赖真实版式；已用 6 篇真实论文校准（24/24）与 4 份真实合同扫描件校准（4/4 判为合同、字段 14/20），字段、正则与结构化来源均可在界面调整。</li>"
             "<li>只处理所选目录直属 *.pdf；Word（.doc/.docx）与其它格式不在本期范围。</li>"
             "<li>Excel 若正被 Excel 程序打开，保存会失败，需关闭后用「恢复上次结果」补写。</li></ul>")
    b.append("<h1>8. 运行环境与依赖</h1>")
    b.append("<div class=\"note\"><strong>解释器陷阱：</strong>若 PATH 上的 <code>python</code> 不是标准 CPython"
             "（例如某些精简内置解释器缺少 tkinter），必须显式使用 <code>py -3.13</code> 或标准 "
             "CPython 3.13 解释器，建 venv 后统一从项目根目录使用 <code>.venv/Scripts/python.exe</code>。</div>")
    b.append(table(["组件", "版本 / 说明", "用途 / 许可"], [
        ["Python", "标准 CPython 3.13（tkinter 8.6）", "运行时与 GUI / Python 许可证"],
        ["PyMuPDF", "1.26.7（必须 &lt; 2.0）", "PDF 文本层主引擎 / AGPL 3.0，源码随项目交付"],
        ["openpyxl", "3.1.5", "Excel 读写 / MIT"],
        ["pypdf / pdfplumber", "7.1.0 / 0.11.10", "可选备用 PDF 后端 / BSD、MIT"],
        ["PyInstaller", "6.22.3", "打包期 / GPLv2 with bootloader exception"],
        ["Inno Setup", "6.7.4", "安装向导构建 / 免费软件"],
        ["python-docx", "1.2.0", "仅文档生成期 / MIT"],
    ]))
    b.append("<p class=\"small\">PyMuPDF 必须锁定 1.26.x：2.x 会强制拉取 onnxruntime、numpy、pymupdf-layout 等推理库，"
             "既违反「不嵌 AI」，也会显著放大安装包。本项目已把推理库从构建环境中移除，并以 "
             "<code>tests/scan_no_ai.py</code> 作为构建门禁。</p>")
    b.append("<h1>9. 风险与应对</h1>")
    b.append(table(["风险", "影响", "应对"], [
        ["真实 PDF 版式差异导致提取不准", "字段缺失或误取值", "已用 6 篇真实英文论文 + 2 份中文合同范本校准：新增 PDF 元数据/首页版式解析层，论文命中率 24/24；空白范本占位判缺失、正文连写不误取；规则仍可在界面调整"],
        ["非合同公文被误当成合同", "生成「项目名_未知_未知_未知.pdf」类错误文件名、污染台账", "V1.1.1 合同文档类型闸门（保守得分制 + 白名单 + 阈值 + 开关）；3 份绩效评价报告作为负样本验证判 not_contract 且不改名"],
        ["闸门误杀真实合同", "合同被跳过、不改名", "强信号白名单旁路、阈值可配、界面可关闭闸门、负词表只收报告专属词、全量自造合同样例回归；真实合同到位后复核阈值"],
        ["表头新增列导致旧 Excel 被重建", "历史台账分散到备份文件", "无损升列：旧表头为新表头严格前缀时就地追加列并按 A 列「模式」回填旧行，不备份、不重建、不丢历史"],
        ["PyPI / Inno Setup 下载失败", "无法构建安装包", "镜像 → 离线 wheels → 自制 setup.exe 三级兜底"],
        ["中文 PDF 缺 ToUnicode 映射", "文本乱码", "乱码率判定 → 标记「需人工处理」，不改名"],
        ["重名覆盖", "文件丢失", "大小写不敏感去重加 _2 序号；目标已存在则跳过并记失败"],
        ["撤销时原名被占用", "覆盖他人文件", "跳过并提示，绝不覆盖、绝不删除"],
        ["Excel 被占用", "台账写入失败", "增量 rows.jsonl 兜底 + 「恢复上次结果」"],
        ["中途强杀 / 崩溃", "状态不一致", "plan.json 逐条原子更新；rows.jsonl 增量落盘"],
        ["杀软误报", "exe 被拦截", "关闭 UPX、不使用混淆；提供源码与构建脚本可自行复现"],
        ["AGPL 合规", "对外分发义务", "当前默认构建与 OCR 页面渲染均使用 PyMuPDF（AGPL 3.0）；仅内部自用且源码随项目交付。如需对外分发，需整体评估 AGPL 义务或商业许可；仅把提取后端切到 pdfplumber 不足以完全规避（OCR 渲染仍依赖 PyMuPDF）"],
    ]))
    b.append("<h1>10. 交付物清单</h1>")
    b.append("<ul><li><code>dist/PdfRenamer.exe</code>：绿色单文件可执行程序</li>"
             "<li><code>dist/PdfRenamer_setup.exe</code>：带安装向导的安装包</li>"
             "<li><code>src/</code>：完整源码；<code>config/default_config.json</code>：出厂预设</li>"
             "<li><code>build/</code>：spec、bat、Inno Setup .iss、图标生成脚本</li>"
             "<li><code>docs/</code>：本说明书与 PRD</li>"
             "<li><code>tests/</code>：样例 PDF、单元测试、UI 冒烟测试、验收用例表、合规扫描</li>"
             "<li><code>README.md</code>、<code>requirements.txt</code>、<code>wheels/</code> 离线依赖</li></ul>")
    b.append("<h1>附录 A　预设字段字典</h1>")
    b.append(table(FIELD_HEADERS, field_rows()))
    b.append("<h1>附录 B　状态枚举</h1>")
    b.append(table(["层级", "取值", "含义"], [
        ["字段", "ok", "结构化来源（PDF 元数据/首页版式）或正则命中"], ["字段", "fallback", "关键词回退命中"],
        ["字段", "heuristic", "启发式推测，建议人工复核"], ["字段", "missing", "未提取到，填「未知」"],
        ["文档", "ok / partial", "字段齐全 / 部分缺失"],
        ["文档", "no_text_layer / garbled / encrypted / error", "不改名，Excel 标「需人工处理」"],
        ["文档", "not_contract", "合同模式判定为非合同文档（绩效评价报告/工作方案等），不改名，Excel 标「非合同文档（不改名）」"],
        ["改名", "planned / done / skipped / failed / unchanged", "计划 / 已改 / 跳过 / 失败 / 名称未变"],
    ]))
    b.append("<h1>附录 C　真实样本规则校准结论（V1.1.0）</h1>")
    b.append("<p>需求方于 V1.1.0 阶段提供真实样本：<code>samples/user/</code> 下 6 篇英文期刊/会议论文 PDF"
             "（FedOM、FedProto、FedTED、mcmahan17a、pFedC、pFedKD）与 2 份中文合同范本"
             "（<code>买卖合同.doc</code>、<code>房屋租赁合同.docx</code>）。"
             "校准前用 V1.0.0 的中文标签规则测得命中率 <strong>3/24 = 12.5%</strong>，"
             "且存在关键词在正文误命中产生的垃圾值；校准后为 <strong>24/24 = 100%</strong>。</p>")
    b.append(table(["校准项", "V1.0.0 问题", "V1.1.0 处理"], [
        ["论文题目", "英文论文首页无「Title:」标签，全部缺失", "优先读 PDF 元数据 title；被生成器截断时用首页跨行标题补全"],
        ["作者", "正文误命中或缺失", "优先读元数据 author；否则解析首页标题与 Abstract 之间的作者区，过滤单位/邮箱/Member IEEE 并按姓名模式抽取"],
        ["期刊", "全部缺失", "解析 IEEE 元数据 subject「期刊名;年份;卷;期;DOI」；否则取首页期刊页眉，或从会议名/AISTATS/arXiv 推断"],
        ["发表年份", "误取参考文献年份（2020/2012/2024）", "按 subject → 页眉 → 版权/会议行 → 创建日期 → 正文首年 的确定性优先级"],
        ["合同空白范本", "「出租方(甲方)：」误取下一行「联系电话」；「年 月 日」「XXX 元」被当成有效值", "括号别名只认冒号后值；空白占位统一判缺失；正则分隔符禁止跨行；标签后必须紧跟分隔符，正文连写不取值"],
        ["配置升级", "老 config.json 会覆盖新预设", "config_version 升至 3；升级时合并出厂预设的 source 与新关键词，保留用户正则与自定义字段"],
    ]))
    b.append("<div class=\"note\"><strong>范围提示：</strong>两份中文合同为 Word 格式且为空白范本（甲方、金额、日期均为占位符）。"
             "本期按原始需求只处理目录下直属 <code>*.pdf</code>；验证时将其另存为 PDF 放入 "
             "<code>tests/samples/user_contract_pdfs/</code>，确认「合同名称」可提取、其余 4 字段正确判为缺失且无误取。"
             "如需直接处理 .doc/.docx，属于后续需求变更。</div>")
    b.append("<h1>附录 D　V1.1.1 合同模式负样本校准</h1>")
    b.append("<p>需求方在 V1.1.1 阶段新增 3 份 PDF，经逐页核对<strong>均不是合同</strong>，"
             "而是财政支出绩效评价报告 / 工作方案（本节记为<strong>报告样本 A / B / C</strong>）。封面标签为 "
             "<code>项目名称 / 项目单位 / 委托单位 / 评价机构 / 成文年月</code>，"
             "全文没有甲乙双方、签订日期、合同金额的标签-值对；旧预设把「项目名称」当作合同名称同义词，"
             "会把报告误取成封面「项目名称」的值并生成错误文件名。</p>")
    b.append(table(["改进项", "V1.1.0 问题", "V1.1.1 处理"], [
        ["文档类型闸门", "合同模式对任何 PDF 都做字段提取", "新增 contract_gate.py 纯规则得分制；判 not_contract 则纳入 SKIP，全字段缺失、不改名、Excel 标记；白名单/阈值/开关防误杀"],
        ["合同名称", "「项目名称」是同义词，报告封面必然误命中", "删除「项目名称」「标题」同义词；配置 v4 迁移时清理老配置残留"],
        ["字段覆盖", "甲方/供方不认「委托单位/中标单位」等别称；金额正则只认数字紧跟标签", "补充中文合同别称；支持「合同总金额为123.4567 万元」叙述式金额、中文数字与「年月无日」日期、跨行标签续值"],
        ["负样本回归", "无", "tests/calibrate_negative.py + tests/test_negative.py：3/3 判非合同、15/15 字段缺失、0 改名"],
    ]))
    b.append("<div class=\"note\"><strong>前提说明：</strong>「样本越多效果越好」不适用于本软件——它不嵌 AI、"
             "没有训练环节。本轮提升的是确定性规则的覆盖面与防误取能力，结果写进 "
             "<code>presets.py</code> / <code>contract_gate.py</code> 并随 exe 分发。"
             "<code>samples/user/</code> 目前仍没有真实已填写的合同 PDF，正向命中率校准留待样本到位后进行。</div>")
    return "".join(b)


def build_prd() -> str:
    b = []
    b.append(cover("PRD 产品需求文档", "PdfRenamer — 需求拆解、页面规格与验收标准", [
        ("文档版本", f"V{VERSION}"), ("编制日期", TODAY),
        ("对应实现", "本项目源码与 dist/ 成品"),
        ("上游文档", f"《需求分析说明书》V{VERSION}"),
        ("文档状态", "评审稿"),
    ]))
    b.append(toc(["版本信息", "产品定位与目标", "目标用户与 JTBD", "范围界定", "信息架构与流程",
                  "双模式差异", "页面与控件规格", "字段规格", "规则引擎", "数据规格",
                  "异常与边界", "非功能与合规", "验收标准", "发布与打包", "后续迭代"]))
    b.append("<h1>1. 版本信息</h1>")
    b.append(table(["版本", "日期", "变更", "作者"], [
        ["V1.0.0", TODAY, "首版：论文 / 合同双模式、字段可配置、批量更名、Excel 汇总、一键撤销、可执行安装包", "产品开发"],
        ["V1.1.0", TODAY, "真实样本规则校准：新增论文 PDF 元数据 / 首页版式结构化来源（字段可配置）、中文合同范本防误取、配置升级迁移；论文字段命中率 12.5% → 100%", "产品开发"],
        ["V1.1.1", TODAY, "合同文档类型闸门 + 3 份绩效评价报告负样本、界面多选 PDF（同目录）、现代浅色纯 ttk 主题与状态栏、Excel「PDF 类型」列与无损升列、中文合同规则通用性、config v4 迁移", "产品开发"],
        [f"V{VERSION}", TODAY, "真实合同扫描件用 Windows 系统内置离线 OCR 识别（4/4 判为合同）、预览表双击人工补录、UI 文案级排版精简、规则与金额/日期噪声防护、config v5 链式迁移、扫描件正向校准 14/20 字段命中", "产品开发"],
    ]))
    b.append("<h1>2. 产品定位与目标</h1>")
    b.append("<p>一款<strong>纯本地、零 AI、零联网</strong>的 Windows 桌面工具：把一堆命名混乱的论文/合同 PDF，"
             "按可配置规则提取关键信息、批量改成语义化文件名，并在同一目录自动产出 Excel 台账。</p>")
    b.append("<p><strong>成功指标：</strong>标准版式样例的 9 个预设字段全部正确提取；"
             "6 篇真实英文论文 24 个字段命中率 100%（V1.1.0 校准）；"
             "3 份非合同公文 100% 被拦截且不改名（V1.1.1）；"
             "4 份真实合同扫描件 100% 被系统离线 OCR 识别为合同并正常改名（V1.1.2 校准，字段 14/20）；"
             "批量 100 份无需人工逐份干预；任何误操作都能一键完整撤销；安装包可安装、可卸载。</p>")
    b.append("<h1>3. 目标用户与 JTBD</h1>")
    b.append(table(["用户", "当我……", "我想要……", "以便……"], [
        ["科研/教务人员", "下载了一批论文 PDF", "一次性按题目/作者/年份改名并出汇总表", "建立可检索的文献库"],
        ["行政/采购/法务", "收到一批已签合同扫描/电子件", "提取甲方、供方、金额、日期并归档", "做台账与对账，不再手工录入"],
        ["任意用户", "发现规则没配好", "先预览、再确认、必要时撤销", "不破坏原始资料"],
    ]))
    b.append("<h1>4. 范围界定</h1>")
    b.append(table(["In Scope（本期）", "Out of Scope（本期不做）"], [
        ["论文 / 合同两种模式；预设字段 + 自定义字段；结构化来源 + 关键词 + 正则",
         "任何 AI 大模型 / 云端 API / 在线服务 / 推理库（torch、onnxruntime 等）"],
        ["PDF 既有文本层提取；无文本层扫描件调用 Windows 系统内置离线 OCR；人工补录兜底",
         "第三方 OCR 引擎 / 模型文件 / 手写体与印章识别 / 全页无差别 OCR"],
        ["可编辑命名模板；dry-run 预览；原地改名；一键撤销", "修改 PDF 内容、合并/拆分 PDF"],
        ["文件夹模式处理所选目录直属 PDF；文件模式处理单独选择的 1~N 个 PDF（须同一目录）；Excel 汇总到该目录", "递归子目录、跨目录多选（后续迭代）"],
        ["绿色 exe + 安装向导", "macOS / Linux 版本、自动更新服务"],
    ]))
    b.append("<h1>5. 信息架构与全局流程</h1>")
    b.append("<p>启动 → 模式选择（可记住）→ 主窗口（选文件夹 / 字段配置 / 命名模板 / 处理选项）→ "
             "① 扫描并预览 → ② 确认执行 → 写 plan.json → 批量改名 → 写 Excel → 完成；"
             "任意时刻可「撤销上次重命名」或「恢复上次结果」。</p>")
    b.append(table(["步骤", "动作", "系统行为", "输出"], [
        ["S1", "选择模式", "载入该模式预设字段、模板、Excel sheet 名", "模式上下文"],
        ["S2", "选择文件夹", "列出直属 PDF 数量（不递归）", "文件清单"],
        ["S3", "配置字段/模板", "实时校验正则与占位符；配置写 config.json", "字段配置"],
        ["S4", "① 扫描并预览", "后台线程逐份提取 → 生成改名计划（不碰文件）", "预览表 + 日志"],
        ["S5", "② 确认执行", "二次确认 → 写 plan → 改名 → 逐行写 Excel", "新文件名 + 信息汇总.xlsx"],
        ["S6", "撤销 / 恢复", "逆序还原 / 从 rows.jsonl 补写", "还原结果"],
    ]))
    b.append("<h3>状态机</h3>")
    b.append("<p><code>空闲 → 扫描中 → 已预览 → 执行中 → 完成</code>；"
             "<code>已预览</code> 可回到 <code>空闲</code>（切换模式/换目录/改配置即清空预览）；"
             "<code>执行中</code> 禁止重复触发；任一异常回到 <code>空闲</code> 并保留日志与 plan。</p>")
    b.append("<h1>6. 双模式差异</h1>")
    b.append(table(["维度", "论文模式", "合同模式"], [
        ["预设字段", "论文题目、作者、期刊、发表年份", "合同名称、甲方、供方、时间、金额"],
        ["默认模板", esc(MODES["paper"]["template"]), esc(MODES["contract"]["template"])],
        ["Excel sheet", "论文汇总", "合同汇总"],
        ["值处理特点", "多作者取第一作者入文件名；年份归一化为 4 位", "日期 YYYY-MM-DD；金额去千分位/万元换算；公司名去盖章装饰"],
    ]))
    b.append("<h1>7. 页面与控件规格</h1>")
    b.append("<h2>7.1 启动模式选择（模态卡片）</h2>")
    b.append("<p>两张并排卡片显示模式名称、说明、默认模板；按钮进入对应模式；复选框「记住本次选择，下次启动直接进入」；"
             "取消则退出。已记住时跳过本页，可从「模式」菜单切换。</p>")
    b.append("<h2>7.2 主窗口（1180×760，可缩放）</h2>")
    b.append("<p class=\"small\">V1.1.2 排版精简：合并重复说明、缩短按钮与单选文案、窗口高度 820→760、"
             "最小尺寸 1040×680、预览表 9→8 行、日志 7→5 行，完整规则说明收进「帮助 → 处理规则说明」。"
             "不删控件、不改变量名、不引入折叠面板，1366×768 屏上状态栏不再被挤出可视区。</p>")
    b.append(table(["区域", "控件", "行为"], [
        ["1 选择要处理的 PDF", "输入方式单选（文件夹 / 选择 PDF 文件（同目录））+ 只读/可编辑路径框 + 浏览或添加按钮 + 清空 + PDF 计数标签", "文件夹态列直属 PDF；文件态可多选，跨目录弹窗提示分批处理，同目录时把共同父目录写回唯一 directory 锚点；Excel 仍输出到该目录"],
        ["2 字段配置", "Treeview（字段名/关键词/正则/类型/结构化来源/启用）+ 编辑表单（含结构化来源下拉）+ 新增/应用/删除/上移/下移/恢复预设",
         "关键词逗号分隔；正则即时编译校验；结构化来源可选「不使用 / 论文题目 / 作者 / 期刊 / 年份」，优先级高于关键词与正则；论文专用说明在合同模式隐藏"],
        ["2 重命名规则", "模板输入框 + 可用字段提示（仅异常时显示）+ 警告标签 + 恢复默认", "未知占位符/无占位符红字提示"],
        ["2 处理选项", "PDF 后端、Excel 策略、读取前 N 页、缺失值、文件名长度上限、合同类型校验开关 + 阈值 Spinbox；两行短提示", "写入 config.json；闸门开关与阈值仅合同模式生效；OCR 参数由 config v5 提供，界面不新增常驻控件"],
        ["3 扫描预览", "Treeview（原文件名/新文件名/改名状态/提取状态/缺失字段/备注）+ 斑马纹与选中色；双击行弹出补录弹窗", "跳过行红色、启发式行橙色；补录后重新生成文件名并写 Excel/还原日志；此步不动文件"],
        ["4 操作区", "① 扫描并预览 / ② 确认执行（Accent 强调按钮）/ 撤销 / 恢复 + 进度条", "执行前二次确认并再次应用人工补录；忙碌时按钮禁用；执行目录取自扫描快照 output_dir"],
        ["5 运行日志", "带滚动条的只读文本框（等宽字体，5 行）", "时间戳日志；线程消息经队列回灌，界面不卡死"],
        ["6 状态栏", "左侧状态文本 + 右侧版本号", "显示 模式｜输入方式｜运行状态；v1.1.2"],
        ["菜单", "模式（单选 + 切换模式…）、帮助（处理规则说明 / 打开配置目录 / 关于）", "切换前保存当前模式配置；规则说明集中在此，不占主窗口空间"],
    ]))
    b.append("<h1>8. 字段规格</h1>")
    b.append("<p>下表与代码 <code>src/pdfrenamer/presets.py</code> 完全一致，字段名即模板占位符名。</p>")
    b.append(table(FIELD_HEADERS, field_rows()))
    b.append("<p class=\"small\">类型说明：text 纯文本；list 多值（文件名取第一作者）；year 提取 19xx/20xx；"
             "company 去盖章装饰与地址电话噪声；date 归一化 YYYY-MM-DD；money 去千分位、万元换算为元。</p>")
    b.append("<h1>9. 规则引擎</h1>")
    b.append("<h2>9.1 取值优先级矩阵</h2>")
    b.append(table(["优先级", "策略", "命中条件", "字段状态"], [
        ["-2", "扫描件离线 OCR（V1.1.2）", "doc.status = no_text_layer 时，渲染前 2 页 + 末页调 Windows 系统内置离线 OCR 补文；失败保持原状态（详见 9.7）", "文档状态 ok / 仍为 no_text_layer"],
        ["-1", "文档类型闸门（合同模式）", "仅在物理层状态为 ok / partial 时判定 PDF 是否为合同文档；不通过则全部字段缺失、不改名（详见 9.2）", "文档状态 not_contract"],
        ["0", "结构化来源", "字段声明 source 时，从 PDF 元数据 / 首页版式解析题目、作者、期刊、年份；真实英文论文首页无标签，主要用于此场景", "ok（元数据/版式）或 heuristic（推测）"],
        ["1", "正则", "字段 regex 编译后 re.search 命中，取第 1 个捕获组；值若像另一个标签或空白占位则丢弃", "ok"],
        ["2", "关键词", "按关键词顺序查找：同行取值，容忍（盖章）装饰与 :/：；标签后必须紧跟分隔符；仅短标签行可向下取下一非空行", "fallback"],
        ["3", "启发式", "按类型兜底：年份抓 19xx/20xx、日期抓年月日、金额抓 ¥数字、合同名抓含「合同」的短行、题目抓首页长中文行", "heuristic（建议复核）"],
        ["4", "缺失", "以上均未命中，或值被判为空白占位（年 月 日 / ____ / XXX 元）", "missing → 填「未知」"],
    ]))
    b.append("<h2>9.2 合同文档类型闸门（V1.1.1）</h2>")
    b.append("<p>真实样本中出现过财政支出绩效评价报告被当成合同：封面写着「项目名称：…」，"
             "旧预设把「项目名称」列为合同名称同义词，于是生成了错误文件名。"
             "<code>src/pdfrenamer/contract_gate.py</code> 用<strong>确定性关键词与正则</strong>做文档级判定，"
             "只在合同模式、且物理层状态正常（非扫描件/乱码/加密）时执行；判定依据是首页未重排原文与正文文本层，"
             "<strong>不采用 PDF 元数据 title</strong>（实测样本的 title 与首页标题不一致）。</p>")
    b.append(table(["类别", "判据", "分值"], [
        ["正向", "首页独立大标题含「合同/协议/契约/合约」且无冒号", "+3"],
        ["正向", "甲乙双方等标签对（必须带冒号，避免「后，甲方支付」正文碎片）", "+2（单个 +1）"],
        ["正向", "签订/签署/盖章/合同编号等标记；合同名称/合同金额等专有标签", "+1 ~ +2 / +1"],
        ["白名单", "合同编号：/签订地点：/甲乙双方盖章 且无报告专属负信号", "直接放行"],
        ["负向", "绩效评价/财政支出/评价报告/工作方案 等标题", "-3"],
        ["负向", "评价机构/委托单位/预算单位/成文年月 等报告专属标签；仅有「项目名称：」", "各 -2"],
    ]))
    b.append("<p class=\"small\">默认阈值 2，得分 ≥ 阈值判为合同；不通过则 <code>doc_status = not_contract</code>，"
             "纳入 SKIP_DOC_STATUSES，复用既有「全字段缺失 → 不改名 → Excel 标记」链路。"
             "界面「处理选项」提供开关与阈值 Spinbox；真实合同样本到位后可复核阈值。"
             "判定逻辑写在引擎里而非配置里，因此升级 exe 后对老 config 也立即生效。</p>")
    b.append("<h2>9.3 论文结构化来源（V1.1.0）</h2>")
    b.append("<p>真实论文首页的典型结构是「期刊页眉 → 跨行标题 → 作者区（上标数字、Member, IEEE）→ 单位/邮箱 → Abstract」，"
             "不存在「Title: xxx」标签。引擎在读取文本时额外保留<strong>首页未重排原文</strong>与 <strong>PDF 元数据字典</strong>，"
             "由 <code>src/pdfrenamer/structured.py</code> 以固定优先级做纯规则解析：</p>")
    b.append(table(["字段", "取值优先级（从高到低）"], [
        ["题目", "元数据 title → 用元数据标题对齐首页行数并拼接（可补全被截断到 80 字符的 title）→ 无元数据时按首页版式推测"],
        ["作者", "元数据 author → 首页标题区与 Abstract 之间的作者区（过滤单位/邮箱/Member IEEE，按英文姓名模式抽取）"],
        ["期刊", "元数据 subject 首段（IEEE 格式「期刊名;年份;卷;期;DOI」）→ 元数据 subject 会议全称 → 首页 IEEE 页眉 → 正文会议缩写 / arXiv → 元数据 keywords"],
        ["年份", "subject 中的 ;YYYY; → 页眉月份年份 → 版权/会议行（Copyright 2022 / AISTATS 2017）→ creationDate → 正文首个年份"],
    ]))
    b.append("<p class=\"small\">以上全部为字符串匹配与正则，不含模型、不含网络；解析结果写入字段 note 标明来源，"
             "推测类结果标记为 heuristic 供人工复核。字段的「结构化来源」可在界面下拉框里关闭或改配。</p>")
    b.append("<h2>9.4 文本预处理</h2>")
    b.append("<p>默认读前 3 页（可配前 N 页 + 后 M 页）；正文用 <code>get_text(sort=True)</code>，"
             "另单独保留首页 <code>get_text(\"text\")</code> 未重排原文与 PDF metadata；逐行 NFKC 归一化，"
             "去零宽字符与控制字符，折叠全角/不间断空格；有效字符 &lt; 20 判为扫描件；"
             "替换符/私用区占比 &gt; 15% 判为乱码。</p>")
    b.append("<h2>9.5 文件名合法化</h2>")
    b.append("<p>NFKC → <code>\\ / : * ? \" &lt; &gt; |</code> 替换为下划线 → 去首尾点空格 → "
             "Windows 设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）加前缀 → basename 上限 120 → "
             "与目录内其它文件大小写不敏感比对，冲突追加 _2、_3。</p>")
    b.append("<h2>9.6 跳过规则</h2>")
    b.append("<ul><li>文档状态为 no_text_layer（含 OCR 降级后）/ garbled / encrypted / error → 不改名，Excel 标红「需人工处理」。</li>"
             "<li>合同模式判定 not_contract → 不改名，Excel/预览标「非合同文档」。</li>"
             "<li>模板中所有占位字段均缺失 → 不改名，避免产生「未知_未知_未知.pdf」。</li>"
             "<li>新旧名称一致 → 标记 unchanged。</li>"
             "<li>人工补录后重新生成计划：补录值使字段不再缺失，文档状态改为 partial / ok 从而脱离 SKIP 集合，正常参与改名。</li></ul>")
    b.append("<h2>9.7 扫描件离线 OCR 与人工补录（V1.1.2）</h2>")
    b.append("<p>真实合同样本中有 4 份是 CamScanner / Sharp 输出的<strong>纯图片扫描 PDF</strong>："
             "全文文本层 0 字符、文件名是哈希、元数据只有扫描时间，任何关键词/正则都取不到字段。"
             "<code>src/pdfrenamer/extractor/ocr_winrt.py</code> 补了一条确定性的本地补文通道：</p>")
    b.append(table(["环节", "实现", "约束"], [
        ["页面渲染", "PyMuPDF 以 dpi 200 / 最长边 ≤2400 渲染前 2 页 + 末页为临时 PNG（签章页常含日期）", "临时文件写在系统 TEMP 的 TemporaryDirectory，用完即删；绝不写用户所选目录"],
        ["文字识别", "powershell.exe -STA -EncodedCommand 调 WinRT Windows.Media.Ocr，AsTask 泛型桥接等待异步，识别结果按行以 UTF-8→Base64 回传", "仅用操作系统随附 DLL 与本地中文语言数据（zh-Hans-CN）；零联网、零新增 Python 依赖、CREATE_NO_WINDOW 不弹控制台"],
        ["文本归一化", "删除汉字之间的伪空格（「甲 方 ：」→「甲方:」），保留英文单词间空格；按页分段并保留首页 head_text；NFKC 清洗", "OCR 会在汉字间插空格，不归一化则既有正则全部失效"],
        ["回灌规则链", "构造新 TextDoc(DOC_OK, text, head_text, note)，metadata 强制清空；原样进入闸门与 source→正则→关键词→启发式", "扫描件 metadata.title 是「扫描全能王 2024-…」，绝不能被当成题目或签订日期"],
        ["降级", "语言包缺失 / 引擎创建失败 / 超时 / 渲染异常 → 返回空文本，保持 no_text_layer", "物理层异常优先于合同闸门；闸门条件改为显式 (ok, partial) 白名单，避免把扫描件误标成「非合同文档」"],
        ["人工补录", "预览表双击行 → 按需创建 Toplevel 填写 5 字段 → 重新调用 renamer.plan 生成新文件名，写入 Excel 与 plan.json 并标「人工补录」", "不持久化；清空预览时一并清除；主窗口不新增常驻控件；撤销链路零改动"],
    ]))
    b.append("<p class=\"small\"><strong>已知限制：</strong>OCR 默认只读前 2 页 + 末页以控制耗时（每份约 1.5–2.3 秒）；"
             "金额与签订日期常在正文中间页，实测字段命中 14/20 = 70%，其余靠人工补录。"
             "OCR 错字（如公司名首字被误识）与「支付合同金额的 25%」这类分期比例已加噪声防护，"
             "但启发式命中仍建议在预览里复核后执行。</p>")
    b.append("<h1>10. 数据规格</h1>")
    b.append(table(["数据", "位置", "结构与用途"], [
        ["config.json", "%APPDATA%/PdfRenamer/", "config_version=5；两套模式字段/模板/结构化来源、后端、Excel 策略、上次目录与模式、last_input_mode、合同闸门开关与阈值、7 个 scan_ocr_* 参数（开关/页数/末页/dpi/最长边/超时/语言）；原子写。v3→v4→v5 链式迁移：v4 删「项目名称」黑名单同义词、仅替换等于 v3 出厂值的 regex、追加新别名；v5 纯 setdefault 注入 OCR 键，不重复执行 v4 逻辑，用户正则/模板/自定义字段不丢，迁移前按旧版本号自动备份"],
        ["plan_*.json", "%APPDATA%/PdfRenamer/plans/", "run_id、directory、mode、created_at、undone、records(src/dst/status)；改名前全量落盘，逐条原子更新"],
        ["rows_*.jsonl", "%APPDATA%/PdfRenamer/rows/", "每处理一个 PDF 追加一行 {mode,row}，用于 Excel 被占用/崩溃后的结果恢复"],
        ["信息汇总.xlsx", "用户所选目录（唯一写入该目录的文件；多选 PDF 时为这些文件的共同父目录）", "表头：模式|原文件名|新文件名|&lt;动态字段列&gt;|提取状态|缺失字段|处理时间|备注|PDF 类型；「PDF 类型」逐行写 论文/合同 并加类型配色，A 列「模式」保留兼容旧表；旧表按严格前缀做无损升列并按 A 列回填历史行，不备份重建；冻结首行、自动筛选、状态着色"],
    ]))
    b.append("<h1>11. 异常与边界</h1>")
    b.append(table(["场景", "系统行为", "用户可感知提示"], [
        ["目录不存在 / 无 PDF", "不启动扫描", "弹窗提示 + 日志"],
        ["正则编译失败", "保存字段时拒绝", "弹窗指出错误位置"],
        ["模板含未知占位符", "允许扫描但红字警告", "扫描前二次确认"],
        ["PDF 加密", "跳过改名", "预览/Excel 标「需人工处理」"],
        ["两份 PDF 提取结果相同", "第二份追加 _2", "预览可见不同新名"],
        ["目标文件名已被占用", "该条记 failed，不影响其它文件", "日志 + 完成汇总里的失败数"],
        ["Excel 正被打开", "捕获 PermissionError", "提示关闭后用「恢复上次结果」补写"],
        ["撤销时原文件名被占用", "跳过该条，绝不覆盖", "撤销结果明细列出跳过原因"],
        ["中途强杀", "plan.json 与 rows.jsonl 已落盘", "重启后可撤销 / 恢复结果"],
    ]))
    b.append("<h1>12. 非功能与合规</h1>")
    b.append("<ul><li><strong>零 AI 证明方式：</strong><code>tests/scan_no_ai.py</code> 静态扫描 src/ 与 requirements.txt，"
             "禁止 torch/transformers/onnxruntime/openai/requests/httpx/socket 等导入；构建门禁强制执行。</li>"
             "<li><strong>零联网：</strong>运行时代码不含任何 HTTP 客户端；仅 PDF 读取、文件改名与本地 Excel 写入。</li>"
             "<li><strong>可卸载：</strong>Inno Setup 生成卸载项；卸载不删除 %APPDATA%/PdfRenamer/。</li>"
             "<li><strong>许可证：</strong>PyMuPDF 1.26.7 为 AGPL 3.0，当前默认构建与 OCR 页面渲染均依赖它；"
             "本项目仅内部自用且源码随项目交付。如需对外分发，需整体评估 AGPL 义务或商业许可——"
             "仅把提取后端切到 pdfplumber 不足以完全规避（OCR 渲染仍依赖 PyMuPDF）。</li></ul>")
    b.append("<h1>13. 验收标准</h1>")
    cases = [
        "启动后可选择论文/合同两种模式，且可记住选择",
        "自定义字段 + 正则重启软件后仍在（配置持久化）",
        "论文 4 个预设字段从标准论文样例中正确提取",
        "合同「甲方（盖章）」+ 金额 + 签订日期归一化正确",
        "正则未命中时自动回退到关键词取值",
        "缺失字段填「未知」并在 Excel 标浅黄",
        "非法字符、超长名称、重名、大小写重名均被正确处理",
        "扫描件（无文本层）不改名且 Excel 标红「需人工处理」",
        "加密 PDF 不改名并标记",
        "Excel 固定生成在所选目录，含冻结首行与自动筛选",
        "已存在 Excel 时按模式分 sheet 追加，旧数据不丢",
        "一键撤销后所有原文件名完整恢复，零文件丢失",
        "撤销冲突时不覆盖、不删除任何文件",
        "中途崩溃后可用「恢复上次结果」补写 Excel",
        "tests/scan_no_ai.py 通过，运行时零外网请求",
        "dist/PdfRenamer.exe --selftest 返回 PASS",
        "setup.exe 可完成向导安装与卸载",
        "所有产物位于项目目录内，原始需求文件仅读取未改动",
        "6 篇真实英文论文的 24 个字段命中率 ≥ 95%（实测 24/24 = 100%）",
        "2 份中文空白合同范本：合同名称可提取，甲方/供方/时间/金额判为缺失且无误取正文",
        "V1.0.0 的 config.json 升级到 v3 后，论文字段自动获得结构化来源且用户自定义字段不丢",
        "3 份绩效评价报告全部判 not_contract、15/15 合同字段缺失、0 改名，且不误取「项目名称」",
        "自造合同样例（02/05/07/08/09）闸门不误杀，5 个字段照常提取，原 26 项单测不退化",
        "中文数字日期「二〇一八年十一月」→ 2018-11；叙述式金额「合同总金额为123.4567 万元」→ 1234567元",
        "跨行标签值合并生效，且「出租方(甲方)：」空白范本仍返回空",
        "多选 PDF（同目录）：选 2 个只处理 2 个，Excel 仍在该目录，原地改名与撤销正常",
        "多选 PDF（跨目录）：弹「请按目录分批处理」，不产生任何改名或 Excel 文件",
        "文件夹模式默认路径零回归（ui_smoke.py 全过），cfg.last_dir 链路不变",
        "Excel A1 仍为「模式」，末列为「PDF 类型」并带类型配色；旧表无损升列、无备份重建、历史行保留",
        "config v3→v4：生成 config_v3_backup.json，删「项目名称」、追加新别名，用户正则/模板/自定义字段不丢",
        "现代浅色主题生效（clam / 斑马纹 / 状态栏 / 窗口图标），--selftest 与 ui_smoke 均不报错",
        "版本 1.1.1 → 1.1.2 全位置一致，V1.1.0 / V1.1.1 历史叙述保留；no-AI 门禁 PASS（25 个源文件）",
        "4 份真实合同扫描件：4/4 OCR 出文本、4/4 判为合同、4/4 正常改名、0 垃圾文件名",
        "扫描件字段命中 14/20 = 70%（金额/日期多在正文中间页，属已知限制，双击预览行可补录）",
        "OCR 关闭时退回 V1.1.1 行为：no_text_layer、5 字段缺失、skipped 不改名",
        "OCR 语言包缺失 / 超时 / 渲染异常时优雅降级，且 no_text_layer 优先于合同闸门（不误标 not_contract）",
        "临时 PNG 只落系统 TEMP 且用完即删，samples/user/ 10 个样本 SHA256 + 大小 + 时间戳前后一致",
        "人工补录：双击预览行填 5 字段后 skipped → planned，值按类型归一化，Excel/plan.json 标「人工补录」，撤销可还原",
        "清空预览后人工补录值一并清除；无补录时 _apply_overrides 是 no-op",
        "UI 文案级精简：窗口 1180×760 / 最小 1040×680、日志 5 行、预览 8 行、帮助菜单含「处理规则说明」",
        "ui_smoke / test_ui_files 3 项 / 补录 6 项 / 全量单测 69 项全绿，0 skip（负样本改由合成 PDF 覆盖）",
        "config v4→v5：用户显式关闭的 scan_ocr_enabled 不被覆盖，v3→v5 链式迁移两种迁移逻辑均生效",
        "金额噪声防护：「支付合同金额的 25%」不取为合同总金额，继续匹配到页面上的真实合同价格",
        "日期噪声防护：OCR 错字「戔为炀一」等无年份数字的值判为缺失，不进文件名",
        "requirements.txt / PdfRenamer.spec / scan_no_ai.py 零改动，零新增 Python 依赖",
        "setup.exe 静默安装/卸载与安装版 --selftest 通过，SHA256 与绿色版一致",
    ]
    b.append(table(["#", "验收用例", "结果"], [[str(i + 1), c, "通过"] for i, c in enumerate(cases)]))
    b.append("<p class=\"small\">结果列以 <code>tests/acceptance_cases.md</code> 的实测记录为准。</p>")
    b.append("<h1>14. 发布与打包</h1>")
    b.append("<p><code>build_venv.bat</code> → <code>build_exe.bat</code>（scan_no_ai 门禁 → 图标 → 导出默认配置 → PyInstaller onefile）"
             " → <code>make_setup.bat</code>（Inno Setup 6.7.4 + 简体中文语言包）。产物："
             "<code>dist/PdfRenamer.exe</code> 与 <code>dist/PdfRenamer_setup.exe</code>。"
             "spec 关闭 UPX、关闭控制台、隐藏导入显式声明、构建路径全 ASCII。</p>")
    b.append("<h1>15. 后续迭代 Backlog</h1>")
    b.append(table(["优先级", "条目", "说明"], [
        ["P1", "扫描件 OCR 覆盖更多页", "V1.1.2 已用 Windows 系统内置离线 OCR 覆盖前 2 页 + 末页；后续可按需扫描全部页以提高正文中间页的金额/日期命中率（需权衡耗时）"],
        ["P1", "规则测试器", "选中单个 PDF 即时预览每个字段的命中来源与正则匹配片段"],
        ["P2", "递归子目录", "支持跨子目录批量处理，Excel 增加相对路径列"],
        ["P2", "CSV / 多格式导出", "除 xlsx 外导出 csv，便于导入其它系统"],
        ["P2", "更多模式", "发票、简历、招标文件等预设模板"],
        ["P3", "PDF 后端自动回退", "主后端乱码时自动尝试备用后端并标注来源"],
        ["P2", "支持 Word 合同（.doc/.docx）", "本期只处理 *.pdf；真实样本中含 2 份 Word 空白范本，如需直接处理需扩展文档解析层"],
        ["P2", "跨目录多选", "按文件所在目录自动分组，每组各出一份 Excel 并各自可撤销"],
        ["P2", "已选文件列表", "界面可视化列出/移除已选中的单个 PDF（V1.1.1 用计数 + 清空代替）"],
        ["P1", "真实合同正向校准（V1.1.2 已交付）", "4 份真实合同扫描件已完成 4/4 判为合同与 14/20 字段命中；后续可补更多版式复核闸门阈值与 OCR 错字率"],
    ]))
    b.append("<h1>附录 A　真实样本校准验证记录（V1.1.0）</h1>")
    b.append(table(["样本", "版式特征", "校准后结果"], [
        ["FedOM、FedOMF.pdf（IEEE IoT J. 2025）", "元数据 subject 含期刊/年份；首页标题 2 行 + 作者 3 行，无 author 元数据", "题目/作者/期刊/年份 4/4"],
        ["FedProto.pdf（AAAI-22）", "元数据含完整 title/author/subject(AAAI-22)；首页无 IEEE 页眉", "4/4；年份由 Copyright 2022 行判定（正文首个年份是引用 2017，已避免）"],
        ["FedTED.pdf（IEEE TNNLS 2025）", "subject 含期刊/年份；首页页眉 + 2 行标题 + 单行 7 位作者", "4/4"],
        ["mcmahan17a.pdf（AISTATS 2017）", "无 title/author/subject；首页 2 行标题 + 每人一行作者；AISTATS 在首页页脚", "4/4；题目/作者由首页版式推测并标 heuristic"],
        ["pFedC.pdf（IEEE TMC 2025）", "元数据 title 被截断到 80 字符；标题 3 行；作者带 Member, IEEE", "4/4；题目由首页完整标题补全"],
        ["pFedKD.pdf（IEEE IoT J. 2025）", "元数据 title 被截断；标题 4 行；作者 5 行", "4/4；题目由首页完整标题补全"],
        ["买卖合同 / 房屋租赁合同（转 PDF 的空白范本）", "甲方(买方): / 出租方(甲方): 后全为待填项；正文大量「甲方…」连写", "合同名称正确；甲方/供方/时间/金额均判缺失，无误取「联系电话」「公司住所地」「开具收据」等正文"],
    ]))
    b.append("<p>校准脚本：<code>tests/calibrate.py</code>（输出 <code>output/calibration_before.json</code> / "
             "<code>calibration_after.json</code>）；回归用例：<code>tests/test_calibration.py</code>。"
             "基线 3/24 = 12.5% → 校准后 24/24 = 100%，且 V1.0.0 的 15 项核心测试与 UI 全链路回归仍全部通过。</p>")
    b.append("<h1>附录 B　V1.1.1 合同负样本与功能验证</h1>")
    b.append(table(["验证项", "样本 / 场景", "结果"], [
        ["非合同文档拦截", "报告样本 A（绩效跟踪结果报告）", "not_contract｜5 字段缺失｜skipped 不改名"],
        ["非合同文档拦截", "报告样本 B（财政支出绩效评价报告）", "not_contract｜5 字段缺失｜skipped 不改名"],
        ["非合同文档拦截", "报告样本 C（社区项目绩效评价报告）", "not_contract｜5 字段缺失｜skipped 不改名"],
        ["不误杀真实合同", "tests/samples 下 02/05/07/08/09 与 --selftest 自造合同", "闸门判通过，字段照常提取"],
        ["多选 PDF 同目录", "tests/test_ui_files.py：选 2 个同目录文件", "只处理 2 个、Excel 在该目录、撤销恢复"],
        ["多选 PDF 跨目录", "tests/test_ui_files.py：两个不同目录各 1 个", "弹窗拒绝、无改名、无 Excel"],
        ["Excel 类型列", "新建表 / v1.1.0 旧表", "末列「PDF 类型」+ 配色；旧表无损升列并回填，无备份重建"],
        ["配置迁移", "v3 老 config（含「项目名称」、v3 regex、用户自定义字段）", "黑名单清理、新别名追加、用户资产保留、备份生成"],
    ]))
    b.append("<p>负样本脚本 <code>tests/calibrate_negative.py</code>（报告 <code>output/calibration_negative.json</code>）"
             "实测：<strong>3/3 判非合同、15/15 字段缺失、0 改名</strong>；论文校准保持 24/24 = 100%；"
             "V1.1.1 全量单元测试 44 项、no-AI 门禁、UI 冒烟与多选 UI 测试全部通过。"
             "V1.1.2 起这 3 份真实报告已由用户移除，等价负样本改由 <code>tests/make_samples.py</code> 合成，"
             "回归覆盖不依赖用户样本。样本只读使用，未改动 <code>samples/user/</code> 内任何文件。</p>")
    b.append("<h1>附录 C　V1.1.2 真实合同扫描件校准与验证</h1>")
    b.append(table(["样本", "版式特征", "OCR 与提取结果"], [
        ["扫描样本 A（5 页）", "CamScanner；首页「合同书」+ 项目名称/甲方/乙方；末页手写日期与双公章", "847 字符｜合同名称/甲方/供方 3/3 命中｜日期、金额在正文中间页未取到"],
        ["扫描样本 B（10 页）", "CamScanner；竖排标题「采购合同」；正文含签订日期", "1511 字符｜合同名称/甲方/供方/年份 4/5 命中｜金额在正文中间页未取到"],
        ["扫描样本 C（4 页）", "Sharp 二值黑白；首页即含合同价格与甲乙双方", "2274 字符｜4/5 命中（含金额）；「25%」分期比例被噪声防护拦下"],
        ["扫描样本 D（25 页）", "CamScanner，含 2 页横向；首页合同编号 + 采购人/投标人；末页含签署时间", "2119 字符｜合同名称/甲方/供方 3/5 命中；OCR 对个别字存在错识"],
    ]))
    b.append("<p>校准脚本 <code>tests/calibrate_scanned.py</code>（期望值 <code>tests/scanned_expect.json</code>，"
             "由人工逐页目视核对抄录；报告 <code>output/calibration_scanned.json</code>）实测："
             "<strong>4/4 OCR 出文本、4/4 判为合同、4/4 正常改名、字段命中 14/20 = 70%</strong>。"
             "未命中的 6 项集中在正文中间页的金额与签订日期——默认只 OCR 前 2 页 + 末页以控制耗时，"
             "属已知限制，可在预览表双击该行手动补录后重新生成文件名。</p>")
    b.append("<p><strong>工程验证：</strong>V1.1.2 全量单元测试 <strong>69 项全绿、0 skip</strong>；"
             "no-AI 门禁扫描 25 个源文件 PASS；论文校准 24/24 不退化；负样本 3/3 + 15/15 + 0 改名；"
             "UI 冒烟、多选 UI 3/3、人工补录 6/6 全部通过；<code>--selftest</code> PASS；"
             "静默安装/卸载 ExitCode 均为 0。10 个真实样本 SHA256 + 大小 + 时间戳前后一致，"
             "原始需求文件仅读取未改动。</p>")
    return "".join(b)


def main() -> None:
    p1 = OUT / "需求分析说明书.html"
    p2 = OUT / "PRD产品需求文档.html"
    p1.write_text(doc("需求分析说明书", build_analysis()), encoding="utf-8")
    p2.write_text(doc("PRD产品需求文档", build_prd()), encoding="utf-8")
    print("HTML ->", p1)
    print("HTML ->", p2)


if __name__ == "__main__":
    main()
