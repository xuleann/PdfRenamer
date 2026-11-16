# -*- coding: utf-8 -*-
"""重命名还原日志与一键撤销。

原则：
- 改名前先落盘完整 plan.json，每次改名成功后原子更新
- 撤销逆序执行，遇到冲突/缺失只跳过，绝不删除任何文件
- 中途异常可重复点击继续（断点续做）
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import plans_dir
from .models import RenameRecord


def directory_key(directory: str | Path) -> str:
    return hashlib.sha256(str(Path(directory).resolve()).encode("utf-8")).hexdigest()[:16]


class UndoManager:
    def __init__(self, base: Path | None = None):
        self.base = Path(base) if base else plans_dir()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str, run_id: str) -> Path:
        return self.base / f"{key}_{run_id}.json"

    def _atomic(self, path: Path, data: dict) -> None:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def save_plan(self, directory: str | Path, mode: str,
                  records: list[RenameRecord], run_id: str | None = None) -> Path:
        key = directory_key(directory)
        rid = run_id or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        data = {
            "run_id": rid,
            "directory": str(Path(directory).resolve()),
            "mode": mode,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "undone": False,
            "records": [r.to_dict() for r in records],
        }
        p = self._path(key, rid)
        self._atomic(p, data)
        return p

    def list_plans(self, directory: str | Path) -> list[dict]:
        key = directory_key(directory)
        out = []
        for p in sorted(self.base.glob(f"{key}_*.json"), reverse=True):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                d["_path"] = str(p)
                out.append(d)
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda d: d.get("created_at", ""), reverse=True)

    def latest_active(self, directory: str | Path) -> dict | None:
        for d in self.list_plans(directory):
            if not d.get("undone", False):
                return d
        return None

    def undo(self, directory: str | Path, progress: Callable | None = None) -> dict:
        plan = self.latest_active(directory)
        if plan is None:
            return {"ok": False, "message": "该目录没有可撤销的重命名记录。",
                    "restored": 0, "skipped": 0, "failed": 0, "details": []}

        p = Path(plan["_path"])
        records = plan.get("records", [])
        restored = skipped = failed = 0
        details: list[str] = []
        total = len(records)

        for i in range(len(records) - 1, -1, -1):
            rec = records[i]
            if rec.get("status") != "done":
                continue
            src, dst = Path(rec.get("src", "")), Path(rec.get("dst", ""))
            try:
                if not dst.exists():
                    skipped += 1
                    details.append(f"跳过：{dst.name} 已不存在")
                elif src.exists():
                    skipped += 1
                    details.append(f"跳过：原文件名 {src.name} 已被占用，为避免覆盖未还原")
                else:
                    os.rename(dst, src)
                    rec["status"] = "undone"
                    restored += 1
                    # 每成功一条就原子落盘，中断后可继续
                    self._atomic(p, plan)
            except OSError as exc:
                failed += 1
                details.append(f"失败：{dst.name} → {src.name}，{exc}")
            if progress:
                progress(total - i, total, dst.name)

        plan["undone"] = restored > 0 and failed == 0 and all(
            r.get("status") != "done" for r in records
        )
        plan["undo_finished_at"] = datetime.now().isoformat(timespec="seconds")
        self._atomic(p, plan)
        return {
            "ok": True, "restored": restored, "skipped": skipped, "failed": failed,
            "details": details,
            "message": f"已还原 {restored} 个文件名；跳过 {skipped} 个；失败 {failed} 个。",
        }
