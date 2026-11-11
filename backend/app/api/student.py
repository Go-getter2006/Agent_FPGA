"""学生端接口：/api/student/*（docs/data-api.md 3.2 节）。学生只能读写自己的数据。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import get_db, utcnow
from ..models import (Assignment, Attempt, ChatMessage, Event, Explanation, Hint, Investigation, KnowledgePoint,
                      Prediction, Problem, Progress, ReviewItem, ShuffleRun, TbSubmission, User)
from judge import schematic as judge_schematic

from ..services import answer, chat, jobs, llm_hints, review_scheduler, workflow
from ..services.llm import get_llm
from ..services.events import CLIENT_EVENT_TYPES, log_event, primary_enrollment
from ..services.flags import flags_for_user
from ..services.learner_model import MISCONCEPTION_LABELS, normalize_value
from ..services.report import student_report
from .deps import ApiError, not_found, student_user

router = APIRouter(prefix="/student", tags=["student"])

PRIMM_LABEL = {"predict": "预测题", "modify": "修改题", "make": "创作题"}


# ---------------------------------------------------------------- 公共

def _problem(db: DbSession, pid: str) -> Problem:
    p = db.get(Problem, pid)
    if p is None:
        raise not_found("题目")
    return p


def _attempt(db: DbSession, user: User, aid: int) -> Attempt:
    a = db.get(Attempt, aid)
    if a is None or a.user_id != user.id:      # 别人的尝试一律当作不存在
        raise not_found("这次提交")
    return a


def _kp_names(db: DbSession) -> dict[str, str]:
    return {k.code: k.name for k in db.scalars(select(KnowledgePoint)).all()}


def _visible_assignments(db: DbSession, user: User) -> list[Assignment]:
    enrollment = primary_enrollment(db, user.id)
    if enrollment is None:
        return []
    rows = db.scalars(select(Assignment).where(Assignment.class_id == enrollment.class_id)
                      .order_by(Assignment.due_at)).all()
    return [a for a in rows if a.group_scope in ("all", enrollment.group)]


def _latest_attempt(db: DbSession, user_id: int, pid: str) -> Attempt | None:
    return db.scalar(select(Attempt).where(Attempt.user_id == user_id, Attempt.problem_id == pid)
                     .order_by(Attempt.id.desc()))


def _status(db: DbSession, user_id: int, pid: str) -> str:
    progress = db.scalar(select(Progress).where(Progress.user_id == user_id, Progress.problem_id == pid))
    last = db.scalar(select(Attempt).where(Attempt.user_id == user_id, Attempt.problem_id == pid,
                                           Attempt.status == "done").order_by(Attempt.id.desc()))
    if progress is None and last is None:
        return "not_started"
    if last is not None and last.quadrant == "mastered":
        return "mastered"
    if progress is not None and workflow.state_of(progress)["passed"]:
        return "passed"
    return "in_progress"


def _commit_and_run(db: DbSession, job) -> None:
    db.commit()
    if get_settings().jobs_inline:
        jobs.run_job_inline(db, job)


def _require_flag(flags: dict, name: str, label: str) -> None:
    if not flags.get(name, True):
        raise ApiError(403, "FEATURE_OFF", f"本班当前没有开放“{label}”")


# ---------------------------------------------------------------- 首页与题目列表

@router.get("/home")
def home(user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    problems = {p.id: p for p in db.scalars(select(Problem)).all()}
    assignments = []
    for a in _visible_assignments(db, user):
        items = [{"id": pid, "title": problems[pid].title, "status": _status(db, user.id, pid)}
                 for pid in a.problem_ids if pid in problems]
        done = sum(1 for i in items if i["status"] in ("passed", "mastered"))
        assignments.append({"id": a.id, "title": a.title, "open_at": a.open_at, "due_at": a.due_at,
                            "problems": items, "done": done, "total": len(items)})
    progress = db.scalar(select(Progress).where(Progress.user_id == user.id, Progress.step != "done")
                         .order_by(Progress.updated_at.desc()))
    cont = None
    if progress is not None:
        cont = {"problem_id": progress.problem_id, "title": problems[progress.problem_id].title,
                "step": progress.step}
    last = db.scalar(select(Attempt).where(Attempt.user_id == user.id, Attempt.status == "done")
                     .order_by(Attempt.id.desc()))
    feedback = None
    if last is not None:
        feedback = {"problem_id": last.problem_id, "title": problems[last.problem_id].title,
                    "attempt_id": last.id, "sim_ok": last.sim_ok, "quadrant": last.quadrant,
                    "tags": (last.judge or {}).get("tags", []), "created_at": last.created_at}
    due, remaining = review_scheduler.due_items(db, user.id)
    report = student_report(db, user, brief=True)
    return {"user": {"display_name": user.display_name}, "assignments": assignments, "continue": cont,
            "review_due": len(due), "review_remaining_today": remaining,
            "mastery": report["mastery"], "last_feedback": feedback}


@router.get("/problems")
def list_problems(assignment_id: int | None = None, kp: str | None = None, status: str | None = None,
                  user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    names = _kp_names(db)
    assignments = _visible_assignments(db, user)
    due_by_problem: dict[str, datetime] = {}
    for a in assignments:
        for pid in a.problem_ids:
            due_by_problem.setdefault(pid, a.due_at)
    allowed = None
    if assignment_id is not None:
        match = [a for a in assignments if a.id == assignment_id]
        if not match:
            raise not_found("作业")
        allowed = set(match[0].problem_ids)
    rows = []
    kp_order = {k.code: k.sort_order for k in db.scalars(select(KnowledgePoint)).all()}
    problems = sorted(db.scalars(select(Problem)).all(),
                      key=lambda p: (p.meta.get("order", 100),
                                     min((kp_order.get(k, 99) for k in p.knowledge_points), default=99),
                                     p.difficulty, p.id))
    for p in problems:
        if allowed is not None and p.id not in allowed:
            continue
        if kp and kp not in p.knowledge_points:
            continue
        st = _status(db, user.id, p.id)
        if status and st != status:
            continue
        rows.append({"id": p.id, "title": p.title, "primm_type": p.primm_type, "stage": p.meta.get("stage") or "",
                     "primm_label": PRIMM_LABEL[p.primm_type], "difficulty": p.difficulty,
                     "knowledge_points": [{"code": k, "name": names.get(k, k)} for k in p.knowledge_points],
                     "status": st, "due_at": due_by_problem.get(p.id)})
    return {"items": rows,
            "assignments": [{"id": a.id, "title": a.title, "due_at": a.due_at} for a in assignments],
            "knowledge_points": [{"code": c, "name": n} for c, n in
                                 sorted(names.items(), key=lambda kv: kp_order.get(kv[0], 99))]}


def _attempt_summary(a: Attempt) -> dict:
    return {"id": a.id, "attempt_no": a.attempt_no, "step": a.step, "status": a.status,
            "created_at": a.created_at, "sim_ok": a.sim_ok, "quadrant": a.quadrant,
            "pred_accuracy": a.pred_accuracy, "tags": (a.judge or {}).get("tags", [])}


def _editable(problem: Problem, progress: Progress) -> bool:
    if problem.primm_type == "predict":
        return False
    if problem.primm_type == "modify":
        return workflow.state_of(progress)["modify_phase"]
    # 创作题：第一次探究完成之前，探究步骤里代码只读
    return progress.step != "investigate" or workflow.state_of(progress)["investigated"]


@router.get("/problems/{pid}")
def problem_detail(pid: str, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    p = _problem(db, pid)
    flags = flags_for_user(db, user)
    progress = workflow.get_progress(db, user.id, p, flags["predict_step"])
    db.commit()
    names = _kp_names(db)
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.problem_id == pid)
                          .order_by(Attempt.id)).all()
    pending = workflow.pending_predictions(db, user.id, pid)
    latest_tb = db.scalar(select(TbSubmission).where(TbSubmission.user_id == user.id, TbSubmission.problem_id == pid)
                          .order_by(TbSubmission.id.desc()))
    meta = p.meta
    last = attempts[-1] if attempts else None
    code = last.code if last is not None else (meta.get("starter") or "")
    if p.primm_type == "make" and last is None:
        code = ""
    st = workflow.state_of(progress)
    return {
        "id": p.id, "title": p.title, "primm_type": p.primm_type, "primm_label": PRIMM_LABEL[p.primm_type],
        "difficulty": p.difficulty,
        "knowledge_points": [{"code": k, "name": names.get(k, k)} for k in p.knowledge_points],
        "spec": meta["spec"], "starter": meta.get("starter"), "modify_goal": meta.get("modify_goal", ""),
        "predict_points": meta["predict_points"], "hardware_questions": meta["hardware_questions"],
        "skeleton": meta["skeleton"], "tb_template": meta["tb_template"] if p.primm_type == "make" else None,
        "steps": workflow.STEPS_BY_TYPE[p.primm_type],
        "progress": {"step": progress.step, "completed": workflow.completed_steps(p, progress),
                     "investigated": st["investigated"], "passed": st["passed"],
                     "modify_phase": st["modify_phase"], "tb_done": st["tb_done"]},
        "editable": _editable(p, progress),
        "code": code,
        "attempts": [_attempt_summary(a) for a in attempts],
        "latest_attempt_id": last.id if last is not None else None,
        "pending_prediction": [{"id": x.id, "kind": x.kind, "answers": x.answers, "locked_at": x.locked_at,
                                "confidence": x.confidence} for x in pending],
        "latest_tb": _tb_payload(latest_tb) if latest_tb else None,
        "flags": flags,
        "stage": meta.get("stage") or "",
        "answer": answer.status(db, user.id, p),
    }


# ---------------------------------------------------------------- ① 预测

class Cell(BaseModel):
    signal: str
    step: int
    value: str


class WaveformIn(BaseModel):
    cells: list[Cell] = Field(default_factory=list)


class HardwareIn(BaseModel):
    ff_count: int | None = Field(default=None, ge=0, le=4096)
    latch: bool | None = None
    ff_signals: list[str] | None = None


class PredictionIn(BaseModel):
    waveform: WaveformIn | None = None
    hardware: HardwareIn | None = None
    confidence: int | None = Field(default=None, ge=1, le=3)   # 把握程度：1 没把握 / 2 有点把握 / 3 很有把握


@router.post("/problems/{pid}/predictions")
def lock_prediction(pid: str, body: PredictionIn, user: User = Depends(student_user),
                    db: DbSession = Depends(get_db)):
    p = _problem(db, pid)
    flags = flags_for_user(db, user)
    _require_flag(flags, "predict_step", "预测")
    if workflow.running_attempt(db, user.id, pid):
        raise ApiError(409, "ATTEMPT_RUNNING", "仿真还在进行中，完成后再预测下一次")
    if workflow.pending_predictions(db, user.id, pid):
        raise ApiError(409, "PREDICTION_LOCKED", "预测已经锁定，先运行仿真")
    meta = p.meta
    widths = {o["name"]: o["width"] for o in meta["skeleton"]["outputs"]}
    given = {(c.signal, c.step): c.value for c in (body.waveform.cells if body.waveform else [])}
    cells = []
    for point in meta["predict_points"]:
        for step in point["steps"]:
            raw = given.get((point["signal"], step))
            value = normalize_value(raw, widths.get(point["signal"], 1))
            if value is None:
                raise ApiError(400, "PREDICTION_INCOMPLETE",
                               f"{point['signal']} 第 {step} 步还没填，或格式不对（用二进制，或 0x 开头的十六进制）")
            cells.append({"signal": point["signal"], "step": step, "value": value})
    hw_answers = {}
    questions = meta["hardware_questions"]
    if questions:
        hw = body.hardware or HardwareIn()
        if "ff_count" in questions:
            if hw.ff_count is None:
                raise ApiError(400, "PREDICTION_INCOMPLETE", "还没回答“会综合出几个触发器”")
            hw_answers["ff_count"] = hw.ff_count
        if "latch" in questions:
            if hw.latch is None:
                raise ApiError(400, "PREDICTION_INCOMPLETE", "还没回答“有没有锁存器”")
            hw_answers["latch"] = hw.latch
        if "ff_signals" in questions:
            hw_answers["ff_signals"] = sorted({s.strip() for s in (hw.ff_signals or []) if s.strip()})
    created = []
    if cells:
        w = Prediction(user_id=user.id, problem_id=pid, kind="waveform", answers={"cells": cells},
                       confidence=body.confidence)
        db.add(w)
        created.append(w)
    if questions:
        h = Prediction(user_id=user.id, problem_id=pid, kind="hardware", answers=hw_answers,
                       confidence=body.confidence)
        db.add(h)
        created.append(h)
    db.flush()
    for pred in created:
        log_event(db, user, "predict.submit", problem_id=pid, payload={
            "kind": pred.kind, "cells": len(pred.answers.get("cells", [])) if pred.kind == "waveform" else len(questions),
            "answers": pred.answers, "prediction_id": pred.id, "accuracy": None, "confidence": body.confidence})
    progress = workflow.get_progress(db, user.id, p, True)
    workflow.on_predictions_locked(progress)
    db.commit()
    return {"prediction_ids": [x.id for x in created], "step": progress.step}


# ---------------------------------------------------------------- ② 运行

class AttemptIn(BaseModel):
    code: str = Field(max_length=100_000)


@router.post("/problems/{pid}/attempts")
def submit_attempt(pid: str, body: AttemptIn, user: User = Depends(student_user),
                   db: DbSession = Depends(get_db)):
    p = _problem(db, pid)
    flags = flags_for_user(db, user)
    progress = workflow.get_progress(db, user.id, p, flags["predict_step"])
    try:
        jobs.check_submit_limits(db, user.id)
    except jobs.RateLimited as exc:
        raise ApiError(429, "RATE_LIMITED", str(exc)) from exc
    pending = workflow.pending_predictions(db, user.id, pid)
    if flags["predict_step"] and not pending:
        raise ApiError(409, "PREDICTION_REQUIRED", "先填预测格并锁定预测，再运行仿真")
    code = body.code
    if not _editable(p, progress) and p.meta.get("starter") is not None:
        code = p.meta["starter"]                 # 预测题、修改题改代码之前：运行的是起始代码
    if not code.strip():
        raise ApiError(400, "EMPTY_CODE", "代码是空的，先写一点再运行")
    attempt_no = (db.scalar(select(func.count()).select_from(Attempt).where(
        Attempt.user_id == user.id, Attempt.problem_id == pid)) or 0) + 1
    step = workflow.on_attempt_submitted(progress)
    attempt = Attempt(user_id=user.id, problem_id=pid, attempt_no=attempt_no, step=step, code=code,
                      code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(), status="queued")
    db.add(attempt)
    db.flush()
    for pred in pending:
        pred.attempt_id = attempt.id
    attempt.confidence = next((x.confidence for x in pending if x.confidence is not None), None)
    log_event(db, user, "code.submit", problem_id=pid, attempt_id=attempt.id, payload={
        "attempt_id": attempt.id, "code_hash": attempt.code_hash, "lines": code.count("\n") + 1,
        "attempt_no": attempt_no, "step": step})
    job = jobs.enqueue(db, "judge", {"attempt_id": attempt.id, "code": code, "problem_id": pid,
                                     "anon_id": user.anon_id}, user.id)
    _commit_and_run(db, job)
    return {"attempt_id": attempt.id, "job_id": job.id}


@router.get("/attempts/{aid}")
def attempt_detail(aid: int, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    a = _attempt(db, user, aid)
    p = _problem(db, a.problem_id)
    preds = db.scalars(select(Prediction).where(Prediction.attempt_id == a.id)).all()
    analysis = a.analysis or {}
    evaluation = analysis.get("evaluation")
    out = {
        **_attempt_summary(a), "problem_id": a.problem_id, "code": a.code,
        "finished_at": a.finished_at, "judge": None, "expected": None, "evaluation": evaluation,
        "predictions": [{"id": x.id, "kind": x.kind, "answers": x.answers, "accuracy": x.accuracy} for x in preds],
        "misconceptions": [{"code": m, "label": MISCONCEPTION_LABELS.get(m, m)}
                           for m in analysis.get("misconceptions", [])],
        "investigation": None, "hints": [], "shuffle": None, "previous": None,
        "confidence": a.confidence, "confident_miss": bool(analysis.get("confident_miss")),
        "under_confident": bool(analysis.get("under_confident")),
    }
    if a.status != "done":
        return out
    out["judge"] = a.judge
    out["expected"] = p.meta["ref_trace"]
    if a.judge["compile"]["ok"]:
        out["investigation"] = workflow.investigation_status(db, a, evaluation)
    out["hints"] = [_hint_payload(h) for h in db.scalars(select(Hint).where(
        Hint.attempt_id == a.id, Hint.level < answer.ANSWER_LEVEL).order_by(Hint.level)).all()]
    run = db.scalar(select(ShuffleRun).where(ShuffleRun.attempt_id == a.id).order_by(ShuffleRun.id.desc()))
    if run is not None:
        out["shuffle"] = {"id": run.id, "status": run.status, "prediction": run.prediction, "result": run.result}
    prev = db.scalar(select(Attempt).where(Attempt.user_id == user.id, Attempt.problem_id == a.problem_id,
                                           Attempt.id < a.id, Attempt.status == "done")
                     .order_by(Attempt.id.desc()))
    if prev is not None and prev.judge and prev.judge["compile"]["ok"]:
        out["previous"] = {"id": prev.id, "attempt_no": prev.attempt_no, "trace": prev.judge["sim"]["trace"]}
    return out


# ---------------------------------------------------------------- ③ 探究

class InvestigationIn(BaseModel):
    kind: str = Field(pattern="^(locate_step|locate_line)$")
    chosen: dict


def _done_attempt(db: DbSession, user: User, aid: int) -> Attempt:
    a = _attempt(db, user, aid)
    if a.status != "done" or not a.judge or not a.judge["compile"]["ok"]:
        raise ApiError(409, "NOT_READY", "这次提交还没有可以探究的仿真结果")
    return a


def _maybe_complete_investigation(db: DbSession, user: User, a: Attempt) -> dict:
    p = _problem(db, a.problem_id)
    status = workflow.investigation_status(db, a, (a.analysis or {}).get("evaluation"))
    if status["complete"]:
        flags = flags_for_user(db, user)
        progress = workflow.get_progress(db, user.id, p, flags["predict_step"])
        workflow.on_investigation_complete(p, progress, a, flags["predict_step"])
    return status


@router.post("/attempts/{aid}/investigations")
def investigate(aid: int, body: InvestigationIn, user: User = Depends(student_user),
                db: DbSession = Depends(get_db)):
    a = _done_attempt(db, user, aid)
    p = _problem(db, a.problem_id)
    evaluation = (a.analysis or {}).get("evaluation")
    target = workflow.investigation_target(a, evaluation)
    if body.kind == "locate_step":
        correct = workflow.check_locate_step(a, target, p.meta["ref_trace"], body.chosen)
    else:
        correct = workflow.check_locate_line(a, target, body.chosen)
    db.add(Investigation(attempt_id=a.id, kind=body.kind, chosen=body.chosen, correct=correct))
    log_event(db, user, f"investigate.{body.kind}", problem_id=a.problem_id, attempt_id=a.id,
              payload={"attempt_id": a.id, "chosen": body.chosen, "correct": correct})
    db.flush()
    status = _maybe_complete_investigation(db, user, a)
    db.commit()
    return {"correct": correct, "message": "找到了" if correct else "再看看", "investigation": status}


class ExplanationIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/attempts/{aid}/explanations")
def explain(aid: int, body: ExplanationIn, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    a = _done_attempt(db, user, aid)
    text = body.text.strip()
    if len(text) < 4:
        raise ApiError(400, "TOO_SHORT", "多写几个字，说说你认为的原因")
    db.add(Explanation(attempt_id=a.id, text=text))
    log_event(db, user, "explain.submit", problem_id=a.problem_id, attempt_id=a.id,
              payload={"attempt_id": a.id, "length": len(text)})
    db.flush()
    status = _maybe_complete_investigation(db, user, a)
    db.commit()
    return {"ok": True, "investigation": status}


# ---------------------------------------------------------------- 提示阶梯

def _hint_payload(h: Hint) -> dict:
    return {"id": h.id, "level": h.level, "source": h.source, "created_at": h.created_at, **h.content}


@router.post("/attempts/{aid}/hints")
def request_hint(aid: int, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    a = _attempt(db, user, aid)
    if a.status != "done":
        raise ApiError(409, "NOT_READY", "等仿真结果出来再要提示")
    existing = db.scalars(select(Hint).where(Hint.attempt_id == a.id, Hint.level < answer.ANSWER_LEVEL)
                          .order_by(Hint.level)).all()
    level = (existing[-1].level if existing else 0) + 1
    if level > 3:
        raise ApiError(409, "HINT_MAX", "已经是最高一级提示了，试着按提示改一改再运行；实在不会可以看参考答案")
    last_hint = db.scalar(select(Hint).join(Attempt, Attempt.id == Hint.attempt_id).where(
        Attempt.user_id == user.id, Attempt.problem_id == a.problem_id).order_by(Hint.created_at.desc()))
    if last_hint is not None and existing:
        wait_s = get_settings().hint_interval_seconds - (utcnow() - last_hint.created_at).total_seconds()
        acted = db.scalar(select(Event.id).where(
            Event.user_id == user.id, Event.problem_id == a.problem_id, Event.ts > last_hint.created_at,
            Event.type.in_(("code.submit", "investigate.locate_step", "investigate.locate_line"))))
        if wait_s > 0 and acted is None:
            raise ApiError(429, "HINT_TOO_SOON",
                           f"先看看波形，{int(wait_s) + 1} 秒后可以再要一级提示（或者先完成一次定位）")
    log_event(db, user, "hint.request", problem_id=a.problem_id, attempt_id=a.id,
              payload={"attempt_id": a.id, "level": level})
    run = db.scalar(select(ShuffleRun).where(ShuffleRun.attempt_id == a.id, ShuffleRun.status == "done")
                    .order_by(ShuffleRun.id.desc()))
    p = _problem(db, a.problem_id)
    db.flush()
    # 大模型分级提示；关闭、不可用、校验不通过时降级为规则提示（docs/llm-deepseek.md 第 5、7 节）
    out = llm_hints.generate_hint(db, get_llm(), attempt=a, problem=p, level=level,
                                  llm_enabled=flags_for_user(db, user)["llm_hints"],
                                  shuffle=run.result if run else None)
    content = {**out["content"], "fallback_reason": out["fallback_reason"]}
    hint = Hint(attempt_id=a.id, level=level, source=out["source"], content=content, llm_call_id=out["llm_call_id"])
    db.add(hint)
    db.flush()
    log_event(db, user, "hint.shown", problem_id=a.problem_id, attempt_id=a.id,
              payload={"attempt_id": a.id, "level": level, "source": out["source"], "hint_id": hint.id,
                       "prompt_version": content.get("prompt_version") or "fallback_v1",
                       "fallback_reason": out["fallback_reason"]})
    db.commit()
    return _hint_payload(hint)


# ---------------------------------------------------------------- 电路图（代码 ↔ 综合出的电路联动）

@router.get("/attempts/{aid}/schematic")
def attempt_schematic(aid: int, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    """这次提交综合出的 RTL 级电路（yosys prep 网表），前端画成电路图；第一次生成后存在 attempt.analysis 里。"""
    a = _attempt(db, user, aid)
    if a.status != "done":
        raise ApiError(409, "NOT_READY", "等仿真结果出来再看电路图")
    if not (a.judge or {}).get("compile", {}).get("ok"):
        raise ApiError(409, "COMPILE_FAILED", "代码没有通过编译，先改好再看电路图")
    cached = (a.analysis or {}).get("schematic")
    if cached is None:
        cached = judge_schematic(a.code, timeout=get_settings().judge_timeout)
        a.analysis = {**(a.analysis or {}), "schematic": cached}
        db.commit()
    if not cached["ok"]:
        raise ApiError(409, "SCHEMATIC_FAILED", cached["error"] or "这段代码画不出电路图")
    return {"netlist": cached["netlist"], "cells": cached["cells"], "drivers": (a.judge or {}).get("drivers") or {}}


# ---------------------------------------------------------------- 第 4 级：参考答案

@router.post("/problems/{pid}/answer")
def show_answer(pid: str, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    """满足解锁条件时返回参考答案；第一次查看记一条 level=4 的提示（计入提示依赖度）。"""
    p = _problem(db, pid)
    st = answer.status(db, user.id, p)
    if not st["available"]:
        raise ApiError(409, "ANSWER_NA", st["message"])
    if not st["unlocked"]:
        raise ApiError(403, "ANSWER_LOCKED", st["message"])
    first = not st["revealed"]
    if first:
        latest = _latest_attempt(db, user.id, pid)
        passed_before = any(x.sim_ok for x in db.scalars(select(Attempt).where(
            Attempt.user_id == user.id, Attempt.problem_id == pid, Attempt.status == "done")).all())
        hint = Hint(attempt_id=latest.id, level=answer.ANSWER_LEVEL, source="answer", content={
            "level": answer.ANSWER_LEVEL, "focus": {"step": None, "signal": None, "lines": []},
            "message": "参考答案", "question": "", "concept_tags": [], "code": "",
            "prompt_version": answer.ANSWER_VERSION})
        db.add(hint)
        db.flush()
        log_event(db, user, "answer.reveal", problem_id=pid, attempt_id=latest.id,
                  payload={"hint_id": hint.id, "failed": st["failed"], "passed_before": passed_before})
    else:
        log_event(db, user, "answer.view", problem_id=pid, payload={})
    db.commit()
    return {"code": p.meta.get("ref_code") or "", "first_time": first,
            "note": "看过参考答案之后，这道题再提交的结果不计入掌握度。建议看懂后关掉答案，自己重新写一遍。",
            "answer": answer.status(db, user.id, p)}


# ---------------------------------------------------------------- 助教对话（SSE）

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    attempt_id: int | None = None


@router.get("/problems/{pid}/chat")
def chat_history(pid: str, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    p = _problem(db, pid)
    session = chat.get_session(db, user.id, p.id)
    db.commit()
    return {"session_id": session.id, "enabled": flags_for_user(db, user)["chat"],
            "messages": [{"id": m.id, "role": m.role, "content": m.content, "source": m.source,
                          "flagged": m.flagged, "created_at": m.created_at} for m in chat.history(db, session)]}


@router.post("/problems/{pid}/chat")
def chat_send(pid: str, body: ChatIn, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    p = _problem(db, pid)
    _require_flag(flags_for_user(db, user), "chat", "助教对话")
    if chat.sent_last_hour(db, user.id) >= get_settings().chat_hourly_limit:
        raise ApiError(429, "CHAT_LIMIT", chat.RATE_LIMITED)
    attempt_id = body.attempt_id
    if attempt_id is not None:
        a = db.get(Attempt, attempt_id)
        if a is None or a.user_id != user.id or a.problem_id != pid:
            attempt_id = None
    if attempt_id is None:
        latest = _latest_attempt(db, user.id, pid)
        attempt_id = latest.id if latest else None
    session = chat.get_session(db, user.id, p.id)
    text = body.message.strip()
    msg = ChatMessage(session_id=session.id, role="user", content=text, attempt_id=attempt_id)
    db.add(msg)
    db.flush()
    log_event(db, user, "chat.send", problem_id=pid, attempt_id=attempt_id,
              payload={"session_id": session.id, "length": len(text)})
    db.commit()
    gen = chat.stream_reply(get_llm(), user_id=user.id, session_id=session.id, message_id=msg.id,
                            attempt_id=attempt_id)
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- 顺序打乱实验

class ShuffleIn(BaseModel):
    prediction: str | None = Field(default=None, pattern="^(change|same)$")


@router.post("/attempts/{aid}/shuffle")
def start_shuffle(aid: int, body: ShuffleIn, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    a = _done_attempt(db, user, aid)
    _require_flag(flags_for_user(db, user), "shuffle", "顺序打乱实验")
    busy = db.scalar(select(ShuffleRun.id).where(ShuffleRun.attempt_id == a.id,
                                                 ShuffleRun.status.in_(("queued", "running"))))
    if busy:
        raise ApiError(409, "SHUFFLE_RUNNING", "实验还在进行中")
    run = ShuffleRun(attempt_id=a.id, prediction=body.prediction, status="queued")
    db.add(run)
    db.flush()
    job = jobs.enqueue(db, "shuffle", {"shuffle_run_id": run.id, "code": a.code, "problem_id": a.problem_id,
                                       "anon_id": user.anon_id}, user.id)
    _commit_and_run(db, job)
    return {"shuffle_run_id": run.id, "job_id": job.id}


# ---------------------------------------------------------------- ⑤ 创作：testbench 打分

def _bug_description(problem_id: str, case_name: str) -> str:
    """错误样本第二行的文字说明（“// 错误：……”），只说 bug 的类型，不给代码。"""
    path = get_settings().problems_dir / problem_id / "cases" / case_name
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "一个错误设计"
    text = lines[1].lstrip("/ ").strip() if len(lines) > 1 else ""
    for prefix in ("错误：", "隐患："):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text or "一个错误设计"


def _tb_payload(sub: TbSubmission) -> dict:
    missed = (sub.result or {}).get("missed", [])
    return {"id": sub.id, "status": sub.status, "score": sub.score, "result": sub.result,
            "created_at": sub.created_at, "code": sub.code,
            "missed_types": [_bug_description(sub.problem_id, name) for name in missed]}


class TestbenchIn(BaseModel):
    code: str = Field(min_length=1, max_length=100_000)


@router.post("/problems/{pid}/testbench")
def submit_testbench(pid: str, body: TestbenchIn, user: User = Depends(student_user),
                     db: DbSession = Depends(get_db)):
    p = _problem(db, pid)
    flags = flags_for_user(db, user)
    _require_flag(flags, "tb_scoring", "testbench 打分")
    if p.primm_type != "make":
        raise ApiError(409, "NOT_MAKE", "只有创作题需要写 testbench")
    progress = workflow.get_progress(db, user.id, p, flags["predict_step"])
    if progress.step not in ("make", "done"):
        raise ApiError(409, "STEP_LOCKED", "先让自己的设计仿真通过，再来写 testbench")
    busy = db.scalar(select(TbSubmission.id).where(TbSubmission.user_id == user.id,
                                                   TbSubmission.status.in_(("queued", "running"))))
    if busy:
        raise ApiError(409, "TB_RUNNING", "上一次打分还在进行中")
    sub = TbSubmission(user_id=user.id, problem_id=pid, code=body.code, status="queued")
    db.add(sub)
    db.flush()
    job = jobs.enqueue(db, "tb", {"tb_submission_id": sub.id, "code": body.code, "problem_id": pid,
                                  "anon_id": user.anon_id}, user.id)
    _commit_and_run(db, job)
    return {"tb_submission_id": sub.id, "job_id": job.id}


@router.get("/testbench/{sid}")
def testbench_detail(sid: int, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    sub = db.get(TbSubmission, sid)
    if sub is None or sub.user_id != user.id:
        raise not_found("testbench 提交")
    return _tb_payload(sub)


# ---------------------------------------------------------------- 我的学情、复习

@router.get("/report")
def report(user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    return student_report(db, user)


@router.get("/review")
def review_list(user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    items, remaining = review_scheduler.due_items(db, user.id)
    problems = {p.id: p for p in db.scalars(select(Problem)).all()}
    names = _kp_names(db)
    upcoming = db.scalars(select(ReviewItem).where(ReviewItem.user_id == user.id, ReviewItem.status == "active")
                          .order_by(ReviewItem.due_at)).all()
    return {
        "remaining_today": remaining,
        "items": [{"id": i.id, "problem_id": i.problem_id, "title": problems[i.problem_id].title,
                   "knowledge_point": {"code": i.knowledge_point, "name": names.get(i.knowledge_point)},
                   "box": i.box, "due_at": i.due_at, "question": review_scheduler.public_question(i)}
                  for i in items],
        "upcoming": [{"id": i.id, "title": problems[i.problem_id].title, "box": i.box, "due_at": i.due_at,
                      "kind": i.question.get("kind")} for i in upcoming],
    }


class ReviewAnswerIn(BaseModel):
    waveform: WaveformIn | None = None
    hardware: HardwareIn | None = None
    choice: str | None = Field(default=None, max_length=32)      # 误区复盘：选出的问题标签


@router.post("/review/{item_id}/answer")
def review_answer(item_id: int, body: ReviewAnswerIn, user: User = Depends(student_user),
                  db: DbSession = Depends(get_db)):
    item = db.get(ReviewItem, item_id)
    if item is None or item.user_id != user.id:
        raise not_found("复习条目")
    if item.status != "active" or item.due_at > utcnow():
        raise ApiError(409, "NOT_DUE", "这一条还没到复习时间")
    widths = {o["name"]: o["width"] for o in (item.question.get("skeleton") or {}).get("outputs", [])}
    answers: dict = {"choice": body.choice}
    if body.waveform is not None:
        answers["waveform"] = {"cells": [
            {"signal": c.signal, "step": c.step, "value": normalize_value(c.value, widths.get(c.signal, 1))}
            for c in body.waveform.cells]}
    if body.hardware is not None:
        answers["hardware"] = body.hardware.model_dump()
    graded = review_scheduler.grade(item, answers)
    review_scheduler.apply_answer(item, graded["correct"])
    log_event(db, user, "review.answer", problem_id=item.problem_id, payload={
        "item_id": item.id, "correct": graded["correct"], "box": item.box, "status": item.status,
        "accuracy": graded["evaluation"]["accuracy"], "kind": item.question.get("kind"),
        "choice": body.choice if item.question.get("kind") == "find_bug" else None})
    db.commit()
    return {"correct": graded["correct"], "box": item.box, "status": item.status, "due_at": item.due_at,
            "evaluation": graded["evaluation"]}


# ---------------------------------------------------------------- 界面事件批量上报

class ClientEvent(BaseModel):
    type: str
    ts: datetime | None = None
    problem_id: str | None = None
    attempt_id: int | None = None
    payload: dict = Field(default_factory=dict)


class EventsIn(BaseModel):
    events: list[ClientEvent] = Field(max_length=50)


@router.post("/events")
def report_events(body: EventsIn, user: User = Depends(student_user), db: DbSession = Depends(get_db)):
    now = utcnow()
    accepted = 0
    for e in body.events:
        if e.type not in CLIENT_EVENT_TYPES:
            continue
        ts = e.ts if e.ts is not None else now
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts > now + timedelta(minutes=1) or ts < now - timedelta(days=1):
            ts = now                          # 客户端时间明显不对时用服务器时间
        attempt_id = e.attempt_id
        if attempt_id is not None:
            owned = db.get(Attempt, attempt_id)
            if owned is None or owned.user_id != user.id:
                attempt_id = None
        problem_id = e.problem_id if e.problem_id and db.get(Problem, e.problem_id) else None
        log_event(db, user, e.type, problem_id=problem_id, attempt_id=attempt_id, payload=e.payload, ts=ts)
        accepted += 1
    db.commit()
    return {"accepted": accepted}
