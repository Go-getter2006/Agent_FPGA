"""数据表（docs/data-api.md 第 1 节）。阶段 3 用到的表；对话、大模型调用、ICAP 等在后续阶段加迁移。"""
from __future__ import annotations

import uuid

from sqlalchemy import (JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(16))                      # student / teacher / admin
    login_name: Mapped[str] = mapped_column(String(64), unique=True)   # 学号或工号
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    anon_id: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class Session(Base):
    """登录会话：Cookie 里放随机令牌，库里只存它的哈希。"""
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at = mapped_column(UTCDateTime, default=utcnow)
    expires_at = mapped_column(UTCDateTime)


class Class(Base):
    __tablename__ = "classes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    term: Mapped[str] = mapped_column(String(32))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("class_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group: Mapped[str] = mapped_column(String(16), default="none")     # treatment / control / none
    consent_status: Mapped[str] = mapped_column(String(16), default="pending")   # pending / accepted / declined
    consent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    consent_at = mapped_column(UTCDateTime, nullable=True)


class FeatureFlags(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("class_id", "group"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    group: Mapped[str] = mapped_column(String(16))
    flags: Mapped[dict] = mapped_column(JSON, default=dict)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Problem(Base):
    __tablename__ = "problems"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    knowledge_points: Mapped[list] = mapped_column(JSON, default=list)
    primm_type: Mapped[str] = mapped_column(String(16))
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)     # spec、starter、预测点、波形骨架、参考轨迹等
    synced_at = mapped_column(UTCDateTime, default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    group_scope: Mapped[str] = mapped_column(String(16), default="all")   # all / treatment / control
    problem_ids: Mapped[list] = mapped_column(JSON, default=list)
    open_at = mapped_column(UTCDateTime)
    due_at = mapped_column(UTCDateTime)


class Progress(Base):
    """学生在一道题上的 PRIMM 步骤进度。"""
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "problem_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"))
    step: Mapped[str] = mapped_column(String(16), default="predict")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_user_problem", "user_id", "problem_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"))
    attempt_no: Mapped[int] = mapped_column(Integer)
    step: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at = mapped_column(UTCDateTime, default=utcnow)
    finished_at = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")   # queued / running / done / error
    judge: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sim_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pred_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    quadrant: Mapped[str | None] = mapped_column(String(16), nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # 预测逐格对照、预测误区
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"))
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))          # waveform / hardware
    answers: Mapped[dict] = mapped_column(JSON)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # 判完后每格的对照
    locked_at = mapped_column(UTCDateTime, default=utcnow)


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))          # locate_step / locate_line
    chosen: Mapped[dict] = mapped_column(JSON)
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class Explanation(Base):
    __tablename__ = "explanations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class Hint(Base):
    __tablename__ = "hints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))        # llm / fallback
    content: Mapped[dict] = mapped_column(JSON)
    llm_call_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class ShuffleRun(Base):
    __tablename__ = "shuffle_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    prediction: Mapped[str | None] = mapped_column(String(16), nullable=True)   # 实验前的预测：change / same
    status: Mapped[str] = mapped_column(String(16), default="queued")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class TbSubmission(Base):
    __tablename__ = "tb_submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"))
    code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    knowledge_point: Mapped[str] = mapped_column(String(32))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"))
    box: Mapped[int] = mapped_column(Integer, default=1)
    due_at = mapped_column(UTCDateTime)
    last_result: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")    # active / done
    source_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id"), nullable=True)
    question: Mapped[dict] = mapped_column(JSON, default=dict)   # 代码、预测格；答案只在服务端
    created_at = mapped_column(UTCDateTime, default=utcnow)


class MasterySnapshot(Base):
    __tablename__ = "mastery_snapshots"
    __table_args__ = (Index("ix_mastery_user_kp", "user_id", "knowledge_point"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    knowledge_point: Mapped[str] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(16))
    r_code: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_pred: Mapped[float | None] = mapped_column(Float, nullable=True)
    f_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at = mapped_column(UTCDateTime, default=utcnow)


class Event(Base):
    """事件日志：只追加，不修改、不删除（docs/learner-model.md 第 7 节）。"""
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_class_ts", "class_id", "ts"),
        Index("ix_events_user_ts", "user_id", "ts"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ts = mapped_column(UTCDateTime, default=utcnow)
    anon_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group: Mapped[str | None] = mapped_column(String(16), nullable=True)
    type: Mapped[str] = mapped_column(String(48))
    problem_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    app_version: Mapped[str] = mapped_column(String(16))


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(16))          # judge / shuffle / tb / export / icap
    status: Mapped[str] = mapped_column(String(16), default="queued")   # queued / running / done / error
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(UTCDateTime, default=utcnow)
    started_at = mapped_column(UTCDateTime, nullable=True)
    finished_at = mapped_column(UTCDateTime, nullable=True)


class AppendOnlyError(RuntimeError):
    pass


@event.listens_for(Event, "before_update")
def _no_event_update(mapper, connection, target):
    raise AppendOnlyError("事件日志只能追加，不能修改")


@event.listens_for(Event, "before_delete")
def _no_event_delete(mapper, connection, target):
    raise AppendOnlyError("事件日志只能追加，不能删除")
