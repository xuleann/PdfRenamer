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
from .rules import (clean_value, detect_contract_type, find_department,
                    find_person_name, is_placeholder, normalize_by_type,
                    parse_duration_range, to_filename_value)
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


def _by_keyword(text: str, keyword: str, no_cross_line: bool = False) -> str:
    """在文本中按标签取值：支持同行、装饰括号、标签独占一行取下一行。

    no_cross_line=True 时禁止「标签独占一行取下一行」——用于 person_name 等
    手写字段：手写值 OCR 识别不出时，下一行往往是正文/单位名，跨行取值必误抓。
    """
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
                # V1.2.0：no_cross_line（person_name）只接受「短人名」——
                # 2~6 个字符、不含标点、不含空格分栏；拒绝正文长句（如
                # 「本人接受及履行本合同之条款」「国家自然科学基金委员会机关服务中心」）。
                if no_cross_line:
                    if (2 <= len(cand) <= 6
                            and not re.search(r"[，。；、,.!?！？：:\s]", cand)
                            and not _looks_like_label(cand)):
                        return cand
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
    # V1.2.0：person_name（乙方姓名）「宁缺毋滥」——手写姓名 OCR 识别不出时，
    # 绝不从正文/单位名里乱猜（曾误取「本人接受及履行本合同之条款」「国家自然科学
    # 基金委员会机关服务中心」），直接返回空，交给人工补录。
    if t == "person_name":
        return ""
    if t == "year" or "年" in name:
        m = re.search(r"(?:19|20)\d{2}", text)
        return m.group(0) if m else ""
    if t == "date":
        # V1.3.5：开始/结束日期不许用「全文第一个日期」兜底——那会让三个日期字段
        # 都抓成同一个签订日期（用户看到的「开始=结束=签订」就是这么来的）。
        # 这两个字段必须靠明确的范围正则；认不出就留空，由 Excel 截图兜底。
        if name in ("开始日期", "结束日期"):
            return ""
        m = re.search(r"(?:19|20)\d{2}\s*[年/\-\.]\s*\d{1,2}\s*[月/\-\.]\s*\d{1,2}\s*日?", text)
        return m.group(0) if m else ""
    if t == "money":
        m = re.search(r"[¥￥]\s*[0-9][0-9,]*(?:\.[0-9]+)?|[0-9][0-9,]{3,}(?:\.[0-9]+)?\s*(?:万元|万|元)", text)
        return m.group(0) if m else ""
    if t == "idcard":
        # 兜底：找 17 位数字 + 末位数字/X 的身份证号
        m = re.search(r"(?<!\d)([0-9]{17}[0-9Xx])(?!\d)", text)
        return m.group(1) if m else ""
    if t == "enum":
        # 兜底：在全文里找是否出现任一枚举项
        for c in field.choices or []:
            if re.search(re.escape(c), text):
                return c
        return ""
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
                 scan_ocr_lang: str = "auto", scan_rapid_enabled: bool = True,
                 capture_field_images: bool = True):
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
        # V1.2.0：RapidOCR 手写体识别补强
        self.scan_rapid_enabled = bool(scan_rapid_enabled)
        # V1.3.0：手写字段局部截图嵌入 Excel
        self.capture_field_images = bool(capture_field_images)

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
            no_cross = (field.type == "person_name")   # 手写姓名禁止跨行取值
            for kw in field.keywords:
                cand = _by_keyword(text, kw, no_cross_line=no_cross)
                if cand and not _looks_like_label(cand):
                    raw, status = cand, ST_FALLBACK
                    break

        # 3) 按类型的保守启发式
        if not raw:
            cand = _heuristic(text, field)
            if cand:
                raw, status = cand, ST_HEURISTIC
                note = (note + " " if note else "") + "启发式推测，建议人工复核"

        display = normalize_by_type(raw, field.type, field.choices) if raw else ""
        if field.type == "company" and display:
            display = _NOISE_TAIL.sub("", display).strip()
        # 空白合同范本里的「年 月 日」「____」「XXX 元」应判为未填写，而不是有效值
        if not display or is_placeholder(display):
            if display:
                note = (note + " " if note else "") + "检测到空白占位，按缺失处理"
            return FieldResult(field.name, "", self.missing_value, ST_MISSING, note)

        display = _truncate(display)
        file_value = to_filename_value(display, field.type, field.max_len)
        # V1.2.0：手写敏感字段（日期/身份证/姓名/枚举）在劳动合同里常为手写，
        # 识别结果可能不准，统一标注「建议核对」，让用户在预览表一眼看到需确认的字段。
        if field.type in ("date", "idcard", "person_name", "enum") and status != ST_OK:
            note = (note + " " if note else "") + "手写字段，建议核对"
        return FieldResult(field.name, display, file_value or self.missing_value, status, note)

    def extract_file(self, path: str | Path) -> ExtractResult:
        p = Path(path)
        doc = self.extractor.extract(p, self.first_pages, self.last_pages)
        was_no_text = (doc.status == DOC_NO_TEXT)   # 原始是否为扫描件（无文本层）

        # V1.3.0 速度优化：RapidOCR 可用时，扫描件只跑 RapidOCR 一次
        # （PP-OCRv6 印刷体+手写都能认），不再叠加 Windows OCR，省掉整页重复识别。
        # 只有 RapidOCR 不可用/被关闭时，才退回 Windows 内置 OCR 兜底。
        rapid_ok = False
        if self.scan_rapid_enabled:
            try:
                from .extractor.ocr_rapid import rapid_available
                rapid_ok = rapid_available()
            except Exception:
                rapid_ok = False
        if (self.scan_ocr_enabled and doc.status == DOC_NO_TEXT and not rapid_ok):
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

        # V1.2.1：两阶段提取。先常规提取一次，若合同模式下的手写敏感字段
        # （日期/身份证/姓名/部门）缺失，再补跑 RapidOCR 并重新提取。
        # 这样「印刷文本层 + 手写图片值」的混合合同也能触发手写识别。
        res = self._finalize(doc, p)
        if self._need_rapid(doc, res, was_no_text):
            try:
                from .extractor.ocr_rapid import rapid_ocr_pdf
                if rapid_ok:
                    # V1.4.0：回退到当初「识别效果好」的高清全页模式。
                    # 之前为提速把 DPI 从 200 降到 150、又只扫首页，导致手写识别率
                    # 断崖下降（用户反馈"之前能认现在认不到"）。现在恢复：
                    # 用配置的完整 DPI(200) 和页数（前N页+末页），每页整页+锚点增强。
                    ocr_dpi = self.scan_ocr_dpi          # 恢复 200，不再压到 150
                    ocr_side = self.scan_ocr_max_side    # 恢复 2400，不再压到 1500

                    # V1.4.5 速度优化（准确度不变）：
                    # 逐页识别，每页先只做整页 OCR；只有当「仍未识别出的字段」
                    # 的锚点出现在本页时，才追加一次局部放大识别；字段齐了就停扫。
                    # 旧逻辑是每页无条件跑整页+增强、固定扫满前 N 页+末页，
                    # 三份合同约 90 秒；现在常见的合同 2~3 页即可完成。
                    from .extractor.ocr_rapid import FIELD_ANCHOR_WORDS
                    pages_text: dict[int, str] = {}
                    key_fields = ("乙方", "身份证号", "用工部门",
                                  "开始日期", "结束日期", "签订日期")
                    try:
                        import pymupdf as _mupdf
                        with _mupdf.open(str(p)) as _d:
                            _total = _d.page_count
                    except Exception:
                        _total = 0

                    def _decide(pi: int, page_text: str):
                        """返回 (本页是否值得局部增强, 是否还需要扫后续页)。"""
                        pages_text[pi] = page_text
                        merged = "\n".join(pages_text[k] for k in sorted(pages_text))
                        trial = self._with_text(
                            doc, ((doc.text or "") + "\n" + merged).strip(), status=DOC_OK)
                        rtrial = self._finalize(trial, p)
                        missing: set[str] = set()
                        for n in key_fields:
                            fr = rtrial.fields.get(n)
                            if (fr is None or not fr.value or fr.is_missing
                                    or fr.status in (ST_MISSING, ST_HEURISTIC)):
                                missing.add(n)
                        want = any(w in page_text for n in missing
                                   for w in FIELD_ANCHOR_WORDS.get(n, ()))
                        # 第二条第二点的锚点已在本页出现、仍没认出部门（手写太潦草），
                        # 说明手写值就在这一行，续页再扫也找不到——留给 Excel 贴图人工核对。
                        if (pi >= 1 and missing == {"用工部门"}
                                and any(a in page_text for a in
                                        ("（部门）", "部（室）", "部(室)", "部门）", "部门)"))):
                            return want, False
                        # 末页（签章页）已扫完就收尾：乙方/身份证在首页、部门在第二条、
                        # 签订日期在签章页，正文续页不会再出现这些字段，回头扫纯浪费。
                        # 但若到现在还没扫到「第二条」（版式特殊、封面占页），
                        # 说明岗位条款可能在后面的续页——继续按页序扫。
                        if _total and pi >= _total - 1:
                            if ("第二条" in merged or not missing
                                    or missing <= {"签订日期", "开始日期", "结束日期"}):
                                return want, False
                        return want, bool(missing)

                    rapid_text = clean_value(rapid_ocr_pdf(
                        p, dpi=ocr_dpi, max_side=ocr_side,
                        max_pages=self.scan_ocr_max_pages,
                        include_last=self.scan_ocr_include_last_page,
                        enhanced=True, decide=_decide,
                    ) or "")
                    if rapid_text:
                        doc.text = (doc.text + "\n" + rapid_text).strip()
                        doc.chars = len(doc.text.replace("\n", "").strip())
                        if len(doc.text.strip()) >= 20 and doc.status == DOC_NO_TEXT:
                            doc.status = DOC_OK
                        doc.note = (doc.note + " " if doc.note else "") + "已附加 RapidOCR 手写识别"
                        res = self._finalize(doc, p)  # 用补充后的文本重新提取
            except Exception:
                pass  # RapidOCR 是增强能力，绝不能影响主流程

        # V1.3.0 速度优化：截图不在扫描阶段做（那会拖慢预览），
        # 推迟到「确认执行导出 Excel」时按原始 PDF 现算（见 main_window._execute_worker）。
        return res

    @staticmethod
    def _with_text(doc, text: str, status: str | None = None):
        """浅拷贝 doc 并替换 text/chars，用于探测性提取而不改动原对象。

        status 可覆盖：探测 OCR 文本时要当成有文本层（DOC_OK），否则 _finalize
        会因 no_text_layer 短路把所有字段判为缺失，误触发无谓的局部增强。
        """
        import copy
        d = copy.copy(doc)
        d.text = text
        d.chars = len(text.replace("\n", "").strip())
        if status:
            d.status = status
        return d

    # 合同模式下这些字段通常是手写，OCR 印刷体引擎的盲区
    _HANDWRITING_TYPES = ("date", "idcard", "person_name", "enum")

    def _need_rapid(self, doc, res: ExtractResult, was_no_text: bool) -> bool:
        """是否值得补跑 RapidOCR 手写识别。

        扫描件（无文本层）总是跑；有文本层的混合合同只在手写字段缺失时跑，
        避免对电子版填写、字段齐全的合同白白增加耗时。
        """
        if not self.scan_rapid_enabled or self.mode != MODE_CONTRACT:
            return False
        if was_no_text:
            return True
        for f in self.fields:
            if f.type in self._HANDWRITING_TYPES:
                fr = res.fields.get(f.name)
                if fr is None or fr.is_missing:
                    return True
        return False

    def _finalize(self, doc, p: Path) -> ExtractResult:
        """基于 doc.text 做闸门 + 逐字段提取 + 派生年份，产出完整结果。"""
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

        # V1.3.0 合同模式专项后处理：
        # 1) 合同期限范围一次解析起止日期，纠正旧的错位（开始抓成结束年份）。
        if self.mode == MODE_CONTRACT:
            start, end = parse_duration_range(text)
            if start and end:
                for fname, val in (("开始日期", start), ("结束日期", end)):
                    fr = res.fields.get(fname)
                    # 仅当正则没可靠命中（缺失/启发式）或值明显不是完整日期时覆盖
                    if fr is not None and (fr.is_missing or fr.status == ST_HEURISTIC
                                           or len(re.findall(r"\d", fr.value)) < 8):
                        res.fields[fname] = FieldResult(
                            fname, val, val, ST_OK, "合同期限范围解析")
            # 2) 合同类型：显式标签/正则都没命中时，用标题+正文特征判定
            ctype = res.fields.get("合同类型")
            if ctype is not None and (ctype.is_missing or ctype.status == ST_HEURISTIC):
                detected = detect_contract_type(doc.head_text or text)
                if detected:
                    res.fields["合同类型"] = FieldResult(
                        "合同类型", detected, detected, ST_OK, "合同类型特征判定")
            # 3) 乙方姓名：开放集，宁缺毋滥。只在原字段缺失时用标签定位兜底，
            #    绝不覆盖已有值（曾把正则正确抓到的姓名覆盖成正文「声明已在签字」）。
            name_fr = res.fields.get("乙方")
            if name_fr is not None and name_fr.is_missing:
                detected_name = find_person_name(text)
                if detected_name:
                    res.fields["乙方"] = FieldResult(
                        "乙方", detected_name, detected_name, ST_FALLBACK, "乙方姓名兜底")
            # 4) 用工部门：7选1封闭集，全文直接匹配部门名，避免「（部门）后正文」误取
            dept_fr = res.fields.get("用工部门")
            if dept_fr is not None:
                detected_dept = find_department(text)
                if detected_dept and (dept_fr.is_missing or detected_dept != dept_fr.value):
                    res.fields["用工部门"] = FieldResult(
                        "用工部门", detected_dept, detected_dept, ST_OK, "用工部门7选1")

        # V1.2.0：派生「签订年份」——模板 {签订年份} 从「签订日期」取前 4 位。
        # 若用户显式定义了「签订年份」字段则跳过，避免覆盖。
        if "签订年份" not in res.fields:
            sign = res.fields.get("签订日期")
            year = ""
            if sign and sign.value:
                m = re.search(r"(?:19|20)\d{2}", sign.value)
                year = m.group(0) if m else ""
            res.fields["签订年份"] = FieldResult(
                "签订年份", year, year or self.missing_value,
                ST_OK if year else ST_MISSING, "" if year else "无法从签订日期派生年份")
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
