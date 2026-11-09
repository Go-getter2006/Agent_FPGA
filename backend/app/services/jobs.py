"""任务队列：jobs 表 + worker 进程（docs/data-api.md 第 2 节）。不引入 Redis。

- enqueue：写一行 queued
- claim：worker 用条件更新抢任务（queued → running），多个 worker 不会抢到同一个
- 执行函数是纯函数（只调用裁判，不碰数据库），可以放进进程池；结果写回由 apply 完成
"""
from __future__ import annotations

import traceback
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import utcnow
from ..models import Attempt, Job


class RateLimited(Exception):
    pass


def check_submit_limits(db: DbSession, user_id: int) -> None:
    s = get_settings()
    running = db.scalar(select(func.count()).select_from(Job).where(
        Job.user_id == user_id, Job.type == "judge", Job.status.in_(("queued", "running"))))
    if running:
        raise RateLimited("上一次仿真还在进行中，等它完成再提交")
    since = utcnow() - timedelta(minutes=s.submit_window_minutes)
    recent = db.scalar(select(func.count()).select_from(Attempt).where(
        Attempt.user_id == user_id, Attempt.created_at >= since))
    if recent >= s.submit_limit:
        raise RateLimited("提交太频繁了，稍等一会儿再试")


def enqueue(db: DbSession, type_: str, payload: dict, user_id: int | None) -> Job:
    job = Job(type=type_, payload=payload, user_id=user_id, status="queued")
    db.add(job)
    db.flush()
    return job


def claim(db: DbSession, limit: int = 1) -> list[Job]:
    claimed = []
    candidates = db.scalars(select(Job.id).where(Job.status == "queued").order_by(Job.id).limit(limit * 4)).all()
    for job_id in candidates:
        res = db.execute(update(Job).where(Job.id == job_id, Job.status == "queued")
                         .values(status="running", started_at=utcnow()))
        if res.rowcount == 1:
            db.commit()
            claimed.append(db.get(Job, job_id))
            if len(claimed) >= limit:
                break
        else:
            db.rollback()
    return claimed


def finish(db: DbSession, job: Job, result: dict | None, error: str | None = None) -> None:
    job.status = "error" if error else "done"
    job.result = result
    job.error = error
    job.finished_at = utcnow()
    db.add(job)


def run_job_inline(db: DbSession, job: Job) -> None:
    """测试和 JOBS_INLINE=1 时：在当前进程里立即执行。"""
    from .job_handlers import apply_result, execute
    job.status = "running"
    job.started_at = utcnow()
    db.commit()
    try:
        output = execute(job.type, job.payload)
    except Exception:  # noqa: BLE001  任务失败要记录下来，不能让接口崩溃
        db.rollback()
        apply_error(db, job, traceback.format_exc())
        return
    apply_result(db, job, output)
    db.commit()


def apply_error(db: DbSession, job: Job, error: str) -> None:
    from .job_handlers import apply_failure
    apply_failure(db, job, error)
    finish(db, job, None, error)
    db.commit()
