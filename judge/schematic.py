"""电路图用的网表：yosys `prep` 之后的 RTL 级网表（JSON），前端用 netlistsvg 画成电路图。

- 保留加法器、比较器、选择器、触发器这一级的单元，学生能和代码对上；每个单元带 src 属性（代码行号）
- 只是“看图”用：不参与判对错、不改变裁判输出（docs/judge.md 第 10 节第 16 条）
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from . import config
from .runner import run

NETLIST_JSON = "schematic.json"
_SRC_RE = re.compile(r"(\d+)\.\d+-(\d+)\.\d+")


def src_lines(src: str | None) -> list[int]:
    """yosys 的 src 属性（如 "student.v:16.13-16.26|student.v:18.9-18.20"）→ 覆盖到的代码行号。"""
    out: set[int] = set()
    for part in (src or "").split("|"):
        m = _SRC_RE.search(part.rsplit(":", 1)[-1])
        if m:
            out.update(range(int(m.group(1)), int(m.group(2)) + 1))
    return sorted(out)


def schematic(code: str, timeout: float | None = None) -> dict:
    """返回 {"ok", "netlist", "cells": {名字: {type, lines, outputs}}, "error"}；编译不过时 ok 为 False。
    outputs：这个单元驱动的、代码里有名字的信号（触发器的 src 覆盖整个 always 块，前端按它的输出信号找赋值行）。"""
    timeout = timeout or config.DEFAULT_TIMEOUT
    with tempfile.TemporaryDirectory(prefix="schem_") as tmp:
        work = Path(tmp)
        (work / config.STUDENT_FILE).write_text(code, encoding="utf-8")
        script = (f"read_verilog {config.STUDENT_FILE}; prep -top {config.TOP_MODULE}; "
                  f"opt_clean -purge; write_json -compat-int {NETLIST_JSON}")
        result = run(["yosys", "-q", "-p", script], work, timeout)
        path = work / NETLIST_JSON
        if result.timeout:
            return {"ok": False, "netlist": None, "cells": {}, "error": "生成电路图超时"}
        if result.returncode != 0 or not path.is_file():
            first = next((ln for ln in result.output.splitlines() if "ERROR" in ln), "代码没有通过综合")
            return {"ok": False, "netlist": None, "cells": {}, "error": first.strip()}
        netlist = json.loads(path.read_text(encoding="utf-8"))
    top = netlist.get("modules", {}).get(config.TOP_MODULE, {})
    # 网线编号 → 信号名（只要代码里有名字的，不要 yosys 内部生成的 $ 名字）
    bit_name: dict[int, str] = {}
    for name, net in (top.get("netnames") or {}).items():
        if net.get("hide_name"):
            continue
        for b in net.get("bits", []):
            if isinstance(b, int):
                bit_name.setdefault(b, name)
    cells = {}
    for name, c in (top.get("cells") or {}).items():
        outs = sorted({bit_name[b] for port, d in (c.get("port_directions") or {}).items() if d == "output"
                       for b in (c.get("connections") or {}).get(port, []) if isinstance(b, int) and b in bit_name})
        cells[name] = {"type": c.get("type"), "lines": src_lines((c.get("attributes") or {}).get("src")),
                       "outputs": outs}
    return {"ok": True, "netlist": {"modules": {config.TOP_MODULE: top}}, "cells": cells, "error": None}
