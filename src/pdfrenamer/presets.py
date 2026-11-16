# -*- coding: utf-8 -*-
"""出厂预设：论文 / 合同两套字段、关键词、正则与命名模板。

用户可在界面里增删改字段；改动写入 %APPDATA%/PdfRenamer/config.json。
"""
from __future__ import annotations

from copy import deepcopy

MODE_PAPER = "paper"
MODE_CONTRACT = "contract"

PAPER_FIELDS = [
    {
        "name": "论文题目",
        # 真实英文论文首页没有「Title:」标签，优先用 PDF 元数据 + 首页标题行解析
        "keywords": ["论文题目", "文章题目", "题名", "题目", "标题", "Title", "Article Title"],
        "regex": r"(?:论文题目|文章题目|题\s*名|题\s*目|标\s*题|Title)[ \t]*[:：][ \t]*([^\r\n]{2,150})",
        "enabled": True, "required": True, "type": "text", "max_len": 80,
        "source": "paper_title",
    },
    {
        "name": "作者",
        "keywords": ["作者", "著者", "作者姓名", "Authors", "Author"],
        "regex": r"(?:作\s*者|著\s*者|Authors?|作者姓名)[ \t]*[:：][ \t]*([^\r\n]{1,150})",
        "enabled": True, "required": True, "type": "list", "max_len": 40,
        "source": "paper_authors",
    },
    {
        "name": "期刊",
        "keywords": ["期刊", "刊名", "发表于", "来源期刊", "会议名称", "Journal", "Source", "Conference"],
        "regex": r"(?:期\s*刊|刊\s*名|发表于|来源期刊|会议名称|Journal|Source|Conference)[ \t]*[:：][ \t]*([^\r\n]{1,100})",
        "enabled": True, "required": False, "type": "text", "max_len": 50,
        "source": "paper_venue",
    },
    {
        "name": "发表年份",
        "keywords": ["发表年份", "出版年份", "年份", "发表日期", "出版日期", "Year", "Published"],
        "regex": r"(?:发表年份|出版年份|年\s*份|发表日期|出版日期|Year|Published)\D{0,12}((?:19|20)\d{2})",
        "enabled": True, "required": True, "type": "year", "max_len": 4,
        "source": "paper_year",
    },
]

CONTRACT_FIELDS = [
    {
        "name": "合同名称",
        # V1.1.1：删掉「项目名称」「标题」——绩效评价报告封面也用这两个标签，
        # 旧规则会把「项目名称：2017 年度…改造项目」误当成合同名称。
        "keywords": ["合同名称", "合同标题", "协议名称", "协议书名称", "契约名称", "合同全称"],
        "regex": r"(?:合同名称|合同标题|协议名称|协议书名称|契约名称|合同全称)[ \t]*[:：][ \t]*([^\r\n]{2,150})",
        "enabled": True, "required": True, "type": "text", "max_len": 80,
    },
    {
        "name": "甲方",
        "keywords": ["甲方（盖章）", "甲方(盖章)", "甲方", "需方", "买方", "委托方", "采购方",
                     "出租方", "发包人", "买受人", "定作人",
                     # V1.1.1 中文合同常见别称（放末尾，优先级低于「甲方」）
                     "采购单位", "建设单位", "招标人", "甲方单位", "买受方", "定作方", "委托单位"],
        "regex": r"(?:甲\s*方|需\s*方|买\s*方|委托方|采购方|出租方|发包人)\s*(?:[（(][^）)\r\n]{0,20}[）)])?[ \t]*[:：][ \t]*([^\r\n]{2,100})",
        "enabled": True, "required": True, "type": "company", "max_len": 60,
    },
    {
        "name": "供方",
        "keywords": ["供方（盖章）", "供方(盖章)", "供方", "乙方", "供应商", "卖方", "承包人", "供货方",
                     "承租方", "出卖人", "承揽人",
                     # V1.1.1
                     "中标单位", "成交供应商", "中标人", "承接单位", "服务方", "受托方", "乙方单位", "供应方"],
        "regex": r"(?:供\s*方|乙\s*方|供应商|卖\s*方|承包人|供货方|承租方|出卖人)\s*(?:[（(][^）)\r\n]{0,20}[）)])?[ \t]*[:：][ \t]*([^\r\n]{2,100})",
        "enabled": True, "required": True, "type": "company", "max_len": 60,
    },
    {
        "name": "时间",
        # 不放泛化的「日期/时间」，避免误命中「交货日期」「质保时间」等非签约时间
        "keywords": ["签订日期", "签署日期", "签约日期", "签订时间", "签署时间", "合同日期", "签约时间",
                     "订立日期", "合同订立时间"],
        "regex": r"(?:签订日期|签署日期|签约日期|签订时间|签署时间|合同日期|签约时间|订立日期|合同订立时间)[ \t]*[:：][ \t]*([^\r\n]{2,60})",
        "enabled": True, "required": True, "type": "date", "max_len": 16,
    },
    {
        "name": "金额",
        "keywords": ["合同金额", "合同总价", "总金额", "合同价款", "价款", "金额", "合计"],
        # V1.1.1：支持「合同总金额为123.4567 万元」「人民币 XXX 元」等叙述式写法；
        # 捕获组强制以数字开头（XXX 元不匹配），且所有空白限定 [ \t] 不跨行。
        "regex": r"(?:合同总金额|合同金额|合同总价|总金额|合同价款|价\s*款|金\s*额|合\s*计)"
                 r"[^\r\n0-9]{0,24}?[¥￥]?[ \t]*"
                 r"([0-9][0-9,]*(?:\.[0-9]+)?[ \t]*(?:万元|万|元人民币|元|人民币)?)",
        "enabled": True, "required": False, "type": "money", "max_len": 40,
    },
]

MODES: dict[str, dict] = {
    MODE_PAPER: {
        "label": "论文",
        "icon": "📄",
        "description": "论文 / 期刊文献：题目、作者、期刊、发表年份",
        "template": "{论文题目}_{作者}_{发表年份}",
        "sheet": "论文汇总",
        "fields": PAPER_FIELDS,
    },
    MODE_CONTRACT: {
        "label": "合同",
        "icon": "📃",
        "description": "商务合同：名称、甲方、供方、时间、金额",
        "template": "{合同名称}_{甲方}_{供方}_{时间}",
        "sheet": "合同汇总",
        "fields": CONTRACT_FIELDS,
    },
}

DEFAULT_CONFIG: dict = {
    "config_version": 5,
    "backend": "pymupdf",
    "first_pages": 3,
    "last_pages": 0,
    "missing_value": "未知",
    "require_preview": True,
    "remember_mode": True,
    "last_mode": "",
    "last_dir": "",
    "excel_strategy": "append",   # append / backup / overwrite
    "max_filename_len": 120,
    # V1.1.1：合同文档类型闸门（可在界面「处理选项」关闭）
    "contract_type_gate": True,
    "contract_gate_threshold": 2,
    # 输入方式：folder=整个文件夹 / files=单独选择 PDF 文件（须同一目录）
    "last_input_mode": "folder",
    # V1.1.2：扫描件使用操作系统内置离线 OCR（零新增 Python 依赖、零联网）。
    # 目标机缺中文 OCR 语言包时自动降级为「保持原名 + Excel 标记需人工处理」。
    "scan_ocr_enabled": True,
    "scan_ocr_max_pages": 2,             # 前 N 页，clamp [1,3]
    "scan_ocr_include_last_page": True,  # 末页（签章页）也识别
    "scan_ocr_dpi": 200,                 # clamp [72,300]
    "scan_ocr_max_side": 2400,           # 必须 < OcrEngine.MaxImageDimension
    "scan_ocr_timeout": 60,              # 单文件总超时（秒），clamp [10,180]
    "scan_ocr_lang": "auto",             # auto / zh-Hans-CN …
    "modes": deepcopy(MODES),
}


def default_mode_config(mode: str) -> dict:
    return deepcopy(MODES[mode])
