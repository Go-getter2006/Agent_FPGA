"""事件日志（docs/learner-model.md 第 7 节）。每个关键操作写一条，只追加。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import APP_VERSION
from ..db import utcnow
from ..models import Enrollment, Event, User

# 前端可以批量上报的界面事件；其余事件只由后端在对应操作里写
CLIENT_EVENT_TYPES = frozenset({
    "page.view", "step.enter", "problem.open", "waveform.view", "waveform.cell_click",
    # 新手入门（第 2 版）：打开一节课、答课内小测、看完做题页分步引导
    "lesson.open", "lesson.quiz", "tour.done",
})


def primary_enrollment(db: DbSession, user_id: int) -> Enrollment | None:
    return db.scalar(select(Enrollment).where(Enrollment.user_id == user_id).order_by(Enrollment.id))


def log_event(db: DbSession, user: User | None, type_: str, *, problem_id: str | None = None,
              attempt_id: int | None = None, payload: dict | None = None,
              ts: datetime | None = None, class_id: int | None = None) -> Event:
    enrollment = primary_enrollment(db, user.id) if user is not None else None
    ev = Event(
        ts=ts or utcnow(),
        anon_id=user.anon_id if user is not None else None,
        user_id=user.id if user is not None else None,
        class_id=class_id if class_id is not None else (enrollment.class_id if enrollment else None),
        group=enrollment.group if enrollment else None,
        type=type_,
        problem_id=problem_id,
        attempt_id=attempt_id,
        payload=payload or {},
        app_version=APP_VERSION,
    )
    db.add(ev)
    return ev
