# -*- coding: utf-8 -*-
"""论文 PDF 的结构化信息解析（纯规则，不调用任何模型、不联网）。

真实学术论文首页没有「Title: xxx」这类标签，但通常具备两类确定性线索：
  1. PDF 元数据：IEEE 系期刊的 subject 常为「期刊名;年份;卷;期;DOI」，
     title / author / creationDate 也常直接可用；
  2. 首页版式：页眉期刊行 → 跨行标题 → 作者区（含上标、Member IEEE）→ Abstract。

本模块按「元数据 → 首页版式 → 全文兜底」的固定优先级解析出
title / authors / venue / year 四个值，供引擎按字段的 source 声明取用。
所有逻辑均为字符串匹配与正则，结果可复现、可人工校验。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import ST_HEURISTIC, ST_OK

# 可识别为「期刊 / 会议」的缩写（用于无元数据、无 IEEE 页眉的预印本）
_VENUE_HINTS = (
    "AISTATS", "NeurIPS", "NIPS", "ICLR", "ICML", "AAAI", "IJCAI", "ACL",
    "EMNLP", "CVPR", "ICCV", "ECCV", "KDD", "SIGMOD", "VLDB", "ICASSP",
    "WWW", "INFOCOM", "PMLR", "JMLR", "IJCAI", "UAI", "AAMAS",
)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_HEADER_HINT = re.compile(
    r"IEEE|TRANSACTIONS|JOURNAL|PROCEEDINGS|VOL\.|ARXIV|CONFERENCE ON|ACM ", re.I)
_ABSTRACT_RE = re.compile(r"^\s*abstract\b|^\s*摘\s*要", re.I)
_AFFILIATION_RE = re.compile(
    r"@|university|institute|college|department|laborator|inc\.|ltd\.|"
    r"school of|research center|beijing|shanghai|usa|china", re.I)
_PERSON_RE = re.compile(r"^[A-Z]\.\s|^[A-Z][a-zéèüöä\-]+\s+[A-Z][a-zéèüöä\-]+$")
# 从作者区里抽取英文姓名（含 "H. Brendan McMahan" 这类带首字母缩写的形式）
_NAME_RE = re.compile(
    r"\b(?:[A-Z]\.\s*)?[A-Z][a-zA-ZéèüöäÀ-ÿ\-]+(?:\s+[A-Z]\.)?\s+[A-Z][a-zA-ZéèüöäÀ-ÿ\-]+\b")
_SUPERSCRIPT_RE = re.compile(r"(?<=[a-zA-Z])\d{1,3}(?=[,\s]|$)")
_MEMBER_RE = re.compile(r",?\s*(?:Member|Senior Member|Fellow|Student Member),\s*IEEE\s*,?", re.I)
_AND_RE = re.compile(r"^\s*,\s*and\s+", re.I)


def _norm(s: str) -> str:
    """用于比对：NFKC → 小写 → 只留字母数字与汉字。"""
    t = unicodedata.normalize("NFKC", str(s or ""))
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", t.lower())


def _lines(raw: str) -> list[str]:
    out = []
    for line in str(raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        t = unicodedata.normalize("NFKC", line)
        t = re.sub(r"[ \t\u00a0\u3000]+", " ", t).strip()
        if t:
            out.append(t)
    return out


def _year_from_subject(subject: str) -> str:
    m = re.search(r";\s*((?:19|20)\d{2})\s*;", subject or "")
    return m.group(1) if m else ""


def _venue_from_subject(subject: str) -> str:
    s = (subject or "").strip()
    if not s:
        return ""
    parts = [p.strip() for p in s.split(";")]
    # IEEE 元数据：期刊名;年份;卷;期;DOI
    if len(parts) >= 3 and re.fullmatch(r"(?:19|20)\d{2}", parts[1] or ""):
        return parts[0]
    # 会议名 / 关键词串，保留原文（含 AAAI-22 之类缩写）
    if len(s) <= 160:
        return s
    return ""


def _header_and_year(lines: list[str]) -> tuple[str, str, int]:
    """返回 (期刊页眉, 页眉年份, 页眉所在行下标)。"""
    for i, ln in enumerate(lines[:12]):
        if not _HEADER_HINT.search(ln) or _ABSTRACT_RE.match(ln):
            continue
        venue = re.split(r",\s*VOL\.|,?\s*VOL\.\s|\s+NO\.\s*\d+", ln, maxsplit=1, flags=re.I)[0]
        venue = re.sub(r"\s*,?\s*(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
                       r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b.*$", "", venue, flags=re.I).strip(" ,")
        m = _YEAR_RE.search(ln)
        return venue.strip(), (m.group(0) if m else ""), i
    return "", "", -1


def _title_line_count(block: list[str], md_title: str) -> int:
    """用元数据标题对齐首页行，返回标题占了几行；同时可补全被截断的元数据。

    一旦累加结果「刚好等于」或「已完整覆盖」元数据标题就立即停止，
    否则会误把紧随其后的作者行当成标题续行。
    """
    if not md_title:
        return 0
    n_md = _norm(md_title)
    if not n_md:
        return 0
    acc = ""
    for k, ln in enumerate(block[:8], 1):
        acc += ln
        n = _norm(acc)
        if not n:
            continue
        if n == n_md or n.startswith(n_md):
            return k
        if n_md.startswith(n):
            continue          # 还没凑齐，继续读下一行
        break                 # 已经偏离标题
    return 0


def _guess_title_line_count(block: list[str]) -> int:
    """无元数据时：连续收集标题行，遇到人名/机构/邮箱行即停。"""
    if not block:
        return 0
    count = 0
    for ln in block[:8]:
        if _PERSON_RE.match(ln) or _AFFILIATION_RE.search(ln) or "@" in ln:
            break
        # 作者行特征：多个逗号 + and / Member IEEE / 上标数字
        if re.search(r",\s*(?:and\s+)?[A-Z][a-z]", ln) and _SUPERSCRIPT_RE.search(ln):
            break
        if _MEMBER_RE.search(ln):
            break
        count += 1
        if count >= 6:
            break
    return max(1, count)


def _clean_authors(raw: str) -> str:
    t = _MEMBER_RE.sub(", ", raw)
    t = _SUPERSCRIPT_RE.sub("", t)
    t = _AND_RE.sub("", t)
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\b(?:and|&)\b\s*", "", t, flags=re.I)
    t = re.sub(r"^[\s,]+|[\s,]+$", "", t)
    t = re.sub(r",\s*,", ",", t)
    return t.strip()


def parse_paper(head_text: str, metadata: dict[str, Any] | None = None,
                full_text: str = "") -> dict[str, tuple[str, str, str]]:
    """解析论文结构化信息。

    返回 {key: (值, 字段状态, 来源说明)}，key ∈ title/authors/venue/year。
    状态为 ST_OK（元数据或首页版式）或 ST_HEURISTIC（全文兜底，建议复核）。
    """
    md = {str(k).lower(): str(v or "").strip() for k, v in (metadata or {}).items() if v}
    md_title = md.get("title", "")
    md_author = md.get("author", "")
    subject = md.get("subject", "")
    keywords = md.get("keywords", "")
    created = md.get("creationdate", "")

    lines = _lines(head_text) or _lines(full_text)
    abstract_at = next((i for i, ln in enumerate(lines[:40]) if _ABSTRACT_RE.match(ln)), len(lines))
    header_venue, header_year, header_idx = _header_and_year(lines[:abstract_at or 12])

    # 首页正文块：跳过页眉 / 纯数字页码 / 空行，截止到 Abstract
    block: list[str] = []
    for i, ln in enumerate(lines[:abstract_at]):
        if i == header_idx:
            continue
        if re.fullmatch(r"\d{1,7}", ln):        # 期刊页码，如 40415 / 379
            continue
        if _HEADER_HINT.search(ln) and _YEAR_RE.search(ln):
            continue
        block.append(ln)

    # ---------- 题目 ----------
    title, title_status, title_note = "", "", ""
    k = _title_line_count(block, md_title) if md_title else 0
    if k:
        joined = " ".join(block[:k]).strip()
        # 元数据标题被 PDF 生成器截断时，用首页完整标题补全
        if len(_norm(joined)) > len(_norm(md_title)):
            title, title_status, title_note = joined, ST_OK, "来源：首页标题（补全被截断的元数据）"
        else:
            title, title_status, title_note = md_title, ST_OK, "来源：PDF 元数据 title"
    elif not md_title:
        k2 = _guess_title_line_count(block)
        if k2:
            cand = " ".join(block[:k2]).strip()
            if 8 <= len(cand) <= 300:
                title, title_status, title_note = cand, ST_HEURISTIC, "来源：首页版式推测，建议人工复核"
    elif md_title:
        title, title_status, title_note = md_title, ST_OK, "来源：PDF 元数据 title"

    # ---------- 作者 ----------
    authors, authors_status, authors_note = "", "", ""
    if md_author:
        authors, authors_status, authors_note = _clean_authors(md_author), ST_OK, "来源：PDF 元数据 author"
    else:
        tail = block[k:] if k else block[_guess_title_line_count(block):]
        kept = [ln for ln in tail if not _AFFILIATION_RE.search(ln) and "@" not in ln]
        blob = _clean_authors(" ".join(kept))
        names: list[str] = []
        for m in _NAME_RE.finditer(blob):
            nm = m.group(0).strip()
            if nm not in names and not re.search(r"member|fellow|ieee|university", nm, re.I):
                names.append(nm)
        cand = ", ".join(names[:12]) if names else blob
        if 2 <= len(cand) <= 300:
            authors, authors_status = cand, ST_HEURISTIC
            authors_note = "来源：首页作者区解析，建议人工复核"

    # ---------- 期刊 / 会议 ----------
    venue, venue_status, venue_note = "", "", ""
    sv = _venue_from_subject(subject)
    if sv and not re.fullmatch(r"[\d;\s.]+", sv):
        venue, venue_status, venue_note = sv, ST_OK, "来源：PDF 元数据 subject"
    elif header_venue:
        venue, venue_status, venue_note = header_venue, ST_OK, "来源：首页期刊页眉"
    else:
        # 会议信息常出现在首页页脚（未重排原文）或前几页的版权行，
        # 因此探测范围要覆盖整篇首页原文，而不是只看前 40 行。
        probe = (head_text or "") + "\n" + "\n".join(lines[:40]) + "\n" + (full_text or "")[:12000]
        for hint in _VENUE_HINTS:
            if re.search(r"\b" + re.escape(hint) + r"\b", probe, re.I):
                m = re.search(r"Proceedings of the .{0,90}?\(" + hint + r"\)", probe, re.I)
                venue = m.group(0) if m else hint
                venue_status, venue_note = ST_HEURISTIC, "来源：正文会议名推测，建议人工复核"
                break
        if not venue and re.search(r"arxiv", probe, re.I):
            venue, venue_status, venue_note = "arXiv", ST_HEURISTIC, "来源：正文 arXiv 标记"
        if not venue and keywords:
            venue, venue_status, venue_note = keywords[:120], ST_OK, "来源：PDF 元数据 keywords"

    # ---------- 年份 ----------
    year, year_status, year_note = "", "", ""
    y = _year_from_subject(subject)
    if y:
        year, year_status, year_note = y, ST_OK, "来源：PDF 元数据 subject"
    elif header_year:
        year, year_status, year_note = header_year, ST_OK, "来源：首页期刊页眉"
    else:
        probe = "\n".join(lines[:40]) + "\n" + (full_text or "")[:6000]
        m = re.search(r"Copyright\s*(?:©|\(c\)|C)?\s*((?:19|20)\d{2})", probe, re.I)
        if not m:
            m = re.search(r"\b(?:AISTATS|AAAI|NeurIPS|ICLR|ICML|CVPR|ACL|KDD)\)?\s*[-,]?\s*((?:19|20)\d{2})", probe, re.I)
        if m:
            year, year_status, year_note = m.group(1), ST_OK, "来源：版权/会议行"
        else:
            m2 = re.search(r"D:((?:19|20)\d{2})", created)
            if m2:
                year, year_status, year_note = m2.group(1), ST_OK, "来源：PDF 创建日期"
    if not year:
        m3 = _YEAR_RE.search(full_text or "\n".join(lines))
        if m3:
            year, year_status = m3.group(0), ST_HEURISTIC
            year_note = "来源：正文首个年份，可能引自参考文献，务必人工复核"

    return {
        "title": (title, title_status, title_note),
        "authors": (authors, authors_status, authors_note),
        "venue": (venue, venue_status, venue_note),
        "year": (year, year_status, year_note),
    }


SOURCE_KEYS = {
    "paper_title": "title",
    "paper_authors": "authors",
    "paper_venue": "venue",
    "paper_year": "year",
}

SOURCE_LABELS = [
    ("不使用（仅关键词/正则）", ""),
    ("论文题目 · 结构化", "paper_title"),
    ("论文作者 · 结构化", "paper_authors"),
    ("期刊/会议 · 结构化", "paper_venue"),
    ("发表年份 · 结构化", "paper_year"),
]
