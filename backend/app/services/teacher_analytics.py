"""教师端统计（docs/pages.md T1–T5，指标定义见 docs/learner-model.md）。

先把一个班的数据一次性读进 ClassData，再用纯函数计算各页面的数字；
公式与学生端共用 learner_model 里的函数。口径（与 docs/learner-model.md 第 11 节一致）：
- “本周”“上周”按北京时间自然周（周一 0 点起）
- 作业完成率：已开放作业里（学生, 题目）对中，到该时刻已有仿真通过的比例
- 全班预测准确率：该周带预测尝试的 A_pred 平均值
- 全班 F 值：所有学生、所有知识点上（最近 5 次带预测尝试）分子之和 / 分母之和
- 平均提示等级：该周首次通过的（学生, 题目）对上，通过前用过的最高提示等级的平均值
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import utcnow
from ..models import (Assignment, Attempt, Enrollment, Event, Hint, Investigation, KnowledgePoint, Prediction,
                      Problem, Progress, ShuffleRun, TbSubmission, User)
from . import fallback_hints
from .learner_model import (MISCONCEPTION_LABELS, QUADRANTS, TAG_LABELS, AttemptView, LookEvent, Submission,
                            calibration_bias, class_f_value, f_counts, f_value, is_look_event, mastery_level,
                            overconfidence_rate, prediction_ok, r_values, with_confidence)

BEIJING = timezone(timedelta(hours=8))
CORE_KPS = ("blocking", "sequential", "fsm", "parallel")
LOOK_TYPES = ("waveform.view", "waveform.cell_click", "investigate.locate_step", "investigate.locate_line")


def week_start(t: datetime) -> datetime:
    local = t.astimezone(BEIJING)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


@dataclass
class Student:
    user_id: int
    alias: str
    name: str
    login: str
    group: str
    consent: str
    anon_id: str


@dataclass
class ClassData:
    class_id: int
    students: list[Student]
    problems: dict[str, Problem]
    kps: list[KnowledgePoint]
    attempts: list[Attempt]                      # 已判完的尝试（按时间）
    hints: list[tuple[Hint, Attempt]]
    looks: list[Event]                           # 查看仿真结果类事件
    last_event: dict[int, datetime]              # 每个学生最近一次事件
    active: dict[int, list[datetime]]            # 每个学生的事件时间（只取近 9 周）
    assignments: list[Assignment]
    tbs: list[TbSubmission]
    shuffles: list[tuple[ShuffleRun, Attempt]]
    progress: list[Progress]
    investigations: list[tuple[Investigation, Attempt]]
    first_open: dict[tuple[int, str], datetime]
    predictions: list[Prediction] = field(default_factory=list)

    def by_id(self) -> dict[int, Student]:
        return {s.user_id: s for s in self.students}

    def answer_reveals(self) -> dict[tuple[int, str], datetime]:
        """每个学生每道题第一次看参考答案（4 级提示）的时间。"""
        out: dict[tuple[int, str], datetime] = {}
        for h, a in self.hints:
            if h.level == 4 and ((a.user_id, a.problem_id) not in out or h.created_at < out[(a.user_id, a.problem_id)]):
                out[(a.user_id, a.problem_id)] = h.created_at
        return out

    def in_group(self, group: str | None) -> set[int]:
        return {s.user_id for s in self.students if not group or group == "all" or s.group == group}


def load(db: DbSession, class_id: int, now: datetime | None = None) -> ClassData:
    now = now or utcnow()
    rows = db.execute(select(Enrollment, User).join(User, User.id == Enrollment.user_id)
                      .where(Enrollment.class_id == class_id).order_by(Enrollment.id)).all()
    students = [Student(user_id=u.id, alias=f"S{i:02d}", name=u.display_name, login=u.login_name, group=e.group,
                        consent=e.consent_status, anon_id=u.anon_id or "")
                for i, (e, u) in enumerate(rows, start=1)]
    ids = [s.user_id for s in students] or [-1]
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id.in_(ids), Attempt.status == "done")
                               .order_by(Attempt.created_at, Attempt.id)).all())
    hints = list(db.execute(select(Hint, Attempt).join(Attempt, Attempt.id == Hint.attempt_id)
                            .where(Attempt.user_id.in_(ids)).order_by(Hint.created_at)).all())
    looks = list(db.scalars(select(Event).where(Event.user_id.in_(ids), Event.type.in_(LOOK_TYPES))).all())
    since = week_start(now) - timedelta(weeks=9)
    active: dict[int, list[datetime]] = defaultdict(list)
    for uid, ts in db.execute(select(Event.user_id, Event.ts).where(Event.user_id.in_(ids), Event.ts >= since)).all():
        active[uid].append(ts)
    last_event = {}
    for uid, ts in db.execute(select(Event.user_id, Event.ts).where(Event.user_id.in_(ids))).all():
        if uid not in last_event or ts > last_event[uid]:
            last_event[uid] = ts
    first_open: dict[tuple[int, str], datetime] = {}
    for uid, pid, ts in db.execute(select(Event.user_id, Event.problem_id, Event.ts).where(
            Event.user_id.in_(ids), Event.type.in_(("problem.open", "code.submit")), Event.problem_id.is_not(None))).all():
        key = (uid, pid)
        if key not in first_open or ts < first_open[key]:
            first_open[key] = ts
    return ClassData(
        class_id=class_id, students=students,
        problems={p.id: p for p in db.scalars(select(Problem)).all()},
        kps=list(db.scalars(select(KnowledgePoint).order_by(KnowledgePoint.sort_order)).all()),
        attempts=attempts, hints=hints, looks=looks, last_event=last_event, active=active,
        assignments=list(db.scalars(select(Assignment).where(Assignment.class_id == class_id)
                                    .order_by(Assignment.due_at)).all()),
        tbs=list(db.scalars(select(TbSubmission).where(TbSubmission.user_id.in_(ids), TbSubmission.status == "done")
                            .order_by(TbSubmission.created_at)).all()),
        shuffles=list(db.execute(select(ShuffleRun, Attempt).join(Attempt, Attempt.id == ShuffleRun.attempt_id)
                                 .where(Attempt.user_id.in_(ids), ShuffleRun.status == "done")).all()),
        progress=list(db.scalars(select(Progress).where(Progress.user_id.in_(ids))).all()),
        investigations=list(db.execute(select(Investigation, Attempt).join(Attempt, Attempt.id == Investigation.attempt_id)
                                       .where(Attempt.user_id.in_(ids))).all()),
        first_open=first_open,
    )


# ---------------------------------------------------------------- 基础

def views(cd: ClassData, *, users: set[int] | None = None, kp: str | None = None, problem: str | None = None,
          before: datetime | None = None, after: datetime | None = None) -> dict[int, list[AttemptView]]:
    theta = get_settings().pred_threshold
    revealed = cd.answer_reveals()
    out: dict[int, list[AttemptView]] = defaultdict(list)
    for a in cd.attempts:
        if a.quadrant not in QUADRANTS:
            continue
        if (a.user_id, a.problem_id) in revealed and a.created_at > revealed[(a.user_id, a.problem_id)]:
            continue                 # 看过参考答案之后的尝试不计入掌握度（services/answer.py）
        if users is not None and a.user_id not in users:
            continue
        if problem and a.problem_id != problem:
            continue
        if kp and kp not in cd.problems[a.problem_id].knowledge_points:
            continue
        if before and a.created_at >= before:
            continue
        if after and a.created_at < after:
            continue
        out[a.user_id].append(AttemptView(a.created_at, bool(a.sim_ok),
                                          bool(prediction_ok(a.pred_accuracy, theta)), a.quadrant, a.problem_id,
                                          pred_accuracy=a.pred_accuracy, confidence=a.confidence))
    return out


def class_f(cd: ClassData, users: set[int], before: datetime | None = None) -> float | None:
    n = get_settings().f_window
    lists = []
    for kp in cd.kps:
        per_user = views(cd, users=users, kp=kp.code, before=before)
        lists.extend(per_user.values())
    return class_f_value(lists, n)


def first_passes(cd: ClassData, users: set[int]) -> dict[tuple[int, str], datetime]:
    out: dict[tuple[int, str], datetime] = {}
    for a in cd.attempts:
        if a.user_id in users and a.sim_ok and (a.user_id, a.problem_id) not in out:
            out[(a.user_id, a.problem_id)] = a.created_at
    return out


def hint_level_before(cd: ClassData, uid: int, pid: str, t: datetime) -> int:
    return max((h.level for h, a in cd.hints if a.user_id == uid and a.problem_id == pid and h.created_at < t), default=0)


def avg_hint_level(cd: ClassData, users: set[int], start: datetime | None = None,
                   end: datetime | None = None, problem: str | None = None) -> float | None:
    levels = [hint_level_before(cd, uid, pid, t) for (uid, pid), t in first_passes(cd, users).items()
              if (start is None or t >= start) and (end is None or t < end) and (problem is None or pid == problem)]
    return mean([float(x) for x in levels])


def completion_rate(cd: ClassData, users: set[int], at: datetime) -> float | None:
    by_id = cd.by_id()
    passed = {k for k, t in first_passes(cd, users).items() if t < at}
    total = done = 0
    for asg in cd.assignments:
        if asg.open_at > at:
            continue
        scope = [u for u in users if asg.group_scope in ("all", by_id[u].group)]
        for uid in scope:
            for pid in asg.problem_ids:
                total += 1
                done += (uid, pid) in passed
    return done / total if total else None


def pred_accuracy(cd: ClassData, users: set[int], start: datetime, end: datetime) -> float | None:
    return mean([a.pred_accuracy for a in cd.attempts if a.user_id in users and a.pred_accuracy is not None
                 and start <= a.created_at < end])


def active_count(cd: ClassData, users: set[int], start: datetime, end: datetime) -> int:
    return sum(1 for uid in users if any(start <= t < end for t in cd.active.get(uid, [])))


def misconception_codes(a: Attempt) -> list[str]:
    codes = [t for t in (a.judge or {}).get("tags", []) if t in TAG_LABELS]
    return codes + [m for m in (a.analysis or {}).get("misconceptions", []) if m in MISCONCEPTION_LABELS]


def resubmission_flags(subs: list[Submission], looks: list[LookEvent]) -> list[tuple[datetime, bool]]:
    """每一次重复提交（同一题的第 2 次及以后）按时间排列，标出是不是盲改。"""
    by_problem: dict[str, list[datetime]] = defaultdict(list)
    for x in sorted(subs, key=lambda x: x.ts):
        by_problem[x.problem_id].append(x.ts)
    look_ts: dict[str, list[datetime]] = defaultdict(list)
    for e in looks:
        if is_look_event(e.type):
            look_ts[e.problem_id].append(e.ts)
    flags = []
    for pid, times in by_problem.items():
        for prev, cur in zip(times, times[1:]):
            flags.append((cur, not any(prev < t < cur for t in look_ts.get(pid, []))))
    return sorted(flags)


def blind(cd: ClassData, users: set[int], problem: str | None = None, last_n: int | None = None):
    """盲改率 B（docs/learner-model.md 4.3）。last_n：每个学生只取最近 n 次重复提交。返回 (B, 盲改数, 重复提交数)。"""
    subs_by_user: dict[int, list[Submission]] = defaultdict(list)
    for a in cd.attempts:
        if a.user_id in users and (problem is None or a.problem_id == problem):
            subs_by_user[a.user_id].append(Submission(a.problem_id, a.created_at))
    looks = defaultdict(list)
    for e in cd.looks:
        if e.problem_id:
            looks[e.user_id].append(LookEvent(e.problem_id, e.ts, e.type))
    total_blind = total_resub = 0
    for uid, subs in subs_by_user.items():
        flags = resubmission_flags(subs, looks.get(uid, []))
        if last_n:
            flags = flags[-last_n:]
        total_blind += sum(1 for _, b in flags if b)
        total_resub += len(flags)
    return (total_blind / total_resub if total_resub else None), total_blind, total_resub


# ---------------------------------------------------------------- T1 班级概览

def overconfidence(cd: ClassData, uid: int) -> tuple[float | None, int]:
    """过度自信率 O 和其分母（最近 n 次带把握程度的尝试里选“很有把握”的次数），第 4.7 节。"""
    vs = views(cd, users={uid}).get(uid, [])
    n = get_settings().confidence_window
    sure = [v for v in with_confidence(vs, n) if v.confidence == 3]
    return overconfidence_rate(vs, n), len(sure)


def calibration(cd: ClassData, uid: int) -> float | None:
    return calibration_bias(views(cd, users={uid}).get(uid, []), get_settings().confidence_window)


def alerts(cd: ClassData, users: set[int], now: datetime) -> list[dict]:
    """需要关注的学生（docs/learner-model.md 第 6 节，满足任一条即列入）。"""
    names = {k.code: k.name for k in cd.kps}
    out = []
    n = get_settings().f_window
    for s in cd.students:
        if s.user_id not in users:
            continue
        reasons = []
        high_f = [kp for kp in CORE_KPS
                  if (f := f_value(views(cd, users={s.user_id}, kp=kp).get(s.user_id, []), n)) is not None and f >= 0.5]
        if len(high_f) >= 2:
            reasons.append({"rule": 1, "text": f"{'、'.join(names.get(k, k) for k in high_f)} {len(high_f)} 个核心知识点 F ≥ 0.5"})
        for kp in cd.kps:
            seq = views(cd, users={s.user_id}, kp=kp.code).get(s.user_id, [])
            if len(seq) >= 3 and all(v.quadrant == "concept_gap" for v in seq[-3:]):
                reasons.append({"rule": 2, "text": f"{kp.name}连续 3 次“概念未通”"})
                break
        last = cd.last_event.get(s.user_id)
        if last is None or last < now - timedelta(days=7):
            reasons.append({"rule": 3, "text": "7 天没有任何操作"})
        b, nb, nr = blind(cd, {s.user_id}, last_n=10)
        if b is not None and b >= 0.7:
            reasons.append({"rule": 4, "text": f"近 {nr} 次重复提交，盲改率 {b:.0%}"})
        o, k = overconfidence(cd, s.user_id)
        if o is not None and k >= 3 and o >= 0.5:
            reasons.append({"rule": 5, "text": f"“很有把握”的 {k} 次预测里 {o:.0%} 没对上（过度自信）"})
        if reasons:
            out.append({"user_id": s.user_id, "alias": s.alias, "name": s.name, "group": s.group, "reasons": reasons})
    return out


def misconception_counts(cd: ClassData, users: set[int], start: datetime | None = None,
                         end: datetime | None = None) -> list[dict]:
    students: dict[str, set[int]] = defaultdict(set)
    times: dict[str, int] = defaultdict(int)
    problems: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in cd.attempts:
        if a.user_id not in users or (start and a.created_at < start) or (end and a.created_at >= end):
            continue
        for code in set(misconception_codes(a)):
            students[code].add(a.user_id)
            times[code] += 1
            problems[code][a.problem_id] += 1
    rows = [{"code": c, "label": TAG_LABELS.get(c) or MISCONCEPTION_LABELS[c],
             "source": "judge" if c in TAG_LABELS else "prediction", "students": len(u), "occurrences": times[c],
             "problems": sorted(problems[c].items(), key=lambda kv: -kv[1])}
            for c, u in students.items()]
    return sorted(rows, key=lambda r: (-r["students"], -r["occurrences"], r["code"]))


def problem_rows(cd: ClassData, users: set[int]) -> list[dict]:
    pids = []
    for asg in cd.assignments:
        pids += [p for p in asg.problem_ids if p not in pids]
    pids += sorted({a.problem_id for a in cd.attempts if a.problem_id not in pids})
    return [problem_metrics(cd, users, pid) for pid in pids if pid in cd.problems]


def problem_metrics(cd: ClassData, users: set[int], pid: str) -> dict:
    n = get_settings().f_window
    attempts = [a for a in cd.attempts if a.problem_id == pid and a.user_id in users]
    tried = {a.user_id for a in attempts}
    fp = {uid: t for (uid, p), t in first_passes(cd, users).items() if p == pid}
    num = den = 0
    for uid, vs in views(cd, users=users, problem=pid).items():
        a, b = f_counts(vs, n)
        num, den = num + a, den + b
    durations = [(t - cd.first_open.get((uid, pid), t)).total_seconds() / 60 for uid, t in fp.items()]
    b, _, _ = blind(cd, users, problem=pid)
    p = cd.problems[pid]
    return {
        "problem_id": pid, "title": p.title, "knowledge_points": p.knowledge_points,
        "attempted": len(tried), "passed": len(fp),
        "pass_rate": len(fp) / len(tried) if tried else None,
        "avg_submissions": len(attempts) / len(tried) if tried else None,
        "f_value": num / den if den else None,
        "blind_rate": b,
        "avg_hint_level": avg_hint_level(cd, users, problem=pid),
        "avg_minutes": mean(durations),
    }


def overview(cd: ClassData, group: str | None, now: datetime) -> dict:
    users = cd.in_group(group)
    ws = week_start(now)
    prev = ws - timedelta(weeks=1)
    kpis = {
        "active": {"value": active_count(cd, users, ws, now), "prev": active_count(cd, users, prev, ws),
                   "total": len(users)},
        "completion": {"value": completion_rate(cd, users, now), "prev": completion_rate(cd, users, ws)},
        "pred_accuracy": {"value": pred_accuracy(cd, users, ws, now), "prev": pred_accuracy(cd, users, prev, ws)},
        "class_f": {"value": class_f(cd, users), "prev": class_f(cd, users, before=ws)},
        "avg_hint": {"value": avg_hint_level(cd, users, ws, now), "prev": avg_hint_level(cd, users, prev, ws)},
    }
    trend = []
    for k in range(7, -1, -1):
        start = ws - timedelta(weeks=k)
        end = min(start + timedelta(weeks=1), now)
        trend.append({"week": start.astimezone(BEIJING).date().isoformat(),
                      "pred_accuracy": pred_accuracy(cd, users, start, end),
                      "class_f": class_f(cd, users, before=end)})
    groups = defaultdict(int)
    for s in cd.students:
        groups[s.group] += 1
    return {"kpis": kpis, "trend": trend, "misconceptions": misconception_counts(cd, users)[:5],
            "alerts": alerts(cd, users, now), "problems": problem_rows(cd, users), "groups": dict(groups)}


# ---------------------------------------------------------------- T2 热力图

def heatmap(cd: ClassData, group: str | None, start: datetime | None, end: datetime | None) -> dict:
    users = cd.in_group(group)
    m = get_settings().mastery_window
    n = get_settings().f_window
    rows = []
    for s in cd.students:
        if s.user_id not in users:
            continue
        cells = {}
        for kp in cd.kps:
            vs = views(cd, users={s.user_id}, kp=kp.code, after=start, before=end).get(s.user_id, [])
            r_code, r_pred = r_values(vs, m)
            cells[kp.code] = {"level": mastery_level(vs, m), "attempts": len(vs), "f_value": f_value(vs, n),
                              "r_code": r_code, "r_pred": r_pred}
        rows.append({"user_id": s.user_id, "alias": s.alias, "name": s.name, "group": s.group, "cells": cells})
    return {"knowledge_points": [{"code": k.code, "name": k.name} for k in cd.kps], "rows": rows}


# ---------------------------------------------------------------- T3 误区

def snippet(a: Attempt, code: str) -> dict:
    """典型代码片段：围绕规则提示 1 级所指的代码行，上下各 2 行（不含学生信息）。"""
    lines = a.code.splitlines()
    hint = fallback_hints.generate(a.judge or {}, 1, evaluation=(a.analysis or {}).get("evaluation"))
    focus = [x for x in hint["focus"]["lines"] if 1 <= x <= len(lines)]
    if not focus:
        return {"start": 1, "lines": lines[:8], "focus": []}
    lo, hi = max(1, min(focus) - 2), min(len(lines), max(focus) + 2)
    return {"start": lo, "lines": lines[lo - 1:hi], "focus": focus}


def misconception_detail(cd: ClassData, users: set[int], code: str) -> dict:
    by_id = cd.by_id()
    hits = [a for a in cd.attempts if a.user_id in users and code in misconception_codes(a)]
    examples, seen = [], set()
    for a in reversed(hits):
        if a.user_id in seen:
            continue
        seen.add(a.user_id)
        examples.append({"attempt_id": a.id, "problem_id": a.problem_id, "title": cd.problems[a.problem_id].title,
                         "alias": by_id[a.user_id].alias, **snippet(a, code)})
        if len(examples) >= 3:
            break
    students = sorted({a.user_id for a in hits}, key=lambda u: by_id[u].alias)
    per_problem = defaultdict(int)
    for a in hits:
        per_problem[a.problem_id] += 1
    return {"code": code, "label": TAG_LABELS.get(code) or MISCONCEPTION_LABELS.get(code, code),
            "source": "judge" if code in TAG_LABELS else "prediction",
            "students": [{"user_id": u, "alias": by_id[u].alias, "name": by_id[u].name} for u in students],
            "occurrences": len(hits), "examples": examples,
            "problems": [{"problem_id": p, "title": cd.problems[p].title, "count": c}
                         for p, c in sorted(per_problem.items(), key=lambda kv: -kv[1])]}


# ---------------------------------------------------------------- T4 题目分析

def problem_analytics(cd: ClassData, group: str | None, pid: str) -> dict:
    users = cd.in_group(group)
    metrics = problem_metrics(cd, users, pid)
    prog = {p.user_id: p for p in cd.progress if p.problem_id == pid and p.user_id in users}
    attempts = [a for a in cd.attempts if a.problem_id == pid and a.user_id in users]
    tb_users = {t.user_id for t in cd.tbs if t.problem_id == pid and t.user_id in users}
    inv_users = {a.user_id for _, a in cd.investigations if a.problem_id == pid and a.user_id in users}
    funnel = {
        "predict": len({u for u, p in prog.items() if (p.state or {}).get("predicted")} | {a.user_id for a in attempts}),
        "run": len({a.user_id for a in attempts}),
        "investigate": len(inv_users | {u for u, p in prog.items() if (p.state or {}).get("investigated")}),
        "modify": len({a.user_id for a in attempts if a.step == "modify"}),
        "make": len(tb_users),
    }
    cells = defaultdict(int)
    for a in attempts:
        mm = ((a.judge or {}).get("sim") or {}).get("first_mismatch")
        if mm:
            cells[(mm["step"], mm["signal"])] += 1
    top_cells = [{"step": s, "signal": sig, "count": c}
                 for (s, sig), c in sorted(cells.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
    # 各提示等级之后下一次提交的通过率（按提示词版本）
    after: dict[tuple[int, str], list[bool]] = defaultdict(list)
    for h, a in cd.hints:
        if a.problem_id != pid or a.user_id not in users:
            continue
        nxt = next((x for x in attempts if x.user_id == a.user_id and x.created_at > h.created_at), None)
        if nxt is not None:
            version = (h.content or {}).get("prompt_version") or "fallback_v1"
            after[(h.level, version)].append(bool(nxt.sim_ok))
    hint_rows = [{"level": lv, "prompt_version": v, "n": len(xs), "next_pass_rate": sum(xs) / len(xs)}
                 for (lv, v), xs in sorted(after.items())]
    p = cd.problems[pid]
    return {**metrics, "primm_type": p.primm_type, "steps": ["predict", "run", "investigate"] +
            (["modify"] if p.primm_type == "modify" else []) + (["make"] if p.primm_type == "make" else []),
            "funnel": funnel, "top_mismatch_cells": top_cells, "after_hint": hint_rows}


# ---------------------------------------------------------------- T5 学生详情

def student_detail(cd: ClassData, uid: int) -> dict:
    s = cd.by_id()[uid]
    n = get_settings().f_window
    m = get_settings().mastery_window
    timeline = []
    for a in reversed([a for a in cd.attempts if a.user_id == uid]):
        timeline.append({"attempt_id": a.id, "problem_id": a.problem_id, "title": cd.problems[a.problem_id].title,
                         "attempt_no": a.attempt_no, "step": a.step, "created_at": a.created_at,
                         "quadrant": a.quadrant, "sim_ok": a.sim_ok, "pred_accuracy": a.pred_accuracy,
                         "tags": (a.judge or {}).get("tags", []),
                         "misconceptions": (a.analysis or {}).get("misconceptions", []),
                         "max_hint_level": max((h.level for h, x in cd.hints if x.id == a.id), default=0),
                         "confidence": a.confidence, "confident_miss": bool((a.analysis or {}).get("confident_miss"))})
    kps = []
    for kp in cd.kps:
        vs = views(cd, users={uid}, kp=kp.code).get(uid, [])
        kps.append({"code": kp.code, "name": kp.name, "level": mastery_level(vs, m), "f_value": f_value(vs, n),
                    "attempts": len(vs)})
    b, nb, nr = blind(cd, {uid})
    latest_tb = {}
    for t in cd.tbs:
        if t.user_id == uid:
            latest_tb[t.problem_id] = t
    return {
        "user_id": uid, "alias": s.alias, "name": s.name, "group": s.group, "consent": s.consent,
        "timeline": timeline, "knowledge_points": kps,
        "blind_rate": b, "resubmissions": nr, "hint_dependence": avg_hint_level(cd, {uid}),
        "overconfidence": overconfidence(cd, uid)[0], "calibration_bias": calibration(cd, uid),
        "tb": [{"problem_id": p, "title": cd.problems[p].title, "score": t.score} for p, t in latest_tb.items()],
        "shuffle": [{"attempt_id": a.id, "problem_id": a.problem_id, "order_sensitive": (r.result or {}).get("order_sensitive"),
                     "prediction": r.prediction} for r, a in cd.shuffles if a.user_id == uid],
    }
