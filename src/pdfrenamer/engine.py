# -*- coding: utf-8 -*-
"""确定性提取引擎：正则 → 关键词 → 启发式 → 缺失。

全流程纯本地、纯规则：不调用任何模型、不发任何网络请求。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .contract_gate import is_contract_document
from .extractor import get_extractor
from .models import (
    DOC_ERROR, DOC_NOT_CONTRACT, DOC_NO_TEXT, DOC_OK, DOC_PARTIAL,
    ExtractResult, Field, FieldResult,
    SKIP_DOC_STATUSES, ST_FALLBACK, ST_HEURISTIC, ST_MISSING, ST_OK,
)
from .presets import MODE_CONTRACT
from .rules import clean_value, is_placeholder, normalize_by_type, to_filename_value
from .structured import SOURCE_KEYS, parse_paper

_LABEL_WORDS = ("甲方", "乙方", "供方", "需方", "合同名称", "项目名称", "金额",
                "日期", "时间", "作者", "题目", "期刊", "摘要", "关键词", "签字",
                "公司住所地", "统一社会信用代码", "法定代表人", "法人代表", "联系人",
                "联系电话", "电话", "地址", "开户行", "账号", "税号", "职务",
                "营业执照", "身份证", "合同编号", "签订地点", "盖章", "签章")
_NOISE_TAIL = re.compile(r"(?:法定代表人|法人代表|联系人|电话|地址|开户行|账号|税号).*$")


def _looks_like_label(value: str) -> bool:
    """取值本身其实是另一个标签或正文片段（空白合同范本常见），应判为无效。"""
    t = clean_value(value)
    if not t or is_placeholder(t):
        return True
    if t.endswith((":", "：")):
        return True
    if len(t) <= 10 and any(w in t for w in _LABEL_WORDS):
        return True
    return False


def list_pdfs(directory: str | Path, recursive: bool = False) -> list[Path]:
    """列出目录下的 PDF（默认不递归子目录）。"""
    p = Path(directory)
    if not p.is_dir():
        return []
    it = p.rglob("*") if recursive else p.glob("*")
    return sorted(
        (f for f in it if f.is_file() and f.suffix.lower() == ".pdf" and not f.name.startswith("~$")),
        key=lambda f: f.name.lower(),
    )


def normalize_pdf_paths(paths) -> list[Path]:
    """把「选择多个 PDF 文件」对话框返回的路径规范成 PDF 列表。

    与 list_pdfs 使用同一套卫生规则（只收 .pdf、排除 ~$ 临时文件、按名称排序）。
    """
    out = [Path(p) for p in (paths or ()) if str(p).strip()]
    return sorted(
        (f for f in out if f.is_file() and f.suffix.lower() == ".pdf"
         and not f.name.startswith("~$")),
        key=lambda f: f.name.lower(),
    )


def check_same_parent(paths) -> tuple[bool, Path | None]:
    """判断一组文件是否都位于同一目录，返回 (是否同目录, 共同父目录)。

    V1.1.1 的「多选 PDF」限制同一目录：这样 Excel 仍固定输出到该目录，
    原地改名、撤销日志与重名检测的 directory 锚点完全不用改。
    """
    parents = {Path(p).parent.resolve() for p in (paths or ()) if str(p).strip()}
    if not parents:
        return True, None
    if len(parents) == 1:
        return True, next(iter(parents))
    return False, None


def _by_keyword(text: str, keyword: str) -> str:
    """在文本中按标签取值：支持同行、装饰括号、标签独占一行取下一行。"""
    if not keyword:
        return ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        idx = line.find(keyword)
        if idx < 0:
            continue
        rest = line[idx + len(keyword):]
        # 「出租方(甲方)：某某公司」这类括号别名：只认冒号后面的值；
        # 冒号后为空（空白范本）则跳过本行，避免误取下一行的「联系电话」。
        m = re.match(r"^\s*[）)]\s*[:：]?\s*(.*)$", rest)
        if m:
            cand0 = clean_value(m.group(1))
            if cand0:
                return re.split(r"\s{2,}", cand0)[0].strip()
            continue
        # 标签后必须紧跟分隔符 / 括号 / 空白，不能是「甲方将位于…」这类正文连写；
        # 英文泛化词（Title/Author/Date…）同理，避免命中 "the authors of …"。
        if rest and not re.match(r"^[\s（(:：=\-–—_]", rest):
            continue
        # 去掉「（盖章）」「(签章)」等装饰
        rest = re.sub(r"^\s*[（(][^）)]{0,20}[）)]", "", rest)
        # 去掉前导分隔符
        rest = re.sub(r"^[\s:：=（）()\[\]【】\-–—_、，,]+", "", rest)
        # clean_value 会 strip 掉末尾顿号/逗号，先记录，供跨行续值判断使用
        continuation = rest.rstrip().endswith(("、", ",", "，", ";", "；"))
        rest = clean_value(rest)
        if rest:
            # PDF 里常用多空格分栏，取第一栏
            rest = re.split(r"\s{2,}", rest)[0].strip()
            if rest:
                # V1.1.1：值以顿号/逗号结尾说明跨行续值（如「预算单位：…、」下一行续「…街道办事处」）
                if continuation and i + 1 < len(lines):
                    nxt = clean_value(lines[i + 1])
                    if (nxt and not re.search(r"[:：]", nxt)
                            and not _looks_like_label(nxt) and len(nxt) <= 40):
                        rest = rest.rstrip("、,，;；") + "、" + nxt
                return rest
        # 仅当整行基本就是一个标签（短行）时，才向下找第一个「不像标签」的非空行。
        # 正文长句行尾恰好出现「…向乙方」时不能当成独占标签，否则会误取下一行正文。
        if len(line) <= 20:
            for nxt in lines[i + 1: i + 4]:
                cand = clean_value(nxt)
                if not cand:
                    continue
                # 「公司住所地：」「统一社会信用代码：」这类空标签行不能当成取值，
                # 尤其是空白范本里标签下方全是待填项时。
                if re.search(r"[:：]", cand) and (
                        any(w in cand for w in _LABEL_WORDS) or re.search(r"[:：]\s*$", cand)):
                    continue
                return cand
    return ""


def _money_ratio_guard(text: str, m: re.Match, field: Field) -> bool:
    """V1.1.2：扫描件 OCR 常见「支付合同金额的 25%」这类分期比例，
    数字后紧跟 % / ％ / 「折」时不是合同总金额，不能取为「金额」字段。
    """
    if field.type != "money":
        return True
    tail = text[m.end():m.end() + 3].lstrip()
    if tail.startswith(("%", "％", "折", "成", "个点")):
        return False
    # 无货币单位且数值很小（如「25」），几乎都是条款号/页码碎片
    cand = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
    if re.fullmatch(r"[0-9]{1,2}(?:\.[0-9]+)?", cand.strip() or ""):
        return False
    return True


# V1.1.2：OCR 文本里「合同编号」「合同金额」这类章节/标签短语不是合同名称，
# 启发式必须排除，否则扫描合同会被命名为「合同编号_甲方_供方…」。
_CONTRACT_LABEL_NOISE = re.compile(
    r"^(?:合同|协议|契约|合约)"
    r"(?:编号|金额|价款|条款|条款及格式|文件|专用条款|通用条款|标的|份数|正文|附件|"
    r"生效|期限|签订|签署|盖章|内容|总价|合计|费用|文本|范本|样本)?$"
)
# OCR 正文常有「…立本采购合同,共同信守」「…一致,签订本合同」这类句子碎片，
# 不能当成合同名称；标题行应独立成行、不含句读与叙述虚词。
_TITLE_SENTENCE = re.compile(r"[,，。;；:：!！?？、]|的|共同|一致|签订|根据|双方|遵守|如下|本采购|本合同")


def _heuristic(text: str, field: Field) -> str:
    """按字段类型的保守兜底，命中会标记为 heuristic（需人工复核）。"""
    t, name = field.type, field.name
    if t == "year" or "年" in name:
        m = re.search(r"(?:19|20)\d{2}", text)
        return m.group(0) if m else ""
    if t == "date":
        m = re.search(r"(?:19|20)\d{2}\s*[年/\-\.]\s*\d{1,2}\s*[月/\-\.]\s*\d{1,2}\s*日?", text)
        return m.group(0) if m else ""
    if t == "money":
        m = re.search(r"[¥￥]\s*[0-9][0-9,]*(?:\.[0-9]+)?|[0-9][0-9,]{3,}(?:\.[0-9]+)?\s*(?:万元|万|元)", text)
        return m.group(0) if m else ""
    if "合同" in name or "协议" in name:
        # 1) 首页「项目名称：…」在扫描合同里往往就是合同标的全称，但仅在
        #    已确认存在甲乙方等合同要素时才采用，避免绩效评价报告被误取。
        if re.search(r"(?:甲\s*方|乙\s*方|采购人|投标人|中标人|供应商)\s*[（(]?[^：:\r\n]{0,8}[：:]", text[:4000]):
            m = re.search(r"项目名称[ \t]*[:：][ \t]*([^\r\n]{4,80})", text[:4000])
            if m:
                cand = clean_value(m.group(1))
                if cand and not _CONTRACT_LABEL_NOISE.match(cand):
                    return cand
        # 2) 首页独立标题行（「采购合同」「合同书」），排除句子碎片与章节标签
        for ln in text.splitlines()[:25]:
            c = clean_value(ln)
            if (2 <= len(c) <= 40 and ("合同" in c or "协议" in c)
                    and not re.search(r"[:：]", c)
                    and not _TITLE_SENTENCE.search(c)
                    and not _CONTRACT_LABEL_NOISE.match(c)):
                return c
    if "题目" in name or "标题" in name or "题名" in name:
        for ln in text.splitlines()[:25]:
            c = clean_value(ln)
            if (8 <= len(c) <= 120 and not re.search(r"[:：]", c)
                    and re.search(r"[\u4e00-\u9fff]", c)
                    and not c.startswith(("摘要", "关键词", "参考", "第", "目录", "收稿"))):
                return c
    return ""


def _truncate(value: str, limit: int = 300) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


class ExtractEngine:
    """对单个 PDF 按字段配置提取信息。"""

    def __init__(self, mode: str, mode_cfg: dict, backend: str = "pymupdf",
                 first_pages: int = 3, last_pages: int = 0, missing_value: str = "未知",
                 contract_gate: bool = True, gate_threshold: int = 2,
                 scan_ocr_enabled: bool = True, scan_ocr_max_pages: int = 2,
                 scan_ocr_include_last_page: bool = True, scan_ocr_dpi: int = 200,
                 scan_ocr_max_side: int = 2400, scan_ocr_timeout: int = 60,
                 scan_ocr_lang: str = "auto"):
        self.mode = mode
        self.mode_cfg = mode_cfg
        self.missing_value = missing_value
        self.fields: list[Field] = [
            Field.from_dict(d) for d in mode_cfg.get("fields", []) if d.get("enabled", True)
        ]
        self.extractor = get_extractor(backend)
        self.first_pages = first_pages
        self.last_pages = last_pages
        # V1.1.1 合同文档类型闸门：仅合同模式生效，可在界面「处理选项」关闭
        self.contract_gate = (mode == MODE_CONTRACT) and bool(contract_gate)
        self.gate_threshold = max(1, min(9, int(gate_threshold or 2)))
        # V1.1.2 扫描件离线 OCR（仅无文本层时触发；缺中文语言包自动降级）
        self.scan_ocr_enabled = bool(scan_ocr_enabled)
        self.scan_ocr_max_pages = max(1, min(3, int(scan_ocr_max_pages or 2)))
        self.scan_ocr_include_last_page = bool(scan_ocr_include_last_page)
        self.scan_ocr_dpi = max(72, min(300, int(scan_ocr_dpi or 200)))
        self.scan_ocr_max_side = max(800, min(2600, int(scan_ocr_max_side or 2400)))
        self.scan_ocr_timeout = max(10, min(180, int(scan_ocr_timeout or 60)))
        self.scan_ocr_lang = str(scan_ocr_lang or "auto")

    def _field_result(self, text: str, field: Field,
                      structured: dict | None = None) -> FieldResult:
        raw, status, note = "", ST_MISSING, ""

        # 0) 结构化来源（PDF 元数据 / 首页版式），仅当字段声明了 source
        if field.source and structured:
            key = SOURCE_KEYS.get(field.source)
            if key:
                value, st, src_note = structured.get(key, ("", "", ""))
                if value:
                    raw, status, note = clean_value(value), (st or ST_OK), src_note

        # 1) 正则优先（第一个捕获组）
        if not raw and field.regex:
            try:
                m = re.search(field.regex, text, re.IGNORECASE | re.MULTILINE)
                if m and _money_ratio_guard(text, m, field):
                    cand = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                    cand = clean_value(cand)
                    if cand and not _looks_like_label(cand):
                        raw, status = cand, ST_OK
            except re.error as exc:
                note = f"正则无效：{exc}"

        # 2) 关键词回退
        if not raw:
            for kw in field.keywords:
                cand = _by_keyword(text, kw)
                if cand and not _looks_like_label(cand):
                    raw, status = cand, ST_FALLBACK
                    break

        # 3) 按类型的保守启发式
        if not raw:
            cand = _heuristic(text, field)
            if cand:
                raw, status = cand, ST_HEURISTIC
                note = (note + " " if note else "") + "启发式推测，建议人工复核"

        display = normalize_by_type(raw, field.type) if raw else ""
        if field.type == "company" and display:
            display = _NOISE_TAIL.sub("", display).strip()
        # 空白合同范本里的「年 月 日」「____」「XXX 元」应判为未填写，而不是有效值
        if not display or is_placeholder(display):
            if display:
                note = (note + " " if note else "") + "检测到空白占位，按缺失处理"
            return FieldResult(field.name, "", self.missing_value, ST_MISSING, note)

        display = _truncate(display)
        file_value = to_filename_value(display, field.type, field.max_len)
        return FieldResult(field.name, display, file_value or self.missing_value, status, note)

    def extract_file(self, path: str | Path) -> ExtractResult:
        p = Path(path)
        doc = self.extractor.extract(p, self.first_pages, self.last_pages)

        # V1.1.2：无文本层 → 尝试操作系统内置离线 OCR 补文。
        # 任何失败（语言包缺失 / 超时 / 渲染异常）都保持 DOC_NO_TEXT，由下方短路优雅降级。
        if self.scan_ocr_enabled and doc.status == DOC_NO_TEXT:
            try:
                from .extractor.ocr_winrt import supplement_textdoc
                ocr_doc = supplement_textdoc(
                    p, doc,
                    max_pages=self.scan_ocr_max_pages,
                    include_last=self.scan_ocr_include_last_page,
                    dpi=self.scan_ocr_dpi,
                    max_side=self.scan_ocr_max_side,
                    timeout=self.scan_ocr_timeout,
                    lang=self.scan_ocr_lang,
                )
                if ocr_doc is not None:
                    doc = ocr_doc
            except Exception:
                pass  # OCR 是增强能力，绝不能影响主流程

        res = ExtractResult(
            path=str(p), original_name=p.name, mode=self.mode,
            doc_status=doc.status, text_chars=doc.chars, note=doc.note,
        )
        # V1.1.2：闸门只在「确有正常文本层」时执行（显式白名单）。
        # 保证 OCR 降级后仍是 no_text_layer，不会被误标成「非合同文档」。
        if (self.mode == MODE_CONTRACT and self.contract_gate
                and doc.status in (DOC_OK, DOC_PARTIAL)):
            ok, info = is_contract_document(doc.head_text or doc.text, doc.text,
                                            doc.metadata, self.gate_threshold)
            if not ok:
                res.doc_status = DOC_NOT_CONTRACT
                res.note = (f"非合同文档（{info.get('reason') or '合同要素不足'}），"
                            "不参与改名")
        if res.doc_status in SKIP_DOC_STATUSES:
            res.fields = {
                f.name: FieldResult(f.name, "", self.missing_value, ST_MISSING, res.skip_reason)
                for f in self.fields
            }
            return res

        text = doc.text
        structured = None
        if any(f.source for f in self.fields):
            structured = parse_paper(doc.head_text or text, doc.metadata, text)
        for f in self.fields:
            res.fields[f.name] = self._field_result(text, f, structured)
        if res.missing_names():
            res.doc_status = DOC_PARTIAL
        elif doc.status == DOC_OK:
            res.doc_status = DOC_OK
        if doc.note:
            res.note = doc.note
        return res

    def extract_many(self, paths: list[Path], progress=None) -> list[ExtractResult]:
        out = []
        total = len(paths)
        for i, p in enumerate(paths, 1):
            try:
                out.append(self.extract_file(p))
            except Exception as exc:  # 单文件失败不影响整批
                r = ExtractResult(str(p), p.name, self.mode, doc_status=DOC_ERROR,
                                  note=f"{type(exc).__name__}: {exc}")
                r.fields = {f.name: FieldResult(f.name, "", self.missing_value,
                                                ST_MISSING, r.skip_reason) for f in self.fields}
                out.append(r)
            if progress:
                progress(i, total, p.name)
        return out
