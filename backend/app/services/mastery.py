"""从数据库取尝试，算知识点掌握，并写入 mastery_snapshots（每次判完后追加）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..models import Attempt, KnowledgePoint, MasterySnapshot, Problem
from .learner_model import QUADRANTS, AttemptView, KpSummary, prediction_ok, summarize_kp


def attempt_views(db: DbSession, user_id: int, kp: str | None = None) -> list[AttemptView]:
    """该学生已判完、带预测、编译通过的尝试；指定 kp 时只取关联该知识点的题。"""
    theta = get_settings().pred_threshold
    rows = db.execute(
        select(Attempt, Problem.knowledge_points)
        .join(Problem, Problem.id == Attempt.problem_id)
        .where(Attempt.user_id == user_id, Attempt.status == "done", Attempt.quadrant.in_(QUADRANTS))
        .order_by(Attempt.created_at, Attempt.id)
    ).all()
    out = []
    for attempt, kps in rows:
        if kp is not None and kp not in (kps or []):
            continue
        out.append(AttemptView(created_at=attempt.created_at, sim_ok=bool(attempt.sim_ok),
                               pred_ok=bool(prediction_ok(attempt.pred_accuracy, theta)),
                               quadrant=attempt.quadrant, problem_id=attempt.problem_id))
    return out


def kp_summaries(db: DbSession, user_id: int) -> list[tuple[KnowledgePoint, KpSummary]]:
    s = get_settings()
    kps = db.scalars(select(KnowledgePoint).order_by(KnowledgePoint.sort_order)).all()
    views = attempt_views(db, user_id)
    problems = {p.id: p.knowledge_points for p in db.scalars(select(Problem)).all()}
    result = []
    for kp in kps:
        mine = [v for v in views if kp.code in problems.get(v.problem_id, [])]
        result.append((kp, summarize_kp(kp.code, mine, n=s.f_window, m=s.mastery_window)))
    return result


def recompute(db: DbSession, user_id: int, kp_codes: list[str]) -> list[MasterySnapshot]:
    s = get_settings()
    snaps = []
    for code in kp_codes:
        summary = summarize_kp(code, attempt_views(db, user_id, code), n=s.f_window, m=s.mastery_window)
        snap = MasterySnapshot(user_id=user_id, knowledge_point=code, level=summary.level,
                               r_code=summary.r_code, r_pred=summary.r_pred, f_value=summary.f_value)
        db.add(snap)
        snaps.append(snap)
    return snaps
