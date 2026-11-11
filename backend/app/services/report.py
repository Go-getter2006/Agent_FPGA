"""学生端“我的学情”（docs/pages.md S5，docs/learner-model.md 第 1 节学生端一列）。

只显示学生自己的数据，不显示排名、不和同学比较；盲改率、ICAP 等只在教师端出现。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import utcnow
from ..models import Attempt, Hint, Prediction, Problem, ReviewItem, ShuffleRun, TbSubmission, User
from .learner_model import (MISCONCEPTION_LABELS, PRACTICE_KP, TAG_LABELS, TbView, calibration_bias,
                            latest_tb_scores, overconfidence_rate, with_confidence)
from .mastery import attempt_views, kp_summaries
from .review_scheduler import BEIJING


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _accuracy_rows(db: DbSession, user_id: int) -> list[Prediction]:
    return list(db.scalars(select(Prediction).where(
        Prediction.user_id == user_id, Prediction.accuracy.is_not(None)).order_by(Prediction.locked_at)).all())


def student_report(db: DbSession, user: User, brief: bool = False) -> dict:
    summaries = kp_summaries(db, user.id)
    mastery = [{"code": kp.code, "name": kp.name, "level": s.level, "r_code": s.r_code,
                "r_pred": s.r_pred, "f_value": s.f_value, "attempts": s.attempts} for kp, s in summaries]
    if brief:
        return {"mastery": mastery}

    now = utcnow()
    preds = _accuracy_rows(db, user.id)
    wave = [p for p in preds if p.kind == "waveform"]
    recent = [p.accuracy for p in wave if p.locked_at >= now - timedelta(days=14)]
    before = [p.accuracy for p in wave if now - timedelta(days=28) <= p.locked_at < now - timedelta(days=14)]
    recent_acc, before_acc = _mean(recent), _mean(before)

    # 按周（北京时间，周一开始）的预测准确率趋势，最近 8 周
    weeks: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"waveform": [], "hardware": []})
    for p in preds:
        local = p.locked_at.astimezone(BEIJING)
        monday = (local - timedelta(days=local.weekday())).date()
        weeks[monday.isoformat()][p.kind].append(p.accuracy)
    trend = [{"week": w, "waveform": _mean(v["waveform"]), "hardware": _mean(v["hardware"])}
             for w, v in sorted(weeks.items())][-8:]

    problems = {p.id: p for p in db.scalars(select(Problem)).all()}
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.status == "done")
                          .order_by(Attempt.id)).all()

    latest_by_problem: dict[str, Attempt] = {}
    for a in attempts:
        latest_by_problem[a.problem_id] = a
    fragile_list = []
    for pid, a in latest_by_problem.items():
        if a.quadrant != "fragile":
            continue
        mis = (a.analysis or {}).get("misconceptions", [])
        reason = MISCONCEPTION_LABELS[mis[0]] if mis else "代码对了，但预测和实际没对上"
        fragile_list.append({"problem_id": pid, "title": problems[pid].title, "reason": reason,
                             "attempt_id": a.id, "knowledge_points": problems[pid].knowledge_points})

    counts: dict[str, dict] = {}
    for a in attempts:
        codes = [t for t in (a.judge or {}).get("tags", []) if t in TAG_LABELS]
        codes += (a.analysis or {}).get("misconceptions", [])
        for code in codes:
            entry = counts.setdefault(code, {"code": code, "count": 0, "latest_attempt": a.id,
                                             "label": TAG_LABELS.get(code) or MISCONCEPTION_LABELS.get(code),
                                             "source": "judge" if code in TAG_LABELS else "prediction"})
            entry["count"] += 1
            entry["latest_attempt"] = a.id
            entry["latest_problem"] = problems[a.problem_id].title
            entry["latest_problem_id"] = a.problem_id
    misconceptions = sorted(counts.values(), key=lambda e: -e["latest_attempt"])[:5]
    for m in misconceptions:
        kp = PRACTICE_KP.get(m["code"])
        practice = next((p for p in sorted(problems.values(), key=lambda p: p.id)
                         if kp in p.knowledge_points and p.id != m["latest_problem_id"]), None)
        m["practice_kp"] = kp
        m["practice_problem_id"] = practice.id if practice else m["latest_problem_id"]

    tbs = db.scalars(select(TbSubmission).where(TbSubmission.user_id == user.id, TbSubmission.status == "done")
                     .order_by(TbSubmission.id)).all()
    tb_scores = latest_tb_scores([TbView(s.problem_id, s.created_at, s.score) for s in tbs])
    latest_tb = None
    if tbs:
        r = tbs[-1].result or {}
        latest_tb = {"problem_id": tbs[-1].problem_id, "title": problems[tbs[-1].problem_id].title,
                     "score": tbs[-1].score, "caught": len(r.get("caught", [])),
                     "total": len(r.get("caught", [])) + len(r.get("missed", []))}

    shuffle_pass = db.scalar(select(ShuffleRun.id).join(Attempt, Attempt.id == ShuffleRun.attempt_id).where(
        Attempt.user_id == user.id, ShuffleRun.status == "done", Attempt.sim_ok.is_(True))
        .where(ShuffleRun.result["order_sensitive"].as_boolean().is_(False))) is not None
    tb_full = sum(1 for v in tb_scores.values() if v == 1.0)
    badges = []
    if shuffle_pass:
        badges.append({"code": "shuffle_pass", "label": "顺序打乱实验通过"})
    if tb_full:
        badges.append({"code": "tb_full", "label": f"testbench 满分 ×{tb_full}"})

    # 预测把握度（第 4.7 节）：很有把握却没预测对的题，最值得回头弄明白
    s_ = get_settings()
    views = attempt_views(db, user.id)
    recent_conf = with_confidence(views, s_.confidence_window)
    confident_misses = [{"attempt_id": a.id, "problem_id": a.problem_id, "title": problems[a.problem_id].title,
                         "pred_accuracy": a.pred_accuracy, "created_at": a.created_at}
                        for a in attempts if (a.analysis or {}).get("confident_miss")][-5:][::-1]
    calibration = {"overconfidence": overconfidence_rate(views, s_.confidence_window),
                   "bias": calibration_bias(views, s_.confidence_window), "n": len(recent_conf),
                   "confident_misses": confident_misses}

    hints = db.execute(select(Hint, Attempt.problem_id).join(Attempt, Attempt.id == Hint.attempt_id)
                       .where(Attempt.user_id == user.id).order_by(Hint.id.desc()).limit(10)).all()
    upcoming = db.scalars(select(ReviewItem).where(ReviewItem.user_id == user.id, ReviewItem.status == "active")
                          .order_by(ReviewItem.due_at).limit(6)).all()

    return {
        "kpis": {
            "mastered": sum(1 for m in mastery if m["level"] == "mastered"),
            "fragile": sum(1 for m in mastery if m["level"] == "fragile"),
            "total_kps": len(mastery),
            "waveform_accuracy": recent_acc,
            "waveform_accuracy_delta": (recent_acc - before_acc) if recent_acc is not None and before_acc is not None else None,
            "tb": latest_tb,
        },
        "mastery": mastery,
        "calibration": calibration,
        "trend": trend,
        "fragile_list": fragile_list,
        "misconceptions": misconceptions,
        "badges": badges,
        "hints": [{"id": h.id, "problem_id": pid, "title": problems[pid].title, "level": h.level,
                   "message": h.content.get("message"), "question": h.content.get("question"),
                   "created_at": h.created_at} for h, pid in hints],
        "review_upcoming": [{"id": i.id, "title": problems[i.problem_id].title, "box": i.box,
                             "due_at": i.due_at, "kind": i.question.get("kind")} for i in upcoming],
    }
