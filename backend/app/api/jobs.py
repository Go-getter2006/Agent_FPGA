"""任务状态：/api/jobs/{id}（前端每秒轮询一次）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Job, User
from .deps import current_user, not_found

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or (job.user_id != user.id and user.role != "admin"):
        raise not_found("任务")
    ref = {k: v for k, v in job.payload.items() if k.endswith("_id") and k not in ("problem_id", "job_id")}
    if job.type in ("export", "icap") and job.status == "done":
        ref["result"] = {k: v for k, v in (job.result or {}).items() if k != "path"}   # 不暴露服务器路径
    return {"id": job.id, "type": job.type, "status": job.status, **ref,
            "error": "任务执行失败，请稍后重试" if job.status == "error" else None,
            "created_at": job.created_at, "finished_at": job.finished_at}
