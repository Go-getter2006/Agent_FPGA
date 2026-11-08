"""解析 testbench 打印的 STEP 行，并与参考答案逐行比较。

格式（docs/judge.md 第 4 节）：
    STEP <序号> | <输入名>=<值> ... | <输出名>=<值> ...
"""
from __future__ import annotations

import re

_STEP_RE = re.compile(r"^STEP\s+(\d+)\s*\|([^|]*)\|([^|]*)$")


def _parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in text.split():
        name, sep, value = token.partition("=")
        if sep and name:
            fields[name] = value
    return fields


def parse_trace(stdout: str) -> list[dict]:
    """只认 STEP 行，其他输出（如 $finish 提示）忽略。"""
    trace = []
    for line in stdout.splitlines():
        m = _STEP_RE.match(line.strip())
        if not m:
            continue
        trace.append({
            "step": int(m.group(1)),
            "inputs": _parse_fields(m.group(2)),
            "outputs": _parse_fields(m.group(3)),
        })
    return trace


def first_mismatch(ref: list[dict], student: list[dict]) -> dict | None:
    """按行比较，返回第一个不一致的 STEP 与信号；完全一致返回 None。

    同一 STEP 有多个信号不一致时，取 testbench 打印顺序里的第一个。
    学生轨迹缺少某行时 actual 为 None；多出行时 expected 为 None。
    """
    for i, ref_row in enumerate(ref):
        stu_row = student[i] if i < len(student) else None
        stu_outputs = stu_row["outputs"] if stu_row and stu_row["step"] == ref_row["step"] else {}
        for signal, expected in ref_row["outputs"].items():
            actual = stu_outputs.get(signal)
            if actual != expected:
                return {
                    "step": ref_row["step"],
                    "signal": signal,
                    "expected": expected,
                    "actual": actual,
                    "inputs": dict(ref_row["inputs"]),
                }
        if stu_row is not None:
            extra = [s for s in stu_row["outputs"] if s not in ref_row["outputs"]]
            if extra:
                return {
                    "step": ref_row["step"],
                    "signal": extra[0],
                    "expected": None,
                    "actual": stu_row["outputs"][extra[0]],
                    "inputs": dict(ref_row["inputs"]),
                }
    if len(student) > len(ref):
        row = student[len(ref)]
        signal = next(iter(row["outputs"]), None)
        return {
            "step": row["step"],
            "signal": signal,
            "expected": None,
            "actual": row["outputs"].get(signal) if signal else None,
            "inputs": dict(row["inputs"]),
        }
    return None
