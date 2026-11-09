"""裁判运行日志：logs/judge.jsonl，一行一条记录，只追加。时间戳只写在这里，不进裁判输出。"""
from __future__ import annotations

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config


def append_log(record: dict, path: Path | None = None) -> None:
    path = Path(path) if path else config.log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record},
        ensure_ascii=False, separators=(",", ":"),
    ) + "\n"
    with path.open("a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)     # 多个 worker 同时写时不互相穿插
        try:
            f.write(line)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
