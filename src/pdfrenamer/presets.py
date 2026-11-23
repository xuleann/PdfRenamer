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
        "name": "合同类型",
        # V1.2.0：劳动合同 / 劳务合同，枚举字段
        "keywords": ["合同类型", "合同类别", "合同性质", "用工形式", "合同名称"],
        "regex": r"(?:合同类型|合同类别|合同性质|用工形式)[ \t]*[:：][ \t]*([^\r\n]{2,20})",
        "enabled": True, "required": True, "type": "enum", "max_len": 20,
        "choices": ["劳动合同", "劳务合同"],
    },
    {
        "name": "乙方",
        # V1.2.0：乙方是自然人（员工姓名）。type=person_name：手写姓名识别不出时
        # 「宁缺毋滥」——绝不误取正文句子或甲方单位名，宁可标缺失交人工补录。
        "keywords": ["乙方（签字）", "乙方(签字)", "乙方签字", "乙方签名", "乙方", "劳动者", "受雇人"],
        "regex": r"(?:乙\s*方|劳动者|受雇人)\s*(?:[（(][^）)\r\n]{0,10}[）)])?[ \t]*[:：][ \t]*([^\r\n]{2,20})",
        "enabled": True, "required": True, "type": "person_name", "max_len": 20,
    },
    {
        "name": "身份证号",
        # V1.2.0：18 位身份证号，常为手写
        "keywords": ["身份证号", "身份证号码", "公民身份号码", "身份证编号", "身份证"],
        "regex": r"(?:身份证号|身份证号码|公民身份号码|身份证编号|身份证)[ \t]*[:：][ \t]*([0-9OolI]{15,18}[0-9XxOolI]?)",
        "enabled": True, "required": True, "type": "idcard", "max_len": 18,
    },
    {
        "name": "开始日期",
        # V1.2.0：合同期限起点，常为手写
        "keywords": ["合同期限", "合同起止日期", "开始日期", "起始日期", "合同期限自", "合同期限：自"],
        "regex": r"(?:开始日期|起始日期|合同期限)[^\r\n]{0,20}((?:19|20)\d{2})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})",
        "enabled": True, "required": True, "type": "date", "max_len": 16,
    },
    {
        "name": "结束日期",
        # V1.2.0：合同期限终点，常为手写
        "keywords": ["结束日期", "截止日期", "合同期限至", "终止日期", "合同期限：至"],
        "regex": r"(?:结束日期|截止日期|终止日期|合同期限至)[^\r\n]{0,20}((?:19|20)\d{2})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})",
        "enabled": True, "required": True, "type": "date", "max_len": 16,
    },
    {
        "name": "签订日期",
        # V1.2.0：签订日期，常为手写；年份从它派生
        "keywords": ["签订日期", "签署日期", "签约日期", "签订时间", "签署时间", "合同日期", "签约时间",
                     "订立日期", "合同订立时间"],
        "regex": r"(?:签订日期|签署日期|签约日期|签订时间|签署时间|合同日期|签约时间|订立日期|合同订立时间)[ \t]*[:：][ \t]*([^\r\n]{2,60})",
        "enabled": True, "required": True, "type": "date", "max_len": 16,
    },
    {
        "name": "用工部门",
        # V1.2.0：办公室/财务室/交通/物业/服务一部/服务二部/资产，7 选 1
        "keywords": ["用工部门", "工作部门", "所属部门", "部门", "用工单位"],
        "regex": r"(?:用工部门|工作部门|所属部门|部门|用工单位)[ \t]*[:：][ \t]*([^\r\n]{2,20})",
        "enabled": True, "required": True, "type": "enum", "max_len": 20,
        "choices": ["办公室", "财务室", "交通", "物业", "服务一部", "服务二部", "资产"],
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
        "description": "劳动合同/劳务合同：类型、乙方、身份证、期限、签订日期、用工部门",
        "template": "{合同类型}_{签订年份}_{序号}_{乙方}",
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
    # V1.2.0：RapidOCR 手写体识别补强（可选依赖，纯离线）
    "scan_rapid_enabled": True,          # 是否启用手写体二次识别
    # V1.3.0：手写字段局部截图嵌入 Excel（乙方/部门/日期/身份证，压缩小图）
    "capture_field_images": True,
    # V1.2.0：全局序号计数器（{序号} 占位符，从 1 开始持续累加不重置）
    "sequence_counter": 1,
    "modes": deepcopy(MODES),
}


def default_mode_config(mode: str) -> dict:
    return deepcopy(MODES[mode])
