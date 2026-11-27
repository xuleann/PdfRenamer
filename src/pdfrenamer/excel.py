# -*- coding: utf-8 -*-
"""Excel 汇总：固定输出到用户所选目录的「信息汇总.xlsx」。

- 按模式分 sheet 追加（论文汇总 / 合同汇总），旧数据不丢
- 每处理一个 PDF 都增量写 rows.jsonl，Excel 被占用/中途崩溃后可恢复
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .config import rows_dir
from .models import (DOC_GARBLED, DOC_ENCRYPTED, DOC_ERROR, DOC_NOT_CONTRACT,
                     DOC_NO_TEXT, DOC_OK, DOC_PARTIAL, ExtractResult, RenameRecord)
from .undo import directory_key

FILE_NAME = "信息汇总.xlsx"
# V1.1.1：末尾追加「PDF 类型」标签列（A 列「模式」保留，兼容旧表）
HEADER_TAIL = ["提取状态", "缺失字段", "处理时间", "备注", "PDF 类型"]

# V1.6.0：六个手写敏感字段在表格里都展开为「结果列 + 原件图列」两列，
# 结果列（字段名）存识别/复核结果，图片列紧跟其后放该字段的原件截图。
# 人工复核时直接改结果列，改名阶段再从 Excel 读回这些值。
REVIEW_IMAGE_FIELDS = ("乙方", "身份证号", "开始日期", "结束日期", "签订日期", "用工部门")
# V1.6.5：表头改为「结果列（复核）」+「图片列（识别结果）」
IMAGE_COL_SUFFIX = "（识别结果）"
RESULT_COL_SUFFIX = "（复核）"


def image_col_name(field_name: str) -> str:
    """字段名对应的识别结果（图片）列名。"""
    return field_name + IMAGE_COL_SUFFIX


def result_col_name(field_name: str) -> str:
    """字段名对应的复核结果列名。"""
    return field_name + RESULT_COL_SUFFIX
STATUS_CN = {
    DOC_OK: "完整", DOC_PARTIAL: "部分缺失", DOC_NO_TEXT: "需人工处理",
    DOC_GARBLED: "需人工处理", DOC_ENCRYPTED: "需人工处理", DOC_ERROR: "需人工处理",
    DOC_NOT_CONTRACT: "非合同文档（不改名）",
}
TYPE_FILL = {
    "论文": PatternFill("solid", fgColor="DDEBF7"),
    "合同": PatternFill("solid", fgColor="E2EFDA"),
}

_HEADER_FILL = PatternFill("solid", fgColor="D9E2F3")
_MISS_FILL = PatternFill("solid", fgColor="FFF2CC")
_ALERT_FILL = PatternFill("solid", fgColor="F8CBAD")


class ExcelBusyError(Exception):
    """Excel 文件正被其它程序占用，无法写入。"""


def _rows_path(directory: str | Path) -> Path:
    return rows_dir() / f"{directory_key(directory)}.jsonl"


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(f"{path.stem}_备份_{stamp}{path.suffix}")
    n = 1
    while dst.exists():
        dst = path.with_name(f"{path.stem}_备份_{stamp}_{n}{path.suffix}")
        n += 1
    shutil.copy2(path, dst)
    return dst


class ExcelWriter:
    def __init__(self, directory: str | Path, mode: str, sheet_name: str,
                 mode_label: str, field_names: list[str], missing_value: str = "未知",
                 strategy: str = "append"):
        self.directory = Path(directory)
        self.path = self.directory / FILE_NAME
        self.mode = mode
        self.sheet_name = sheet_name
        self.mode_label = mode_label
        self.field_names = list(field_names)
        self.missing_value = missing_value
        self.strategy = strategy
        # V1.4.9：合同模式下，乙方/用工部门各展开为「文字列 + 原件图列」。
        # 论文模式不含这些字段，表头保持原样。
        self.image_fields = [n for n in self.field_names if n in REVIEW_IMAGE_FIELDS]
        expanded: list[str] = []
        for n in self.field_names:
            expanded.append(result_col_name(n) if n in self.image_fields else n)
            if n in self.image_fields:
                expanded.append(image_col_name(n))
        self.header = ["模式", "原文件名", "新文件名"] + expanded + HEADER_TAIL
        self.wb: Workbook | None = None
        self.ws = None
        self.rows_written = 0
        self.backup_path: Path | None = None

    def _new_workbook(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = self.sheet_name
        ws.append(self.header)
        self._style_header(ws)
        self.wb, self.ws = wb, ws

    def _style_header(self, ws) -> None:
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = _HEADER_FILL
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 22
        for i, name in enumerate(self.header, 1):
            width = 12
            if name in ("原文件名", "新文件名"):
                width = 42
            elif name == "备注":
                width = 36
            elif name == "处理时间":
                width = 20
            elif name.endswith(IMAGE_COL_SUFFIX):
                width = 34  # 识别结果（图片）列
            elif name in self.field_names or any(
                    name == result_col_name(f) for f in self.field_names):
                width = max(14, min(40, len(name) * 2 + 16))
            ws.column_dimensions[get_column_letter(i)].width = width

    def _header_without_images(self) -> list[str]:
        """去掉识别结果图列、并把结果列后缀还原后的表头（旧版表头结构）。"""
        base = [h for h in self.header if not h.endswith(IMAGE_COL_SUFFIX)]
        # V1.6.5：结果列新表头带「（复核）」，旧表是纯字段名
        return [h[:-len(RESULT_COL_SUFFIX)] if h.endswith(RESULT_COL_SUFFIX) else h
                for h in base]

    def _can_upgrade(self, current: list) -> bool:
        """判断旧表头能否无损就地升级到新表头。

        支持两类增量：
        1. 末尾少「PDF 类型」列（V1.1.1 → V1.1.4）；
        2. 缺少「原件图」列（V1.4.9）——图片列插在对应文字列之后。
        V1.6.5：结果列从纯字段名改为「字段名（复核）」，属于文字重命名，
        就地升级会导致数据列错位，这类旧表一律备份重建（历史留档）。
        """
        if not current or len(current) > len(self.header):
            return False
        # 新表头的结果列带「（复核）」，若当前表用的是纯字段名旧表头 → 不升级
        if any(result_col_name(f) in self.header and f in current
               for f in self.field_names):
            return False
        base = self._header_without_images()
        # 旧表 = 新表头去掉图片列（可再少末尾 PDF 类型）
        if current == base or (base and base[-1] == "PDF 类型" and current == base[:-1]):
            return current != self.header
        # 兼容旧逻辑：严格前缀 + 末尾只少 PDF 类型
        if self.header[:len(current)] == current and current[-1] == "备注":
            return self.header[len(current):] == ["PDF 类型"]
        return False

    def _upgrade_columns(self, ws, current: list) -> None:
        """就地插入缺失列并按 A 列回填旧行类型。不备份、不重建、不丢历史。

        图片列插在对应文字列之后；插入列时同步把右侧历史图片的锚点右移，
        避免旧图与新列错位。
        """
        from openpyxl.drawing.image import Image as XLImage  # noqa: F401

        # 从右往左逐列对齐到目标表头，避免插入列时列号漂移
        for j in range(len(self.header), 0, -1):
            name = self.header[j - 1]
            if name in current:
                continue
            # 该列缺失 → 在第 j 列插入
            ws.insert_cols(j)
            for img in getattr(ws, "_images", []):
                try:
                    if img.anchor._from.col >= j - 1:
                        img.anchor._from.col += 1
                except Exception:
                    pass
            c = ws.cell(row=1, column=j, value=name)
            c.font = Font(bold=True)
            c.fill = _HEADER_FILL
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[get_column_letter(j)].width = (
                34 if name.endswith(IMAGE_COL_SUFFIX) else 12)
            current.insert(j - 1, name)

        # 统一重写表头文字（保证顺序与样式一致）
        for j, name in enumerate(self.header, 1):
            cell = ws.cell(row=1, column=j)
            cell.value = name
            cell.font = Font(bold=True)
            cell.fill = _HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # 回填「PDF 类型」列（按 A 列模式）
        if "PDF 类型" in self.header:
            last = self.header.index("PDF 类型") + 1
            for r in range(2, ws.max_row + 1):
                mode = ws.cell(row=r, column=1).value or self.mode_label
                val = mode if mode in TYPE_FILL else self.mode_label
                c = ws.cell(row=r, column=last, value=val)
                c.alignment = Alignment(vertical="top")
                if val in TYPE_FILL:
                    c.fill = TYPE_FILL[val]
        ws.freeze_panes = "A2"

    def prepare(self) -> None:
        """按策略打开/新建工作簿，并重置本轮 rows.jsonl。"""
        if self.strategy in ("backup", "overwrite") and self.path.exists():
            self.backup_path = _backup(self.path)
            self._new_workbook()
        elif self.path.exists():
            try:
                self.wb = load_workbook(self.path)
            except Exception:
                self.backup_path = _backup(self.path)
                self._new_workbook()
            else:
                if self.sheet_name in self.wb.sheetnames:
                    ws = self.wb[self.sheet_name]
                    current = [c.value for c in ws[1]] if ws.max_row >= 1 else []
                    if current == self.header:
                        self.ws = ws
                    elif self._can_upgrade(current):
                        # 仅末尾新增「PDF 类型」列 → 无损升列，保留全部历史行
                        self._upgrade_columns(ws, current)
                        self.ws = ws
                    else:
                        # 表头确实不兼容 → 备份后重建（历史留档）
                        self.backup_path = _backup(self.path)
                        self._new_workbook()
                else:
                    ws = self.wb.create_sheet(self.sheet_name)
                    ws.append(self.header)
                    self._style_header(ws)
                    self.ws = ws
                # 清掉无内容的默认 Sheet
                for name in list(self.wb.sheetnames):
                    s = self.wb[name]
                    if s.max_row == 1 and all(c.value is None for c in s[1]) and name != self.sheet_name:
                        self.wb.remove(s)
        else:
            self._new_workbook()

        rp = _rows_path(self.directory)
        rp.write_text("", encoding="utf-8")
        self._save()

    def _save(self) -> None:
        if self.wb is None:
            return
        try:
            self.wb.save(self.path)
        except PermissionError as exc:
            raise ExcelBusyError(
                "无法保存「信息汇总.xlsx」：文件可能正被 Excel 打开。请关闭后重试，"
                "本轮结果已保存在还原日志中，可用「恢复上次结果」补写。"
            ) from exc

    def build_row(self, result: ExtractResult, record: RenameRecord | None) -> dict:
        new_name = result.original_name
        if record and record.status in ("planned", "done", "unchanged"):
            new_name = record.new_name
        elif record and record.status == "skipped":
            new_name = "（未改名）"
        row = {
            "模式": self.mode_label,
            "原文件名": result.original_name,
            "新文件名": new_name,
        }
        for name in self.field_names:
            fr = result.fields.get(name)
            # V1.5.0：乙方 xxN 占位符只用于重命名文件名；
            # 表格文字列始终显示识别出的原值，配合原件图列由人工核对。
            row[result_col_name(name) if name in self.image_fields else name] = (
                fr.value if fr and not fr.is_missing else self.missing_value)
        # V1.4.9：原件图列本身不放文字（图片由 _embed_images 嵌入），留空占位。
        # 这样表头与行数据列数一致，追加/恢复时不会错位。
        for name in self.image_fields:
            row[image_col_name(name)] = ""
        row["提取状态"] = STATUS_CN.get(result.doc_status, result.doc_status)
        row["缺失字段"] = "、".join(result.missing_names())
        row["处理时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notes = [x for x in (result.note, result.skip_reason, record.reason if record else "") if x]
        row["备注"] = "；".join(dict.fromkeys(notes))
        row["PDF 类型"] = self.mode_label
        return row

    def append_row(self, row: dict, field_images: dict[str, bytes] | None = None,
                   save: bool = True) -> None:
        """追加一行。save=False 时跳过立即保存，供批量写入后由 finish() 一次落盘
        （V1.6.0 提速：N 份 PDF 从 save N 次降为 1 次）。"""
        if self.ws is None:
            raise RuntimeError("请先调用 prepare()")
        values = [row.get(h, "") for h in self.header]
        self.ws.append(values)
        r = self.ws.max_row
        for i, h in enumerate(self.header, 1):
            cell = self.ws.cell(row=r, column=i)
            wrap_names = ("原文件名", "新文件名", "备注") + tuple(self.field_names) + tuple(
                result_col_name(f) for f in self.field_names)
            cell.alignment = Alignment(vertical="top", wrap_text=(h in wrap_names))
            if cell.value == self.missing_value:
                cell.fill = _MISS_FILL
            if h == "提取状态" and cell.value == "需人工处理":
                cell.fill = _ALERT_FILL
            if h == "PDF 类型" and cell.value in TYPE_FILL:
                cell.fill = TYPE_FILL[cell.value]
        # V1.3.0：把手写字段局部截图嵌入对应字段单元格（低体积灰度小图）
        if field_images:
            self._embed_images(r, field_images)
        self.rows_written += 1
        # 增量兜底：先写 jsonl，再存 Excel（图片字节不写 jsonl，避免撑大日志）
        with _rows_path(self.directory).open("a", encoding="utf-8") as f:
            f.write(json.dumps({"mode": self.mode, "row": row}, ensure_ascii=False) + "\n")
        if save:
            self._save()

    # V1.3.6：截图显示尺寸上限（像素）。手写截图是横向长条，
    # 必须同时约束宽和高，否则图片会横跨多列、盖住相邻单元格（用户实测反馈）。
    _IMG_MAX_W = 235     # 约等于一个加宽后的字段列
    _IMG_MAX_H = 90      # 允许的最大高度（条带兜底图可能偏高）
    # V1.5.0：用工部门原件图要能看清笔画，显示尺寸与行高单独放宽。
    _IMG_HQ_MAX_W = 560
    _IMG_HQ_MAX_H = 170
    _IMG_HQ_FIELD = "用工部门"

    def _embed_images(self, row_idx: int, field_images: dict[str, bytes]) -> None:
        """把 {字段名: JPEG字节} 嵌到该行对应字段列，等比缩放并约束在单元格内。

        openpyxl 保存时会对同一图片多次重新打开，BytesIO 容易被关闭；改用系统临时
        目录下的小文件作图片源（保存完成后在 finish() 清理），稳定且不占内存。
        """
        import tempfile
        from openpyxl.drawing.image import Image as XLImage
        col_of = {name: i + 1 for i, name in enumerate(self.header)}
        if not hasattr(self, "_image_dir"):
            self._image_dir = tempfile.mkdtemp(prefix="pdfrenamer_imgs_")
            self._image_seq = 0
        for name, data in field_images.items():
            if not data:
                continue
            # V1.4.9/V1.6.5：复核字段的图片放到紧邻的「识别结果」列，
            # 其它字段仍嵌在自身列。注意 name 是纯字段名，不在带后缀的 header 里，
            # 必须先算出 target_col 再判断列是否存在。
            target_col = image_col_name(name) if name in self.image_fields else name
            if target_col not in col_of:
                continue
            try:
                # V1.3.6：直接缩放图片像素本身（而非只设 XLImage.width）——
                # openpyxl 保存时以图片实际像素为准，只设显示属性会被忽略，
                # 导致原图 300~900px 宽直接盖住多列（用户实测反馈）。
                from PIL import Image
                from io import BytesIO
                pil = Image.open(BytesIO(data))
                hq = name == self._IMG_HQ_FIELD
                max_w = self._IMG_HQ_MAX_W if hq else self._IMG_MAX_W
                max_h = self._IMG_HQ_MAX_H if hq else self._IMG_MAX_H
                ratio = min(max_w / float(pil.width or 1),
                            max_h / float(pil.height or 1), 1.0)
                new_w = max(1, int(pil.width * ratio))
                new_h = max(1, int(pil.height * ratio))
                pil = pil.resize((new_w, new_h), Image.LANCZOS)
                self._image_seq += 1
                img_path = Path(self._image_dir) / f"snip_{row_idx}_{self._image_seq}.jpg"
                pil.save(str(img_path), format="JPEG",
                         quality=90 if hq else 72, optimize=True)
                img = XLImage(str(img_path))
                anchor = f"{get_column_letter(col_of[target_col])}{row_idx}"
                img.anchor = anchor
                self.ws.add_image(img)
                # 列宽/行高调到能容纳图片：列宽字符数≈像素/7，行高磅≈像素*0.75
                letter = get_column_letter(col_of[target_col])
                need_w = new_w / 7.0 + 2
                cur_w = self.ws.column_dimensions[letter].width
                if cur_w is None or cur_w < need_w:
                    self.ws.column_dimensions[letter].width = min(need_w, 84 if hq else 36)
                need_h = new_h * 0.75 + 4
                cur_h = self.ws.row_dimensions[row_idx].height
                if cur_h is None or cur_h < need_h:
                    self.ws.row_dimensions[row_idx].height = min(need_h, 150 if hq else 70)
            except Exception:
                continue

    def _cleanup_images(self) -> None:
        import shutil
        d = getattr(self, "_image_dir", None)
        if d:
            shutil.rmtree(d, ignore_errors=True)
            self._image_dir = None

    def finish(self) -> None:
        if self.ws is not None and self.ws.max_row >= 1:
            self.ws.auto_filter.ref = f"A1:{get_column_letter(len(self.header))}{self.ws.max_row}"
        self._save()
        self._cleanup_images()  # 图片已写入 xlsx，删除系统临时目录


def has_recoverable_rows(directory: str | Path) -> bool:
    rp = _rows_path(directory)
    return rp.exists() and rp.stat().st_size > 0


def recover_rows(directory: str | Path, mode: str, sheet_name: str, mode_label: str,
                 field_names: list[str], missing_value: str = "未知") -> int:
    """从 rows.jsonl 重建本轮结果（Excel 被占用 / 中途崩溃后使用）。"""
    rp = _rows_path(directory)
    if not rp.exists():
        return 0
    rows = []
    for line in rp.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            if d.get("mode") == mode:
                rows.append(d["row"])
        except (ValueError, KeyError):
            continue
    if not rows:
        return 0
    # V1.1.0 及以前的 jsonl 行没有「PDF 类型」键，补齐后写回保持一致
    for row in rows:
        row.setdefault("PDF 类型", mode_label)
    w = ExcelWriter(directory, mode, sheet_name, mode_label, field_names,
                    missing_value, strategy="append")
    w.prepare()
    # prepare 会清空 jsonl，这里改为从内存写回，避免数据丢失
    for row in rows:
        values = [row.get(h, "") for h in w.header]
        w.ws.append(values)
        w.rows_written += 1
    with rp.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps({"mode": mode, "row": row}, ensure_ascii=False) + "\n")
    w.finish()
    return len(rows)


def _cell_text(cell) -> str:
    """把单元格值转成干净字符串；Excel 日期序列号/日期对象按显示文本处理。"""
    v = cell.value
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        # 用户输入的日期被 Excel 存成日期对象 → 按 YYYY-MM-DD 读回
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            return str(v)
    return str(v).strip()


def read_reviewed_values(path: str | Path, sheet_name: str,
                         field_names: list[str],
                         image_fields: tuple[str, ...] = REVIEW_IMAGE_FIELDS
                         ) -> dict[str, dict[str, str]]:
    """从人工复核后的 Excel 读回字段值，返回 {原文件名: {字段名: 值}}。

    V1.6.0：扫描阶段先把识别结果写进 Excel，人工直接在结果列修改；
    改名阶段读回这些值覆盖识别结果。只读取「结果列」（字段名），
    跳过原件图列；空单元格视为未改（返回空串，由调用方决定是否保留原值）。

    若表头缺少某字段（旧表），该字段不返回，调用方保留原识别值。
    """
    from openpyxl import load_workbook
    p = Path(path)
    if not p.exists():
        return {}
    try:
        wb = load_workbook(p, read_only=True, data_only=True)
    except Exception:
        return {}
    try:
        if sheet_name not in wb.sheetnames:
            return {}
        ws = wb[sheet_name]
        rows = ws.iter_rows(values_only=False)
        try:
            header = [_cell_text(c) for c in next(rows)]
        except StopIteration:
            return {}
        # 列索引：原文件名 + 各字段结果列（排除原件图列）
        try:
            name_idx = header.index("原文件名")
        except ValueError:
            name_idx = 0
        field_idx: dict[str, int] = {}
        for f in field_names:
            # V1.6.5：新表头结果列为「字段名（复核）」，同时兼容旧表头「字段名」
            h = result_col_name(f) if result_col_name(f) in header else f
            if h in header:
                field_idx[f] = header.index(h)
        out: dict[str, dict[str, str]] = {}
        for row in rows:
            if name_idx >= len(row):
                continue
            key = _cell_text(row[name_idx])
            if not key:
                continue
            vals: dict[str, str] = {}
            for f, idx in field_idx.items():
                if idx < len(row):
                    vals[f] = _cell_text(row[idx])
            out[key] = vals
        return out
    finally:
        try:
            wb.close()
        except Exception:
            pass


def update_excel_after_rename(path: str | Path, sheet_name: str,
                              new_names: dict[str, str]) -> int:
    """改名完成后，按「原文件名」匹配把最终新文件名写回 Excel。

    V1.6.0：复核表在扫描阶段已写好（含字段值与截图），改名阶段只更新
    「新文件名」/「提取状态」列，绝不覆盖人工复核过的字段值。
    用普通模式加载以保留嵌入图片；返回更新行数。
    """
    from openpyxl import load_workbook
    p = Path(path)
    if not p.exists() or not new_names:
        return 0
    try:
        wb = load_workbook(p)   # 不用 data_only，避免图片/格式丢失
    except Exception:
        return 0
    try:
        if sheet_name not in wb.sheetnames:
            return 0
        ws = wb[sheet_name]
        header = [_cell_text(c) for c in ws[1]]
        try:
            name_idx = header.index("原文件名") + 1
            new_idx = header.index("新文件名") + 1
        except ValueError:
            return 0
        updated = 0
        for r in range(2, ws.max_row + 1):
            key = _cell_text(ws.cell(row=r, column=name_idx))
            if key in new_names:
                ws.cell(row=r, column=new_idx, value=new_names[key])
                updated += 1
        if updated:
            wb.save(p)
        return updated
    finally:
        try:
            wb.close()
        except Exception:
            pass
