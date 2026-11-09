"""顺序打乱实验（docs/judge.md 9.2 节）。

真实硬件里所有 always 块同时工作，没有先后；仿真器却要一个一个地执行。
把模块里的顶层 always 块换个先后顺序重新仿真，结果变了，就说明代码依赖仿真器的执行顺序（竞争）。

试验结论（iverilog 12）：交换源码里 always 块的先后会改变 iverilog 的执行顺序——
阻塞赋值写法（tests/fixtures/race_blocking.v）结果随之改变，非阻塞写法（race_nonblocking.v）不变。
"""
from __future__ import annotations

import itertools
import random
import tempfile
from pathlib import Path

from . import config
from .log import append_log
from .problem import load_problem
from .sim import compile_design, simulate
from .tags import TAG_ORDER
from .trace import first_mismatch
from .vparse import AlwaysBlock, ParseError, parse_top

MAX_ORDERS = 6          # 含原顺序在内最多 6 种排列
VARIANT_FILE = "variant.v"


def block_orders(n: int) -> list[tuple[int, ...]]:
    """除原顺序外的排列（块编号从 1 开始）。块数 ≤ 3 时穷举；更多时取固定的几种，保证可复现。"""
    identity = tuple(range(1, n + 1))
    if n < 2:
        return []
    if n <= 3:
        return [p for p in itertools.permutations(identity) if p != identity]
    candidates = [
        identity[::-1],                                   # 整体倒序
        identity[1:] + identity[:1],                      # 左移一位
        identity[-1:] + identity[:-1],                    # 右移一位
        tuple(x for pair in zip(identity[1::2], identity[::2]) for x in pair) + identity[n - n % 2:],
    ]
    rng = random.Random(n)                                # 固定种子
    while len(candidates) < 50:
        perm = list(identity)
        rng.shuffle(perm)
        candidates.append(tuple(perm))
    orders: list[tuple[int, ...]] = []
    for p in candidates:
        if p != identity and p not in orders:
            orders.append(p)
        if len(orders) == MAX_ORDERS - 1:
            break
    return orders


def build_variant(code: str, blocks: list[AlwaysBlock], order: tuple[int, ...]) -> tuple[str, dict[int, int]]:
    """按 order 重排 always 块：第 k 个块的位置放原来的第 order[k] 个块，块内一个字符都不改。

    返回 (变体源码, 变体行号 → 原文件行号)。
    """
    segments: list[tuple[int, str]] = []     # (该段在原文件中的起始偏移, 文本)
    pos = 0
    for slot, src_index in zip(blocks, order):
        src = blocks[src_index - 1]
        segments.append((pos, code[pos:slot.start]))
        segments.append((src.start, code[src.start:src.end]))
        pos = slot.end
    segments.append((pos, code[pos:]))

    line_map: dict[int, int] = {}
    vline = 1
    for offset, text in segments:
        oline = code.count("\n", 0, offset) + 1
        for k, piece in enumerate(text.split("\n")):
            if piece.strip():
                line_map[vline + k] = oline + k
        vline += text.count("\n")
    return "".join(text for _, text in segments), line_map


def _simulate(work: Path, text: str, timeout: float) -> tuple[dict, list[dict], bool]:
    (work / VARIANT_FILE).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="")
    comp, vvp = compile_design(work, VARIANT_FILE, "variant.vvp", timeout)
    if not comp["ok"]:
        return comp, [], False
    trace, timed_out = simulate(work, vvp, timeout)
    return comp, trace, timed_out


def _result(*, ok: bool, order_sensitive: bool | None = None, blocks: int = 0,
            block_lines: list | None = None, variants: list | None = None, message: str | None = None,
            base_trace: list | None = None) -> dict:
    return {
        "ok": ok,
        "order_sensitive": order_sensitive,
        "blocks": blocks,
        "block_lines": block_lines or [],
        "variants": variants or [],
        "message": message,
        "base_trace": base_trace or [],     # 原顺序的轨迹（前端 diff 模式用）
    }


def shuffle_test(
    code: str,
    problem_id: str,
    *,
    student: str | None = None,
    problems_dir: Path | None = None,
    timeout: float = config.DEFAULT_TIMEOUT,
    log: bool = True,
) -> dict:
    problem = load_problem(problem_id, problems_dir)
    result = _shuffle(code, problem, timeout)
    if log:
        append_log({"type": "shuffle_test", "problem": problem.id, "student": student, "result": result})
    return result


def _shuffle(code: str, problem, timeout: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="judge_shuffle_") as tmp:
        work = Path(tmp)
        (work / config.TB_FILE).write_text(problem.tb_path.read_text(encoding="utf-8"), encoding="utf-8")

        comp, base, base_timeout = _simulate(work, code, timeout)
        if not comp["ok"]:
            return _result(ok=False, message="代码还没有通过编译，先修好编译错误再做顺序打乱实验")
        if base_timeout:
            return _result(ok=False, message="原代码仿真超时，先解决超时问题再做顺序打乱实验")
        try:
            blocks = parse_top(code, config.TOP_MODULE).always_blocks
        except ParseError as exc:
            return _result(ok=False, message=f"没能识别代码里的 always 块：{exc}")

        block_lines = [[b.first_line, b.last_line] for b in blocks]
        if len(blocks) < 2:
            return _result(ok=True, order_sensitive=False, blocks=len(blocks), block_lines=block_lines,
                           message="只有 1 个 always 块，没有可以交换的顺序" if blocks else "代码里没有 always 块",
                           base_trace=base)

        variants = []
        for order in block_orders(len(blocks)):
            text, line_map = build_variant(code, blocks, order)
            vcomp, trace, timed_out = _simulate(work, text, timeout)
            errors = [
                {**e, "line": line_map.get(e["line"], e["line"]) if e["file"] == VARIANT_FILE else e["line"],
                 "file": config.STUDENT_FILE if e["file"] == VARIANT_FILE else e["file"]}
                for e in vcomp["errors"]
            ]
            diff = None
            if vcomp["ok"] and not timed_out:
                mm = first_mismatch(base, trace)
                if mm:
                    diff = {"step": mm["step"], "signal": mm["signal"],
                            "base": mm["expected"], "variant": mm["actual"]}
            variants.append({
                "order": list(order),
                "first_diff": diff,
                "timeout": timed_out,
                "errors": errors,
                "trace": trace,
            })

    sensitive = any(v["first_diff"] or v["timeout"] or v["errors"] for v in variants)
    return _result(ok=True, order_sensitive=sensitive, blocks=len(blocks),
                   block_lines=block_lines, variants=variants, base_trace=base)


def apply_shuffle(diagnosis: dict, shuffle: dict) -> dict:
    """顺序打乱实验结果为“顺序相关”时，返回加上 race_order_sensitive 标签的诊断副本。"""
    if not shuffle.get("order_sensitive"):
        return diagnosis
    tags = set(diagnosis["tags"]) | {"race_order_sensitive"}
    return {**diagnosis, "tags": [t for t in TAG_ORDER if t in tags]}
