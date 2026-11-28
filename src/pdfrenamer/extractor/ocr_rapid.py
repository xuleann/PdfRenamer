# -*- coding: utf-8 -*-
"""RapidOCR 手写体识别补强（V1.2.1，纯本地离线）。

Windows.Media.Ocr 是「印刷体」引擎，对手写体（签章日期、手写身份证号、
手写姓名、手写部门）几乎无能为力。本模块用 RapidOCR（ONNXRuntime 后端）
对「手写敏感字段」所在区域做局部裁剪 + 高清放大 + 预处理后二次识别。

设计约束（延续「零联网、零 AI、可纯离线」）：
- RapidOCR 是可选依赖：``try import``，缺失时优雅降级，绝不抛错影响主流程。
- 模型文件首次运行会自动缓存到包内；打包时预置到本地，保证纯离线可用。
- 所有临时数据都在内存中处理，绝不写用户目录。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

try:  # 可选依赖：未安装时 rapid_available() == False
    from rapidocr import RapidOCR
    _HAS_RAPID = True
except Exception:  # pragma: no cover - 依赖缺失或环境不兼容
    RapidOCR = None
    _HAS_RAPID = False

_ENGINE = None  # 进程内单例，避免每份 PDF 重复加载模型

# V1.6.4：页级 OCR 结果缓存——同一次运行中「提取」与「截图」会对同一页
# 重复渲染+OCR（实测占单份耗时约 38%）。这里缓存每页的渲染图与词框，
# 让截图直接复用提取阶段的结果，扫描提速明显。
# key = (绝对路径, 页索引)；只缓存最近 N 页，避免多文件处理时内存膨胀。
_PAGE_CACHE: dict[tuple[str, int], tuple] = {}
_PAGE_CACHE_MAX = 60   # V1.6.5：覆盖多份文件的页，截图阶段尽量命中缓存


def _page_cache_key(path, page_index: int, dpi: int = 0, max_side: int = 0
                    ) -> tuple[str, int, int, int]:
    """V1.7.5：缓存键必须带渲染参数，否则 200dpi 存的图会被 300dpi 请求取走，
    既拿不到清晰度又要重新渲染，是「时好时坏 + 慢」的根因之一。"""
    return (str(Path(path).resolve()), int(page_index), int(dpi), int(max_side))


def _page_cache_get(path, page_index: int, dpi: int = 0, max_side: int = 0):
    return _PAGE_CACHE.get(_page_cache_key(path, page_index, dpi, max_side))


def _page_cache_put(path, page_index: int, img, pairs,
                    dpi: int = 0, max_side: int = 0) -> None:
    if len(_PAGE_CACHE) >= _PAGE_CACHE_MAX:
        # 简单 FIFO：清掉最早的一批（dict 保序）
        for k in list(_PAGE_CACHE.keys())[:_PAGE_CACHE_MAX // 2]:
            _PAGE_CACHE.pop(k, None)
    _PAGE_CACHE[_page_cache_key(path, page_index, dpi, max_side)] = (img, pairs)


def clear_page_cache() -> None:
    """切换模式/换目录时可主动清空（截图与提取 dpi 不一致时也用它强制刷新）。"""
    _PAGE_CACHE.clear()


def rapid_available() -> bool:
    """RapidOCR 是否可用（依赖已装且引擎可实例化）。

    PDFRENAMER_NO_RAPID=1 时强制关闭，供自动化测试隔离 OCR 耗时。
    """
    if os.environ.get("PDFRENAMER_NO_RAPID") == "1":
        return False
    return _HAS_RAPID


def _get_engine():
    """惰性实例化 RapidOCR（首次调用加载模型，较慢）。失败返回 None。"""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    if not _HAS_RAPID:
        return None
    try:
        _ENGINE = RapidOCR()
        return _ENGINE
    except Exception:  # pragma: no cover
        return None


def rapid_ocr_image(image_path: str | Path) -> str:
    """对单张图片做 RapidOCR 识别，返回拼接文本；失败/不可用返回 ''。"""
    if not _HAS_RAPID:
        return ""
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        result = engine(str(image_path))
        txts = _txts_of(result)
        if isinstance(txts, str):
            return txts
        return "\n".join(str(t) for t in (txts or ()) if t)
    except Exception:  # pragma: no cover
        return ""


def _txts_of(result):
    """兼容不同 RapidOCR 版本的返回结构，取文本列表。"""
    txts = getattr(result, "txts", None)
    if txts is None and isinstance(result, dict):
        txts = result.get("txts")
    if txts is None and hasattr(result, "rec_texts"):
        txts = result.rec_texts
    return txts


def _boxes_of(result):
    boxes = getattr(result, "boxes", None)
    if boxes is None and isinstance(result, dict):
        boxes = result.get("boxes")
    return boxes


# ---------------------------------------------------------------------------
# 手写敏感字段的锚点：这些词附近往往就是需要手写识别的内容
# ---------------------------------------------------------------------------
_HANDWRITE_ANCHORS = (
    "身份证号码", "身份证号", "公民身份号码", "身份证编号", "身份证",
    "签订日期", "签署日期", "签约日期", "签订时间", "签署时间", "订立日期",
    "合同期限", "合同起止日期", "开始日期", "起始日期", "结束日期", "截止日期", "终止日期",
    "用工部门", "工作部门", "所属部门", "部门",
    "乙方签字", "乙方签名", "乙方（签字）", "乙方(签字)", "乙方", "劳动者", "受雇人",
)

# V1.4.5 速度优化：字段 -> 该字段可能出现的锚点词。
# 用于「这一页还值不值得做局部放大增强」——只有缺失字段的锚点在本页出现时才增强，
# 避免每页无条件跑两轮 OCR（增强轮约占单页耗时的一半）。
FIELD_ANCHOR_WORDS: dict[str, tuple[str, ...]] = {
    "乙方": ("乙方", "劳动者", "受雇人"),
    "身份证号": ("身份证",),
    "用工部门": ("部门", "用工部门", "工作部门", "所属部门",
                 "部（室）", "部(室)", "部（室", "部(室",
                 "（部门）", "(部门)", "部门）", "部门)"),
    "签订日期": ("签订日期", "签署日期", "签约日期", "签订时间", "签署时间", "订立日期"),
    "开始日期": ("合同期限", "开始日期", "起始日期", "合同起止日期"),
    "结束日期": ("结束日期", "截止日期", "终止日期", "合同期限"),
}


def find_handwrite_anchors(text: str) -> dict[str, list[int]]:
    """在（印刷体 OCR 或文本层）文本里定位手写敏感锚点的行号。

    返回 {锚点词: [行号列表]}。版式不固定，靠锚点行 + 其附近行来圈定手写区。
    """
    hits: dict[str, list[int]] = {}
    compact_lines = [re.sub(r"\s+", "", ln) for ln in text.splitlines()]
    for i, ln in enumerate(compact_lines):
        for a in _HANDWRITE_ANCHORS:
            if a in ln:
                hits.setdefault(a, []).append(i)
    return hits


# ---------------------------------------------------------------------------
# 图像预处理：放大 + 灰度 + 自动对比度，显著提升手写数字识别率
# ---------------------------------------------------------------------------
def _enhance_region(pil_img, scale: int = 2):
    """灰度 + 自动对比度 + 放大。只增强局部区域，速度可控。"""
    from PIL import Image, ImageEnhance, ImageOps
    g = pil_img.convert("L")
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(1.5)
    w, h = g.size
    return g.resize((w * scale, h * scale), Image.LANCZOS)


def _ocr_pil(engine, pil_img):
    """对 PIL 图像调用 RapidOCR，用 numpy 数组传入，返回 (txts, boxes)。"""
    import numpy as np
    arr = np.asarray(pil_img)
    result = engine(arr)
    return list(_txts_of(result) or ()), _boxes_of(result)


# ---------------------------------------------------------------------------
# V1.6.4：页面方向自动检测与校正。
# 有些扫描页整体被旋转 90/180/270°（横放倒置），直接 OCR 会认成乱码/竖排，
# 导致该页的字段（姓名/身份证/部门等）全部提取不到。这里在 OCR 前检测方向，
# 只在「正立方向得分过低」时才额外试其它角度，正常页零额外开销（不影响速度）。
# ---------------------------------------------------------------------------
_UPRIGHT_HINTS = (
    "甲方", "乙方", "身份", "合同", "期限", "姓名", "日期", "编号",
    "劳动", "劳务", "签字", "签订", "性别", "部门", "地址", "聘用",
    "条款", "工作", "地址", "生效", "终止",
)


def _orient_score(txts) -> int:
    """OCR 文本像不像「正立中文合同页」的评分。"""
    text = "".join(str(t) for t in (txts or ()))
    if not text:
        return 0
    score = sum(1 for h in _UPRIGHT_HINTS if h in text)
    # 中文字符数也计入（正立页能认出成段中文，旋转页多为乱码/单字）
    han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return score + min(4, han // 30)


def _ocr_page_auto_orient(engine, pil_img):
    """对页面图做 OCR，必要时自动转正。

    返回 (校正后的PIL图, txts, boxes, angle)。angle 为实际采用的旋转角（度，
    PIL rotate 的逆时针语义）。只在该页 0° 得分过低时才额外 OCR 其它角度，
    正常页只 OCR 一次——与优化扫描速度的目标一致。
    """
    txts, boxes = _ocr_pil(engine, pil_img)
    score0 = _orient_score(txts)
    if score0 >= 3:
        return pil_img, txts, boxes, 0
    # 正立得分低 → 逐个角度试（逆时针 90/180/270）
    best = (score0, pil_img, txts, boxes, 0)
    for angle in (90, 180, 270):
        try:
            rotated = pil_img.rotate(angle, expand=True, fillcolor="white")
            t, b = _ocr_pil(engine, rotated)
            s = _orient_score(t)
            if s > best[0]:
                best = (s, rotated, t, b, angle)
            if s >= 5:   # 足够像正立页，提前收敛，少试角度
                break
        except Exception:
            continue
    _s, img_up, t_up, b_up, angle = best
    return img_up, t_up, b_up, angle


def _boxes_to_pairs(txts, boxes) -> list[tuple[str, tuple]]:
    """把 RapidOCR 的原始 boxes 转成 (文字, (x0,y0,x1,y1)) 词框列表。"""
    pairs: list[tuple[str, tuple]] = []
    if boxes is None:
        return pairs
    for t, box in zip(txts or (), list(boxes)):
        try:
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
        except (IndexError, TypeError, ValueError):
            continue
        pairs.append((str(t), (min(xs), min(ys), max(xs), max(ys))))
    return pairs


def _dedup_preserve(seq) -> list[str]:
    """去重且保序（多轮识别会有重复文本）。"""
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        s = str(s).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _anchor_local_texts(engine, pil_img, txts, boxes) -> list[str]:
    """按锚点坐标裁剪值区域，纵向拼接成一张长图后**一次**放大识别。

    合同通常是「标签（印刷体）+ 值（手写）」结构。整页识别时手写值体小、
    与印刷字混在一起易漏；这里用锚点框定位值区域，拼图放大后一次识别，
    把多份局部 OCR 合并为一次，速度可控（每页仅多 1 次 OCR）。
    """
    if boxes is None or not txts:
        return []
    from PIL import Image
    W, H = pil_img.size
    try:
        box_list = list(boxes)
    except TypeError:
        return []
    regions = []
    for t, box in zip(txts, box_list):
        t = str(t)
        if not any(a in re.sub(r"\s+", "", t) for a in _HANDWRITE_ANCHORS):
            continue
        try:
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
        except (IndexError, TypeError, ValueError):
            continue
        if not xs or not ys:
            continue
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        row_h = max(10.0, y1 - y0)
        # 值区域：从锚点右缘向右扩到页面 55%，纵向覆盖本行并略向上下延伸
        crop_x0 = max(0.0, x0 - 8)
        crop_x1 = min(float(W), x1 + W * 0.55)
        crop_y0 = max(0.0, y0 - row_h * 0.35)
        crop_y1 = min(float(H), y1 + row_h * 0.75)
        if crop_x1 - crop_x0 < 10 or crop_y1 - crop_y0 < 6:
            continue
        regions.append(pil_img.crop((int(crop_x0), int(crop_y0),
                                     int(crop_x1), int(crop_y1))))
    if not regions:
        return []
    # 纵向拼接：统一宽度，白色间隙分隔，避免相邻区域文字粘连
    pad = 12
    strip_w = max(r.width for r in regions)
    strip_h = sum(r.height for r in regions) + pad * (len(regions) - 1)
    strip = Image.new("RGB", (strip_w, strip_h), "white")
    y = 0
    for r in regions:
        strip.paste(r, (0, y))
        y += r.height + pad
    enhanced = _enhance_region(strip, scale=3)
    sub_txts, _ = _ocr_pil(engine, enhanced)
    return [str(s) for s in sub_txts if s]


# V1.4.8：用工部门专项补识别。
# 真实样本里手写「交通服务」在整页 OCR 里被认成「之」，但把「第二条第二点」
# 那行的手写区裁出来、放大 4 倍并做二值化后，能稳定认出「交通」。
# 只在「本页含（部门）/部（室）锚点、却没认出七个部门名之一」时调用，
# 不增加正常合同的耗时。
_DEPT_NAMES = ("办公室", "财务室", "交通", "物业", "服务一部", "服务二部", "资产")
_DEPT_ANCHOR_HINTS = ("部（室", "部(室", "（部门", "(部门", "部门）", "部门)")


def _binarize(pil_img):
    """灰度 + 自动对比度 + 二值化（手写笔画细，二值化后轮廓更清楚）。"""
    from PIL import ImageOps
    g = ImageOps.autocontrast(pil_img.convert("L"), cutoff=1)
    return g.point(lambda v: 255 if v > 165 else 0).convert("RGB")


def _recognize_single_line(engine, pil_img) -> list[str]:
    """V1.6.5（提速）：对已定位的单行局部图直接识别，跳过文字检测。

    RapidOCR 的 detect_and_crop（检测）单页约 0.5s，而 recognize_txt（仅识别）
    单行约 0.01s。部门手写值所在的局部裁剪是已知单行，无需再做检测。
    失败时回退到常规 _ocr_pil，保证兼容性。
    """
    try:
        import numpy as np
        out = engine.recognize_txt([np.asarray(pil_img.convert("RGB"))])
        return [str(s) for s in (getattr(out, "txts", None) or ()) if s]
    except Exception:
        try:
            sub, _ = _ocr_pil(engine, pil_img)
            return [str(s) for s in sub if s]
        except Exception:
            return []


def _dept_zoom_texts(engine, pil_img, txts, boxes) -> list[str]:
    """裁「在___部（室）/（部门）」那行的手写区，放大+二值化后识别。

    返回多次识别的文本片段（含少量噪声），交给 rules.find_department 做封闭集匹配。
    """
    if boxes is None or not txts:
        return []
    out: list[str] = []
    from PIL import Image
    for t, box in zip(txts, boxes):
        norm = re.sub(r"\s+", "", str(t))
        if not any(k in norm for k in _DEPT_ANCHOR_HINTS):
            continue
        try:
            # box 有两种来源：整页 OCR 返回四点坐标 [(x,y)...]，
            # 定位函数返回矩形 (x0,y0,x1,y1)。两种都要能吃下。
            x0, y0, x1, y1 = (float(box[0]), float(box[1]),
                              float(box[2]), float(box[3]))
        except (IndexError, TypeError, ValueError):
            try:
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
            except (IndexError, TypeError, ValueError):
                continue
        W, H = x1 - x0, y1 - y0
        if W < 40 or H < 8:
            continue
        # 手写值在「在」与「部（室）」之间；按行宽比例多试几个窗口
        # V1.6.5：局部是已知单行，改用 recognize_txt 直接识别（跳过检测），
        # 实测 5 份样本识别率不变、OCR 检测次数减少约 20%。
        # 认出部门（或「交通」特征字「通」）立即早停。
        for lo, hi in ((0.46, 0.74), (0.52, 0.80), (0.40, 0.70)):
            crop = pil_img.crop((int(x0 + W * lo), int(y0 - H * 0.35),
                                 int(x0 + W * hi), int(y1 + H * 0.35)))
            if crop.width < 20 or crop.height < 8:
                continue
            big = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
            for proc in (_binarize(big), big):
                got = _recognize_single_line(engine, proc)
                out.extend(got)
                # 认到部门名（或「交通」的特征字「通」）就停，不必把所有组合试完
                flat = "".join(re.sub(r"\s+", "", x) for x in got)
                if any(d in flat for d in _DEPT_NAMES):
                    return out
                if "通" in flat and not any(w in flat for w in ("通知", "通行", "通信")):
                    return out
    return out


# ---------------------------------------------------------------------------
# PDF 级：高清渲染 → 整页识别 + 锚点局部增强识别 → 合并去重
# ---------------------------------------------------------------------------
def rapid_ocr_pdf(path: str | Path, *, dpi: int = 300, max_side: int = 2400,
                  pages: list[int] | None = None, max_pages: int = 0,
                  include_last: bool = True, enhanced: bool = True,
                  decide=None, start_page: int = 0) -> str:
    """把 PDF 指定页渲染成图后用 RapidOCR 识别，返回全文。

    V1.2.1：默认开启 enhanced——除了整页原图识别，还做「锚点局部放大」增强。
    V1.4.5：新增 decide 回调实现「按需增强 + 早停」，准确度不变、耗时大幅下降：
        decide(page_index, page_text) -> (want_enhance, need_more)
        · want_enhance=False：本页整页已拿到所需字段，跳过局部放大（省约一半时间）
        · need_more=False：字段已齐，不再扫后续页
        页序也改为「第1页 → 第2页 → 末页 → 其余页」，关键页优先。

    失败或依赖缺失时返回 ''，由调用方决定是否降级。
    """
    if not _HAS_RAPID:
        return ""
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        import pymupdf
        from PIL import Image
        texts: list[str] = []
        dept_zoom_done = False   # 部门专项补识别每份文件只跑一次，控制总耗时
        with pymupdf.open(str(Path(path))) as doc:
            total = doc.page_count
            # V1.7.0：start_page 是合同正文首页（跳过前面的审批表/说明页）。
            # 所有页索引都从它起算；末页（-1）仍是真末页（签章页）。
            sp = max(0, min(int(start_page or 0), max(0, total - 1)))
            if pages:
                # -1 表示末页（签章页），其余按原索引；去重且保序
                idx = []
                for i in pages:
                    real = (total - 1) if i == -1 else i
                    if 0 <= real < total and real not in idx:
                        idx.append(real)
            elif max_pages > 0:
                idx = list(range(sp, min(sp + max_pages, total)))
                if include_last and total > 0 and (total - 1) not in idx:
                    idx.append(total - 1)
            else:
                idx = list(range(sp, total))
            # V1.4.5：关键页优先——合同首页（乙方/身份证）、次页（第二条第二点部门，
            # 往往还有合同期限）、末页（签章页手写签订日期）。正文续页放最后，
            # 配合 decide 早停，字段齐了就不用白扫续页。
            if decide is not None and len(idx) > 2:
                head = [i for i in (sp, sp + 1, total - 1) if i in idx]
                idx = head + [i for i in idx if i not in head]
            for i in idx:
                page = doc.load_page(i)
                rect = page.rect
                scale = min(max(72, min(300, int(dpi))) / 72.0,
                            max(800, min(2600, int(max_side))) / max(rect.width, rect.height))
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                      colorspace=pymupdf.csRGB, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                # pass 1：整页原图（V1.6.4 自动转正后再 OCR）
                img, t1, boxes, _angle = _ocr_page_auto_orient(engine, img)
                # V1.6.4：把本页图/词框写入缓存，供后续截图复用（免二次 OCR）
                _page_cache_put(path, i, img, _boxes_to_pairs(t1, boxes),
                                dpi, max_side)
                page_text = "\n".join(t1)
                texts.extend(t1)
                want_enhance, need_more = True, True
                if decide is not None:
                    try:
                        want_enhance, need_more = decide(i, page_text)
                    except Exception:
                        want_enhance, need_more = True, True
                # pass 2：锚点局部拼接放大增强（只在本页确实有缺失字段的锚点时跑）
                if enhanced and want_enhance:
                    extra = _anchor_local_texts(engine, img, t1, boxes)
                    # 部门专项补识别：有「（部门）/部（室）」但七个部门名一个都没认出来
                    page_joined = "".join(re.sub(r"\s+", "", x) for x in t1)
                    if (not dept_zoom_done
                            and "第二条" in page_joined
                            and any(k in page_joined for k in _DEPT_ANCHOR_HINTS)
                            and not any(d in page_joined for d in _DEPT_NAMES)):
                        dept_zoom_done = True
                        zoom = _dept_zoom_texts(engine, img, t1, boxes)
                        if zoom:
                            extra = list(extra or []) + zoom
                            # 七个部门里只有「交通」带「通」字。手写「交通」的「交」
                            # 常被认成「之/这/文」，但「通」几乎总能认出来——据此补一条
                            # 结构化线索，交给 find_department 的标签分支精确命中。
                            zoom_flat = "".join(re.sub(r"\s+", "", x) for x in zoom)
                            if "通" in zoom_flat and not any(
                                    w in zoom_flat for w in ("通知", "通行", "通信")):
                                extra.append("用工部门：交通")
                    if extra:
                        texts.extend(extra)
                        if decide is not None and need_more:
                            # 增强后重新判定：字段可能已补齐，不必再扫后续页
                            try:
                                _, need_more = decide(i, page_text + "\n" + "\n".join(extra))
                            except Exception:
                                pass
                if decide is not None and not need_more:
                    break
        return "\n".join(_dedup_preserve(texts))
    except Exception:  # pragma: no cover
        return ""


def rapid_locate_words(path: str | Path, *, dpi: int = 150, max_side: int = 1600,
                       page_index: int = 0) -> tuple:
    """OCR 指定页，返回 (PIL.Image, [(文字, 坐标框), ...])。

    供截图定位用：扫描件没有文本层坐标，只能靠 OCR 词框。
    坐标是渲染图上的像素坐标（与返回的 Image 尺寸一致）。
    失败返回 (None, [])。
    """
    if not _HAS_RAPID:
        return None, []
    engine = _get_engine()
    if engine is None:
        return None, []
    # V1.6.4：复用提取阶段缓存的页图/词框，免于重复渲染+OCR
    cached = _page_cache_get(path, page_index, dpi, max_side)
    if cached is not None:
        return cached
    try:
        import pymupdf
        from PIL import Image
        with pymupdf.open(str(Path(path))) as doc:
            if page_index < 0 or page_index >= doc.page_count:
                return None, []
            page = doc.load_page(page_index)
            rect = page.rect
            scale = min(max(72, min(300, int(dpi))) / 72.0,
                        max(800, min(2600, int(max_side))) / max(rect.width, rect.height))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                  colorspace=pymupdf.csRGB, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            # V1.6.4：翻转页自动转正，保证定位与截图都是正立方向
            img, txts, boxes, _angle = _ocr_page_auto_orient(engine, img)
            pairs = []
            if boxes is not None:
                for t, box in zip(txts or (), list(boxes)):
                    try:
                        xs = [float(p[0]) for p in box]
                        ys = [float(p[1]) for p in box]
                    except (IndexError, TypeError, ValueError):
                        continue
                    pairs.append((str(t), (min(xs), min(ys), max(xs), max(ys))))
            _page_cache_put(path, page_index, img, pairs, dpi, max_side)
            return img, pairs
    except Exception:  # pragma: no cover
        return None, []


def rapid_ocr_pdf_aggressive(path: str | Path, *, dpi: int = 200, max_side: int = 2400,
                             page_index: int = 0) -> str:
    """无锚点兜底：整页放大 + 灰度 + 二值化后 OCR，专攻整页漏掉的小字/手写。

    当常规识别（含锚点局部增强）后手写字段仍缺失时使用——不依赖任何标签识别，
    纯靠提升整图清晰度多认一遍。失败返回 ''。
    """
    if not _HAS_RAPID:
        return ""
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        import pymupdf
        from PIL import Image, ImageOps, ImageEnhance
        with pymupdf.open(str(Path(path))) as doc:
            if page_index < 0 or page_index >= doc.page_count:
                return ""
            page = doc.load_page(page_index)
            rect = page.rect
            scale = min(max(72, min(300, int(dpi))) / 72.0,
                        max(800, min(2600, int(max_side))) / max(rect.width, rect.height))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                  colorspace=pymupdf.csRGB, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            # V1.6.4：翻转页先转正，再增强识别
            img, _t, _b, _angle = _ocr_page_auto_orient(engine, img)
        # 放大2x + 灰度 + 自动对比度 + 二值化（三种变体各认一遍，合并）
        texts: list[str] = []
        base = img.convert("L")
        big = base.resize((base.width * 2, base.height * 2), Image.LANCZOS)
        variants = [
            ImageOps.autocontrast(big, cutoff=1),
            ImageEnhance.Contrast(ImageOps.autocontrast(big, cutoff=2)).enhance(1.8),
            big.point(lambda x: 0 if x < 160 else 255),
        ]
        for v in variants:
            t, _ = _ocr_pil(engine, v.convert("RGB"))
            texts.extend(t or ())
        return "\n".join(_dedup_preserve(texts))
    except Exception:  # pragma: no cover
        return ""


# ---------------------------------------------------------------------------
# V1.7.0：合同起始页定位。
# 有些合同 PDF 前面夹了别的页（如「用工计划申报审批表」「封面/说明页」），
# 真正的合同从「劳动合同书 / 劳务合同书」标题页开始。若从第一页起识别，
# 前置页的单位名、姓名、日期会污染字段（乙方取错、日期取错）。
# 这里先定位标题页，后续文本层提取、OCR、截图都从该页起算。
# ---------------------------------------------------------------------------
_TITLE_PATTERNS = (
    re.compile(r"劳\s*动\s*合\s*同\s*书"),
    re.compile(r"劳\s*务\s*合\s*同\s*书"),
    re.compile(r"劳\s*动\s*合\s*同\s*(?:文本|范本)?", re.I),
)


def _is_contract_title(text: str) -> bool:
    """短标题行才算数；正文里提到「劳动合同书」不算标题页。"""
    for line in (text or "").splitlines()[:12]:
        s = re.sub(r"\s+", "", line).strip("：: 　·-—")
        if not s or len(s) > 18:
            continue
        for pat in _TITLE_PATTERNS:
            if pat.search(s):
                return True
    return False


def find_contract_start_page(path: str | Path, *, dpi: int = 110,
                             max_side: int = 1400, max_scan: int = 4,
                             text: str = "") -> int:
    """返回「劳动合同书」标题所在页索引（0 起）；找不到返回 0。

    - 有文本层：直接逐页 get_text（快，无 OCR）；外部传入 text 时可复用作粗判。
    - 无文本层：低 dpi 逐页 OCR，只认标题行，命中即停。
    - 前置页（审批表/说明页）一律跳过，返回其后的合同首页。
    """
    try:
        import pymupdf
        with pymupdf.open(str(Path(path))) as doc:
            total = doc.page_count
            if total <= 0:
                return 0
            limit = min(max_scan, total)
            # 路径1：文本层
            for i in range(limit):
                try:
                    page_text = doc.load_page(i).get_text("text")
                except Exception:
                    continue
                if _is_contract_title(page_text):
                    return i
            # 路径2：扫描件低清 OCR（只为找标题，不追求字段名）
            if not _HAS_RAPID or not _get_engine():
                return 0
            for i in range(limit):
                hit = rapid_ocr_pdf(path, dpi=dpi, max_side=max_side,
                                    pages=[i], enhanced=False)
                if _is_contract_title(hit):
                    return i
    except Exception:
        return 0
    return 0


# ---------------------------------------------------------------------------
# V1.7.0：乙方姓名专项补识别。
# 手写签名在整页 OCR 里常只认出第一个字（如「高」），而 find_person_name
# 要求 2~8 字，导致字段直接判空。这里把「乙方：___」标签右侧的值区裁出、
# 放大 + 二值化多次识别，取最长的纯中文候选补回姓名。
# ---------------------------------------------------------------------------
_NAME_ANCHORS = ("乙方（签字）", "乙方(签字)", "乙方签字", "乙方签名", "乙方")
_NAME_BAD_WORDS = ("本人", "接受", "履行", "合同", "签字", "盖章", "声明", "承诺",
                   "同意", "根据", "需要", "工作", "岗位", "规定", "按时", "准时",
                   "劳动", "劳务", "甲乙", "双方", "以下", "如下", "期限", "签订",
                   "点明", "须依", "依照", "办理", "执行", "完成", "服从")


def rapid_recover_name(path: str | Path, *, page_index: int = 0,
                       dpi: int = 200, max_side: int = 2400) -> str:
    """定位「乙方：」标签右侧手写值，放大+二值化识别，返回最可信姓名。"""
    if not _HAS_RAPID or not _get_engine():
        return ""
    try:
        from PIL import Image, ImageOps
        img, words = rapid_locate_words(path, dpi=dpi, max_side=max_side,
                                        page_index=page_index)
        if img is None or not words:
            return ""
        box = None
        for t, b in words:
            flat = re.sub(r"\s+", "", str(t))
            if any(a in flat for a in _NAME_ANCHORS) and len(flat) <= 24:
                box = b
                break
        if box is None:
            return ""
        x0, y0, x1, y1 = (float(box[0]), float(box[1]),
                          float(box[2]), float(box[3]))
        W, H = img.size
        # 值区从标签右侧开始，向右给足手写宽度
        crop_x0 = max(0, int(x0 + (x1 - x0) * 0.42))
        crop_x1 = min(W, int(x1 + 300))
        cy0, cy1 = max(0, int(y0 - H * 0.02)), min(H, int(y1 + H * 0.03))
        if crop_x1 - crop_x0 < 20:
            return ""
        crop = img.crop((crop_x0, cy0, crop_x1, cy1))
        engine = _get_engine()
        candidates: list[str] = []
        for scale in (3, 4):
            big = crop.resize((crop.width * scale, crop.height * scale),
                              Image.LANCZOS)
            variants = (big, _binarize(big),
                        ImageOps.autocontrast(big.convert("L")).convert("RGB"))
            for proc in variants:
                try:
                    txts, _ = _ocr_pil(engine, proc)
                except Exception:
                    continue
                for s in txts:
                    cand = re.sub(r"[^一-龥·]", "", str(s))
                    if not cand or any(w in cand for w in _NAME_BAD_WORDS):
                        continue
                    # 姓名 2~4 字最常见；更长的多为正文串入
                    if 2 <= len(cand) <= 5:
                        candidates.append(cand)
        if not candidates:
            return ""
        # 取出现次数最多、其次最长的候选
        from collections import Counter
        counts = Counter(candidates)
        return sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# V1.7.0：合同期限日期专项识别。
# 截图能定位到「合同期限」下方日期整行，但全文 OCR 的日期值偶有偏差
# （年/月认错、取到别处日期）。这里按截图同样的定位规则找到那一行，
# 局部放大 + 二值化再识别，用这一行的结果解析起止日期。
# ---------------------------------------------------------------------------
_TERM_ANCHORS = ("合同期限", "劳动合同期限", "劳务合同期限", "合同有效期")
_DATE_CHARS = re.compile(r"[0-9０-９一二三四五六七八九十百千零〇年/月.\-—~至到起止]")


def _parse_dates_from_line(line: str) -> tuple[str, str]:
    """从一行 OCR 文本解析 (开始, 结束)，返回 YYYY-MM-DD。"""
    t = re.sub(r"\s+", "", line)
    t = t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    # OCR 常把「年」认成「日/目」、「月」认成「区」
    t = re.sub(r"(?<=\d)\s*[日目]\s*(?=\d{1,2}\s*[月区])", "年", t)
    t = re.sub(r"(?<=\d)\s*[区囗]\s*(?=\d{1,2}\s*日)", "月", t)
    token = r"((?:19|20)\d{2})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})"
    def iso(g):
        try:
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
            return f"{y:04d}-{mo:02d}-{d:02d}" if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31 else ""
        except Exception:
            return ""
    starts = list(re.finditer(r"(?:自|从)\s*" + token, t))
    if starts:
        s = starts[0]
        e = re.search(r"(?:至|到|截止|终止|止)\s*" + token, t[s.end():])
        if e:
            a, b = iso(s.groups()), iso(e.groups())
            if a and b:
                return a, b
    # 紧凑范围
    m = re.search(token + r"\s*(?:—|－|-|~|～|至|到|起)\s*" + token, t)
    if m:
        a, b = iso(m.groups()[:3]), iso(m.groups()[3:6])
        if a and b:
            return a, b
    return "", ""


def rapid_recover_dates(path: str | Path, *, page_index: int = 0,
                        dpi: int = 200, max_side: int = 2400) -> tuple[str, str]:
    """定位合同期限标题下方的日期行，局部放大识别并返回 (开始, 结束)。"""
    if not _HAS_RAPID or not _get_engine():
        return "", ""
    try:
        from PIL import Image, ImageOps
        img, words = rapid_locate_words(path, dpi=dpi, max_side=max_side,
                                        page_index=page_index)
        if img is None or not words:
            return "", ""
        W, H = img.size
        header_y = None
        for t, b in words:
            flat = re.sub(r"\s+", "", str(t))
            if any(a in flat for a in _TERM_ANCHORS) and not re.search(r"\d{4}\s*[年/\-]", flat):
                header_y = float(b[3])
                break
        candidates = []
        for t, b in words:
            flat = re.sub(r"\s+", "", str(t))
            if not re.search(r"\d{4}\s*[年/\-.]\s*\d{1,2}", flat):
                continue
            y0 = float(b[1])
            if header_y is not None and y0 < header_y - 12:
                continue
            candidates.append((y0, b, flat))
        if not candidates:
            return "", ""
        candidates.sort(key=lambda x: x[0])
        # 标题下方最近的 1~2 行就够了
        for _y, b, _flat in candidates[:2]:
            x0, y0, x1, y1 = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            crop = img.crop((max(0, int(x0 - 10)), max(0, int(y0 - 8)),
                             min(W, int(x1 + 30)), min(H, int(y1 + 8))))
            if crop.width < 20 or crop.height < 8:
                continue
            big = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
            texts = []
            for proc in (big, _binarize(big),
                         ImageOps.autocontrast(big.convert("L")).convert("RGB")):
                try:
                    t2, _ = _ocr_pil(_get_engine(), proc)
                except Exception:
                    continue
                texts.extend(t2 or ())
            for line in texts:
                a, b2 = _parse_dates_from_line(str(line))
                if a and b2:
                    return a, b2
        return "", ""
    except Exception:
        return ""


def rapid_name_from_prefix_pages(path: str | Path, *, start_page: int,
                                 dpi: int = 180, max_side: int = 2000) -> str:
    """从合同前面的登记表页取清晰姓名（「姓名」独占行，下一行是值）。

    有些合同第一页是「合同期满考核登记表」，姓名/部门是打印或填写清晰的，
    而正文签名页手写潦草 OCR 错乱。前置页的姓名可作更可靠的来源。
    """
    if start_page <= 0 or not _HAS_RAPID or not _get_engine():
        return ""
    try:
        for pi in range(0, min(start_page, 4)):
            t = rapid_ocr_pdf(path, dpi=dpi, max_side=max_side,
                              pages=[pi], enhanced=False)
            lines = [re.sub(r"\s+", "", ln) for ln in (t or "").splitlines()]
            for i, ln in enumerate(lines[:40]):
                if ln in ("姓名", "姓名：", "名字") and i + 1 < len(lines):
                    val = re.sub(r"[^一-龥]", "", lines[i + 1])
                    if 2 <= len(val) <= 4 and not any(
                            w in val for w in ("性别", "民族", "出生", "部门", "岗位")):
                        # 常见形近字纠正（手写/OCR 高频）：镱→镜 等
                        val = val.replace("镱", "镜").replace("競", "镜")
                        return val
    except Exception:
        return ""
    return ""


def rapid_department_from_prefix_pages(path: str | Path, *, start_page: int,
                                       dpi: int = 180, max_side: int = 2000) -> str:
    """从前置登记表页取「部门：XX」——正文手写部门常认不出，登记表更清晰。"""
    if start_page <= 0 or not _HAS_RAPID or not _get_engine():
        return ""
    try:
        for pi in range(0, min(start_page, 4)):
            t = rapid_ocr_pdf(path, dpi=dpi, max_side=max_side,
                              pages=[pi], enhanced=False)
            for ln in (t or "").splitlines():
                flat = re.sub(r"\s+", "", ln)
                m = re.match(r"^(?:所在)?部门[:：]?(.{2,12})$", flat)
                if m:
                    val = m.group(1)
                    for dept in ("服务一部", "服务二部", "办公室", "财务室", "交通", "物业", "资产"):
                        if dept in val or (dept == "资产" and "资产" in val):
                            return dept
                    if "服务二部" in val:
                        return "服务二部"
    except Exception:
        return ""
    return ""


def rapid_recover_sign_date(path: str | Path, *, page_index: int = -1,
                            dpi: int = 200, max_side: int = 2400) -> str:
    """定位签章页手写落款日期（页面上最靠下的完整日期行），返回 YYYY-MM-DD。

    签订日期不能取封面的「制表日期」（如 2022年1月），也不能取合同期限；
    必须以末页签章区的手写落款为准。
    """
    if not _HAS_RAPID or not _get_engine():
        return ""
    try:
        import pymupdf
        from PIL import Image, ImageOps
        with pymupdf.open(str(Path(path))) as doc:
            total = doc.page_count
            pi = (total - 1) if page_index < 0 else min(page_index, total - 1)
        img, words = rapid_locate_words(path, dpi=dpi, max_side=max_side,
                                        page_index=pi)
        if img is None or not words:
            return ""
        W, H = img.size
        token = r"((?:19|20)\d{2})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})"
        dated = []
        for t, b in words:
            flat = re.sub(r"\s+", "", str(t))
            # 落款常被拆成「2025年」「月」「29」「日」多个词框；
            # 先直接解析词框文本本身，命中就返回（最可靠）。
            m0 = re.search(token, flat)
            if m0:
                try:
                    yy, mo, dd = int(m0.group(1)), int(m0.group(2)), int(m0.group(3))
                    if 1900 <= yy <= 2100 and 1 <= mo <= 12 and 1 <= dd <= 31:
                        # 词框本身就是完整日期，直接记住值；后续放大 OCR 只作兜底
                        dated.append((float(b[3]), b, f"{yy:04d}-{mo:02d}-{dd:02d}"))
                except Exception:
                    pass
        if not dated:
            return ""
        dated.sort(key=lambda x: x[0], reverse=True)   # 最靠下 = 落款日期
        # 最靠下的完整词框日期就是落款，直接返回
        if dated:
            return dated[0][2]
        for _y, b in dated[:4]:
            x0, y0, x1, y1 = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            crop = img.crop((max(0, int(x0 - 12)), max(0, int(y0 - 10)),
                             min(W, int(x1 + 40)), min(H, int(y1 + 10))))
            if crop.width < 20 or crop.height < 8:
                continue
            big = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
            texts = []
            for proc in (big, _binarize(big),
                         ImageOps.autocontrast(big.convert("L")).convert("RGB")):
                try:
                    t2, _ = _ocr_pil(_get_engine(), proc)
                except Exception:
                    continue
                texts.extend(t2 or ())
            for line in texts:
                # 落款是单个日期，直接解析，不走「自…至…」区间解析
                t = re.sub(r"\s+", "", str(line)).translate(
                    str.maketrans("０１２３４５６７８９", "0123456789"))
                m = re.search(token, t)
                if m:
                    try:
                        yy, mo, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
                        if 1900 <= yy <= 2100 and 1 <= mo <= 12 and 1 <= dd <= 31:
                            return f"{yy:04d}-{mo:02d}-{dd:02d}"
                    except Exception:
                        pass
        return ""
    except Exception:
        return ""


def rapid_recover_department(path: str | Path, *, page_index: int = 0,
                             dpi: int = 200, max_side: int = 2400) -> str:
    """第二条第二点专项：定位「2.乙方同意…在XX（部门）XX岗位」行并放大识别部门。

    整页 OCR 有时整行漏检（郎小龙合同），有时把「（部门）」认成「部门）」（姚）。
    这里从「第二条 工作岗位」标题下到「第三条」标题上的固定区域裁切，
    多种预处理放大识别，再按 7 选 1 归一。
    """
    if not _HAS_RAPID or not _get_engine():
        return ""
    try:
        from PIL import Image, ImageOps
        img, words = rapid_locate_words(path, dpi=dpi, max_side=max_side,
                                        page_index=page_index)
        if img is None or not words:
            return ""
        W, H = img.size
        header_y = None
        h2 = None
        for t, b in words:
            flat = re.sub(r"\s+", "", str(t))
            if ("工作岗位" in flat or "第二条" in flat) and header_y is None:
                header_y = float(b[3])
            if "第三条" in flat and h2 is None:
                h2 = float(b[1])
        if header_y is None or h2 is None or h2 <= header_y:
            return ""
        crop = img.crop((max(0, int(W * 0.12)), int(header_y + 4),
                         min(W, int(W * 0.95)), int(h2 - 2)))
        if crop.width < 30 or crop.height < 8:
            return ""
        from ..rules import normalize_department
        for sc in (3, 4):
            big = crop.resize((crop.width * sc, crop.height * sc), Image.LANCZOS)
            for proc in (big, _binarize(big),
                         ImageOps.autocontrast(big.convert("L")).convert("RGB")):
                try:
                    txts, _ = _ocr_pil(_get_engine(), proc)
                except Exception:
                    continue
                # 只看「乙方同意…在X（部门）X岗位」这一行，
                # 避免第一点「办公地点」被误认成部门「办公室」
                for line in (txts or ()):
                    flat = re.sub(r"\s+", "", str(line))
                    if "乙方同意" not in flat:
                        continue
                    d = ""
                    for anchor in ("（部门）", "(部门)", "部门）", "部门)", "部（室", "部(室"):
                        i = flat.find(anchor)
                        if i > 0:
                            d = normalize_department(flat[max(0, i - 12):i])
                            if d:
                                break
                    if not d:
                        d = normalize_department(flat)
                    if d:
                        return d
        return ""
    except Exception:
        return ""
