"""阶段 4 验收：校验器对一组“故意泄露代码”的样例全部拦截，正常提示不误拦。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.hint_guard import leak_reason, validate_hint

SAMPLES = json.loads((Path(__file__).parent / "fixtures" / "leaky_outputs.json").read_text(encoding="utf-8"))


def _raw(sample: dict, level: int = 1, lines=(5,)) -> str:
    return json.dumps({"level": level, "focus": {"step": 3, "signal": "out", "lines": list(lines)},
                       "message": sample["message"], "question": sample["question"],
                       "concept_tags": ["sequential"]}, ensure_ascii=False)


@pytest.mark.parametrize("sample", SAMPLES["leaky"], ids=[s["name"] for s in SAMPLES["leaky"]])
def test_leaky_outputs_are_blocked(sample):
    result = validate_hint(_raw(sample), level=1, code_lines=30)
    assert not result["ok"]
    assert any(r.startswith("泄露代码") for r in result["reasons"]), result["reasons"]


@pytest.mark.parametrize("sample", SAMPLES["clean"], ids=[s["name"] for s in SAMPLES["clean"]])
def test_clean_outputs_pass(sample):
    result = validate_hint(_raw(sample), level=1, code_lines=30)
    assert result["ok"], result["reasons"]


def test_structure_rules():
    ok = SAMPLES["clean"][0]
    assert not validate_hint("不是 json", level=1, code_lines=30)["ok"]
    assert "level 应为 2" in validate_hint(_raw(ok, level=1), level=2, code_lines=30)["reasons"]
    long = {**ok, "message": "很" * 201}
    assert any("超过 200" in r for r in validate_hint(_raw(long), level=1, code_lines=30)["reasons"])
    no_q = {**ok, "question": "去看看第 5 步"}
    assert any("？" in r for r in validate_hint(_raw(no_q), level=1, code_lines=30)["reasons"])
    out_of_range = validate_hint(_raw(ok, lines=(31,)), level=1, code_lines=30)
    assert any("超出代码行号范围" in r for r in out_of_range["reasons"])
    missing = json.dumps({"level": 1, "message": "看第 5 步", "question": "为什么？"})
    assert any("缺少字段" in r for r in validate_hint(missing, level=1, code_lines=30)["reasons"])


def test_ascii_question_mark_is_normalized_and_drivers_only_warn():
    sample = {**SAMPLES["clean"][0], "question": "这一行做了什么?"}
    result = validate_hint(_raw(sample, lines=(9,)), level=1, code_lines=30, drivers={"out": [17]})
    assert result["ok"] and result["hint"]["question"].endswith("？")
    assert result["warnings"] == ["focus.lines 没有落在 drivers 里"]


def test_leak_reason_single_quoted_line_allowed():
    assert leak_reason("第 17 行写的是 assign out = (state == S101);") is None
    assert leak_reason("assign a = b;\nassign c = d;") is not None
