"""做题工作台的 PRIMM 步骤（docs/pages.md S4）。

预测题：① 预测 → ② 运行 → ③ 探究
修改题：① ② ③ → ④ 修改（改代码 → 先预测变化 → 再运行，直到仿真通过）
创作题：①（预测自己的代码）② ③ → ⑤ 创作（写 testbench 并打分）

规则：
- 每次运行前都要先锁定预测（对照组关闭 predict_step 时跳过）
- 编译没通过：回到预测（修改阶段则留在修改），改好代码重新预测再运行
- 探究至少完成一次才能进入后面的步骤
- 创作题的设计仿真通过后才进入 ⑤；没通过就继续“重新预测并仿真”
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import Attempt, Explanation, Investigation, Prediction, Problem, Progress

STEPS_BY_TYPE = {
    "predict": ["predict", "run", "investigate"],
    "modify": ["predict", "run", "investigate", "modify"],
    "make": ["predict", "run", "investigate", "make"],
}
ALL_STEPS = ["predict", "run", "investigate", "modify", "make"]
DEFAULT_STATE = {"investigated": False, "passed": False, "modify_phase": False,
                 "modify_done": False, "tb_done": False, "predicted": False, "ran": False}


class StepError(Exception):
    """当前步骤不允许这个操作。"""


def get_progress(db: DbSession, user_id: int, problem: Problem, predict_enabled: bool = True) -> Progress:
    row = db.scalar(select(Progress).where(Progress.user_id == user_id, Progress.problem_id == problem.id))
    if row is None:
        row = Progress(user_id=user_id, problem_id=problem.id,
                       step="predict" if predict_enabled else "run", state=dict(DEFAULT_STATE))
        db.add(row)
        db.flush()
    return row


def state_of(progress: Progress) -> dict:
    return {**DEFAULT_STATE, **(progress.state or {})}


def _set(progress: Progress, step: str | None = None, **changes) -> None:
    state = state_of(progress)
    state.update(changes)
    progress.state = state          # 重新赋值，JSON 字段才会被标记为已修改
    if step is not None:
        progress.step = step


def completed_steps(problem: Problem, progress: Progress) -> list[str]:
    st = state_of(progress)
    done = []
    if st["predicted"]:
        done.append("predict")
    if st["ran"]:
        done.append("run")
    if st["investigated"]:
        done.append("investigate")
    if st["modify_done"]:
        done.append("modify")
    if st["tb_done"]:
        done.append("make")
    return [s for s in done if s in STEPS_BY_TYPE[problem.primm_type]]


def pending_predictions(db: DbSession, user_id: int, problem_id: str) -> list[Prediction]:
    """已锁定、还没关联到尝试的预测（最近一次锁定的那一组）。"""
    return list(db.scalars(select(Prediction).where(
        Prediction.user_id == user_id, Prediction.problem_id == problem_id,
        Prediction.attempt_id.is_(None)).order_by(Prediction.id)).all())


def running_attempt(db: DbSession, user_id: int, problem_id: str) -> Attempt | None:
    return db.scalar(select(Attempt).where(
        Attempt.user_id == user_id, Attempt.problem_id == problem_id,
        Attempt.status.in_(("queued", "running"))))


# ---------------------------------------------------------------- 步骤转换

def on_predictions_locked(progress: Progress) -> None:
    st = state_of(progress)
    _set(progress, step="modify" if st["modify_phase"] else "run", predicted=True)


def on_attempt_submitted(progress: Progress) -> str:
    """返回这次尝试记在哪一步。"""
    st = state_of(progress)
    step = "modify" if st["modify_phase"] else "run"
    _set(progress, step=step)
    return step


def after_investigation_step(problem: Problem, progress: Progress, sim_ok: bool,
                             predict_enabled: bool = True) -> str:
    st = state_of(progress)
    kind = problem.primm_type
    if kind == "predict":
        return "done"
    if kind == "modify":
        if st["modify_phase"] and sim_ok:
            return "done"
        return "modify"
    # 创作题
    if st["tb_done"]:
        return "done"
    if sim_ok:
        return "make"
    return "predict" if predict_enabled else "run"


def on_attempt_judged(problem: Problem, progress: Progress, attempt: Attempt,
                      predict_enabled: bool = True) -> None:
    st = state_of(progress)
    compiled = bool(attempt.judge and attempt.judge["compile"]["ok"])
    changes = {"ran": True}
    if attempt.sim_ok:
        changes["passed"] = True
    if problem.primm_type == "modify" and st["modify_phase"] and attempt.sim_ok:
        changes["modify_done"] = True
    _set(progress, **changes)
    if not compiled:
        step = "modify" if st["modify_phase"] else ("predict" if predict_enabled else "run")
    elif not st["investigated"]:
        step = "investigate"
    else:
        step = after_investigation_step(problem, progress, bool(attempt.sim_ok), predict_enabled)
    _set(progress, step=step)


def on_investigation_complete(problem: Problem, progress: Progress, attempt: Attempt,
                              predict_enabled: bool = True) -> None:
    if state_of(progress)["investigated"]:
        return
    _set(progress, investigated=True)
    step = after_investigation_step(problem, progress, bool(attempt.sim_ok), predict_enabled)
    if problem.primm_type == "modify" and step == "modify":
        _set(progress, modify_phase=True)
    _set(progress, step=step)


def on_tb_scored(progress: Progress) -> None:
    _set(progress, step="done", tb_done=True)


# ---------------------------------------------------------------- 探究任务

def investigation_target(attempt: Attempt, evaluation: dict | None) -> dict:
    """探究步骤要找的那个格子：

    - 仿真与参考答案对不上：第一个对不上的格子（kind=sim）
    - 仿真对了但预测有没对上的格子：第一个没预测对的格子（kind=pred）
    - 都对了：只要求找出决定第一个预测信号的代码行并解释（kind=none）
    """
    judge = attempt.judge or {}
    mm = (judge.get("sim") or {}).get("first_mismatch")
    if mm:
        return {"kind": "sim", "step": mm["step"], "signal": mm["signal"]}
    cells = ((evaluation or {}).get("waveform") or {}).get("cells", [])
    wrong = sorted((c for c in cells if c["correct"] is False), key=lambda c: (c["step"], c["signal"]))
    if wrong:
        return {"kind": "pred", "step": wrong[0]["step"], "signal": wrong[0]["signal"]}
    trace = (judge.get("sim") or {}).get("trace") or []
    signal = cells[0]["signal"] if cells else (next(iter(trace[0]["outputs"])) if trace else None)
    step = cells[0]["step"] if cells else None
    return {"kind": "none", "step": step, "signal": signal}


def mismatching_signals_at(judge: dict, ref_trace: list[dict], step: int) -> set[str]:
    trace = {row["step"]: row["outputs"] for row in (judge.get("sim") or {}).get("trace", [])}
    ref = {row["step"]: row["outputs"] for row in ref_trace}
    stu, exp = trace.get(step, {}), ref.get(step, {})
    return {s for s, v in exp.items() if stu.get(s) != v}


def check_locate_step(attempt: Attempt, target: dict, ref_trace: list[dict], chosen: dict) -> bool:
    if target["kind"] not in ("sim", "pred"):
        return False
    try:
        step, signal = int(chosen["step"]), str(chosen["signal"])
    except (KeyError, TypeError, ValueError):
        return False
    if step != target["step"]:
        return False
    if target["kind"] == "sim":
        # 同一步有多个信号对不上时，点到其中任意一个都算对
        return signal in mismatching_signals_at(attempt.judge, ref_trace, step)
    return signal == target["signal"]


def driver_lines(attempt: Attempt, signal: str | None) -> list[int]:
    drivers = (attempt.judge or {}).get("drivers") or {}
    return drivers.get(signal, []) if signal else []


def check_locate_line(attempt: Attempt, target: dict, chosen: dict) -> bool:
    try:
        line = int(chosen["line"])
    except (KeyError, TypeError, ValueError):
        return False
    return line in driver_lines(attempt, target.get("signal"))


def investigation_status(db: DbSession, attempt: Attempt, evaluation: dict | None) -> dict:
    target = investigation_target(attempt, evaluation)
    records = db.scalars(select(Investigation).where(Investigation.attempt_id == attempt.id)
                         .order_by(Investigation.id)).all()
    explained = db.scalar(select(Explanation.id).where(Explanation.attempt_id == attempt.id)) is not None

    def task(kind: str, required: bool) -> dict:
        mine = [r for r in records if r.kind == kind]
        correct = [r for r in mine if r.correct]
        return {"required": required, "tries": len(mine), "done": bool(correct),
                "chosen": correct[0].chosen if correct else (mine[-1].chosen if mine else None)}

    locate_step = task("locate_step", target["kind"] in ("sim", "pred"))
    locate_line = task("locate_line", bool(driver_lines(attempt, target.get("signal"))))
    complete = all(t["done"] for t in (locate_step, locate_line) if t["required"]) and explained
    return {"target": target, "locate_step": locate_step, "locate_line": locate_line,
            "explanation": {"required": True, "done": explained}, "complete": complete}
