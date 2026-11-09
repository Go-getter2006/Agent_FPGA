"""实验分组与功能开关（docs/learner-model.md 第 8 节）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import FeatureFlags, User
from .events import primary_enrollment

FLAG_NAMES = ("predict_step", "llm_hints", "chat", "shuffle", "tb_scoring", "review")
DEFAULT_FLAGS = {
    "treatment": {name: True for name in FLAG_NAMES},
    "control": {"predict_step": False, "llm_hints": False, "chat": False,
                "shuffle": True, "tb_scoring": True, "review": True},
    "none": {name: True for name in FLAG_NAMES},
}


def flags_for(db: DbSession, class_id: int | None, group: str | None) -> dict:
    group = group or "none"
    flags = dict(DEFAULT_FLAGS.get(group, DEFAULT_FLAGS["none"]))
    if class_id is not None:
        row = db.scalar(select(FeatureFlags).where(FeatureFlags.class_id == class_id, FeatureFlags.group == group))
        if row is not None:
            flags.update({k: bool(v) for k, v in (row.flags or {}).items() if k in FLAG_NAMES})
    return flags


def flags_for_user(db: DbSession, user: User) -> dict:
    enrollment = primary_enrollment(db, user.id)
    if enrollment is None:
        return dict(DEFAULT_FLAGS["none"])
    return flags_for(db, enrollment.class_id, enrollment.group)
