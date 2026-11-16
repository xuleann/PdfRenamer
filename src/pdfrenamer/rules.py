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
    """
    t = clean_value(value)
    m = _CN_DATE.search(t)
    if m:
        y = _cn_int(m.group(1))
        mo = _cn_int(m.group(2))
        d = _cn_int(m.group(3)) if m.group(3) else 0
        if 1900 <= y <= 2100 and 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}" + (f"-{d:02d}" if 1 <= d <= 31 else "")
    for pat in _DATE_PATTERNS:
        m = pat.search(t)
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
    if not re.search(r"(?:19|20)\d{2}", t):
        return ""
    return t


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


def normalize_by_type(value: str, field_type: str) -> str:
    """返回用于 Excel 展示的标准值。"""
    if field_type == "date":
        return normalize_date(value)
    if field_type == "money":
        return normalize_money(value)
    if field_type == "year":
        return normalize_year(value)
    if field_type == "company":
        return clean_company(value)
    return clean_value(value)


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
