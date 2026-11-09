"""教师端接口：/api/teacher/*（docs/data-api.md 3.3 节）。教师只能访问自己的班级；admin 可以访问全部。

匿名显示：除班级管理（名单）外，接口默认只返回 S01、S02 这样的代号；
带 anonymous=false 时才返回真实姓名。教师在界面上关闭匿名时调用 POST .../anonymity 写一条事件。
"""
from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db, utcnow
from ..models import (AnalysisLabel, Assignment, Attempt, ChatMessage, ChatSession, Class, Enrollment,
                      FeatureFlags, Hint, Job, Prediction, Problem, TeacherNote, User)
from ..services import jobs, teacher_analytics as ta
from ..services.consent import current_consent
from ..services.events import log_event
from ..services.flags import DEFAULT_FLAGS, FLAG_NAMES
from ..services.icap import ICAP_VERSION, LABELS, cohen_kappa, ensure_sample, target_text
from ..services.llm import get_llm, spent_today
from ..services.security import anon_id_for, hash_password
from .deps import ApiError, current_user, not_found

router = APIRouter(prefix="/teacher", tags=["teacher"])
GROUPS = ("treatment", "control", "none")


def teacher_user(user: User = Depends(current_user)) -> User:
    if user.role not in ("teacher", "admin"):
        raise ApiError(403, "FORBIDDEN", "只有教师可以访问")
    return user


def own_class(db: DbSession, user: User, cid: int) -> Class:
    cls = db.get(Class, cid)
    if cls is None:
        raise not_found("班级")
    if user.role != "admin" and cls.teacher_id != user.id:
        raise ApiError(403, "FORBIDDEN", "不能访问其他教师的班级")
    return cls


def own_student(db: DbSession, user: User, uid: int) -> tuple[User, Enrollment]:
    student = db.get(User, uid)
    if student is None or student.role != "student":
        raise not_found("学生")
    q = select(Enrollment).join(Class, Class.id == Enrollment.class_id).where(Enrollment.user_id == uid)
    if user.role != "admin":
        q = q.where(Class.teacher_id == user.id)
    enrollment = db.scalar(q.order_by(Enrollment.id))
    if enrollment is None:
        raise ApiError(403, "FORBIDDEN", "不能访问其他班级的学生")
    return student, enrollment


def _parse_time(v: str | None) -> datetime | None:
    if not v:
        return None
    t = datetime.fromisoformat(v)
    return t if t.tzinfo else t.replace(tzinfo=timezone(ta.timedelta(hours=8)))


def _mask(rows, anonymous: bool):
    """匿名时去掉学生的真实姓名：只处理带 alias（S01 这类代号）的学生记录，知识点、题目等的 name 不动。"""
    if isinstance(rows, list):
        return [_mask(r, anonymous) for r in rows]
    if isinstance(rows, dict):
        student = "alias" in rows
        return {k: (None if anonymous and student and k == "name" else _mask(v, anonymous)) for k, v in rows.items()}
    return rows


# ---------------------------------------------------------------- 班级、状态

@router.get("/classes")
def classes(user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    q = select(Class).order_by(Class.id)
    if user.role != "admin":
        q = q.where(Class.teacher_id == user.id)
    out = []
    for c in db.scalars(q).all():
        groups = dict(db.execute(select(Enrollment.group, func.count()).where(Enrollment.class_id == c.id)
                                 .group_by(Enrollment.group)).all())
        out.append({"id": c.id, "name": c.name, "term": c.term, "students": sum(groups.values()), "groups": groups})
    return {"classes": out}


@router.get("/status")
def status(user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    llm = get_llm()
    reason = llm.unavailable_reason(db)
    return {"llm": {"available": reason is None, "reason": reason, "spent_today_cny": round(spent_today(db), 4),
                    "daily_budget_cny": llm.settings.llm_daily_budget_cny, "budget_exceeded": reason == "budget"}}


class AnonymityIn(BaseModel):
    anonymous: bool


@router.post("/classes/{cid}/anonymity")
def set_anonymity(cid: int, body: AnonymityIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    log_event(db, user, "teacher.anonymity", class_id=cid, payload={"anonymous": body.anonymous})
    db.commit()
    return {"anonymous": body.anonymous}


# ---------------------------------------------------------------- T1–T4

@router.get("/classes/{cid}/overview")
def overview(cid: int, group: str | None = None, anonymous: bool = True, user: User = Depends(teacher_user),
             db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    now = utcnow()
    data = ta.overview(ta.load(db, cid, now), group, now)
    return _mask(data, anonymous)


@router.get("/classes/{cid}/heatmap")
def heatmap(cid: int, group: str | None = None, start: str | None = None, end: str | None = None,
            anonymous: bool = True, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    return _mask(ta.heatmap(ta.load(db, cid), group, _parse_time(start), _parse_time(end)), anonymous)


@router.get("/classes/{cid}/heatmap/cell")
def heatmap_cell(cid: int, user_id: int, kp: str, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    cd = ta.load(db, cid)
    if user_id not in cd.by_id():
        raise ApiError(403, "FORBIDDEN", "这名学生不在该班级")
    rows = [a for a in cd.attempts if a.user_id == user_id and kp in cd.problems[a.problem_id].knowledge_points]
    return {"attempts": [{"attempt_id": a.id, "problem_id": a.problem_id, "title": cd.problems[a.problem_id].title,
                          "created_at": a.created_at, "quadrant": a.quadrant, "sim_ok": a.sim_ok,
                          "pred_accuracy": a.pred_accuracy, "tags": (a.judge or {}).get("tags", [])}
                         for a in reversed(rows[-10:])]}


@router.get("/classes/{cid}/misconceptions")
def misconceptions(cid: int, group: str | None = None, user: User = Depends(teacher_user),
                   db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    cd = ta.load(db, cid)
    return {"items": ta.misconception_counts(cd, cd.in_group(group))}


@router.get("/classes/{cid}/misconceptions/{code}")
def misconception_detail(cid: int, code: str, group: str | None = None, anonymous: bool = True,
                         user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    cd = ta.load(db, cid)
    return _mask(ta.misconception_detail(cd, cd.in_group(group), code), anonymous)


@router.get("/classes/{cid}/problems/{pid}/analytics")
def problem_analytics(cid: int, pid: str, group: str | None = None, user: User = Depends(teacher_user),
                      db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    if db.get(Problem, pid) is None:
        raise not_found("题目")
    return ta.problem_analytics(ta.load(db, cid), group, pid)


# ---------------------------------------------------------------- T5 学生详情

@router.get("/students/{uid}")
def student_detail(uid: int, anonymous: bool = True, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    student, enrollment = own_student(db, user, uid)
    cd = ta.load(db, enrollment.class_id)
    detail = ta.student_detail(cd, uid)
    notes = db.scalars(select(TeacherNote).where(TeacherNote.student_id == uid).order_by(TeacherNote.id.desc())).all()
    labels = []
    for row in db.scalars(select(AnalysisLabel).where(AnalysisLabel.class_id == enrollment.class_id,
                                                     AnalysisLabel.prompt_version == ICAP_VERSION)).all():
        info = target_text(db, row)
        if row.target_type == "explanation":
            owner = db.scalar(select(Attempt.user_id).where(Attempt.id == _explanation_attempt(db, row.target_id)))
        else:
            owner = db.scalar(select(ChatSession.user_id).join(ChatMessage, ChatMessage.session_id == ChatSession.id)
                              .where(ChatMessage.id == row.target_id))
        if owner == uid:
            labels.append({"id": row.id, "label": row.label, "rationale": row.rationale, "human_label": row.human_label,
                           **info, "note": "AI 编码" + ("，已人工抽检" if row.human_label else "，待人工抽检")})
    detail.update({"class_id": enrollment.class_id, "class_group": enrollment.group, "icap": labels,
                   "notes": [{"id": n.id, "text": n.text, "created_at": n.created_at} for n in notes]})
    return _mask(detail, anonymous)


def _explanation_attempt(db: DbSession, explanation_id: int) -> int | None:
    from ..models import Explanation
    e = db.get(Explanation, explanation_id)
    return e.attempt_id if e else None


@router.get("/attempts/{aid}")
def attempt_detail(aid: int, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    a = db.get(Attempt, aid)
    if a is None:
        raise not_found("这次提交")
    own_student(db, user, a.user_id)
    p = db.get(Problem, a.problem_id)
    hints = db.scalars(select(Hint).where(Hint.attempt_id == a.id).order_by(Hint.level)).all()
    session = db.scalar(select(ChatSession).where(ChatSession.user_id == a.user_id, ChatSession.problem_id == a.problem_id))
    chat = []
    if session is not None:
        chat = [{"role": m.role, "content": m.content, "flagged": m.flagged, "source": m.source,
                 "created_at": m.created_at}
                for m in db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id)
                                    .order_by(ChatMessage.id)).all()]
    from ..models import Explanation
    explanations = [e.text for e in db.scalars(select(Explanation).where(Explanation.attempt_id == a.id)).all()]
    return {"attempt_id": a.id, "problem_id": a.problem_id, "title": p.title, "code": a.code, "judge": a.judge,
            "expected": p.meta["ref_trace"], "skeleton": p.meta["skeleton"], "predict_points": p.meta["predict_points"],
            "evaluation": (a.analysis or {}).get("evaluation"), "quadrant": a.quadrant,
            "predictions": [{"kind": x.kind, "answers": x.answers}
                            for x in db.scalars(select(Prediction).where(Prediction.attempt_id == a.id)).all()],
            "hints": [{"level": h.level, "source": h.source, **h.content} for h in hints],
            "explanations": explanations, "chat": chat}


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/students/{uid}/notes")
def add_note(uid: int, body: NoteIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_student(db, user, uid)
    note = TeacherNote(teacher_id=user.id, student_id=uid, text=body.text.strip())
    db.add(note)
    db.commit()
    return {"id": note.id, "text": note.text, "created_at": note.created_at}


# ---------------------------------------------------------------- T6 作业与题库

@router.get("/problems")
def problem_bank(user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(Problem).order_by(Problem.id)).all()
    return {"problems": [{"id": p.id, "title": p.title, "knowledge_points": p.knowledge_points,
                          "primm_type": p.primm_type, "difficulty": p.difficulty, "spec": p.meta["spec"],
                          "starter": p.meta.get("starter"), "predict_points": p.meta["predict_points"],
                          "modify_goal": p.meta.get("modify_goal", "")} for p in rows]}


@router.get("/classes/{cid}/assignments")
def list_assignments(cid: int, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    rows = db.scalars(select(Assignment).where(Assignment.class_id == cid).order_by(Assignment.due_at)).all()
    return {"assignments": [{"id": a.id, "title": a.title, "group_scope": a.group_scope, "problem_ids": a.problem_ids,
                             "open_at": a.open_at, "due_at": a.due_at} for a in rows]}


class AssignmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    problem_ids: list[str] = Field(min_length=1)
    group_scope: str = Field(default="all", pattern="^(all|treatment|control)$")
    open_at: datetime
    due_at: datetime


@router.post("/classes/{cid}/assignments")
def create_assignment(cid: int, body: AssignmentIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    unknown = [p for p in body.problem_ids if db.get(Problem, p) is None]
    if unknown:
        raise ApiError(400, "UNKNOWN_PROBLEM", f"题库里没有这些题目：{'、'.join(unknown)}")
    tz = lambda t: t if t.tzinfo else t.replace(tzinfo=timezone(ta.timedelta(hours=8)))  # noqa: E731
    if tz(body.due_at) <= tz(body.open_at):
        raise ApiError(400, "BAD_TIME", "截止时间要晚于开始时间")
    a = Assignment(class_id=cid, title=body.title.strip(), group_scope=body.group_scope,
                   problem_ids=list(dict.fromkeys(body.problem_ids)), open_at=tz(body.open_at), due_at=tz(body.due_at))
    db.add(a)
    log_event(db, user, "teacher.assignment_create", class_id=cid, payload={"title": a.title, "problem_ids": a.problem_ids})
    db.commit()
    return {"id": a.id}


# ---------------------------------------------------------------- T7 实验分组、功能开关、导出、ICAP

@router.get("/classes/{cid}/groups")
def get_groups(cid: int, anonymous: bool = True, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    cd = ta.load(db, cid)
    flags = {}
    for g in GROUPS:
        row = db.scalar(select(FeatureFlags).where(FeatureFlags.class_id == cid, FeatureFlags.group == g))
        flags[g] = {**DEFAULT_FLAGS[g], **(row.flags if row else {})}
    students = [{"user_id": s.user_id, "alias": s.alias, "name": s.name, "login_name": s.login, "group": s.group,
                 "consent": s.consent} for s in cd.students]
    if anonymous:
        students = [{**s, "name": None, "login_name": None} for s in students]
    return {"students": students, "flags": flags, "flag_names": list(FLAG_NAMES)}


class GroupsIn(BaseModel):
    assignments: list[dict] = Field(default_factory=list)      # [{"user_id": 1, "group": "treatment"}]
    csv: str | None = None                                      # “学号,分组” 每行一个
    flags: dict[str, dict[str, bool]] | None = None


@router.put("/classes/{cid}/groups")
def put_groups(cid: int, body: GroupsIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    enrollments = {e.user_id: e for e in db.scalars(select(Enrollment).where(Enrollment.class_id == cid)).all()}
    changes = list(body.assignments)
    if body.csv:
        by_login = {u.login_name: u.id for u in db.scalars(select(User).where(User.id.in_(list(enrollments) or [-1]))).all()}
        for row in csv.reader(io.StringIO(body.csv.strip())):
            if len(row) < 2 or row[0].strip() in ("学号", "login_name"):
                continue
            uid = by_login.get(row[0].strip())
            if uid is None:
                raise ApiError(400, "UNKNOWN_STUDENT", f"名单里没有学号 {row[0].strip()}")
            changes.append({"user_id": uid, "group": row[1].strip()})
    for ch in changes:
        g = ch.get("group")
        if g not in GROUPS:
            raise ApiError(400, "BAD_GROUP", "分组只能是 treatment、control 或 none")
        e = enrollments.get(ch.get("user_id"))
        if e is None:
            raise ApiError(400, "UNKNOWN_STUDENT", "学生不在这个班级")
        e.group = g
    if body.flags:
        for g, values in body.flags.items():
            if g not in GROUPS or any(k not in FLAG_NAMES for k in values):
                raise ApiError(400, "BAD_FLAGS", "功能开关的名字不对")
            row = db.scalar(select(FeatureFlags).where(FeatureFlags.class_id == cid, FeatureFlags.group == g))
            if row is None:
                row = FeatureFlags(class_id=cid, group=g, flags={})
                db.add(row)
            row.flags = {**DEFAULT_FLAGS[g], **(row.flags or {}), **{k: bool(v) for k, v in values.items()}}
    log_event(db, user, "teacher.groups_update", class_id=cid,
              payload={"changed_students": len(changes), "flags": body.flags or {}})
    db.commit()
    return {"ok": True, "changed": len(changes)}


class ExportIn(BaseModel):
    kinds: list[str] = Field(default_factory=lambda: ["events", "attempts", "metrics"])


def _run_job(db: DbSession, job: Job) -> None:
    db.commit()
    from ..config import get_settings
    if get_settings().jobs_inline:
        jobs.run_job_inline(db, job)


@router.post("/classes/{cid}/exports")
def start_export(cid: int, body: ExportIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    kinds = [k for k in body.kinds if k in ("events", "attempts", "metrics")]
    if not kinds:
        raise ApiError(400, "BAD_KINDS", "至少选一种导出内容")
    job = jobs.enqueue(db, "export", {"class_id": cid, "kinds": kinds}, user.id)
    job.payload = {**job.payload, "job_id": job.id}
    log_event(db, user, "teacher.export", class_id=cid, payload={"kinds": kinds, "job_id": job.id})
    _run_job(db, job)
    return {"job_id": job.id}


@router.get("/exports/{job_id}/download")
def download_export(job_id: int, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or job.type != "export" or (job.user_id != user.id and user.role != "admin"):
        raise not_found("导出文件")
    if job.status != "done" or not job.result:
        raise ApiError(409, "NOT_READY", "导出还没完成")
    path = Path(job.result["path"])
    if not path.is_file():
        raise not_found("导出文件")
    return FileResponse(path, media_type="application/zip", filename=f"class{job.payload['class_id']}_export_{job.id}.zip")


class IcapIn(BaseModel):
    start: str | None = None
    end: str | None = None


@router.post("/classes/{cid}/analysis/icap")
def start_icap(cid: int, body: IcapIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    s, e = _parse_time(body.start), _parse_time(body.end)
    job = jobs.enqueue(db, "icap", {"class_id": cid, "from": s.isoformat() if s else None,
                                    "to": e.isoformat() if e else None}, user.id)
    _run_job(db, job)
    return {"job_id": job.id}


@router.get("/classes/{cid}/analysis/icap")
def icap_summary(cid: int, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    rows = db.scalars(select(AnalysisLabel).where(AnalysisLabel.class_id == cid,
                                                  AnalysisLabel.prompt_version == ICAP_VERSION)).all()
    by_label = {k: sum(1 for r in rows if r.label == k) for k in LABELS}
    by_type = {t: {k: sum(1 for r in rows if r.label == k and r.target_type == t) for k in LABELS}
               for t in ("explanation", "chat_message")}
    pairs = [(r.label, r.human_label) for r in rows if r.sampled and r.human_label]
    k = cohen_kappa(pairs)
    last = db.scalar(select(Job).where(Job.type == "icap", Job.payload["class_id"].as_integer() == cid)
                     .order_by(Job.id.desc()))
    return {"total": len(rows), "by_label": by_label, "by_type": by_type, "prompt_version": ICAP_VERSION,
            "sampled": sum(1 for r in rows if r.sampled), "human_labeled": len(pairs), "agreement": k,
            "low_agreement": k["kappa"] is not None and k["kappa"] < 0.6,
            "last_job": {"id": last.id, "status": last.status, "result": last.result, "error": last.error and "编码任务失败"}
            if last else None}


@router.get("/classes/{cid}/analysis/icap/sample")
def icap_sample(cid: int, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    rows = ensure_sample(db, cid)
    # 人工标注时不显示 AI 的标签，避免先入为主
    return {"items": [{"id": r.id, **target_text(db, r), "human_label": r.human_label} for r in rows]}


class SampleLabelsIn(BaseModel):
    labels: list[dict]                   # [{"id": 1, "human_label": "C"}]


@router.put("/classes/{cid}/analysis/icap/sample")
def icap_label(cid: int, body: SampleLabelsIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    for item in body.labels:
        row = db.get(AnalysisLabel, int(item.get("id", 0)))
        if row is None or row.class_id != cid or not row.sampled:
            raise ApiError(400, "NOT_SAMPLED", "只能标注被抽中的条目")
        label = str(item.get("human_label", "")).upper()
        if label not in LABELS:
            raise ApiError(400, "BAD_LABEL", "标签只能是 P、A、C、I")
        row.human_label = label
        row.human_labeler_id = user.id
    db.commit()
    rows = db.scalars(select(AnalysisLabel).where(AnalysisLabel.class_id == cid, AnalysisLabel.sampled.is_(True),
                                                  AnalysisLabel.human_label.is_not(None))).all()
    k = cohen_kappa([(r.label, r.human_label) for r in rows])
    return {**k, "low_agreement": k["kappa"] is not None and k["kappa"] < 0.6,
            "message": "一致性偏低，结论需谨慎" if k["kappa"] is not None and k["kappa"] < 0.6 else None}


# ---------------------------------------------------------------- T8 班级管理（唯一默认显示真实姓名的页面）

@router.get("/classes/{cid}/roster")
def roster(cid: int, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    rows = db.execute(select(Enrollment, User).join(User, User.id == Enrollment.user_id)
                      .where(Enrollment.class_id == cid).order_by(Enrollment.id)).all()
    return {"current_consent_version": current_consent().version,
            "students": [{"user_id": u.id, "alias": f"S{i:02d}", "login_name": u.login_name, "name": u.display_name,
                          "group": e.group, "consent_status": e.consent_status, "consent_version": e.consent_version,
                          "consent_at": e.consent_at} for i, (e, u) in enumerate(rows, start=1)]}


class RosterIn(BaseModel):
    csv: str = Field(min_length=1, max_length=200_000)   # “学号,姓名[,分组]” 每行一个


def _temp_password() -> str:
    return secrets.token_urlsafe(6)


@router.post("/classes/{cid}/roster")
def import_roster(cid: int, body: RosterIn, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    own_class(db, user, cid)
    created = []
    for row in csv.reader(io.StringIO(body.csv.strip())):
        row = [c.strip() for c in row]
        if len(row) < 2 or not row[0] or row[0] in ("学号", "login_name"):
            continue
        login, name = row[0], row[1]
        group = row[2] if len(row) > 2 and row[2] in GROUPS else "none"
        u = db.scalar(select(User).where(User.login_name == login))
        password = None
        if u is None:
            password = _temp_password()
            u = User(login_name=login, display_name=name, role="student", password_hash=hash_password(password))
            db.add(u)
            db.flush()
            u.anon_id = anon_id_for(u.id)
        elif u.role != "student":
            raise ApiError(400, "NOT_STUDENT", f"{login} 不是学生账号")
        if db.scalar(select(Enrollment).where(Enrollment.class_id == cid, Enrollment.user_id == u.id)) is None:
            db.add(Enrollment(class_id=cid, user_id=u.id, group=group, consent_status="pending"))
        created.append({"login_name": login, "name": name, "temp_password": password, "new_account": password is not None})
    log_event(db, user, "teacher.roster_import", class_id=cid, payload={"rows": len(created)})
    db.commit()
    return {"imported": created}


@router.post("/students/{uid}/reset_password")
def reset_password(uid: int, user: User = Depends(teacher_user), db: DbSession = Depends(get_db)):
    student, enrollment = own_student(db, user, uid)
    password = _temp_password()
    student.password_hash = hash_password(password)
    log_event(db, user, "teacher.password_reset", class_id=enrollment.class_id, payload={"student_id": uid})
    db.commit()
    return {"login_name": student.login_name, "temp_password": password}
