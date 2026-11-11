"""三类任务：判题、顺序打乱实验、testbench 打分。

execute 只调用裁判（纯函数，可放进进程池）；apply_* 在主进程里把结果写回数据库、
推进做题步骤、写事件、重算掌握等级、安排复习。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from judge import apply_shuffle, diagnose, score_testbench, shuffle_test

from ..config import get_settings
from ..db import utcnow
from ..models import Attempt, Job, Prediction, Problem, ShuffleRun, TbSubmission, User
from . import mastery, review_scheduler, workflow
from .events import log_event
from .flags import flags_for_user
from .jobs import finish
from .learner_model import (QUADRANTS, confidence_flags, evaluate_prediction, order_belief_misconception,
                            prediction_misconceptions, prediction_ok, quadrant)


def execute(type_: str, payload: dict) -> dict:
    timeout = get_settings().judge_timeout
    student = payload.get("anon_id")
    if type_ == "judge":
        return diagnose(payload["code"], payload["problem_id"], student=student, timeout=timeout)
    if type_ == "shuffle":
        return shuffle_test(payload["code"], payload["problem_id"], student=student, timeout=timeout)
    if type_ == "tb":
        return score_testbench(payload["code"], payload["problem_id"], student=student, timeout=timeout)
    if type_ in ("export", "icap"):
        # 这两类任务要读写数据库：在任务进程里自己开会话
        from ..db import SessionLocal
        from .exports import build_export, exports_dir
        from .icap import run_icap
        from .llm import get_llm
        from datetime import datetime
        with SessionLocal() as db:
            if type_ == "export":
                path = exports_dir() / f"export_{payload['job_id']}.zip"
                counts = build_export(db, payload["class_id"], payload["kinds"], path)
                return {"path": str(path), "counts": counts}
            parse = lambda v: datetime.fromisoformat(v) if v else None  # noqa: E731
            return run_icap(db, get_llm(), payload["class_id"], parse(payload.get("from")), parse(payload.get("to")))
    raise ValueError(f"未知任务类型：{type_}")


def apply_result(db: DbSession, job: Job, output: dict) -> None:
    if job.type == "judge":
        apply_judge(db, db.get(Attempt, job.payload["attempt_id"]), output)
    elif job.type == "shuffle":
        apply_shuffle_run(db, db.get(ShuffleRun, job.payload["shuffle_run_id"]), output)
    elif job.type == "tb":
        apply_tb(db, db.get(TbSubmission, job.payload["tb_submission_id"]), output)
    if job.type in ("export", "icap"):
        finish(db, job, output)
        return
    finish(db, job, {"ok": True})


def apply_failure(db: DbSession, job: Job, error: str) -> None:
    if job.type == "judge":
        attempt = db.get(Attempt, job.payload["attempt_id"])
        attempt.status = "error"
        attempt.error = error[-2000:]
        attempt.finished_at = utcnow()
        problem = db.get(Problem, attempt.problem_id)
        user = db.get(User, attempt.user_id)
        progress = workflow.get_progress(db, attempt.user_id, problem)
        st = workflow.state_of(progress)
        progress.step = "modify" if st["modify_phase"] else (
            "predict" if flags_for_user(db, user)["predict_step"] else "run")
    elif job.type == "shuffle":
        run = db.get(ShuffleRun, job.payload["shuffle_run_id"])
        run.status = "error"
    elif job.type == "tb":
        sub = db.get(TbSubmission, job.payload["tb_submission_id"])
        sub.status = "error"


def apply_judge(db: DbSession, attempt: Attempt, diagnosis: dict) -> None:
    problem = db.get(Problem, attempt.problem_id)
    user = db.get(User, attempt.user_id)
    meta = problem.meta
    preds = db.scalars(select(Prediction).where(Prediction.attempt_id == attempt.id)).all()
    waveform = next((p for p in preds if p.kind == "waveform"), None)
    hardware = next((p for p in preds if p.kind == "hardware"), None)
    compiled = diagnosis["compile"]["ok"]

    evaluation = None
    misconceptions: list[str] = []
    if preds and compiled:
        evaluation = evaluate_prediction(
            predict_points=meta["predict_points"], hardware_questions=meta["hardware_questions"],
            waveform=waveform.answers if waveform else None,
            hardware=hardware.answers if hardware else None, diagnosis=diagnosis)
        if waveform:
            waveform.accuracy = evaluation["waveform"]["accuracy"]
            waveform.result = evaluation["waveform"]
        if hardware:
            hardware.accuracy = evaluation["hardware"]["accuracy"]
            hardware.result = evaluation["hardware"]
        misconceptions = prediction_misconceptions(evaluation, diagnosis)

    sim_ok = bool(compiled and diagnosis["sim"]["ok"])
    acc = evaluation["accuracy"] if evaluation else None
    attempt.judge = diagnosis
    attempt.sim_ok = sim_ok
    attempt.pred_accuracy = acc
    pred_ok = prediction_ok(acc, get_settings().pred_threshold)
    attempt.quadrant = quadrant(sim_ok, pred_ok, compiled)
    attempt.analysis = {"evaluation": evaluation, "misconceptions": misconceptions,
                        **confidence_flags(attempt.confidence, pred_ok if compiled else None)}
    attempt.status = "done"
    attempt.finished_at = utcnow()

    log_event(db, user, "judge.done", problem_id=problem.id, attempt_id=attempt.id, payload={
        "attempt_id": attempt.id, "sim_ok": sim_ok, "tags": diagnosis["tags"],
        "quadrant": attempt.quadrant, "pred_accuracy": acc, "confidence": attempt.confidence,
    })

    flags = flags_for_user(db, user)
    progress = workflow.get_progress(db, user.id, problem, flags["predict_step"])
    workflow.on_attempt_judged(problem, progress, attempt, flags["predict_step"])

    if attempt.quadrant in QUADRANTS:
        db.flush()
        mastery.recompute(db, user.id, problem.knowledge_points)
        if flags.get("review", True):
            review_scheduler.enqueue_for_attempt(db, attempt, problem, misconceptions)
    if flags.get("review", True):         # 误区复盘：编译没过也可以出（语法错误也是一类问题）
        review_scheduler.enqueue_find_bug(db, attempt)


def apply_shuffle_run(db: DbSession, run: ShuffleRun, result: dict) -> None:
    attempt = db.get(Attempt, run.attempt_id)
    user = db.get(User, attempt.user_id)
    run.result = result
    run.status = "done"
    if attempt.judge and result.get("ok"):
        attempt.judge = apply_shuffle(attempt.judge, result)
        if order_belief_misconception(run.prediction, result.get("order_sensitive")):
            analysis = dict(attempt.analysis or {})
            analysis["misconceptions"] = sorted(set(analysis.get("misconceptions", [])) | {"pred_order_belief"})
            attempt.analysis = analysis
    log_event(db, user, "shuffle.run", problem_id=attempt.problem_id, attempt_id=attempt.id, payload={
        "attempt_id": attempt.id, "order_sensitive": result.get("order_sensitive"),
        "prediction": run.prediction, "shuffle_run_id": run.id,
    })


def apply_tb(db: DbSession, sub: TbSubmission, result: dict) -> None:
    user = db.get(User, sub.user_id)
    problem = db.get(Problem, sub.problem_id)
    sub.result = result
    sub.score = result.get("score")
    sub.status = "done"
    log_event(db, user, "tb.submit", problem_id=problem.id, payload={
        "tb_submission_id": sub.id, "ok": result.get("ok"), "score": result.get("score"),
        "caught": result.get("caught", []), "missed": result.get("missed", []),
    })
    if result.get("ok"):
        progress = workflow.get_progress(db, user.id, problem)
        workflow.on_tb_scored(progress)
