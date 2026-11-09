"""提取练习（复习）调度（docs/learner-model.md 第 5 节）。

- 触发：某次尝试落在 fragile 或 concept_gap，就把该题关联知识点的一道预测题加入复习队列，
  优先选同知识点的其他题（有起始代码的预测题、修改题）；没有时用学生自己这次的代码
- 4 个盒子，间隔 1、3、7、14 天；答对进入下一个盒子，答错回到第 1 个，第 4 个盒子答对后移出
- 每天最多推送 5 条，到期越久越优先
- 题目的标准答案来自裁判对那份代码的仿真与综合结果，只存在服务端
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import utcnow
from ..models import Attempt, Event, Problem, ReviewItem
from .learner_model import evaluate_prediction, prediction_ok

INTERVAL_DAYS = {1: 1, 2: 3, 3: 7, 4: 14}
TRIGGER_QUADRANTS = ("fragile", "concept_gap")
BEIJING = timezone(timedelta(hours=8))


def _question_from(problem: Problem, code: str, source: str, answer: dict, kind: str) -> dict:
    meta = problem.meta
    return {
        "source": source,
        "kind": kind,
        "code": code,
        "predict_points": meta["predict_points"],
        "hardware_questions": meta["hardware_questions"] if kind == "hardware" else [],
        "skeleton": meta["skeleton"],
        "answer": answer,           # {"sim": {"trace": [...]}, "hardware": {...}}；返回给学生前去掉
    }


def _answer_from_judge(judge: dict) -> dict:
    return {"sim": {"trace": judge["sim"]["trace"]}, "hardware": judge.get("hardware")}


def choose_review(db: DbSession, attempt: Attempt, kp: str, kind: str) -> tuple[Problem, dict] | None:
    candidates = db.scalars(select(Problem).order_by(Problem.id)).all()
    others = [p for p in candidates if kp in p.knowledge_points and p.id != attempt.problem_id
              and p.meta.get("starter") and p.meta.get("starter_eval")]
    if others:
        p = others[0]
        return p, _question_from(p, p.meta["starter"], "starter", p.meta["starter_eval"], kind)
    if attempt.judge and attempt.judge["compile"]["ok"] and attempt.judge["sim"]["trace"]:
        p = db.get(Problem, attempt.problem_id)
        return p, _question_from(p, attempt.code, "attempt", _answer_from_judge(attempt.judge), kind)
    return None


def enqueue_for_attempt(db: DbSession, attempt: Attempt, problem: Problem, misconceptions: list[str],
                        now: datetime | None = None) -> list[ReviewItem]:
    if attempt.quadrant not in TRIGGER_QUADRANTS:
        return []
    now = now or utcnow()
    kind = "hardware" if {"pred_ff_confusion", "pred_latch_blind"} & set(misconceptions) else "waveform"
    added = []
    for kp in problem.knowledge_points:
        exists = db.scalar(select(ReviewItem.id).where(
            ReviewItem.user_id == attempt.user_id, ReviewItem.knowledge_point == kp,
            ReviewItem.status == "active"))
        if exists:
            continue
        chosen = choose_review(db, attempt, kp, kind)
        if chosen is None:
            continue
        p, question = chosen
        item = ReviewItem(user_id=attempt.user_id, knowledge_point=kp, problem_id=p.id, box=1,
                          due_at=now + timedelta(days=INTERVAL_DAYS[1]), status="active",
                          source_attempt_id=attempt.id, question=question)
        db.add(item)
        added.append(item)
    return added


def start_of_beijing_day(now: datetime) -> datetime:
    local = now.astimezone(BEIJING)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def answered_today(db: DbSession, user_id: int, now: datetime) -> int:
    return db.scalar(select(func.count()).select_from(Event).where(
        Event.user_id == user_id, Event.type == "review.answer",
        Event.ts >= start_of_beijing_day(now))) or 0


def due_items(db: DbSession, user_id: int, now: datetime | None = None) -> tuple[list[ReviewItem], int]:
    """今天还能推送的到期条目（到期越久越优先），以及今天剩余条数。"""
    now = now or utcnow()
    remaining = max(0, get_settings().review_daily_limit - answered_today(db, user_id, now))
    items = db.scalars(select(ReviewItem).where(
        ReviewItem.user_id == user_id, ReviewItem.status == "active", ReviewItem.due_at <= now)
        .order_by(ReviewItem.due_at, ReviewItem.id).limit(remaining)).all()
    return list(items), remaining


def public_question(item: ReviewItem) -> dict:
    q = dict(item.question)
    q.pop("answer", None)
    return q


def grade(item: ReviewItem, answers: dict) -> dict:
    q = item.question
    evaluation = evaluate_prediction(
        predict_points=q["predict_points"] if q["kind"] == "waveform" else [],
        hardware_questions=q.get("hardware_questions", []),
        waveform=answers.get("waveform") if q["kind"] == "waveform" else None,
        hardware=answers.get("hardware") if q["kind"] == "hardware" else None,
        diagnosis=q["answer"],
    )
    correct = bool(prediction_ok(evaluation["accuracy"], get_settings().pred_threshold))
    return {"evaluation": evaluation, "correct": correct}


def apply_answer(item: ReviewItem, correct: bool, now: datetime | None = None) -> None:
    now = now or utcnow()
    item.last_result = correct
    if correct:
        if item.box >= 4:
            item.status = "done"
        else:
            item.box += 1
            item.due_at = now + timedelta(days=INTERVAL_DAYS[item.box])
    else:
        item.box = 1
        item.due_at = now + timedelta(days=INTERVAL_DAYS[1])
