"""任务进程：从 jobs 表取任务，在进程池里调用裁判，结果写回数据库。

    python -m backend.worker            # 常驻
    python -m backend.worker --once     # 处理完当前队列就退出（测试、脚本用）

并发数取环境变量 JUDGE_WORKERS（默认 CPU 核数减 1，至少 1）。
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait

from sqlalchemy import update

from backend.app.db import SessionLocal
from backend.app.models import Job
from backend.app.services.job_handlers import apply_result, execute
from backend.app.services.jobs import apply_error, claim

log = logging.getLogger("worker")
_stop = False


def _handle_stop(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def worker_count() -> int:
    env = os.getenv("JUDGE_WORKERS", "").strip()
    if env:
        return max(1, int(env))
    return max(1, (os.cpu_count() or 2) - 1)


def requeue_stale() -> int:
    """worker 异常退出时留下的 running 任务重新排队（只在单 worker 部署时安全）。"""
    with SessionLocal() as db:
        n = db.execute(update(Job).where(Job.status == "running").values(status="queued", started_at=None)).rowcount
        db.commit()
        return n


def _collect(fut: Future, job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        try:
            output = fut.result()
        except Exception:  # noqa: BLE001
            apply_error(db, job, traceback.format_exc())
            return
        try:
            apply_result(db, job, output)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            job = db.get(Job, job_id)
            apply_error(db, job, traceback.format_exc())


def run(once: bool = False, workers: int | None = None) -> None:
    workers = workers or worker_count()
    inflight: dict[Future, int] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        while not _stop:
            free = workers - len(inflight)
            if free > 0:
                with SessionLocal() as db:
                    for job in claim(db, free):
                        log.info("开始任务 %s（%s）", job.id, job.type)
                        inflight[pool.submit(execute, job.type, job.payload)] = job.id
            if not inflight:
                if once:
                    return
                time.sleep(0.3)
                continue
            done, _ = wait(list(inflight), timeout=0.3, return_when=FIRST_COMPLETED)
            for fut in done:
                _collect(fut, inflight.pop(fut))


def main() -> None:
    parser = argparse.ArgumentParser(description="判题任务进程")
    parser.add_argument("--once", action="store_true", help="处理完当前队列就退出")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    n = requeue_stale()
    if n:
        log.info("重新排队 %s 个未完成的任务", n)
    run(once=args.once, workers=args.workers)


if __name__ == "__main__":
    main()
