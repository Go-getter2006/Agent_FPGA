"""第 4 级提示：参考答案（由系统直接展示题目的 ref.v，不经过大模型）。

解锁条件（满足任一）：
- 已经看过（之后随时可以再看）
- 自己写的代码已经仿真通过过（对照参考写法）
- 自己写的代码已有 FAILS_NEEDED 次没通过，并且看过第 3 级代码提示
预测题（只读代码、不写代码）没有参考答案这一级。
看过参考答案之后提交的尝试不计入掌握度（mastery.attempt_views、teacher_analytics.views）；
第一次查看记一条 level=4 的提示，所以提示依赖度 H 会把“通过之前看过答案”记为 4。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import Attempt, Hint, Problem

ANSWER_LEVEL = 4
FAILS_NEEDED = 3
ANSWER_VERSION = "answer_v1"


def revealed_at(db: DbSession, user_id: int, problem_id: str) -> datetime | None:
    return db.scalar(select(Hint.created_at).join(Attempt, Attempt.id == Hint.attempt_id).where(
        Attempt.user_id == user_id, Attempt.problem_id == problem_id, Hint.level == ANSWER_LEVEL)
        .order_by(Hint.created_at))


def reveal_times(db: DbSession, user_id: int) -> dict[str, datetime]:
    """该学生每道题第一次看参考答案的时间。"""
    out: dict[str, datetime] = {}
    for pid, ts in db.execute(select(Attempt.problem_id, Hint.created_at).join(Attempt, Attempt.id == Hint.attempt_id)
                              .where(Attempt.user_id == user_id, Hint.level == ANSWER_LEVEL)).all():
        if pid not in out or ts < out[pid]:
            out[pid] = ts
    return out


def status(db: DbSession, user_id: int, problem: Problem) -> dict:
    if problem.primm_type == "predict":
        return {"available": False, "unlocked": False, "revealed": False, "failed": 0,
                "fails_needed": FAILS_NEEDED, "code_hint_seen": False, "message": "预测题不需要参考答案"}
    starter = problem.meta.get("starter")
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user_id, Attempt.problem_id == problem.id,
                                                Attempt.status == "done")).all()
    own = [a for a in attempts if not starter or a.code != starter]
    failed = sum(1 for a in own if not a.sim_ok)
    passed = any(a.sim_ok for a in own)
    code_hint_seen = db.scalar(select(Hint.id).join(Attempt, Attempt.id == Hint.attempt_id).where(
        Attempt.user_id == user_id, Attempt.problem_id == problem.id, Hint.level == 3)) is not None
    revealed = revealed_at(db, user_id, problem.id) is not None
    unlocked = revealed or passed or (failed >= FAILS_NEEDED and code_hint_seen)
    if revealed:
        message = "你已经看过参考答案，可以随时再看。"
    elif passed:
        message = "你已经做出来了，可以对照一下参考写法。"
    elif unlocked:
        message = "可以查看参考答案了。建议看懂之后，关掉答案自己重新写一遍。"
    else:
        need = []
        if failed < FAILS_NEEDED:
            need.append(f"再提交 {FAILS_NEEDED - failed} 次")
        if not code_hint_seen:
            need.append("先看第 3 级代码提示")
        message = "，".join(need) + "，就可以查看参考答案。"
    return {"available": True, "unlocked": unlocked, "revealed": revealed, "failed": failed,
            "fails_needed": FAILS_NEEDED, "code_hint_seen": code_hint_seen, "message": message}
