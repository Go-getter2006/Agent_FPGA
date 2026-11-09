"""信号 → 代码行映射（docs/judge.md 9.1 节）。

试验结论（2026-11，yosys 0.33）：proc 之后各单元的 src 属性
- 连续赋值、运算符：能精确到行
- 组合 always 块里的 if / case：只给到整个 if / case 语句的行范围
- 时序 always 块里的寄存器：触发器单元的 src 是整个 always 块
- 赋常数的语句（如 q <= 0）：没有任何单元记录这一行

所以做法是两步：
1. yosys：proc 之后从信号出发，沿内部连线往回找驱动它的单元，收集这些单元的 src 行范围（候选范围）
2. 词法扫描（judge.vparse）：在候选范围内，只保留“这个信号出现在赋值号左边”的那些行
   - 连续赋值（assign、wire 声明赋值）在模块层面，不受候选范围限制
   - 子模块例化的输出直接取例化语句所在行
扫描失败或某个信号一行都找不到时，退回 yosys 的候选范围，并把 drivers_granularity 记为 "block"。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from . import config
from .runner import run
from .vparse import ParseError, parse_top

DRIVERS_JSON = "drivers.json"
_SRC_RE = re.compile(r"^(?P<file>.*):(?P<l1>\d+)\.\d+-(?P<l2>\d+)\.\d+$")


def _src_lines(src: str | None, design_file: str) -> set[int]:
    lines: set[int] = set()
    for part in (src or "").split("|"):
        m = _SRC_RE.match(part)
        if not m or Path(m.group("file")).name != design_file:
            continue
        l1, l2 = int(m.group("l1")), int(m.group("l2"))
        if l1 > 0:
            lines.update(range(l1, l2 + 1))
    return lines


def _yosys_module(workdir: Path, design_file: str, timeout: float) -> dict | None:
    script = (f"read_verilog {design_file}; hierarchy -top {config.TOP_MODULE}; "
              f"proc; write_json {DRIVERS_JSON}")
    result = run(["yosys", "-q", "-p", script], workdir, timeout)
    if not result.ok:
        return None
    data = json.loads((workdir / DRIVERS_JSON).read_text(encoding="utf-8"))
    return data["modules"].get(config.TOP_MODULE)


def _cones(module: dict, design_file: str) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    """每个公开信号的 (候选行范围, 子模块例化语句行)。"""
    public_bits = {b for w in module["netnames"].values() if not w["hide_name"]
                   for b in w["bits"] if isinstance(b, int)}
    drivers_of: dict[int, list[str]] = defaultdict(list)
    for cname, cell in module["cells"].items():
        for port, bits in cell["connections"].items():
            if cell["port_directions"].get(port) == "output":
                for b in bits:
                    if isinstance(b, int):
                        drivers_of[b].append(cname)

    inputs = {n for n, p in module["ports"].items() if p["direction"] == "input"}
    cones: dict[str, set[int]] = {}
    instances: dict[str, set[int]] = {}
    for name, wire in module["netnames"].items():
        if wire["hide_name"] or name in inputs:
            continue
        lines: set[int] = set()
        inst_lines: set[int] = set()
        seen: set[str] = set()
        todo = [b for b in wire["bits"] if isinstance(b, int)]
        while todo:
            bit = todo.pop()
            for cname in drivers_of.get(bit, []):
                if cname in seen:
                    continue
                seen.add(cname)
                cell = module["cells"][cname]
                src = _src_lines(cell["attributes"].get("src"), design_file)
                if not cell["type"].startswith("$"):
                    inst_lines |= src          # 子模块例化
                    continue
                lines |= src
                for port, bits in cell["connections"].items():
                    if cell["port_directions"].get(port) == "input":
                        todo.extend(b for b in bits if isinstance(b, int) and b not in public_bits)
        cones[name] = lines
        instances[name] = inst_lines
    return cones, instances


def compute_drivers(workdir: Path, design_file: str, code: str, timeout: float) -> tuple[dict, str]:
    """返回 (drivers, drivers_granularity)。drivers 的键按字母序，行号升序去重。"""
    module = _yosys_module(workdir, design_file, timeout)
    cones, instances = _cones(module, design_file) if module else ({}, {})
    try:
        info = parse_top(code, config.TOP_MODULE)
    except ParseError:
        info = None

    if info is None:
        drivers = {name: sorted(lines) for name, lines in cones.items() if lines}
        return dict(sorted(drivers.items())), "block"

    by_signal: dict[str, list] = defaultdict(list)
    for a in info.assignments:
        for target in a.targets:
            by_signal[target].append(a)

    if module is None:
        # yosys 读不进这份代码（例如不可综合的 while 循环）：只用词法扫描的结果
        names = sorted(by_signal)
        inputs: set[str] = set()
    else:
        names = sorted(cones)
        inputs = {n for n, p in module["ports"].items() if p["direction"] == "input"}

    drivers: dict[str, list[int]] = {}
    granularity = "statement"
    for name in names:
        if name in inputs:
            continue
        cone = cones.get(name, set())
        lines = {
            a.line for a in by_signal.get(name, [])
            if a.kind != "procedural" or module is None or a.line in cone
        }
        lines |= instances.get(name, set())
        if not lines and cone:
            lines = cone
            granularity = "block"
        if lines:
            drivers[name] = sorted(lines)
    return drivers, granularity
