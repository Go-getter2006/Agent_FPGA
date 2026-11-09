"""学情指标（docs/learner-model.md 第 3、4 节）。

全部是确定性计算：输入只有裁判结果、学生锁定的预测和事件日志，大模型的输出不参与任何指标。
本模块的函数都是纯函数，便于逐条公式写单元测试；读写数据库的部分在 mastery.py / report.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

QUADRANTS = ("mastered", "fragile", "design_gap", "concept_gap")
LOOK_EVENT_TYPES = frozenset({"waveform.view", "waveform.cell_click"})
EPS = 1e-9


# ---------------------------------------------------------------- 预测评分（第 3 节）

def normalize_value(raw, width: int) -> str | None:
    """学生填的值 → 与 trace 相同的二进制字符串。支持二进制和十六进制（0x / h 前缀）。"""
    if raw is None:
        return None
    text = str(raw).strip().lower().replace("_", "")
    if not text:
        return None
    if text in ("x", "z") and width == 1:
        return text
    try:
        if text.startswith(("0x", "h", "'h")):
            value = int(text.split("h", 1)[1] if "h" in text else text[2:], 16)
        elif text.startswith(("0b", "b", "'b")):
            value = int(text.split("b", 1)[1], 2)
        elif set(text) <= {"0", "1"}:
            value = int(text, 2)
        else:
            return None
    except ValueError:
        return None
    if value >= 2 ** width:
        return None
    return format(value, f"0{width}b")


def evaluate_prediction(*, predict_points: list[dict], hardware_questions: list[str],
                        waveform: dict | None, hardware: dict | None, diagnosis: dict) -> dict:
    """把锁定的预测与工具结果逐格对照。

    - 波形格以 sim.trace 为准；轨迹里没有这一格（超时、编译失败）时这格不计入
    - 硬件问题以 hardware 字段为准；综合失败（字段为 null）时不计入
    - “哪些信号成了触发器”要求集合完全一致才算对
    """
    trace = {row["step"]: row["outputs"] for row in diagnosis.get("sim", {}).get("trace", [])}
    cells_in = {(c["signal"], int(c["step"])): c.get("value") for c in (waveform or {}).get("cells", [])}
    cells = []
    for point in predict_points:
        for step in point["steps"]:
            value = cells_in.get((point["signal"], step))
            actual = trace.get(step, {}).get(point["signal"])
            correct = None if actual is None else (value == actual)
            cells.append({"signal": point["signal"], "step": step, "value": value,
                          "actual": actual, "correct": correct})

    hw = diagnosis.get("hardware") or {}
    answers = hardware or {}
    items = []
    for q in hardware_questions if hardware is not None else []:
        if q == "ff_count":
            actual = hw.get("ff_count")
            value = answers.get("ff_count")
            correct = None if actual is None else (value is not None and int(value) == actual)
        elif q == "latch":
            latch = hw.get("latch_signals")
            actual = None if latch is None else bool(latch)
            value = answers.get("latch")
            correct = None if actual is None else (value is not None and bool(value) == actual)
        elif q == "ff_signals":
            ffs = hw.get("ff_signals")
            actual = None if ffs is None else sorted(ffs)
            value = sorted(set(answers.get("ff_signals") or []))
            correct = None if actual is None else (value == actual)
        else:
            continue
        items.append({"question": q, "value": value, "actual": actual, "correct": correct})

    def _score(entries):
        judged = [e for e in entries if e["correct"] is not None]
        hits = sum(1 for e in judged if e["correct"])
        return hits, len(judged), (hits / len(judged) if judged else None)

    w_hits, w_total, w_acc = _score(cells)
    h_hits, h_total, h_acc = _score(items)
    total = w_total + h_total
    return {
        "waveform": {"cells": cells, "hits": w_hits, "total": w_total, "accuracy": w_acc},
        "hardware": {"items": items, "hits": h_hits, "total": h_total, "accuracy": h_acc},
        "hits": w_hits + h_hits,
        "total": total,
        "accuracy": (w_hits + h_hits) / total if total else None,
    }


def prediction_ok(accuracy: float | None, theta: float) -> bool | None:
    """预测达标 p：A_pred ≥ θ。"""
    if accuracy is None:
        return None
    return accuracy >= theta - EPS


def quadrant(code_ok: bool | None, pred_ok: bool | None, compiled: bool = True) -> str:
    """四象限；编译失败或没有预测的尝试记为 none。"""
    if not compiled or code_ok is None or pred_ok is None:
        return "none"
    if code_ok:
        return "mastered" if pred_ok else "fragile"
    return "design_gap" if pred_ok else "concept_gap"


# ---------------------------------------------------------------- 知识点指标（第 4.1、4.2 节）

@dataclass(frozen=True)
class AttemptView:
    """计算指标需要的尝试字段。只包含已判完、带预测、编译通过的尝试（quadrant 为四象限之一）。"""
    created_at: datetime
    sim_ok: bool
    pred_ok: bool
    quadrant: str
    problem_id: str = ""


def counted(attempts: list[AttemptView]) -> list[AttemptView]:
    return sorted((a for a in attempts if a.quadrant in QUADRANTS), key=lambda a: a.created_at)


def f_value(attempts: list[AttemptView], n: int = 5) -> float | None:
    """脆弱率 F_k = N(c=1, p=0) / N(c=1)，范围是最近 n 次带预测的尝试；分母为 0 时为空。"""
    num, den = f_counts(attempts, n)
    return num / den if den else None


def f_counts(attempts: list[AttemptView], n: int = 5) -> tuple[int, int]:
    recent = counted(attempts)[-n:]
    passed = [a for a in recent if a.sim_ok]
    return sum(1 for a in passed if not a.pred_ok), len(passed)


def class_f_value(per_student_kp: list[list[AttemptView]], n: int = 5) -> float | None:
    """全班 F：所有学生、所有知识点上分子之和除以分母之和。"""
    num = den = 0
    for attempts in per_student_kp:
        a, b = f_counts(attempts, n)
        num += a
        den += b
    return num / den if den else None


def r_values(attempts: list[AttemptView], m: int = 3) -> tuple[float | None, float | None]:
    """R_code、R_pred：最近 m 次带预测尝试中代码通过、预测达标的比例（不足 m 次取实际次数）。"""
    recent = counted(attempts)[-m:]
    if not recent:
        return None, None
    return (sum(a.sim_ok for a in recent) / len(recent),
            sum(a.pred_ok for a in recent) / len(recent))


def mastery_level(attempts: list[AttemptView], m: int = 3) -> str:
    """四级掌握等级，自上而下命中即停：not_started / mastered / fragile / learning。"""
    recent = counted(attempts)
    if not recent:
        return "not_started"
    r_code, r_pred = r_values(recent, m)
    if r_code >= 2 / 3 - EPS and r_pred >= 2 / 3 - EPS and recent[-1].quadrant == "mastered":
        return "mastered"
    if r_code >= 2 / 3 - EPS:
        return "fragile"
    return "learning"


# ---------------------------------------------------------------- 调试行为与提示（第 4.3、4.4 节）

@dataclass(frozen=True)
class Submission:
    problem_id: str
    ts: datetime


@dataclass(frozen=True)
class LookEvent:
    problem_id: str
    ts: datetime
    type: str


def is_look_event(type_: str) -> bool:
    return type_ in LOOK_EVENT_TYPES or type_.startswith("investigate.")


def blind_rate(submissions: list[Submission], looks: list[LookEvent]) -> tuple[float | None, int, int]:
    """盲改率 B = N_blind / N_resubmit。

    重复提交：同一题的第 2 次及以后的提交；盲改：与上一次提交之间没有任何
    waveform.view、waveform.cell_click 或 investigate.* 事件。返回 (B, N_blind, N_resubmit)。
    """
    by_problem: dict[str, list[datetime]] = {}
    for s in sorted(submissions, key=lambda s: s.ts):
        by_problem.setdefault(s.problem_id, []).append(s.ts)
    look_ts: dict[str, list[datetime]] = {}
    for e in looks:
        if is_look_event(e.type):
            look_ts.setdefault(e.problem_id, []).append(e.ts)
    blind = resubmits = 0
    for pid, times in by_problem.items():
        for prev, cur in zip(times, times[1:]):
            resubmits += 1
            if not any(prev < t < cur for t in look_ts.get(pid, [])):
                blind += 1
    return (blind / resubmits if resubmits else None), blind, resubmits


@dataclass(frozen=True)
class HintRequest:
    problem_id: str
    level: int
    ts: datetime


def hint_dependence(first_pass: dict[str, datetime], hints: list[HintRequest]) -> float | None:
    """提示依赖度 H = 已通过各题“通过之前请求过的最高提示等级”的平均值（没请求过记 0）。"""
    if not first_pass:
        return None
    total = 0
    for pid, passed_at in first_pass.items():
        levels = [h.level for h in hints if h.problem_id == pid and h.ts < passed_at]
        total += max(levels, default=0)
    return total / len(first_pass)


# ---------------------------------------------------------------- testbench 得分（第 4.5 节）

@dataclass(frozen=True)
class TbView:
    problem_id: str
    created_at: datetime
    score: float | None


def latest_tb_scores(submissions: list[TbView]) -> dict[str, float | None]:
    """每道创作题取最近一次提交的 S_tb。"""
    latest: dict[str, TbView] = {}
    for s in sorted(submissions, key=lambda s: s.created_at):
        latest[s.problem_id] = s
    return {pid: s.score for pid, s in latest.items()}


# ---------------------------------------------------------------- 预测误区（第 4.6 节）

MISCONCEPTION_LABELS = {
    "pred_ff_confusion": "分不清哪些信号会变成触发器",
    "pred_off_by_one_cycle": "输出时序差了一拍",
    "pred_latch_blind": "没意识到生成了锁存器",
    "pred_order_belief": "以为结果取决于代码先后",
}

TAG_LABELS = {
    "latch_inferred": "组合逻辑没写全，生成了锁存器",
    "blocking_in_seq": "时序逻辑里用了 =（阻塞赋值）",
    "nonblocking_in_comb": "组合逻辑里用了 <=",
    "width_mismatch": "位宽对不上",
    "multi_driven": "同一个信号被多处赋值",
    "non_synthesizable": "写了不能综合成电路的语句",
    "race_order_sensitive": "结果依赖 always 块的先后顺序",
    "fragile_pass": "仿真对了，但电路描述有隐患",
}

# 误区 → 去练习的知识点
PRACTICE_KP = {
    "latch_inferred": "comb_always", "blocking_in_seq": "blocking", "nonblocking_in_comb": "blocking",
    "width_mismatch": "width", "multi_driven": "sequential", "non_synthesizable": "comb_always",
    "race_order_sensitive": "parallel", "fragile_pass": "comb_always",
    "pred_ff_confusion": "sequential", "pred_off_by_one_cycle": "sequential",
    "pred_latch_blind": "comb_always", "pred_order_belief": "parallel",
}


def prediction_misconceptions(evaluation: dict, diagnosis: dict) -> list[str]:
    """由预测对照和裁判结果判定预测误区（确定性规则）。"""
    found: list[str] = []
    hw_items = {i["question"]: i for i in evaluation["hardware"]["items"]}
    ff_sig, ff_cnt = hw_items.get("ff_signals"), hw_items.get("ff_count")
    if (ff_sig and ff_sig["correct"] is False) or \
            (ff_cnt and ff_cnt["correct"] is False and ff_cnt["value"] is not None
             and abs(int(ff_cnt["value"]) - int(ff_cnt["actual"])) >= 1):
        found.append("pred_ff_confusion")

    trace = {row["step"]: row["outputs"] for row in diagnosis.get("sim", {}).get("trace", [])}
    by_signal: dict[str, list[dict]] = {}
    for cell in evaluation["waveform"]["cells"]:
        by_signal.setdefault(cell["signal"], []).append(cell)
    for signal, cells in by_signal.items():
        if all(c["correct"] for c in cells) or any(c["value"] is None for c in cells):
            continue
        for shift in (-1, 1):
            shifted = [trace.get(c["step"] + shift, {}).get(signal) for c in cells]
            if all(s is not None for s in shifted) and [c["value"] for c in cells] == shifted:
                found.append("pred_off_by_one_cycle")
                break
        if "pred_off_by_one_cycle" in found:
            break

    latch = hw_items.get("latch")
    if latch and latch["actual"] is True and latch["value"] is False:
        found.append("pred_latch_blind")
    return found


def order_belief_misconception(predicted: str | None, order_sensitive: bool | None) -> bool:
    """顺序打乱实验前预测“会变”而实际与顺序无关，或反过来。"""
    if predicted not in ("change", "same") or order_sensitive is None:
        return False
    return (predicted == "change") != order_sensitive


@dataclass
class KpSummary:
    code: str
    level: str
    r_code: float | None = None
    r_pred: float | None = None
    f_value: float | None = None
    attempts: int = 0
    extra: dict = field(default_factory=dict)


def summarize_kp(code: str, attempts: list[AttemptView], *, n: int = 5, m: int = 3) -> KpSummary:
    r_code, r_pred = r_values(attempts, m)
    return KpSummary(code=code, level=mastery_level(attempts, m), r_code=r_code, r_pred=r_pred,
                     f_value=f_value(attempts, n), attempts=len(counted(attempts)))
