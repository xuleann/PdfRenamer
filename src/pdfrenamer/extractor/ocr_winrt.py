# -*- coding: utf-8 -*-
"""Windows 内置离线 OCR 补文（V1.1.2，仅用于无文本层的扫描件）。

合规说明：
- 只调用操作系统随附的 Windows.Media.Ocr（本地 WinRT 组件 + 本地中文语言数据），
  不是大模型、不是云端 API、不是推理框架；全程零网络请求。
- 不引入任何第三方 Python 依赖：只用标准库 subprocess/tempfile/base64 与已锁定的 pymupdf。
- 临时 PNG 一律写入 tempfile.TemporaryDirectory（系统 TEMP），用完即删；
  绝不写用户所选目录，绝不写 samples/user/。

已知限制：Windows OCR 会在汉字之间插入伪空格（「甲 方 ：」），
因此补文前必须做字间空格归一化，否则既有关键词 / 正则规则无法命中。
"""
from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from pathlib import Path

from .base import TextDoc, classify_text, clean_pdf_text
from ..models import DOC_NO_TEXT, DOC_OK

CREATE_NO_WINDOW = 0x08000000          # console=False 的 onefile 下不弹控制台
_PS_EXE = "powershell.exe"             # 必须 5.1；pwsh/.NET Core 的 WinRT 投影不同
_PROBE_CACHE: dict | None = None

_OCR_NOTE = "系统离线 OCR（Windows 内置，非大模型/非云端）｜建议人工复核"

# ---------------------------------------------------------------------------
# PowerShell 5.1 脚本：WinRT 异步桥接 + 逐页识别 + UTF-8→Base64 单行回传
# 注意：PowerShell 变量名大小写不敏感，WinRT 类型变量一律加 T_ 前缀，
# 避免与 $buf / $bmp 等变量名冲突（曾踩坑：把 StringBuilder 当成了 SoftwareBitmap）。
# ---------------------------------------------------------------------------
_PS_OCR = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$script:asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
if (-not $script:asTask) { [Console]::Error.WriteLine('NO_ASTASK'); exit 2 }
function Await($op, [type]$t) {
    $task = $script:asTask.MakeGenericMethod($t).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    return $task.Result
}
$T_SF   = [Windows.Storage.StorageFile, Windows.Foundation, ContentType=WindowsRuntime]
$T_FAM  = [Windows.Storage.FileAccessMode, Windows.Foundation, ContentType=WindowsRuntime]
$T_IRAS = [Windows.Storage.Streams.IRandomAccessStream, Windows.Foundation, ContentType=WindowsRuntime]
$T_BD   = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$T_BPF  = [Windows.Graphics.Imaging.BitmapPixelFormat, Windows.Foundation, ContentType=WindowsRuntime]
$T_BAM  = [Windows.Graphics.Imaging.BitmapAlphaMode, Windows.Foundation, ContentType=WindowsRuntime]
$T_SB   = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime]
$T_OE   = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$T_OR   = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$T_LG   = [Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]

$engine = $null
if ('__LANG__' -ne 'auto') {
    try { $engine = $T_OE::TryCreateFromLanguage($T_LG::new('__LANG__')) } catch { }
}
if (-not $engine) {
    $zh = $T_OE::AvailableRecognizerLanguages | Where-Object { $_.LanguageTag -like 'zh*' } | Select-Object -First 1
    if ($zh) { $engine = $T_OE::TryCreateFromLanguage($zh) }
}
if (-not $engine) { $engine = $T_OE::TryCreateFromUserProfileLanguages() }
if (-not $engine) { [Console]::Error.WriteLine('NO_OCR_ENGINE'); exit 2 }

$buf = [System.Text.StringBuilder]::new()
$pngs = Get-Content -LiteralPath '__LIST__' -Encoding UTF8
foreach ($p in $pngs) {
    if (-not $p.Trim()) { continue }
    $file    = Await ($T_SF::GetFileFromPathAsync($p)) $T_SF
    $stream  = Await ($file.OpenAsync($T_FAM::Read)) $T_IRAS
    $decoder = Await ($T_BD::CreateAsync($stream)) $T_BD
    # 必须 Bgra8 + Premultiplied 两参重载，否则 RecognizeAsync 会失败
    $bmp     = Await ($decoder.GetSoftwareBitmapAsync($T_BPF::Bgra8, $T_BAM::Premultiplied)) $T_SB
    $result  = Await ($engine.RecognizeAsync($bmp)) $T_OR
    foreach ($line in $result.Lines) { [void]$buf.AppendLine($line.Text) }
    [void]$buf.Append([char]12)
    $bmp.Dispose(); $stream.Dispose()
}
$bytes = [System.Text.Encoding]::UTF8.GetBytes($buf.ToString())
[Console]::Out.WriteLine([Convert]::ToBase64String($bytes))
'''

_PS_PROBE = r'''
$ErrorActionPreference = 'Stop'
$T_OE = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$langs = $T_OE::AvailableRecognizerLanguages
$zh = $langs | Where-Object { $_.LanguageTag -like 'zh*' } | Select-Object -First 1
$engine = $null
if ($zh) { $engine = $T_OE::TryCreateFromLanguage($zh) }
if (-not $engine) { $engine = $T_OE::TryCreateFromUserProfileLanguages() }
$obj = @{
    available = ($null -ne $engine)
    lang      = if ($engine) { $engine.RecognizerLanguage.LanguageTag } else { '' }
    max_dim   = $T_OE::MaxImageDimension
}
[Console]::Out.WriteLine([Convert]::ToBase64String(
    [System.Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Compress))))
'''


def _run_powershell(script: str, timeout: int) -> str:
    """执行 PS 脚本并返回最后一行非空 stdout；任何失败返回 ''。"""
    try:
        enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        r = subprocess.run(
            [_PS_EXE, "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", enc],
            capture_output=True, timeout=max(5, int(timeout)),
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            return ""
        lines = [x.strip() for x in r.stdout.decode("ascii", "replace").splitlines() if x.strip()]
        return lines[-1] if lines else ""
    except Exception:
        return ""


def probe_ocr(timeout: int = 8) -> dict:
    """探测中文 OCR 引擎是否可用；结果进程内缓存，失败一律 available=False。"""
    global _PROBE_CACHE
    if _PROBE_CACHE is not None:
        return dict(_PROBE_CACHE)
    result = {"available": False, "lang": "", "max_dim": 0,
              "reason": "Windows 内置 OCR 不可用或缺少中文语言包"}
    try:
        out = _run_powershell(_PS_PROBE, timeout)
        if out:
            import json
            info = json.loads(base64.b64decode(out).decode("utf-8", "replace"))
            result = {
                "available": bool(info.get("available")),
                "lang": str(info.get("lang") or ""),
                "max_dim": int(info.get("max_dim") or 0),
                "reason": "" if info.get("available") else "未找到可用的 OCR 语言包",
            }
    except Exception:
        pass
    _PROBE_CACHE = result
    return dict(result)


# ---------------------------------------------------------------------------
# Windows OCR 的汉字间伪空格归一化
# ---------------------------------------------------------------------------
_CJKISH = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\u3000-\u303f\uff00-\uffef\u2018\u2019\u201c\u201d]"
    # 不含 U+00B7「·」：它在「G B · 2024」这类编号里属于 ASCII 语境，
    # 其两侧空格必须保留，否则会把英文/数字粘连。
)


def _is_cjkish(ch: str) -> bool:
    return bool(ch) and bool(_CJKISH.match(ch))


def normalize_ocr_line(line: str) -> str:
    """「合 同 书」「甲 方 ： 国 家」→「合同书」「甲方：国家」。

    仅删除「一侧为汉字/中文标点」的单空格；两侧都是 ASCII 时保留
    （英文单词间的真空格不能被误删）。
    """
    chars = list(line)
    out: list[str] = []
    for i, ch in enumerate(chars):
        if ch == " ":
            left = chars[i - 1] if i > 0 else ""
            right = chars[i + 1] if i + 1 < len(chars) else ""
            if _is_cjkish(left) or _is_cjkish(right):
                continue
        out.append(ch)
    return "".join(out)


def normalize_ocr_text(raw: str) -> tuple[str, str]:
    """-> (全文, 首页)。先按页归一化，再交 clean_pdf_text 做 NFKC 清洗。"""
    pages = [_normalize_page(p) for p in raw.split("\f")]
    pages = [p for p in pages if p is not None]
    head = clean_pdf_text(pages[0]) if pages else ""
    text = clean_pdf_text("\n".join(pages))
    return text, head


def _normalize_page(page: str) -> str:
    return "\n".join(normalize_ocr_line(ln) for ln in page.splitlines())


# ---------------------------------------------------------------------------
# 页面渲染与 OCR 主流程
# ---------------------------------------------------------------------------
def page_indices(page_count: int, max_pages: int = 2,
                 include_last: bool = True) -> list[int]:
    """前 N 页 + 末页（签章页常有签订日期/盖章），去重保序。"""
    if page_count <= 0:
        return []
    n = max(1, min(3, int(max_pages)))
    idx = list(range(min(page_count, n)))
    if include_last and page_count > 1:
        idx.append(page_count - 1)
    seen: set[int] = set()
    out: list[int] = []
    for i in idx:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _render_pages(path: Path, indices: list[int], dpi: int,
                  max_side: int, tmpdir: Path) -> list[Path]:
    import pymupdf

    out: list[Path] = []
    with pymupdf.open(str(path)) as doc:
        for i in indices:
            page = doc.load_page(i)
            rect = page.rect
            scale = min(max(72, min(300, int(dpi))) / 72.0,
                        max(800, min(2600, int(max_side))) / max(rect.width, rect.height))
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                colorspace=pymupdf.csRGB,   # 1-bit 二值黑白扫描件也能正常转 PNG
                alpha=False,
            )
            target = tmpdir / f"p{i:03d}.png"
            pix.save(str(target))
            out.append(target)
    return out


def _ocr_raw(path: str | Path, *, max_pages: int = 2,
             include_last: bool = True, dpi: int = 200,
             max_side: int = 2400, timeout: int = 60,
             lang: str = "auto") -> str:
    """渲染 + 一次 PowerShell 调用，返回未归一化的 OCR 原文（页间 \\f）；失败返回 ''。"""
    import pymupdf

    src = Path(path)
    with pymupdf.open(str(src)) as probe:
        count = probe.page_count
    indices = page_indices(count, max_pages, include_last)
    if not indices:
        return ""

    with tempfile.TemporaryDirectory(prefix="pdfrenamer_ocr_") as td:
        tmp = Path(td)
        pngs = _render_pages(src, indices, dpi, max_side, tmp)
        if not pngs:
            return ""
        listing = tmp / "png_list.txt"
        # ★WinRT GetFileFromPathAsync 只接受原生反斜杠路径，正斜杠会抛异常
        listing.write_text("\n".join(str(p) for p in pngs), encoding="utf-8")
        script = (_PS_OCR
                  .replace("__LIST__", str(listing))
                  .replace("__LANG__", str(lang or "auto")))
        out = _run_powershell(script, timeout)
        if not out:
            return ""
        return base64.b64decode(out).decode("utf-8", "replace")


def ocr_pdf_text(path: str | Path, *, max_pages: int = 2,
                 include_last: bool = True, dpi: int = 200,
                 max_side: int = 2400, timeout: int = 60,
                 lang: str = "auto") -> str:
    """对外便捷接口：返回归一化后的全文；失败返回 ''。"""
    try:
        raw = _ocr_raw(path, max_pages=max_pages, include_last=include_last,
                       dpi=dpi, max_side=max_side, timeout=timeout, lang=lang)
        if not raw:
            return ""
        text, _ = normalize_ocr_text(raw)
        return text
    except Exception:
        return ""


def supplement_textdoc(path: str | Path, doc: TextDoc, *, max_pages: int = 2,
                       include_last: bool = True, dpi: int = 200,
                       max_side: int = 2400, timeout: int = 60,
                       lang: str = "auto") -> TextDoc | None:
    """OCR 成功且判定为有效文本 → 返回新 TextDoc；否则 None（保持原 DOC_NO_TEXT）。"""
    if doc.status != DOC_NO_TEXT:
        return None
    try:
        raw = _ocr_raw(path, max_pages=max_pages, include_last=include_last,
                       dpi=dpi, max_side=max_side, timeout=timeout, lang=lang)
    except Exception:
        return None
    if not raw:
        return None
    try:
        text, head = normalize_ocr_text(raw)
    except Exception:
        return None
    if not text.strip():
        return None
    status, _ = classify_text(text)
    if status != DOC_OK:
        return None
    return TextDoc(
        text=text,
        status=DOC_OK,
        chars=len(text.replace("\n", "").strip()),
        pages=doc.pages,
        note=_OCR_NOTE,
        metadata={},      # 扫描件 metadata.title 是「扫描全能王 2024-…」，绝不能当题目/日期
        head_text=head,
    )
