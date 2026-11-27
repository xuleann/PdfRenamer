# -*- coding: utf-8 -*-
"""配置持久化：%APPDATA%/PdfRenamer/config.json。

- 出厂默认来自 presets.DEFAULT_CONFIG，并额外支持打包进 exe 的 config/default_config.json
- 用户自定义字段通过 deep_merge 保留，升级不会丢
- 所有写入都是原子的（临时文件 → os.replace）
"""
from __future__ import annotations

import json
import os
import sys
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from .presets import DEFAULT_CONFIG, MODES

APP_DIR_NAME = "PdfRenamer"
CONFIG_VERSION = 8


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / APP_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def plans_dir() -> Path:
    p = appdata_dir() / "plans"
    p.mkdir(parents=True, exist_ok=True)
    return p


def rows_dir() -> Path:
    p = appdata_dir() / "rows"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = appdata_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_path(relative: str) -> Path:
    """兼容 PyInstaller onefile（sys._MEIPASS）与源码运行。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parents[2] / relative


def config_path() -> Path:
    return appdata_dir() / "config.json"


def deep_merge(base: dict, override: dict) -> dict:
    """递归合并；列表整体替换；override 优先。"""
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _factory_defaults() -> dict:
    p = resource_path("config/default_config.json")
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("modes"):
                return data
        except (OSError, ValueError):
            pass
    return deepcopy(DEFAULT_CONFIG)


def _validate(cfg: dict) -> dict:
    cfg["config_version"] = CONFIG_VERSION
    cfg.setdefault("modes", {})
    for key, m in MODES.items():
        if key not in cfg["modes"]:
            cfg["modes"][key] = deepcopy(m)
        mc = cfg["modes"][key]
        mc.setdefault("template", m["template"])
        mc.setdefault("label", m["label"])
        mc.setdefault("sheet", m["sheet"])
        mc.setdefault("icon", m["icon"])
        mc.setdefault("description", m["description"])
        fields = []
        for d in mc.get("fields", []):
            if isinstance(d, dict) and str(d.get("name", "")).strip():
                fields.append(d)
        mc["fields"] = fields or deepcopy(m["fields"])
    if cfg.get("backend") not in ("pymupdf", "pypdf", "pdfplumber"):
        cfg["backend"] = "pymupdf"
    if cfg.get("excel_strategy") not in ("append", "backup", "overwrite"):
        cfg["excel_strategy"] = "append"
    cfg["first_pages"] = max(1, min(20, int(cfg.get("first_pages", 3) or 3)))
    cfg["last_pages"] = max(0, min(10, int(cfg.get("last_pages", 0) or 0)))
    cfg["max_filename_len"] = max(20, min(200, int(cfg.get("max_filename_len", 120) or 120)))
    cfg["missing_value"] = str(cfg.get("missing_value") or "未知")
    # V1.1.1 新增：合同类型闸门开关/阈值、输入方式记忆（不覆盖用户显式值）
    if "contract_type_gate" not in cfg:
        cfg["contract_type_gate"] = True
    cfg["contract_gate_threshold"] = max(1, min(9, int(cfg.get("contract_gate_threshold", 2) or 2)))
    if cfg.get("last_input_mode") not in ("folder", "files"):
        cfg["last_input_mode"] = "folder"
    # V1.1.2：扫描件离线 OCR 开关（不覆盖用户显式值，仅校验取值范围）
    if "scan_ocr_enabled" not in cfg:
        cfg["scan_ocr_enabled"] = True
    else:
        cfg["scan_ocr_enabled"] = bool(cfg["scan_ocr_enabled"])
    cfg["scan_ocr_max_pages"] = max(1, min(3, int(cfg.get("scan_ocr_max_pages", 2) or 2)))
    cfg["scan_ocr_include_last_page"] = bool(cfg.get("scan_ocr_include_last_page", True))
    cfg["scan_ocr_dpi"] = max(72, min(300, int(cfg.get("scan_ocr_dpi", 200) or 200)))
    cfg["scan_ocr_max_side"] = max(800, min(2600, int(cfg.get("scan_ocr_max_side", 2400) or 2400)))
    cfg["scan_ocr_timeout"] = max(10, min(180, int(cfg.get("scan_ocr_timeout", 60) or 60)))
    cfg["scan_ocr_lang"] = str(cfg.get("scan_ocr_lang") or "auto")
    # V1.2.0：RapidOCR 手写识别开关
    cfg["scan_rapid_enabled"] = bool(cfg.get("scan_rapid_enabled", True))
    # V1.5.0：序号每批从 01 开始，不再跨批递增。
    # 保留该键仅为兼容旧配置（旧版可能存了 4/5 等），读取时归一化为 1。
    cfg["sequence_counter"] = 1
    # V1.3.0：手写字段截图嵌入 Excel 开关（默认开，不覆盖用户显式关闭值）
    if "capture_field_images" not in cfg:
        cfg["capture_field_images"] = True
    else:
        cfg["capture_field_images"] = bool(cfg["capture_field_images"])
    _align_contract_field_types(cfg)
    return cfg


# V1.2.1：合同模式内置字段的权威类型。用户历史配置里「乙方」常被存成 text，
# 导致 person_name 的防误取逻辑不生效；每次加载按字段名无条件对齐类型，
# 确保识别规则与字段声明一致。不覆盖用户自定义的正则/关键词/choices。
_CONTRACT_FIELD_TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "合同类型": ("enum", ("劳动合同", "劳务合同")),
    "乙方": ("person_name", ()),
    "身份证号": ("idcard", ()),
    "开始日期": ("date", ()),
    "结束日期": ("date", ()),
    "签订日期": ("date", ()),
    "用工部门": ("enum", ("办公室", "财务室", "交通", "物业", "服务一部", "服务二部", "资产")),
}


def _align_contract_field_types(cfg: dict) -> None:
    lm = (cfg.get("modes") or {}).get("contract")
    if not isinstance(lm, dict) or not isinstance(lm.get("fields"), list):
        return
    for f in lm["fields"]:
        if not isinstance(f, dict):
            continue
        spec = _CONTRACT_FIELD_TYPES.get(str(f.get("name", "")))
        if not spec:
            continue
        ftype, choices = spec
        if f.get("type") != ftype:
            f["type"] = ftype
        if choices and not f.get("choices"):
            f["choices"] = list(choices)


def _merge_preset_fields(defaults: dict, loaded: dict) -> dict:
    """配置升级：把出厂预设新增的 source / 关键词合并进用户已有字段。

    用户的正则、模板、自定义字段一律保留；只补齐缺失的结构化来源并追加新关键词，
    避免「软件升级后老配置里仍是没有论文结构化解析的旧规则」。
    """
    lmodes = loaded.get("modes")
    if not isinstance(lmodes, dict):
        return loaded
    for mode, dm in (defaults.get("modes") or {}).items():
        lm = lmodes.get(mode)
        if not isinstance(lm, dict) or not isinstance(lm.get("fields"), list):
            continue
        preset = {str(f.get("name")): f for f in dm.get("fields", []) if isinstance(f, dict)}
        merged = []
        for f in lm["fields"]:
            if not isinstance(f, dict):
                merged.append(f)
                continue
            pf = preset.get(str(f.get("name", "")))
            if pf:
                if not f.get("source") and pf.get("source"):
                    f["source"] = pf["source"]
                kws = [str(k) for k in (f.get("keywords") or [])]
                for k in (pf.get("keywords") or []):
                    if k not in kws:
                        kws.append(k)
                f["keywords"] = kws
            merged.append(f)
        lm["fields"] = merged
    return loaded


# V1.1.1：v3 出厂正则。只有「与旧出厂值完全一致」才说明用户没自定义过，可安全替换。
_V3_CONTRACT_REGEX = {
    "合同名称": r"(?:合同名称|项目名称|合同标题|协议名称|标\s*题)[ \t]*[:：][ \t]*([^\r\n]{2,150})",
    "时间": r"(?:签订日期|签署日期|签约日期|签订时间|签署时间|合同日期|签约时间)[ \t]*[:：][ \t]*([^\r\n]{2,60})",
    "金额": r"(?:合同金额|合同总价|总金额|合同价款|价\s*款|金\s*额|合\s*计)[ \t]*(?:[（(][^）)\r\n]{0,20}[）)])?[ \t]*[:：]?[ \t]*[¥￥]?[ \t]*([0-9][0-9,]*(?:\.[0-9]+)?[ \t]*(?:万元|万|元)?)",
}
_V4_REMOVE_KEYWORDS = {"合同名称": {"项目名称", "标题"}}


def _migrate_v4(loaded: dict, defaults: dict) -> dict:
    """v3 → v4：修合同误取、补别名、更新出厂正则、注入闸门开关。

    严格保留用户资产：只删黑名单同义词；regex 仅当与 v3 出厂值完全一致才替换
    （用户自定义过的一律不动）；关键词只追加不覆盖；模板/自定义字段完全不碰。
    """
    lmodes = loaded.get("modes")
    dm = (defaults.get("modes") or {}).get("contract")
    if isinstance(lmodes, dict) and isinstance(dm, dict):
        lm = lmodes.get("contract")
        if isinstance(lm, dict) and isinstance(lm.get("fields"), list):
            dfields = {str(f.get("name")): f for f in dm.get("fields", [])
                       if isinstance(f, dict)}
            for f in lm["fields"]:
                if not isinstance(f, dict):
                    continue
                name = str(f.get("name", ""))
                if name in _V4_REMOVE_KEYWORDS:
                    f["keywords"] = [k for k in (f.get("keywords") or [])
                                     if k not in _V4_REMOVE_KEYWORDS[name]]
                if (name in _V3_CONTRACT_REGEX
                        and f.get("regex") == _V3_CONTRACT_REGEX[name]
                        and name in dfields):
                    f["regex"] = dfields[name].get("regex", "")
                if name in dfields:
                    kws = [str(k) for k in (f.get("keywords") or [])]
                    for k in (dfields[name].get("keywords") or []):
                        if k not in kws:
                            kws.append(k)
                    f["keywords"] = kws
    loaded.setdefault("contract_type_gate", True)
    loaded.setdefault("contract_gate_threshold", 2)
    loaded.setdefault("last_input_mode", "folder")
    return loaded


def _migrate_v5(loaded: dict, defaults: dict) -> dict:
    """v4 → v5：只注入 V1.1.2 的扫描件 OCR 开关键。

    沿用 _migrate_v4 的「不覆盖用户显式值」原则：一律 setdefault。
    字段 / 正则 / 关键词 / 模板 / 自定义字段 / cfg.modes 全部原样保留，
    也绝不重复执行 v4 的删词与换正则逻辑。
    """
    for key, value in defaults.items():
        if key.startswith("scan_ocr_"):
            loaded.setdefault(key, value)
    return loaded


def _migrate_v6(loaded: dict, defaults: dict) -> dict:
    """v5 → v6：合同模式重构为「劳动合同/劳务合同」8 字段，注入手写 OCR 与序号计数。

    这是 V1.2.0 的一次**明确的产品转向**：合同模式从「通用商务合同」改为
    「劳动合同/劳务合同」专用，字段整体替换为新预设（合同类型/乙方/身份证号/
    开始日期/结束日期/签订日期/用工部门），并更新默认命名模板。
    """
    # 1) 注入 RapidOCR 开关与序号计数器（不覆盖用户显式值）
    loaded.setdefault("scan_rapid_enabled", True)
    loaded.setdefault("sequence_counter", 1)
    # 2) 合同模式字段 + 模板整体替换为新预设
    dm = (defaults.get("modes") or {}).get("contract")
    lmodes = loaded.get("modes")
    if isinstance(dm, dict) and isinstance(lmodes, dict):
        lm = lmodes.get("contract")
        if isinstance(lm, dict):
            lm["fields"] = deepcopy(dm.get("fields", []))
            lm["template"] = dm.get("template", lm.get("template", ""))
            lm["description"] = dm.get("description", lm.get("description", ""))
    return loaded


def load_config() -> dict:
    defaults = _factory_defaults()
    p = config_path()
    if not p.exists():
        return _validate(defaults)
    try:
        loaded = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config root is not a dict")
        if int(loaded.get("config_version", 1)) < CONFIG_VERSION:
            backup = appdata_dir() / f"config_v{loaded.get('config_version', 1)}_backup.json"
            shutil.copy2(p, backup)
            loaded = _merge_preset_fields(defaults, loaded)
            old_v = int(loaded.get("config_version", 1))
            if old_v < 4:
                loaded = _migrate_v4(loaded, defaults)
            if old_v < 5:
                loaded = _migrate_v5(loaded, defaults)
            # v6（合同字段整体替换 + RapidOCR/序号注入）对任何 < 8 的旧配置都要执行：
            # 历史遗留的 config.json 可能被写过更高版本号（如 7），但其合同字段仍是旧的，
            # 必须无条件走一次 v6 迁移，确保劳动合同 8 字段就位。
            if old_v < 8:
                loaded = _migrate_v6(loaded, defaults)
    except (OSError, ValueError, TypeError):
        bad = appdata_dir() / f"config_broken_{datetime.now():%Y%m%d%H%M%S}.json"
        try:
            shutil.copy2(p, bad)
        except OSError:
            pass
        loaded = {}
    return _validate(deep_merge(defaults, loaded))


def save_config(cfg: dict) -> None:
    p = config_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_validate(deepcopy(cfg)), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def export_defaults(target: Path) -> None:
    """把出厂默认导出成 config/default_config.json（打包时随 exe 携带）。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    data = deepcopy(DEFAULT_CONFIG)
    data["config_version"] = CONFIG_VERSION  # 与代码版本号保持一致
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_mode_config(cfg: dict, mode: str) -> dict:
    return cfg["modes"][mode]
