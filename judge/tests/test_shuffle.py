"""顺序打乱实验（docs/judge.md 9.2 节）。"""
from __future__ import annotations

import pytest

from judge import apply_shuffle, shuffle_test
from judge.problem import list_problem_ids, load_problem
from judge.shuffle import block_orders, build_variant
from judge.vparse import parse_top

from .conftest import FIXTURES

RACE_PROBLEMS = FIXTURES / "problems"


def _race(name: str) -> dict:
    code = (FIXTURES / name).read_text(encoding="utf-8")
    return shuffle_test(code, "race_swap", problems_dir=RACE_PROBLEMS, log=False)


def test_blocking_race_is_order_sensitive():
    result = _race("race_blocking.v")
    assert result["ok"] and result["order_sensitive"] is True
    assert result["blocks"] == 2
    assert result["block_lines"] == [[9, 12], [14, 17]]
    assert result["variants"] == [{
        "order": [2, 1],
        "first_diff": {"step": 1, "signal": "y1", "base": "1", "variant": "0"},
        "timeout": False,
        "errors": [],
    }]


def test_nonblocking_is_order_independent():
    result = _race("race_nonblocking.v")
    assert result["ok"] and result["order_sensitive"] is False
    assert result["variants"][0]["first_diff"] is None


@pytest.mark.parametrize("pid", list_problem_ids())
def test_references_are_order_independent(pid):
    problem = load_problem(pid)
    result = shuffle_test(problem.ref_path.read_text(encoding="utf-8"), pid, log=False)
    assert result["ok"] and result["order_sensitive"] is False


def test_three_blocks_try_all_orders():
    code = (load_problem("seq_detector_101").cases_dir / "c5_fragile_latch.v").read_text(encoding="utf-8")
    result = shuffle_test(code, "seq_detector_101", log=False)
    assert result["blocks"] == 3
    assert [v["order"] for v in result["variants"]] == [
        [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]]


def test_block_orders_capped_and_deterministic():
    assert block_orders(1) == []
    assert block_orders(2) == [(2, 1)]
    for n in (4, 5, 7):
        orders = block_orders(n)
        assert len(orders) == 5 and len(set(orders)) == 5
        assert tuple(range(1, n + 1)) not in orders
        assert orders == block_orders(n)


def test_variant_keeps_block_text_and_maps_lines():
    code = (FIXTURES / "race_blocking.v").read_text(encoding="utf-8")
    blocks = parse_top(code).always_blocks
    text, line_map = build_variant(code, blocks, (2, 1))
    original = code.splitlines()
    variant = text.splitlines()
    assert len(variant) == len(original)
    for vline, oline in line_map.items():
        assert variant[vline - 1].strip() == original[oline - 1].strip()
    assert line_map[9] == 14 and line_map[14] == 9      # 两个块互换了位置
    assert sorted(code) == sorted(text)                  # 只换位置，不改内容


def test_compile_error_is_reported():
    code = (load_problem("seq_detector_101").cases_dir / "c7_compile.v").read_text(encoding="utf-8")
    result = shuffle_test(code, "seq_detector_101", log=False)
    assert result["ok"] is False and "编译" in result["message"]


def test_single_block_has_nothing_to_swap():
    result = shuffle_test(load_problem("counter_mod10").ref_path.read_text(encoding="utf-8"),
                          "counter_mod10", log=False)
    assert result["ok"] and result["order_sensitive"] is False and result["variants"] == []


def test_apply_shuffle_adds_tag_in_order():
    diagnosis = {"tags": ["blocking_in_seq"], "problem": "x"}
    tagged = apply_shuffle(diagnosis, {"order_sensitive": True})
    assert tagged["tags"] == ["blocking_in_seq", "race_order_sensitive"]
    assert diagnosis["tags"] == ["blocking_in_seq"]            # 不改原对象
    assert apply_shuffle(diagnosis, {"order_sensitive": False}) is diagnosis
