"""由诊断结果生成标签（docs/judge.md 第 7 节）。只用工具结果，不做任何推测。"""
from __future__ import annotations

import re

# 标签输出顺序固定，保证 JSON 可复现
TAG_ORDER = (
    "compile_error",
    "sim_mismatch",
    "latch_inferred",
    "non_synthesizable",
    "multi_driven",
    "blocking_in_seq",
    "nonblocking_in_comb",
    "width_mismatch",
    "fragile_pass",
    "race_order_sensitive",
)

LINT_TAGS = {
    "BLKSEQ": "blocking_in_seq",
    "COMBDLY": "nonblocking_in_comb",
    "WIDTH": "width_mismatch",
    "WIDTHTRUNC": "width_mismatch",
    "WIDTHEXPAND": "width_mismatch",
    "WIDTHXZEXPAND": "width_mismatch",
    "WIDTHCONCAT": "width_mismatch",
    "MULTIDRIVEN": "multi_driven",
}

FRAGILE_SOURCES = ("latch_inferred", "non_synthesizable", "multi_driven")

_GENERATES_RE = re.compile(r"generates (\d+) bits?")


def lint_tag(item: dict) -> str | None:
    """把一条 verilator 告警映射成标签；没有对应标签返回 None。

    例外：WIDTHEXPAND 里被扩展的一方只有 1 位时不算位宽不匹配。
    `a + b + cin`、`count + en` 这类 1 位信号参与多位运算的写法是教材标准写法，
    verilator 仍会报 WIDTHEXPAND；把它算成误区会冤枉几乎所有学生。
    多位扩展（例如 4 位的中间结果赋给 5 位，进位丢失）仍然算。
    """
    tag = LINT_TAGS.get(item["code"])
    if tag and item["code"] == "WIDTHEXPAND":
        widths = _GENERATES_RE.findall(item.get("message", ""))
        if widths and int(widths[-1]) <= 1:
            return None
    return tag


def compute_tags(*, compile_ok: bool, sim: dict, synth: dict, hardware: dict,
                 lint: list[dict], yosys_multi_driven: bool) -> list[str]:
    tags: set[str] = set()
    if not compile_ok:
        return ["compile_error"]
    if not sim["ok"]:
        tags.add("sim_mismatch")
    if hardware.get("latch_signals"):
        tags.add("latch_inferred")
    if synth["ok"] is False and not synth.get("timeout"):
        tags.add("non_synthesizable")
    if yosys_multi_driven:
        tags.add("multi_driven")
    for item in lint:
        tag = lint_tag(item)
        if tag:
            tags.add(tag)
    if sim["ok"] and any(t in tags for t in FRAGILE_SOURCES):
        tags.add("fragile_pass")
    return [t for t in TAG_ORDER if t in tags]
