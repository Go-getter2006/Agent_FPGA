"""verilator 静态检查。"""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .runner import run

_LINT_RE = re.compile(
    r"^%(?P<sev>Warning|Error)(?:-(?P<code>[A-Za-z0-9_]+))?:\s*"
    r"(?P<file>[^\s:]+):(?P<line>\d+):(?:\d+:)?\s*(?P<msg>.*)$"
)


def lint_cmd(design_file: str) -> list[str]:
    return [
        "verilator", "--lint-only", "-Wall",
        "-Wno-fatal",           # 告警不中断，全部收集
        "-Wno-DECLFILENAME",    # 文件名由裁判固定为 student.v，这条告警与学生无关
        "--no-timing",          # 设计里写 # 延时 / 事件控制会得到明确告警
        "--default-language", "1364-2005",
        "--top-module", config.TOP_MODULE,
        design_file,
    ]


def run_lint(workdir: Path, design_file: str, timeout: float) -> list[dict]:
    result = run(lint_cmd(design_file), workdir, timeout)
    if result.timeout:
        return [{"code": "TIMEOUT", "line": None, "message": "verilator 检查超时"}]
    items: list[dict] = []
    for raw in result.output.splitlines():
        m = _LINT_RE.match(raw.strip())
        if not m or m.group("file") != design_file:
            continue
        items.append({
            "code": m.group("code") or m.group("sev").upper(),
            "line": int(m.group("line")),
            "message": m.group("msg").strip(),
        })
    return items
