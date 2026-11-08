"""iverilog 编译与 vvp 仿真。"""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .runner import CmdResult, run
from .trace import parse_trace

_LOC_RE = re.compile(r"^(?P<file>[^\s:]+):(?P<line>\d+):\s*(?P<msg>.*)$")
_SKIP_LINES = re.compile(r"^(I give up\.|\d+ error\(s\) during elaboration\.|Elaboration failed)")


def parse_compile_errors(result: CmdResult) -> list[dict]:
    """把 iverilog 的报错整理成 {file, line, message}，保留原始信息，丢掉 warning。"""
    if result.timeout:
        return [{"file": None, "line": None, "message": "编译超时"}]
    errors: list[dict] = []
    loose: list[str] = []
    for raw in result.output.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _LOC_RE.match(line)
        if m:
            msg = m.group("msg").lstrip(": ").strip()
            if msg.lower().startswith("warning:"):
                continue
            errors.append({"file": m.group("file"), "line": int(m.group("line")), "message": msg})
        elif not _SKIP_LINES.match(line.strip()):
            loose.append(line.strip())
    if not errors:
        # 没有带行号的报错（如缺模块），把原始信息整体保留
        errors = [{"file": None, "line": None, "message": text} for text in loose]
    if not errors:
        errors = [{"file": None, "line": None, "message": f"iverilog 退出码 {result.returncode}"}]
    return errors


def compile_design(workdir: Path, design_file: str, out_name: str, timeout: float) -> tuple[dict, str | None]:
    """编译 testbench + 设计文件。返回 (compile 字段, vvp 文件名或 None)。"""
    cmd = ["iverilog", "-g2005", "-s", config.TB_TOP, "-o", out_name, config.TB_FILE, design_file]
    result = run(cmd, workdir, timeout)
    if result.ok:
        return {"ok": True, "errors": []}, out_name
    return {"ok": False, "errors": parse_compile_errors(result)}, None


def simulate(workdir: Path, vvp_file: str, timeout: float) -> tuple[list[dict], bool]:
    """运行仿真，返回 (轨迹, 是否超时)。超时时轨迹为空。"""
    result = run(["vvp", "-n", vvp_file], workdir, timeout)
    if result.timeout:
        return [], True
    return parse_trace(result.stdout), False
