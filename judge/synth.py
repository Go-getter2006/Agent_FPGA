"""yosys 综合检查与硬件统计。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config
from .runner import run

# proc 之后会出现的触发器 / 锁存器单元类型
FF_CELL_TYPES = frozenset({
    "$dff", "$dffe", "$adff", "$adffe", "$aldff", "$aldffe",
    "$sdff", "$sdffe", "$sdffce", "$dffsr", "$dffsre",
})
LATCH_CELL_TYPES = frozenset({"$dlatch", "$adlatch", "$dlatchsr", "$sr"})

_MSG_RE = re.compile(r"^(?:[^\s:]+:\d+:\s*)?(?:Warning|ERROR):")
_NAME_RE = re.compile(r"\\([^\s\[\]{}]+)")
MULTI_DRIVER_TEXT = "multiple conflicting drivers"

PROC_RTLIL = "proc.il"
STAT_JSON = "stat.json"


def _messages(text: str) -> list[str]:
    """取 yosys 的 Warning / ERROR 行（多行告警只取第一行），按出现顺序去重。"""
    seen: dict[str, None] = {}
    for line in text.splitlines():
        line = line.strip()
        if _MSG_RE.match(line):
            seen.setdefault(line.rstrip(":"), None)
    return list(seen)


def synth_check(workdir: Path, design_file: str, timeout: float) -> dict:
    """`synth -top top_module`：报错即视为不可综合。"""
    script = f"read_verilog {design_file}; synth -top {config.TOP_MODULE}"
    result = run(["yosys", "-q", "-p", script], workdir, timeout)
    if result.timeout:
        return {"ok": False, "timeout": True, "messages": ["综合超时"]}
    messages = _messages(result.output)
    ok = result.returncode == 0 and not any("ERROR:" in m for m in messages)
    return {"ok": ok, "timeout": False, "messages": messages}


def has_multi_driver(synth: dict) -> bool:
    return any(MULTI_DRIVER_TEXT in m for m in synth.get("messages", []))


def _q_signals(rtlil: str, cell_types: frozenset[str]) -> list[str]:
    """从 RTLIL 里读出指定类型单元 Q 端连接的信号名（去掉内部 $ 名字）。"""
    names: set[str] = set()
    in_top = False
    cell_type: str | None = None
    top_header = f"module \\{config.TOP_MODULE}"
    for raw in rtlil.splitlines():
        line = raw.strip()
        if raw.startswith("module "):
            in_top = line == top_header
            continue
        if not in_top:
            continue
        if raw == "end":
            in_top = False
            continue
        if line.startswith("cell "):
            parts = line.split()
            cell_type = parts[1] if len(parts) > 1 else None
        elif line == "end":
            cell_type = None
        elif cell_type in cell_types and line.startswith("connect \\Q "):
            names.update(_NAME_RE.findall(line[len("connect \\Q "):]))
    return sorted(names)


def _count_cells(stat: dict) -> tuple[int, int]:
    design = stat.get("design") or next(iter(stat.get("modules", {}).values()), {})
    cells = design.get("num_cells_by_type", {})
    ff = sum(n for t, n in cells.items() if t.startswith("FD"))
    lut = sum(n for t, n in cells.items() if re.fullmatch(r"LUT\d", t))
    return ff, lut


def null_hardware() -> dict:
    return {"ff_signals": None, "latch_signals": None, "ff_count": None, "lut_count": None}


def hardware_stats(workdir: Path, design_file: str, timeout: float) -> dict:
    """触发器 / 锁存器信号来自 proc 之后的单元；个数来自 synth_xilinx 之后的 stat。

    - proc 之后跑 opt_clean：去掉输出没人用的单元，否则 for 循环变量、块内临时变量
      也会被算成触发器
    - fsm_encoding=none：不让 yosys 把状态机改成独热码，触发器个数与代码里写的状态位宽一致
    - -nosrl：不把移位寄存器映射成 SRL16E，否则触发器个数会变成 0
    """
    top = config.TOP_MODULE
    script = "; ".join([
        f"read_verilog {design_file}",
        f"hierarchy -check -top {top}",
        "proc",
        "flatten",
        "opt_clean",
        f"write_rtlil {PROC_RTLIL}",
        "design -reset",
        f"read_verilog {design_file}",
        'setattr -set fsm_encoding "none" w:*',
        f"synth_xilinx -flatten -nosrl -top {top}",
        f"tee -q -o {STAT_JSON} stat -json",
    ])
    result = run(["yosys", "-q", "-p", script], workdir, timeout)
    if not result.ok:
        return null_hardware()
    rtlil = (workdir / PROC_RTLIL).read_text(encoding="utf-8", errors="replace")
    stat = json.loads((workdir / STAT_JSON).read_text(encoding="utf-8"))
    ff_count, lut_count = _count_cells(stat)
    return {
        "ff_signals": _q_signals(rtlil, FF_CELL_TYPES),
        "latch_signals": _q_signals(rtlil, LATCH_CELL_TYPES),
        "ff_count": ff_count,
        "lut_count": lut_count,
    }
