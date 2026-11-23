# -*- coding: utf-8 -*-
"""确定性文本清洗与归一化规则（无 AI、无网络、无第三方依赖）。"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_ILLEGAL = r'[\\/:*?"<>|\r\n\t]'
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
_WS = re.compile(r"[ \t\u00a0\u3000]+")
_DECORATION = re.compile(r"[（(]\s*(?:盖章|签字|签章|公章|签名|盖章签字)\s*[）)]")
_COMPANY_NOISE = re.compile(
    r"(?:法定代表人|法人代表|联系人|联系电话|电话|地址|开户行|账号|税号|统一社会信用代码|邮编|传真).*$"
)
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_AUTHOR_SPLIT = re.compile(r"[、,，;；/]|(?:\s+and\s+)", re.I)
_DATE_PATTERNS = [
    re.compile(r"((?:19|20)\d{2})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})\s*日?"),
    re.compile(r"((?:19|20)\d{2})\s*[年/\-\.]\s*(\d{1,2})\s*月?"),
    # 不能用 \b：中文字符在 Python re 里属于 \w，"2023年" 会因此匹配失败
    re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)"),
]
_MONEY = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万元|万|元|美元|USD|港币)?", re.I)


def clean_value(value: str) -> str:
    """基础清洗：NFKC + 去零宽/控制字符 + 折叠空白 + 去首尾标点空白。"""
    if not value:
        return ""
    t = unicodedata.normalize("NFKC", str(value))
    t = _ZERO_WIDTH.sub("", t)
    t = _CONTROL.sub(" ", t)
    t = t.replace("\ufffd", "")
    t = _WS.sub(" ", t)
    return t.strip(" \t。.;；,，:：、_-")


def clean_company(value: str) -> str:
    """公司/机构名：去盖章装饰、去尾随的地址/电话等噪声。"""
    t = clean_value(value)
    t = _DECORATION.sub("", t)
    t = _COMPANY_NOISE.sub("", t)
    return clean_value(t)


def first_author(value: str) -> str:
    """多作者取第一作者，用于文件名。"""
    t = clean_value(value)
    parts = [p.strip() for p in _AUTHOR_SPLIT.split(t) if p.strip()]
    return parts[0] if parts else t


def normalize_year(value: str) -> str:
    t = clean_value(value)
    m = re.search(r"(?:19|20)\d{2}", t)
    return m.group(0) if m else ""


# V1.1.1：中文数字日期（「二〇一八年十一月」这类报告/公文成文年月）
_CN_DIGITS = {"〇": 0, "零": 0, "○": 0, "O": 0, "0": 0,
              "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
_CN_DATE = re.compile(
    r"([〇零○O一二三四五六七八九十0-9]{2,4})\s*年\s*"
    r"([一二三四五六七八九十]{1,3})\s*月"
    r"(?:\s*([一二三四五六七八九十]{1,3})\s*日)?")


def _cn_int(s: str) -> int:
    """『二〇一八』→2018，『十一』→11，『二十五』→25。"""
    if not s:
        return 0
    if "十" in s:
        a, _, b = s.partition("十")
        head = 1 if not a else (_CN_DIGITS.get(a, 0) if len(a) == 1 else _cn_int(a))
        tail = _CN_DIGITS.get(b, 0) if len(b) <= 1 else _cn_int(b)
        return head * 10 + tail
    out = 0
    for ch in s:
        out = out * 10 + _CN_DIGITS.get(ch, 0)
    return out


def normalize_date(value: str) -> str:
    """2024年3月5日 / 2024-03-05 / 2024/3/5 → 2024-03-05；仅年份 → 2024。

    V1.1.1 增加中文数字与「只有年月」的写法（二〇一八年十一月 → 2018-11）。
    V1.2.0 增加手写数字容错：OCR 常把年份/月日里的数字识别成形近字母
    （如「2o23」「3o日」），解析前先做字母→数字替换。
    """
    t = clean_value(value)
    m = _CN_DATE.search(t)
    if m:
        y = _cn_int(m.group(1))
        mo = _cn_int(m.group(2))
        d = _cn_int(m.group(3)) if m.group(3) else 0
        if 1900 <= y <= 2100 and 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}" + (f"-{d:02d}" if 1 <= d <= 31 else "")
    # V1.2.0：手写日期数字容错（o→0、l→1、O→0、I→1、全角→半角）
    t_fixed = t
    for a, b in (("o", "0"), ("O", "0"), ("l", "1"), ("I", "1"),
                 ("S", "5"), ("s", "5"), ("B", "8"), ("Z", "2")):
        t_fixed = t_fixed.replace(a, b)
    # V1.2.1：OCR 常把日期里的「年/月」识别成形近汉字（日/区/目/□ 等）。
    # 「2023日5区30日」→「2023年5月30日」，只在数字上下文里替换，避免误伤正文。
    t_fixed = re.sub(r"(?<=[\d])\s*[日目]\s*(?=\d{1,2}\s*[区月])", "年", t_fixed)
    t_fixed = re.sub(r"(?<=[\d])\s*[区囗]\s*(?=\d{1,2}\s*日)", "月", t_fixed)
    for pat in _DATE_PATTERNS:
        m = pat.search(t_fixed)
        if not m:
            continue
        g = m.groups()
        if len(g) >= 3 and g[1] and g[2]:
            return f"{int(g[0]):04d}-{int(g[1]):02d}-{int(g[2]):02d}"
        if len(g) == 2 and g[1]:
            return f"{int(g[0]):04d}-{int(g[1]):02d}"
        return str(g[0])
    # V1.1.2：OCR 常把签章日期识别成「戔为炀一」「年月旺日」等噪声，
    # 没有任何年份数字时不应当成有效日期，交给人工补录兜底。
    if not re.search(r"(?:19|20)\d{2}", t_fixed):
        return ""
    return t_fixed


# V1.3.1：合同期限范围解析。
# 真实合同写法（见技术要求文档的截图）：
#   「第一条 劳动合同期限 / 本合同自2023年5月30日起生效，至2026年5月29日终止，共3年」
# 即起点由「自…起」锚定、终点由「至…止」锚定，中间夹着「生效，」「终止」等字。
# 因此不能用一条紧贴的正则，而是分别锚定「自DATE」「至/到DATE」。
_DATE_TOKEN = r"((?:19|20)\s*\d{2})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?"
# 起点：自/从 DATE（「自」与日期间可有空格）
_START_ANCHOR = re.compile(r"(?:自|从)\s*" + _DATE_TOKEN)
# 终点：至/到/截止/终止 DATE
_END_ANCHOR = re.compile(r"(?:至|到|截止|终止|止)\s*" + _DATE_TOKEN)
# 紧凑写法兜底：2023.5.1-2024.4.30 / 2023年5月1日到2024年4月30日（无「自」前缀）
_COMPACT_RANGE = re.compile(_DATE_TOKEN + r"\s*(?:—|－|-|~|～|至|到|起)\s*" + _DATE_TOKEN)


def _date_tuple_to_iso(g: tuple[str, ...]) -> str:
    try:
        y, mo, d = int(g[0]), int(g[1]), int(g[2])
    except (ValueError, IndexError):
        return ""
    if not (1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"


def parse_duration_range(text: str) -> tuple[str, str]:
    """从合同文本解析 (开始日期, 结束日期)，均为 YYYY-MM-DD；解析不到返回 ('','')。

    优先处理「自X…至Y」句式（起点/终点分开锚定，容忍中间的「生效，」「终止」等字）；
    其次处理紧凑范围写法。OCR 常见「年→日、月→区」误识会先做替换。
    """
    if not text:
        return "", ""
    t = text
    t = re.sub(r"(?<=\d)\s*[日目]\s*(?=\d{1,2}\s*[区月])", "年", t)
    t = re.sub(r"(?<=\d)\s*[区囗]\s*(?=\d{1,2}\s*日)", "月", t)

    # 1) 句式：自X起生效，至Y终止 —— 在同一段落内分别找起点和终点
    for para in re.split(r"[\r\n]+", t):
        sm = _START_ANCHOR.search(para)
        if not sm:
            continue
        start = _date_tuple_to_iso(sm.groups())
        # 终点必须在起点之后出现，避免「至」在「自」之前的误配
        em = _END_ANCHOR.search(para, sm.end())
        end = _date_tuple_to_iso(em.groups()) if em else ""
        if start and end:
            return start, end

    # 2) 紧凑范围：2023.5.1-2024.4.30 / 2023年5月1日到2024年4月30日
    for m in _COMPACT_RANGE.finditer(t):
        start = _date_tuple_to_iso(m.groups()[0:3])
        end = _date_tuple_to_iso(m.groups()[3:6])
        if start and end:
            return start, end
    return "", ""


# V1.3.1：合同类型判定（劳动合同 / 劳务合同）。
# 难点：劳务合同常沿用劳动合同模板，正文里也写「劳动合同期限」「劳动法」，
# 因此不能见到「劳动合同」就判劳动；「劳务」类信号必须优先。
_TITLE_LABOR = re.compile(r"劳动\s*合\s*同(?:书|范本|文本|协议)?")
_TITLE_SERVICE = re.compile(r"劳务\s*合\s*同(?:书|范本|文本|协议)?")
_SERVICE_SIGNAL = re.compile(
    r"劳务合同|劳务关系|劳务报酬|提供劳务|接受劳务|劳务人员|劳务费|"
    r"劳务成果|劳务事项|承揽|完成工作|交付成果")
_LABOR_SIGNAL = re.compile(
    r"劳动合同|劳动者|用人单位|劳动关系|《劳动法》|劳动法|试用期|"
    r"劳动报酬|工资|社会保险|考勤|规章制度")


def _clean_title_lines(text: str) -> list[str]:
    """取候选标题行：短、独立成行、不含章节号/冒号/长句。"""
    out = []
    for ln in text.splitlines()[:15]:
        c = re.sub(r"\s+", "", ln)
        if not c:
            continue
        # 跳过「第一条 劳动合同期限」这类章节标题和带冒号的字段行
        if re.match(r"^第[一二三四五六七八九十百\d]+条", c):
            continue
        if "：" in c or ":" in c or len(c) > 30:
            continue
        out.append(c)
    return out


def detect_contract_type(text: str) -> str:
    """判定劳动合同/劳务合同；信号不足返回空。

    规则（按优先级）：
    1) 真正的标题行（短独立行）含「劳动合同书/劳务合同书」→ 直接定；
       劳务优先（劳务合同里常混用"劳动合同"字样）。
    2) 正文信号打分：劳务类词命中即倾向劳务（专一性强），劳动类词为辅。
    """
    if not text:
        return ""
    head = "".join(_clean_title_lines(text))
    # 1) 标题判定：劳务优先
    if _TITLE_SERVICE.search(head):
        return "劳务合同"
    if _TITLE_LABOR.search(head):
        return "劳动合同"
    # 2) 正文信号：劳务信号专一性强，出现即判劳务；劳动信号兜底
    whole = re.sub(r"\s+", "", text)
    service = len(_SERVICE_SIGNAL.findall(whole))
    labor = len(_LABOR_SIGNAL.findall(whole))
    if service > 0:
        return "劳务合同"
    if labor > 0:
        return "劳动合同"
    return ""


# V1.3.4：用工部门 7 选 1 —— 封闭集直接检索。
# 真实合同里部门值常写成「在财务室（部门）出纳岗位工作」，没有「用工部门：」标签。
# V1.4.4（重要修复）：旧模式里「办公室」带了变体「办公」，会命中第二条第一点的
# 「在甲方指定的工作场所或办公地点工作」——导致几乎所有合同都被误判成「办公室」。
# 现改为：先定位「（部门）」/「部（室）」锚点，只在锚点前那一小段里做 7 选 1，
# 且匹配模式全部收紧，绝不使用「办公」「服务一」这类会在正文里误触的短词。
DEPARTMENT_CHOICES = ("办公室", "财务室", "交通", "物业", "服务一部", "服务二部", "资产")

# 严格模式：官方名 + 低风险 OCR/手写变体（漏字、形近、数字写法）。
_DEPT_STRICT: dict[str, tuple[str, ...]] = {
    "服务一部": ("服务一部", "服务1部", "服务Ⅰ部"),
    "服务二部": ("服务二部", "服务2部", "服务Ⅱ部"),
    "办公室": ("办公室",),
    "财务室": ("财务室", "务室", "财条室", "财备室"),
    "交通": ("交通部", "交通室", "交通"),
    "物业": ("物业部", "物业室", "物业"),
    "资产": ("资产部", "资产室", "资产"),
}
# 锚点窗口专用宽变体：窗口只有锚点前十几个字，不会串到别的条款，
# 因此可以接受「办公」「务二部」「二部」这类在全文里会误触的短模式。
# 真实样本：手写「机关服务二部」被 OCR 成「机关务二部」；「财务室」识别正常。
_DEPT_WIDE: dict[str, tuple[str, ...]] = {
    "服务一部": ("服务一部", "服务1部", "服务Ⅰ部", "务一部", "务1部", "一部", "1部"),
    "服务二部": ("服务二部", "服务2部", "服务Ⅱ部", "务二部", "务2部", "二部", "2部"),
    "办公室": ("办公室", "办公"),
    "财务室": ("财务室", "财务", "务室", "财条室", "财备室"),
    "交通": ("交通", "交逼", "交政"),
    "物业": ("物业",),
    "资产": ("资产",),
}
# 命中处若落在这些词内部，说明不是部门（费用、管理职能等）
_NON_DEPT_CTX = ("交通费", "物业费", "交通补贴", "物业管", "资产管理", "交通管制")

# 岗位填写位置的锚点：劳动合同「在 XX（部门）YY 岗位」，劳务合同「在 XX 部（室）YY 岗位」。
# 扫描件偶尔丢括号（「部部门）」），故左括号设为可选、右括号必须存在。
_DEPT_ANCHOR = re.compile(r"[（(]?\s*部\s*门\s*[）)]|部\s*[（(]\s*室\s*[）)]")
# 部门标签行（少数合同会单独填「用工部门：财务室」）
_DEPT_LABEL = re.compile(
    r"(?:用工部门|工作部门|所属部门|所在部门|部门)\s*[:：]\s*([^\r\n]{0,20})")


def _match_in(seg: str, table: dict[str, tuple[str, ...]]) -> str:
    """在片段内按给定表做 7 选 1；多处命中取「结束位置最靠后」的（离锚点最近）。"""
    if not seg:
        return ""
    order = sorted(table.items(), key=lambda kv: -max(len(p) for p in kv[1]))
    best: tuple[int, int, str] | None = None
    for dept, pats in order:
        for pat in pats:
            start = 0
            while True:
                idx = seg.find(pat, start)
                if idx < 0:
                    break
                ctx = seg[max(0, idx - 2): idx + len(pat) + 2]
                if any(nd in ctx for nd in _NON_DEPT_CTX):
                    start = idx + 1
                    continue
                key = (idx + len(pat), len(pat))
                if best is None or key > best[:2]:
                    best = (idx + len(pat), len(pat), dept)
                break
    return best[2] if best else ""


def _match_dept_strict(seg: str) -> str:
    """严格模式：仅官方名与低风险变体，用于全文兜底，避免「办公地点」误触。"""
    return _match_in(seg, _DEPT_STRICT)


def _dept_from_anchor(seg: str) -> str:
    """只在「（部门）」锚点前的一小段文字里找部门名——这是用户指明的固定位置。"""
    if not seg:
        return ""
    for m in _DEPT_ANCHOR.finditer(seg):
        left = seg[max(0, m.start() - 16):m.start()]
        # 只保留同一句内、锚点前最后一段（避免跨句把上一句的部门名带进来）
        left = re.split(r"[，。；;、\r\n]", left)[-1]
        left = re.sub(r"^\s*(?:在|为|到|任|至|于)", "", left).strip()
        dept = _match_in(left, _DEPT_WIDE)
        if dept:
            return dept
    return ""


def _clause2_text(text: str) -> str:
    """截取「第二条」到「第三条」之间的正文（保留换行，便于锚点取句）。"""
    m = re.search(r"第\s*二\s*条", text)
    if not m:
        return ""
    tail = text[m.end():]
    e = re.search(r"第\s*三\s*条", tail)
    return tail[:e.start()] if e else tail[:1600]


def find_department(text: str) -> str:
    """从合同文本找用工部门（7选1）；找不到返回空（由界面贴图交人工核对）。

    V1.4.4 优先级：
      A. 第二条章节内、「（部门）」锚点前的文字（用户指定：第二条第二点）
      B. 全文「（部门）」锚点（OCR 偶尔认不出「第二条」字样）
      C. 第二条章节内严格 7 选 1
      D. 「用工部门：XX」标签行
      E. 首页前 30 行严格 7 选 1
    """
    if not text:
        return ""
    # 保留换行（章节切分要用），只压缩行内空白
    norm = re.sub(r"[ \t\u3000]+", "", text)

    clause2 = _clause2_text(norm)
    if clause2:
        dept = _dept_from_anchor(clause2)
        if dept:
            return dept

    dept = _dept_from_anchor(norm)
    if dept:
        return dept

    if clause2:
        dept = _match_dept_strict(clause2)
        if dept:
            return dept

    for m in _DEPT_LABEL.finditer(norm):
        dept = _match_dept_strict(re.sub(r"\s+", "", m.group(1)))
        if dept:
            return dept

    head = "\n".join(text.splitlines()[:30])
    return _match_dept_strict(re.sub(r"[ \t\u3000]+", "", head))


def normalize_department(value: str) -> str:
    """把任意部门写法（含手写/OCR 变体）归一为 7 选 1 官方名；无法判定返回空。"""
    t = re.sub(r"[\s\u3000]+", "", value or "")
    if not t:
        return ""
    for dept in DEPARTMENT_CHOICES:
        if t == dept:
            return dept
    dept = _match_dept_strict(t)
    if dept:
        return dept
    return _match_in(t, _DEPT_WIDE)



_PLACEHOLDER = re.compile(r"[\s_＿\-—–·．.,，:：/\\x＊*□○〇（）()年月日待填略]", re.I)
_BLANK_DATE = re.compile(r"年\s*月\s*日")


def is_placeholder(value: str) -> bool:
    """判定合同范本里的空白占位（如「年 月 日」「____」「XXX」「—」），应视为字段缺失。"""
    t = clean_value(value)
    if not t:
        return True
    if not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", t):
        return True
    # 「签署日期： 年 月 日」并排两栏被拼成一行时，也要判为空白
    if _BLANK_DATE.search(t) and not re.search(r"(?:19|20)\d{2}", t):
        return True
    return not _PLACEHOLDER.sub("", t)


def normalize_money(value: str) -> str:
    """¥1,200,000.00元 → 1200000.00元；120万元 → 1200000元。"""
    t = clean_value(value)
    m = _MONEY.search(t)
    if not m:
        # 范本里的「人民币 XXX 元」等没有数字，不能当成有效金额
        return ""
    num = m.group(1).replace(",", "")
    unit = (m.group(2) or "").strip()
    if unit in ("万元", "万"):
        try:
            amount = (Decimal(num) * 10000).normalize()
            return f"{amount:f}元"
        except InvalidOperation:
            return f"{num}{unit}"
    # 保持十进制字符串原貌，绝不使用 float 的 g 格式（会输出 1.2e+06 这类科学计数法）
    if unit:
        return f"{num}{unit}"
    return num


def normalize_by_type(value: str, field_type: str, choices: list[str] | None = None) -> str:
    """返回用于 Excel 展示的标准值。"""
    if field_type == "date":
        return normalize_date(value)
    if field_type == "money":
        return normalize_money(value)
    if field_type == "year":
        return normalize_year(value)
    if field_type == "company":
        return clean_company(value)
    if field_type == "idcard":
        return normalize_idcard(value)
    if field_type == "enum":
        return normalize_enum(value, choices or [])
    if field_type == "person_name":
        return normalize_person_name(value)
    return clean_value(value)


# V1.2.1：手写姓名局部识别时，相邻行的标签/值常被 OCR 粘连成
# 「张明远 用工部门: 服务一部」。取开头连续的姓名片段，遇冒号/字段标签即截断；
# 姓名中间的单空格（OCR 常见，如「李 四」）则保留拼接，不让脏串进入文件名。
_NAME_STOP = re.compile(r"[:：,，、;；]|_+|[（(].*$")
_DEPT_WORDS = ("用工部门", "工作部门", "所属部门", "部门", "身份证", "日期", "合同",
               "签字", "签名", "签日", "年月日", "签订", "签署", "签约", "订立",
               "乙方", "甲方", "劳动者", "起始", "截止", "终止", "期限")


def normalize_person_name(value: str) -> str:
    t = clean_value(value)
    if not t:
        return ""
    # V1.3.4：若值以「乙方/劳动者/姓名：」这类标签开头，取冒号后的姓名，
    # 而不是把冒号前的标签当成截断左边（旧 bug：「乙方：孟梅」→「乙方」）。
    m = re.match(r"^(乙方|劳动者|受雇人|姓名|乙方签字|乙方签名)\s*[:：]\s*(.+)$", t)
    if m:
        t = m.group(2)
    head = _NAME_STOP.split(t, maxsplit=1)[0]
    # V1.3.8：遇到字段标签词或机构/正文词，从该处截断（「孟梅国家基金…」→「孟梅」）
    for w in _DEPT_WORDS:
        idx = head.find(w)
        if idx > 0:
            head = head[:idx]
    # 去掉空白，只留中文/·/英文
    head = re.sub(r"\s+", "", head)
    head = re.sub(r"[^\u4e00-\u9fff·A-Za-z]", "", head)
    # 机构词可能在姓名之后粘连（如「刘璇国家…」），从机构词处截断
    for w in _NOT_NAME:
        idx = head.find(w)
        if idx > 0:
            head = head[:idx]
    # 中文姓名一般 2-4 字；过长多为「姓名+单位名」粘连，只取前 4 字
    if re.fullmatch(r"[\u4e00-\u9fff·]{2,}", head) and len(head) > 4:
        head = head[:4]
    # 截断后若是无效词（本人/双方等正文词），判为未识别，交给截图兜底
    if head in ("本人", "双方", "甲方", "乙方", "劳动者", "公司", "中心", "国家"):
        return ""
    return head


# V1.3.4：乙方姓名专提——从合同全文按「乙方」标签取纯姓名。
# 乙方是开放集（任意姓名），只能靠标签定位 + 短名过滤，认不准时由截图兜底。
# 只认「乙方：姓名」或「乙方（签字）：姓名」这种带冒号的标签形式；
# 无冒号的「乙方声明…」是正文，绝不抓（曾误取「声明已在签」当姓名）。
_YIFANG_LABEL = re.compile(
    r"(?:乙方\s*[（(][^）)\r\n]{0,10}[）)]\s*|乙方签字|乙方签名|乙方|劳动者|受雇人)\s*[:：]\s*"
    r"([\u4e00-\u9fff·]{2,8})")
# 明显不是人名的短语（含动词/正文虚词）
_NOT_NAME = ("声明", "签字", "签名", "盖章", "签章", "已在", "已经", "递交", "提交",
             "接受", "履行", "遵守", "应当", "必须", "合同", "甲方", "部门", "日期",
             "义务", "权利", "身份证", "电话", "地址", "如下", "上述", "本人", "双方",
             # 机构/单位名特征词：出现在"姓名+单位名"粘连里，用来截断到纯姓名
             "国家", "基金", "委员会", "中心", "大学", "学院", "公司", "集团", "机关",
             "服务", "研究所", "研究院", "办公室", "财务")


def find_person_name(text: str) -> str:
    """从合同全文找乙方姓名（带冒号标签后的 2-8 字中文），取第一个可信短名。"""
    if not text:
        return ""
    for m in _YIFANG_LABEL.finditer(text):
        cand = m.group(1)
        if any(w in cand for w in _NOT_NAME):
            continue
        # 姓名通常 2-4 字；过长（>6）多为短语，谨慎排除
        if len(cand) > 6:
            continue
        return cand
    return ""


# ---------------------------------------------------------------------------
# V1.2.0：身份证号校验
# ---------------------------------------------------------------------------
_IDCARD_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_IDCARD_CHECK = "10X98765432"


def _fix_handwritten_digits(s: str) -> str:
    """手写/OCR 数字容错：常见形近字母→数字、全角→半角。

    仅针对身份证号/日期这类「应以数字为主」的字段；不作用于普通文本。
    """
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", s)
    t = re.sub(r"\s+", "", t)                        # 去所有空白
    t = t.replace("Ｏ", "0").replace("Ｏ", "0")       # 全角 O
    t = t.replace("Ｉ", "1").replace("ｌ", "1").replace("Ｌ", "1")
    # 形近字母 → 数字（手写体 OCR 高频错误）
    t = t.replace("O", "0").replace("o", "0")         # 字母 O/o → 0
    t = t.replace("I", "1").replace("l", "1")         # 字母 I/l → 1
    t = t.replace("S", "5").replace("s", "5")         # 字母 S/s → 5
    t = t.replace("B", "8").replace("b", "6")         # B→8, b→6（手写易混）
    t = t.replace("Z", "2").replace("z", "2")
    t = t.replace("G", "6").replace("q", "9")
    # 常见标点/分隔符
    t = t.replace("：", "").replace(":", "")
    return t


def _idcard_checksum(prefix17: str) -> str:
    """给定前 17 位数字，返回第 18 位校验码（0-9 或 X）。"""
    if len(prefix17) != 17 or not prefix17.isdigit():
        return ""
    s = sum(int(c) * w for c, w in zip(prefix17, _IDCARD_WEIGHTS))
    return _IDCARD_CHECK[s % 11]


def normalize_idcard(value: str) -> str:
    """身份证号归一化 + 18 位校验。

    手写/OCR 常把数字识别成形近字母（O→0、l→1 等），先做容错替换，
    再做 18 位校验码验证；校验不过但「前 17 位全数字 + 末位数字/X」时
    仍返回容错后的值（可能是 OCR 把校验码识别错了，交给人工复核）。
    非 18 位、明显非法则返回空。
    """
    if not value:
        return ""
    t = _fix_handwritten_digits(value)
    # 去掉末尾可能粘上的「号」字
    t = t.rstrip("号號")
    if len(t) == 15:
        # 15 位老身份证：不做校验码验证，仅要求全数字
        return t if t.isdigit() else ""
    if len(t) != 18:
        return ""
    if not t[:17].isdigit():
        return ""
    last = t[17]
    if last not in "0123456789Xx":
        return ""
    expect = _idcard_checksum(t[:17])
    if expect and last.upper() == expect:
        return t.upper()
    # 校验码不符：可能是 OCR 把末位识别错了，仍返回（标为需复核）
    return t.upper()


# ---------------------------------------------------------------------------
# V1.2.0：枚举字段模糊映射（用工部门 7 选 1 等）
# ---------------------------------------------------------------------------
def _enum_similarity(a: str, b: str) -> float:
    """两个字符串的相似度（0~1）：优先精确/包含，否则字符重叠率。"""
    a, b = a.strip(), b.strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    return inter / max(len(sa), len(sb))


def normalize_enum(value: str, choices: list[str]) -> str:
    """把识别结果映射到最接近的枚举项（去空白 + 相似度打分）。

    用于「用工部门 7 选 1」：OCR 可能识别出「财务 室」「办公室」带空格，
    或「服务一部」识别成「服务一部」。取相似度最高且超过阈值的枚举项；
    都够不着时返回清洗后的原值（交给人工复核），而不是硬塞错误项。
    """
    if not value:
        return ""
    raw = re.sub(r"\s+", "", clean_value(value))
    if not raw:
        return ""
    if not choices:
        return raw
    best, best_score = "", 0.0
    for c in choices:
        cc = re.sub(r"\s+", "", clean_value(c))
        sc = _enum_similarity(raw, cc)
        if sc > best_score:
            best, best_score = cc, sc
    # 阈值：必须足够接近才认作枚举项，否则保留原值人工复核
    return best if best_score >= 0.5 else raw


def to_filename_value(value: str, field_type: str, max_len: int = 0) -> str:
    """生成用于文件名的短值（作者只取第一作者等）。"""
    if field_type == "list":
        t = first_author(value)
    else:
        t = clean_value(value)
    if max_len > 0 and len(t) > max_len:
        t = t[:max_len]
    return t


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Windows 文件名合法化：非法字符、设备名、首尾点空格、长度上限。"""
    t = unicodedata.normalize("NFKC", str(name or ""))
    t = _ZERO_WIDTH.sub("", t)
    t = re.sub(_ILLEGAL, "_", t)
    t = _CONTROL.sub("", t)
    t = _WS.sub(" ", t)
    t = re.sub(r"_{2,}", "_", t)
    t = t.strip(" ._")
    stem, dot, ext = t.rpartition(".")
    if not dot or not ext or len(ext) > 5:
        stem, ext = t, "pdf"
    stem = stem.strip(" ._") or "未命名"
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    # 预留扩展名长度
    keep = max(8, int(max_len) - len(ext) - 1)
    if len(stem) > keep:
        stem = stem[:keep].rstrip(" ._")
    return f"{stem}.{ext.lower()}"


def unique_name(name: str, used_lower: set[str]) -> str:
    """大小写不敏感去重：xxx.pdf → xxx_2.pdf → xxx_3.pdf。"""
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, "pdf"
    candidate = name
    i = 2
    while candidate.lower() in used_lower:
        candidate = f"{stem}_{i}.{ext}"
        i += 1
    used_lower.add(candidate.lower())
    return candidate


# V1.3.8：判断一个"已识别"的字段值是否可疑——状态虽 OK 但值明显错误时，
# 也应放截图供人工核对（避免"错值既不是正确文字、又不给截图"的最差情况）。
def suspect_field_value(name: str, value: str) -> bool:
    if not value:
        return True
    v = re.sub(r"\s+", "", value)
    if name == "乙方":
        # 姓名应是 2-4 字；超长或含机构/正文词即疑为误取单位名/正文
        if len(v) > 5:
            return True
        if any(w in v for w in _NOT_NAME):
            return True
        if not re.fullmatch(r"[\u4e00-\u9fff·A-Za-z]{2,5}", v):
            return True
        # V1.4.6：手写姓名常把下一栏的字串进来（真实样本「张光明」被认成「张气明性」）。
        # 4 字且末字是「性别/签名/日期」这类栏目标签用字时，一律判为不可信，交给截图核对。
        if len(v) == 4 and v[-1] in "性别名签字日期年月":
            return True
    elif name == "身份证号":
        digits = re.sub(r"[^0-9Xx]", "", v)
        if len(digits) not in (15, 18):
            return True
    elif name == "用工部门":
        if v not in DEPARTMENT_CHOICES:
            return True
    elif name in ("开始日期", "结束日期", "签订日期"):
        if not re.search(r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}", v) \
                and not re.fullmatch(r"(?:19|20)\d{2}", v):
            return True
    return False
