"""学情指标的手算对照（docs/learner-model.md 第 3、4 节，每个公式至少一个测试）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.learner_model import (
    AttemptView, HintRequest, LookEvent, Submission, TbView, blind_rate, class_f_value,
    evaluate_prediction, f_value, hint_dependence, latest_tb_scores, mastery_level, normalize_value,
    order_belief_misconception, prediction_misconceptions, prediction_ok, quadrant, r_values)

T0 = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)


def t(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def av(i: int, c: int, p: int) -> AttemptView:
    """第 i 次尝试：c 代码是否通过，p 预测是否达标；象限按第 3 节的表。"""
    return AttemptView(created_at=t(i), sim_ok=bool(c), pred_ok=bool(p), quadrant=quadrant(bool(c), bool(p)))


# ---------------------------------------------------------------- 第 3 节：A_pred、p、四象限

DIAG = {
    "compile": {"ok": True},
    "sim": {"trace": [
        {"step": 0, "inputs": {}, "outputs": {"out": "0", "q": "0000"}},
        {"step": 1, "inputs": {}, "outputs": {"out": "0", "q": "0001"}},
        {"step": 2, "inputs": {}, "outputs": {"out": "1", "q": "0010"}},
        {"step": 3, "inputs": {}, "outputs": {"out": "0", "q": "0011"}},
        {"step": 4, "inputs": {}, "outputs": {"out": "1", "q": "0100"}},
    ]},
    "hardware": {"ff_signals": ["out", "state"], "latch_signals": [], "ff_count": 3, "lut_count": 2},
}
POINTS = [{"signal": "out", "steps": [1, 2, 3, 4]}]
QUESTIONS = ["ff_count", "latch", "ff_signals"]


def test_pred_accuracy_counts_waveform_cells_and_hardware_questions():
    # 波形 4 格对 2 格（STEP 1 ✓、2 ✗、3 ✗、4 ✓），硬件 3 问对 1 问（锁存器 ✓）→ A = 3 / 7
    waveform = {"cells": [{"signal": "out", "step": 1, "value": "0"}, {"signal": "out", "step": 2, "value": "0"},
                          {"signal": "out", "step": 3, "value": "1"}, {"signal": "out", "step": 4, "value": "1"}]}
    hardware = {"ff_count": 2, "latch": False, "ff_signals": ["state"]}
    ev = evaluate_prediction(predict_points=POINTS, hardware_questions=QUESTIONS,
                             waveform=waveform, hardware=hardware, diagnosis=DIAG)
    assert (ev["hits"], ev["total"]) == (3, 7)
    assert ev["accuracy"] == pytest.approx(3 / 7)
    assert ev["waveform"]["accuracy"] == pytest.approx(2 / 4)
    assert ev["hardware"]["accuracy"] == pytest.approx(1 / 3)


def test_ff_signals_question_needs_exact_set():
    base = {"ff_count": 3, "latch": False}
    for answer, ok in ((["state"], False), (["out", "state", "x"], False), (["state", "out"], True)):
        ev = evaluate_prediction(predict_points=[], hardware_questions=QUESTIONS, waveform=None,
                                 hardware={**base, "ff_signals": answer}, diagnosis=DIAG)
        item = next(i for i in ev["hardware"]["items"] if i["question"] == "ff_signals")
        assert item["correct"] is ok


def test_cells_without_tool_result_are_not_counted():
    # 综合失败：hardware 各字段为 null，硬件问题不计入；超时：轨迹为空，波形格不计入
    diag = {"compile": {"ok": True}, "sim": {"trace": []},
            "hardware": {"ff_signals": None, "latch_signals": None, "ff_count": None, "lut_count": None}}
    ev = evaluate_prediction(predict_points=POINTS, hardware_questions=QUESTIONS,
                             waveform={"cells": [{"signal": "out", "step": 1, "value": "0"}]},
                             hardware={"ff_count": 1, "latch": False, "ff_signals": []}, diagnosis=diag)
    assert ev["total"] == 0 and ev["accuracy"] is None


def test_prediction_threshold():
    assert prediction_ok(0.8, 0.8) is True          # A ≥ θ
    assert prediction_ok(4 / 5, 0.8) is True
    assert prediction_ok(0.79, 0.8) is False
    assert prediction_ok(None, 0.8) is None


def test_quadrants():
    assert quadrant(True, True) == "mastered"
    assert quadrant(True, False) == "fragile"
    assert quadrant(False, True) == "design_gap"
    assert quadrant(False, False) == "concept_gap"
    assert quadrant(False, False, compiled=False) == "none"     # 编译失败不划象限
    assert quadrant(True, None) == "none"                       # 没有预测（对照组）


def test_normalize_value():
    assert normalize_value("1", 1) == "1"
    assert normalize_value("101", 4) == "0101"
    assert normalize_value("0xA", 4) == "1010"
    assert normalize_value("h3", 4) == "0011"
    assert normalize_value("10000", 4) is None       # 超出位宽
    assert normalize_value("9", 4) is None           # 只收二进制、十六进制


# ---------------------------------------------------------------- 4.1 脆弱率 F

def test_f_value_last_n_attempts():
    # 6 次带预测的尝试，只看最近 5 次（第 2–6 次）：
    # 第 2 次 c=1 p=0、第 3 次 c=1 p=1、第 4 次 c=0 p=0、第 5 次 c=1 p=0、第 6 次 c=1 p=1
    # N(c=1) = 4，N(c=1, p=0) = 2 → F = 0.5（第 1 次 c=1 p=0 在窗口外，不计）
    attempts = [av(1, 1, 0), av(2, 1, 0), av(3, 1, 1), av(4, 0, 0), av(5, 1, 0), av(6, 1, 1)]
    assert f_value(attempts, n=5) == pytest.approx(0.5)


def test_f_value_empty_denominator_is_none():
    assert f_value([av(1, 0, 1), av(2, 0, 0)], n=5) is None


def test_f_ignores_attempts_without_quadrant():
    none = AttemptView(created_at=t(0), sim_ok=True, pred_ok=False, quadrant="none")
    assert f_value([none, av(1, 1, 1)], n=5) == 0.0


def test_class_f_is_ratio_of_sums_not_mean_of_ratios():
    # 学生甲：分子 1、分母 1（F=1.0）；学生乙：分子 1、分母 4（F=0.25）
    # 全班 F = (1 + 1) / (1 + 4) = 0.4（不是两个 F 的平均 0.625）
    a = [av(1, 1, 0)]
    b = [av(1, 1, 0), av(2, 1, 1), av(3, 1, 1), av(4, 1, 1)]
    assert class_f_value([a, b], n=5) == pytest.approx(0.4)


# ---------------------------------------------------------------- 4.2 掌握等级

def test_r_values_last_m():
    # 最近 3 次：c = 1, 0, 1；p = 1, 1, 0 → R_code = 2/3，R_pred = 2/3
    attempts = [av(1, 0, 0), av(2, 1, 1), av(3, 0, 1), av(4, 1, 0)]
    r_code, r_pred = r_values(attempts, m=3)
    assert r_code == pytest.approx(2 / 3) and r_pred == pytest.approx(2 / 3)


def test_r_values_fewer_than_m():
    assert r_values([av(1, 1, 0), av(2, 1, 1)], m=3) == (1.0, 0.5)


@pytest.mark.parametrize("seq, level", [
    ([], "not_started"),
    ([av(1, 1, 1), av(2, 1, 1), av(3, 1, 1)], "mastered"),
    ([av(1, 1, 1), av(2, 0, 1), av(3, 1, 1)], "mastered"),          # R_code = R_pred = 2/3，最近一次 mastered
    ([av(1, 1, 1), av(2, 1, 1), av(3, 1, 0)], "fragile"),           # 最近一次不是 mastered
    ([av(1, 1, 0), av(2, 1, 0), av(3, 1, 1)], "fragile"),           # R_pred = 1/3
    ([av(1, 1, 1), av(2, 0, 1), av(3, 0, 1)], "learning"),          # R_code = 1/3
    ([av(1, 0, 0)], "learning"),
])
def test_mastery_level_rules(seq, level):
    assert mastery_level(seq, m=3) == level


# ---------------------------------------------------------------- 4.3 盲改率 B

def test_blind_rate():
    # 题 A 提交 3 次：第 1、2 次之间看过波形，第 2、3 次之间什么都没看 → 1 次重复提交是盲改
    # 题 B 提交 2 次：中间有 investigate.locate_step → 不算盲改
    # 题 C 只提交 1 次 → 没有重复提交
    subs = [Submission("A", t(0)), Submission("A", t(10)), Submission("A", t(20)),
            Submission("B", t(5)), Submission("B", t(15)), Submission("C", t(1))]
    looks = [LookEvent("A", t(3), "waveform.view"), LookEvent("B", t(8), "investigate.locate_step"),
             LookEvent("A", t(25), "waveform.cell_click"),        # 在最后一次提交之后，不影响
             LookEvent("A", t(12), "page.view")]                  # 不是查看仿真结果的事件
    b, blind, resubmits = blind_rate(subs, looks)
    assert (blind, resubmits) == (1, 3)
    assert b == pytest.approx(1 / 3)


def test_blind_rate_no_resubmission():
    assert blind_rate([Submission("A", t(0))], [])[0] is None


# ---------------------------------------------------------------- 4.4 提示依赖度 H

def test_hint_dependence():
    # 通过了 A、B、C：A 通过前最高用到 2 级；B 通过前没用提示（通过之后的 3 级不算）；C 通过前用到 3 级
    # H = (2 + 0 + 3) / 3
    first_pass = {"A": t(30), "B": t(30), "C": t(30)}
    hints = [HintRequest("A", 1, t(5)), HintRequest("A", 2, t(10)), HintRequest("B", 3, t(40)),
             HintRequest("C", 3, t(20)), HintRequest("D", 3, t(1))]     # D 没通过，不计入
    assert hint_dependence(first_pass, hints) == pytest.approx(5 / 3)


def test_hint_dependence_nothing_passed():
    assert hint_dependence({}, []) is None


# ---------------------------------------------------------------- 4.5 testbench 得分

def test_latest_tb_score_per_problem():
    subs = [TbView("seq", t(1), 0.5), TbView("seq", t(5), 0.75), TbView("cnt", t(2), 1.0), TbView("seq", t(3), 1.0)]
    assert latest_tb_scores(subs) == {"seq": 0.75, "cnt": 1.0}


# ---------------------------------------------------------------- 4.6 预测误区

def _eval(waveform_cells, hardware):
    return evaluate_prediction(predict_points=POINTS, hardware_questions=QUESTIONS,
                               waveform={"cells": waveform_cells}, hardware=hardware, diagnosis=DIAG)


def _cells(values):
    return [{"signal": "out", "step": s, "value": v} for s, v in zip([1, 2, 3, 4], values)]


HW_OK = {"ff_count": 3, "latch": False, "ff_signals": ["out", "state"]}


def test_misconception_ff_confusion():
    ev = _eval(_cells(["0", "1", "0", "1"]), {**HW_OK, "ff_count": 2})
    assert prediction_misconceptions(ev, DIAG) == ["pred_ff_confusion"]
    ev = _eval(_cells(["0", "1", "0", "1"]), {**HW_OK, "ff_signals": ["state"]})
    assert "pred_ff_confusion" in prediction_misconceptions(ev, DIAG)


def test_misconception_off_by_one_cycle():
    # 实际 out 在 STEP 0–4 为 0 0 1 0 1；学生预测 STEP 1–4 为 0 0 1 0（整体晚了一拍）
    ev = _eval(_cells(["0", "0", "1", "0"]), HW_OK)
    assert prediction_misconceptions(ev, DIAG) == ["pred_off_by_one_cycle"]
    # 预测完全正确时不算
    ev = _eval(_cells(["0", "1", "0", "1"]), HW_OK)
    assert prediction_misconceptions(ev, DIAG) == []
    # 只错一格、错开一拍也对不上时不算
    ev = _eval(_cells(["1", "1", "0", "1"]), HW_OK)
    assert prediction_misconceptions(ev, DIAG) == []


def test_misconception_latch_blind():
    diag = {**DIAG, "hardware": {**DIAG["hardware"], "latch_signals": ["next_state"]}}
    ev = evaluate_prediction(predict_points=POINTS, hardware_questions=QUESTIONS,
                             waveform={"cells": _cells(["0", "1", "0", "1"])}, hardware=HW_OK, diagnosis=diag)
    assert prediction_misconceptions(ev, diag) == ["pred_latch_blind"]


def test_misconception_order_belief():
    assert order_belief_misconception("change", False) is True     # 以为会变，其实与顺序无关
    assert order_belief_misconception("same", True) is True        # 以为不变，其实依赖顺序
    assert order_belief_misconception("same", False) is False
    assert order_belief_misconception(None, True) is False         # 没预测
