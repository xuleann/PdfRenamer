# -*- coding: utf-8 -*-
"""手写字段局部截图（V1.3.0，纯本地、低内存）。

对识别不佳的手写字段（乙方姓名 / 用工部门 / 签订日期 / 身份证号），
从 PDF 中把该字段「标签 + 手写值」所在的小块区域裁下来，压缩成很小的 PNG，
嵌入 Excel 汇总表对应单元格，方便用户对照原件人工核对。

设计约束：
- 低内存：只渲染命中标签所在页；灰度；限制最大边长；JPEG 压缩后转内存字节；
  每张图控制在几十 KB，一份合同最多几张，不撑爆 Excel。
- 纯本地：只用 PyMuPDF + Pillow，不联网、不调用任何模型。
- 定位：优先用文本层关键词矩形（page.search_for）；扫描件用 RapidOCR 词框兜底。
"""
from __future__ import annotations

import io
import re
from pathlib import Path

# 需要截图的字段 -> 定位关键词（按优先级）。负值/不存在时跳过。
FIELD_ANCHORS: dict[str, tuple[str, ...]] = {
    "乙方": ("乙方（签字）", "乙方(签字)", "乙方签字", "乙方签名", "乙方", "劳动者"),
    # V1.4.1：加上 7 个部门名本身作锚点——真实合同里部门常写成「在财务室（部门）」
    # 嵌在句子中，没有「用工部门：」标签；只靠标签词定位会失败、没截图。
    # OCR 认出任一部门名即可定位到那一行截图供人工核对。
    "用工部门": (
        # V1.4.4：把「只在第二条第二点出现」的特异写法放最前，并删掉过于宽泛的
        # 单字「岗」——旧锚点会先命中标题「第二条 工作岗位」，把标题截进单元格。
        "部（室）", "部(室)", "部（室", "部(室",
        "（部门）", "(部门)", "部门）", "部门)",
        "用工部门", "工作部门", "所属部门", "部门",
        "办公室", "财务室", "服务一部", "服务二部", "交通", "物业", "资产",
    ),
    "签订日期": ("签订日期", "签署日期", "签约日期", "签订时间", "签署时间"),
    "身份证号": ("身份证号码", "身份证号", "公民身份号码", "身份证"),
    "开始日期": ("合同期限", "起始日期", "开始日期", "合同期限自"),
    # 结束日期常与开始共用「合同期限」一句（自X至Y），找不到专属词就复用它，
    # 截到同一行即可看到起止两个日期，避免落到条带兜底截整页。
    "结束日期": ("截止日期", "结束日期", "终止日期", "合同期限至", "合同期限"),
}

# V1.3.1：各字段标签右侧要截取的宽度（pt）。身份证 18 位手写数字最宽，必须给足，
# 否则会像之前那样把号码截半截。其它字段保持紧凑。
# V1.3.6：裁剪宽度收窄——之前给 760/520pt 导致图片是 13:1 超宽长条，
# 嵌进 Excel 后被压扁看不清、或撑爆单元格。收紧到够放手写值的合理宽度。
_FIELD_WIDTH_PT: dict[str, float] = {
    "身份证号": 300,   # 18 位数字约 300pt 足够（配 OCR 词框实际值宽度）
    "乙方": 170,
    "用工部门": 180,
    "签订日期": 240,
    "开始日期": 300,
    "结束日期": 300,
}

# 压缩参数：灰度 + 限边长 + JPEG quality，控制单图体积
_MAX_SIDE = 500       # 图片最大边长（像素）：收窄裁剪后 500 足够看清手写
_JPEG_QUALITY = 60    # JPEG 质量（越小体积越小）
_CAP_BYTES = 80_000   # 单图目标上限（字节），超过则进一步降质/缩小

# V1.5.0：用工部门手写截图要「看清笔画」，单独提高分辨率与画质。
# 用工部门常写成「在___部（室）___岗」跨栏长条，旧参数（500px/q60/80KB）
# 会把笔画细节压糊；这里放宽到 1400px/q90/400KB，仍远小于整页图。
_HQ_FIELDS = ("用工部门",)
_HQ_MAX_SIDE = 1400
_HQ_JPEG_QUALITY = 90
_HQ_CAP_BYTES = 400_000

# V1.6.1：日期字段按「日期数字」定位，避免命中「第一条 合同期限」这类章节标题。
# 真实合同期限写法：「本合同自2023年5月30日起生效，至2026年5月29日终止」，
# 一行含两个日期：开始=第 1 个，结束=第 2 个。
_DATE_RE = re.compile(
    r"(?:19|20)\d{2}\s*[年/\-\.]\s*\d{1,2}\s*[月/\-\.]\s*\d{1,2}\s*日?"
    r"|(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月"
    r"|(?:19|20)\d{2}[/\-\.]\d{1,2}[/\-\.]\d{1,2}"
)
_DATE_FIELDS = ("开始日期", "结束日期", "签订日期")
# 字段在含多个日期的行里取第几个日期（0-based）；-1 = 取最后一个（落款日期）
_DATE_INDEX = {"开始日期": 0, "结束日期": 1, "签订日期": -1}


def _pick_date_span(spans: list, want_idx: int):
    """按索引取日期 span；want_idx=-1 表示取最后一个。"""
    if not spans:
        return None
    idx = want_idx if want_idx >= 0 else len(spans) - 1
    if idx >= len(spans):
        idx = 0
    return spans[idx]


# V1.6.2：开始/结束日期截图默认从「合同期限」标题下方提取。
# 真实合同结构：「第一条 劳动合同期限」标题行 → 紧接下一行是「自X年X月X日至Y年X月X日止」。
_TERM_KEYWORDS = ("合同期限", "劳动合同期限", "劳务合同期限", "合同有效期", "有效期")
_TERM_WINDOW_PT = 300   # 标题行下方多少 pt/px 内找日期（覆盖紧接的一两行）


def _term_header_y(rows) -> int | None:
    """从行列表里找「合同期限」类标题行的 y（取最靠上、且自身无日期的）。
    rows: [(y, text, ...)] 的序列。
    """
    cands = [y for y, text, *_ in rows
             if any(k in text for k in _TERM_KEYWORDS) and not _date_spans(text)]
    return min(cands) if cands else None


def _filter_rows_below_term(rows, header_y: int | None):
    """只保留标题行下方 _TERM_WINDOW 内、且含日期的行；无标题则保留全部日期行。
    rows: [(y, text, spans, ...)]
    """
    dated = [r for r in rows if r[2]]
    if not dated:
        return []
    if header_y is None:
        return dated
    near = [r for r in dated if header_y <= r[0] <= header_y + _TERM_WINDOW_PT]
    return near or dated   # 标题下方没找到则退回全页日期行（兼容）


def _date_spans(text: str) -> list[tuple[int, int]]:
    """返回文本中所有日期匹配的 (start, end) 字符位置。"""
    return [(m.start(), m.end()) for m in _DATE_RE.finditer(text or "")]


def _compress(pix, field_name: str = "") -> bytes:
    """把 PyMuPDF pixmap 渲染结果压成尽量小的图片字节（JPEG 内容，PNG 容器无关）。"""
    from PIL import Image
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img = img.convert("L")  # 灰度：手写黑字足够清晰，体积大幅下降
    hq = field_name in _HQ_FIELDS
    max_side = _HQ_MAX_SIDE if hq else _MAX_SIDE
    quality0 = _HQ_JPEG_QUALITY if hq else _JPEG_QUALITY
    cap = _HQ_CAP_BYTES if hq else _CAP_BYTES
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    quality = quality0
    for _ in range(4):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= cap:
            return data
        quality -= 12
        if quality < 25:
            # 仍过大则再缩小一半（高画质字段最多只缩一次，避免又糊回去）
            img = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.LANCZOS)
            quality = 30
    return data


def _crop_around_label(page, rect, page_rect, field_name: str = "") -> tuple:
    """给定标签矩形，算出「标签 + 右侧手写值」的紧凑裁剪区域。

    横向：从标签左缘略前开始，向右给该字段足够宽度（身份证最宽）；
    纵向：覆盖本行并略向上下延伸，避免带进无关行。
    """
    width_pt = _FIELD_WIDTH_PT.get(field_name, 300)
    x0 = max(page_rect.x0 + 2, rect.x0 - 6)
    x1 = min(page_rect.x1 - 2, rect.x1 + width_pt)
    y0 = max(page_rect.y0 + 2, rect.y0 - 6)
    line_h = max(16.0, rect.height * 1.6)
    y1 = min(page_rect.y1 - 2, rect.y1 + line_h)
    from pymupdf import Rect
    return Rect(x0, y0, x1, y1)


def _find_label_rects(page, keywords: tuple[str, ...]):
    """用文本层关键词定位标签矩形，返回按页面出现顺序的第一个命中。"""
    for kw in keywords:
        try:
            rects = page.search_for(kw)
        except Exception:
            rects = []
        if rects:
            # 取最靠上的命中（合同首页标签通常自上而下排布）
            return sorted(rects, key=lambda r: (r.y0, r.x0))[0]
    return None


def _find_date_rect(page, field: str):
    """V1.6.3：在文本层定位日期字段的「整行」裁剪矩形（对齐用户红框示例）。

    开始/结束日期：先找「合同期限」标题行，取其下方最近的日期整行；
    签订日期取页面最靠下的落款日期整行。返回该行的完整 bbox（略留白）。
    """
    if field not in _DATE_FIELDS:
        return None
    try:
        data = page.get_text("dict")
    except Exception:
        return None
    all_rows = []   # (y, 文本, spans, bbox)
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            txt = "".join(sp.get("text", "") for sp in line.get("spans", []))
            bbox = line.get("bbox", (0, 0, 0, 0))
            all_rows.append((bbox[1], txt, _date_spans(txt), bbox))
    if field == "签订日期":
        dated = [r for r in all_rows if r[2]]
        rows_sorted = sorted(dated, key=lambda x: -x[0])
    else:
        header_y = _term_header_y(all_rows)
        kept = _filter_rows_below_term(all_rows, header_y)   # 期限标题下方的日期行
        rows_sorted = sorted(kept, key=lambda x: -len(x[2]))
    if not rows_sorted:
        return None
    _y, _txt, _spans, (x0, y0, x1, y1) = rows_sorted[0]
    from pymupdf import Rect
    # 整行 bbox + 少量留白（对应红框框住整行）
    return Rect(max(0, x0 - 4), max(0, y0 - 3), x1 + 4, y1 + 3)


def _compress_pil(img, field_name: str = "") -> bytes:
    """把 PIL 图像压成灰度 JPEG 字节（用工部门字段走高画质参数）。"""
    from PIL import Image
    g = img.convert("L")
    hq = field_name in _HQ_FIELDS
    max_side = _HQ_MAX_SIDE if hq else _MAX_SIDE
    quality0 = _HQ_JPEG_QUALITY if hq else _JPEG_QUALITY
    cap = _HQ_CAP_BYTES if hq else _CAP_BYTES
    w, h = g.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    quality = quality0
    for _ in range(4):
        buf = io.BytesIO()
        g.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= cap:
            return data
        quality -= 12
        if quality < 25:
            g = g.resize((max(1, g.width // 2), max(1, g.height // 2)), Image.LANCZOS)
            quality = 30
    return data


def _crop_fields_on_words(img, words, fields: list[str]) -> dict[str, bytes]:
    """在一页的 OCR 词框里为各字段定位并裁剪，返回 {字段名: 图片字节}。"""

    def _norm(t: str) -> str:
        return re.sub(r"\s+", "", t)

    def _row_text(box) -> str:
        cy = (box[1] + box[3]) / 2.0
        tol = max(18.0, (box[3] - box[1]) * 0.9)
        return "".join(_norm(t) for (t, b) in words
                       if abs(((b[1] + b[3]) / 2.0) - cy) < tol)

    result: dict[str, bytes] = {}
    W, H = img.size

    # V1.6.5：识别「合同制用工计划申报审批表」这类横放汇总表页——
    # 它上面也有「身份证号」「部（室）名称」表头，锚点会先命中这页，
    # 导致截到竖排的错误区域（张艳东样本实测）。这类页对身份证/部门
    # 字段跳过，让定位落到后续正文页的正确位置。
    page_text = "".join(_norm(t) for (t, _b) in words)
    is_approval_sheet = (
        "申报审批表" in page_text
        or ("中心主任审批" in page_text and "部（室）名称" in page_text)
    )

    # V1.6.2：开始/结束日期只从「合同期限」标题下方找年月日。
    # 先收集所有行 (y, 文本, 日期spans, box)。
    all_rows = []
    for (t, box) in words:
        nt = _norm(t)
        all_rows.append((box[1], nt, _date_spans(nt), box))
    # 期限标题 y（开始/结束日期用）
    header_y = _term_header_y(all_rows)
    # V1.6.3：开始/结束日期必须有「合同期限」标题才截，否则封面日期会被误截
    if header_y is None:
        term_dated = []
    else:
        term_dated = _filter_rows_below_term(all_rows, header_y)
    # date_rows: (span_count, box, norm_text, spans)
    date_rows = [(len(spans), box, nt, spans) for (_y, nt, spans, box) in term_dated]
    date_rows.sort(key=lambda x: (-x[0], x[1][1]))

    for fi in fields:
        # V1.6.5：审批表页的「身份证号/部（室）名称」是表格表头，不是正文手写值，
        # 跳过本页，让定位落到后续正文页的正确位置。
        if is_approval_sheet and fi in ("身份证号", "用工部门"):
            continue
        # 签订日期走独立的落款定位（本页最靠下的日期整行），不依赖期限标题
        if fi == "签订日期":
            sign_rows = [(len(spans), box, nt, spans)
                         for (_y, nt, spans, box) in all_rows if spans]
            if sign_rows:
                sign_rows.sort(key=lambda x: -x[1][1])   # 最靠下
                _n, box, nt, spans = sign_rows[0]
                bx0, by0, bx1, by1 = box
                bw = max(1.0, bx1 - bx0)
                px0 = max(0, int(bx0 - bw * 0.02)); px1 = min(W, int(bx1 + bw * 0.02))
                lh = max(18.0, by1 - by0)
                py0 = max(0, int(by0 - lh * 0.25)); py1 = min(H, int(by1 + lh * 0.35))
                if px1 - px0 >= 20 and py1 - py0 >= 10:
                    data = _compress_pil(img.crop((px0, py0, px1, py1)), fi)
                    if data:
                        result[fi] = data
                continue
        # 开始/结束日期必须有「合同期限」标题才截，否则封面日期会被误截
        if fi in ("开始日期", "结束日期") and header_y is None:
            continue
        if fi in ("开始日期", "结束日期") and date_rows:
            placed = False
            # V1.6.3：按用户红框示例——直接截「合同期限标题下方的整行日期」，
            # 不再按字符比例切小块（那样在手写/竖排版式上会截错）。
            # 签订日期则取末页最靠下的落款日期整行。
            if fi == "签订日期":
                rows_for_field = sorted(date_rows, key=lambda x: -x[1][1])
            elif fi in ("开始日期", "结束日期"):
                rows_for_field = date_rows   # 期限标题下方的日期行
            else:
                rows_for_field = date_rows
            for span_count, box, nt, spans in rows_for_field:
                if not spans:
                    continue
                # 整行截图：横向覆盖整行（略缩两端），纵向覆盖整行并少量留白
                bx0, by0, bx1, by1 = box
                bw = max(1.0, bx1 - bx0)
                px0 = max(0, int(bx0 - bw * 0.02))
                px1 = min(W, int(bx1 + bw * 0.02))
                line_h = max(18.0, by1 - by0)
                py0 = max(0, int(by0 - line_h * 0.25))
                py1 = min(H, int(by1 + line_h * 0.35))
                if px1 - px0 < 20 or py1 - py0 < 10:
                    continue
                data = _compress_pil(img.crop((px0, py0, px1, py1)), fi)
                if data:
                    # 开始/结束共用同一整行（红框就是整行含两个日期）
                    result[fi] = data
                placed = True
                break
            if placed:
                continue

        anchors = FIELD_ANCHORS.get(fi, ())
        # 找含任一锚点的词框（取最靠上的）
        hit = None
        for a in anchors:
            cands = [box for (t, box) in words if a in _norm(t)]
            if not cands:
                continue
            for box in sorted(cands, key=lambda b: (b[1], b[0])):
                # V1.4.4：排除合同尾部「本合同一式叁份，甲乙双方及用人部（室）各执壹份」
                # ——它也含「部（室）」，会把条款末尾截进部门的单元格。
                if fi == "用工部门" and any(
                        x in _row_text(box) for x in ("用人部", "各执", "本合同一式")):
                    continue
                hit = box
                break
            if hit is not None:
                break
        if hit is None:
            continue
        x0, y0, x1, y1 = hit
        label_cy = (y0 + y1) / 2.0
        # 同一行(y 接近)的所有词框里，取标签右侧最远的值框右缘，
        # 这样无论手写值多宽都能完整截到，不受固定宽度估算误差影响。
        row_words = [b for (t, b) in words
                     if abs(((b[1] + b[3]) / 2.0) - label_cy) < max(18.0, (y1 - y0) * 0.9)]
        right_edge = x1
        left_edge = x0
        if fi == "用工部门":
            # 部门模板「在___部（室）___岗」有两处手写，分布在"部（室）"左右两侧。
            # 整行都截，才能同时看到部门和岗位的手写值。
            for b in row_words:
                left_edge = min(left_edge, b[0])
                right_edge = max(right_edge, b[2])
        else:
            for b in row_words:
                if b[0] >= x1 - 4:       # 在标签右侧
                    right_edge = max(right_edge, b[2])
        # 至少给一段最小宽度，避免标签后无值区域太窄看不清
        min_w = _FIELD_WIDTH_PT.get(fi, 200) * (W / 1000.0)
        right_edge = max(right_edge, x1 + min(180, max(80, min_w)))
        if fi == "用工部门":
            # 部门模板值跨越多列：向右多给一段，覆盖「部（室）___岗」右侧手写
            right_edge = max(right_edge, x1 + min(400, max(200, W * 0.35)))
        line_h = max(16.0, y1 - y0)
        cx0 = max(0, int(left_edge - 8))
        cx1 = min(W, int(right_edge + 14))
        cy0 = max(0, int(y0 - line_h * 0.4))
        cy1 = min(H, int(y1 + line_h * 0.9))
        if cx1 - cx0 < 20 or cy1 - cy0 < 10:
            continue
        region = img.crop((cx0, cy0, cx1, cy1))
        data = _compress_pil(region, fi)
        if data:
            result[fi] = data
    return result


def _crop_from_ocr_words(path, fields: list[str], *, dpi: int, max_side: int,
                         field_pages: dict[str, list[int]] | None = None) -> dict[str, bytes]:
    """扫描件兜底：用 RapidOCR 词框定位标签，裁剪其右侧/下方手写区域。

    扫描件没有文本层，page.search_for 永远找不到，必须用 OCR 的词坐标。

    V1.4.4（重要修复）：原来只 OCR 第 1 页，而「用工部门」在合同的第 2 页
    （第二条第二点），导致部门缺失时永远截不到图。现逐页定位，命中即止。

    V1.4.9：field_pages 可为指定字段限定搜索页（乙方固定第 1 页）。
    """
    result: dict[str, bytes] = {}
    field_pages = field_pages or {}
    try:
        from .ocr_rapid import rapid_locate_words
        import pymupdf

        with pymupdf.open(str(Path(path))) as doc:
            total = doc.page_count
        # 手写字段集中在正文前几页与末页签章页
        # V1.6.3：合同期限标题可能在第 4 页（如 xx11 样本在 p3），扩到前 4 页
        pages = list(range(min(4, total)))
        if total > 1 and (total - 1) not in pages:
            pages.append(total - 1)

        remaining = list(fields)
        # V1.5.0：含用工部门时用更高 dpi 渲染，给 hq 压缩留足原始像素
        ocr_dpi = max(dpi, 300) if any(f in _HQ_FIELDS for f in remaining) else dpi
        ocr_side = max(max_side, 2600) if any(f in _HQ_FIELDS for f in remaining) else max_side
        # V1.4.9：有页限制的字段（乙方=首页）单独先处理，避免被公共页序跳过
        limited = [f for f in remaining if f in field_pages]
        for fi in limited:
            for raw_pi in field_pages[fi]:
                pi = total - 1 if raw_pi == -1 else raw_pi   # V1.6.1：-1=末页
                if not (0 <= pi < total):
                    continue
                img, words = rapid_locate_words(path, dpi=ocr_dpi, max_side=ocr_side,
                                                page_index=pi)
                if img is None or not words:
                    continue
                found = _crop_fields_on_words(img, words, [fi])
                if fi in found:
                    result[fi] = found[fi]
                    break
        remaining = [f for f in remaining if f not in result]

        for pi in pages:
            if not remaining:
                break
            # 部门只在正文前几页找：末页签章区已有「用人部（室）各执壹份」这类干扰
            if pi not in (0, 1, 2) and all(f == "用工部门" for f in remaining):
                continue
            img, words = rapid_locate_words(path, dpi=ocr_dpi, max_side=ocr_side,
                                            page_index=pi)
            if img is None or not words:
                continue
            found = _crop_fields_on_words(img, words, remaining)
            if found:
                result.update(found)
                remaining = [f for f in remaining if f not in result]
    except Exception:
        pass
    return result


def _crop_first_page_bands(path, fields: list[str], *, dpi: int, max_side: int) -> dict[str, bytes]:
    """终极兜底：连 OCR 都定位不到时，把首页上部按横向条带切给各字段。

    保证"至少有一张截图进表格"，哪怕定位不精确——用户要的是能看到手写区域。
    """
    result: dict[str, bytes] = {}
    try:
        import pymupdf
        from PIL import Image
        with pymupdf.open(str(Path(path))) as doc:
            if doc.page_count == 0:
                return result
            page = doc.load_page(0)
            rect = page.rect
            scale = min(max(72, min(300, int(dpi))) / 72.0,
                        max(800, min(2600, int(max_side))) / max(rect.width, rect.height))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                  colorspace=pymupdf.csRGB, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        W, H = img.size
        # 只切窄横向带（约 4 行文字高），避免截出大方块撑爆单元格。
        # 在首页上部 8%~60% 区域内按字段数均匀放窄带。
        band_top, band_bottom = int(H * 0.08), int(H * 0.60)
        band_h = max(48, int(H * 0.055))  # 窄带固定高度
        step = (band_bottom - band_top) // max(1, len(fields))
        for i, fi in enumerate(fields):
            y0 = band_top + i * step
            y1 = min(band_bottom, y0 + band_h)
            region = img.crop((int(W * 0.05), y0, int(W * 0.90), y1))
            data = _compress_pil(region, fi)
            if data:
                result[fi] = data
    except Exception:
        pass
    return result


def crop_field_images(path: str | Path, fields: list[str], *,
                      dpi: int = 200, max_side: int = 2000,
                      field_pages: dict[str, list[int]] | None = None) -> dict[str, bytes]:
    """对给定字段列表，从 PDF 裁剪局部截图，返回 {字段名: 图片字节}。

    两条路径按优先级：
    1) 文本层关键词矩形（page.search_for）——文本层 PDF，快而准
    2) RapidOCR 词框定位——扫描件（无文本层）
    定位不到就不截图：截错位置（如截到「劳动合同书」标题）比没有截图更误导。

    V1.4.9：field_pages 可为指定字段限定搜索页（如乙方固定第 1 页）。
    """
    result: dict[str, bytes] = {}
    if not fields:
        return result
    try:
        import pymupdf
    except ImportError:
        return result
    field_pages = field_pages or {}
    remaining = list(fields)
    # 路径1：文本层
    try:
        with pymupdf.open(str(Path(path))) as doc:
            if doc.page_count == 0:
                return result
            total = doc.page_count
            pages = list(range(min(2, total)))
            if total - 1 not in pages:
                pages.append(total - 1)
            located: dict[str, tuple[int, object]] = {}
            for fi in remaining:
                # V1.6.1：日期字段先按日期数字定位（避开标题行）
                want_pages = field_pages.get(fi)
                # V1.6.1：-1 表示末页（签订日期默认末页签章区）
                resolved = [total - 1 if p == -1 else p for p in want_pages] if want_pages else None
                search_pages = ([p for p in resolved if 0 <= p < total]
                                if resolved else pages)
                rect = None
                if fi in _DATE_FIELDS:
                    for pi in search_pages:
                        rect = _find_date_rect(doc.load_page(pi), fi)
                        if rect is not None:
                            located[fi] = (pi, rect)
                            break
                    if fi in located:
                        continue
                anchors = FIELD_ANCHORS.get(fi, ())
                if not anchors:
                    continue
                # V1.4.9：乙方默认只在首页定位；其余字段按原有页序找锚点
                for pi in search_pages:
                    page = doc.load_page(pi)
                    rect = _find_label_rects(page, anchors)
                    if rect is not None:
                        located[fi] = (pi, rect)
                        break
            by_page: dict[int, list[str]] = {}
            for fi, (pi, _rect) in located.items():
                by_page.setdefault(pi, []).append(fi)
            base_zoom = max(1.0, min(2.5, float(dpi) / 72.0))
            for pi, fis in by_page.items():
                page = doc.load_page(pi)
                page_rect = page.rect
                for fi in fis:
                    if fi in _DATE_FIELDS:
                        # V1.6.1：日期 Rect 已经是按字符精确定位的日期本身，
                        # 只需略扩边界，不能再向右扩整列宽。
                        r = located[fi][1]
                        clip = pymupdf.Rect(
                            max(page_rect.x0, r.x0 - 4), max(page_rect.y0, r.y0 - 4),
                            min(page_rect.x1, r.x1 + 4), min(page_rect.y1, r.y1 + 4))
                    else:
                        clip = _crop_around_label(page, located[fi][1], page_rect, fi)
                    try:
                        # V1.5.0：用工部门要清晰度，渲染放大倍数提高到 4x，
                        # 让后续 hq 压缩（上限 1400px）有足够原始像素可用。
                        zoom = 4.0 if fi in _HQ_FIELDS else base_zoom
                        mat = pymupdf.Matrix(zoom, zoom)
                        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False,
                                              colorspace=pymupdf.csRGB)
                        data = _compress(pix, fi)
                        if data:
                            result[fi] = data
                    except Exception:
                        continue
            remaining = [f for f in remaining if f not in result]
    except Exception:
        pass
    # 路径2：扫描件 OCR 词框
    if remaining:
        ocr_result = _crop_from_ocr_words(path, remaining, dpi=dpi, max_side=max_side,
                                          field_pages=field_pages)
        result.update(ocr_result)
    # V1.3.9：不再用「首页条带兜底」——它会截到「劳动合同书」大标题，
    # 用户看到的是错的字段图，比没有截图更误导。定位不到就留空。
    return result
