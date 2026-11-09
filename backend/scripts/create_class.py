"""正式部署时创建第一位教师和班级（学生名单之后在教师端“班级管理”里导入）。

    docker compose exec api python -m backend.scripts.create_class --teacher T001 --name 王老师 --class "数字电路实验 1 班" --term "2026 秋"

教师密码随机生成并打印一次；已有同名教师时只新建班级。
"""
from __future__ import annotations

import argparse
import secrets

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.models import Class, FeatureFlags, User
from backend.app.services.flags import DEFAULT_FLAGS
from backend.app.services.security import hash_password


def main() -> None:
    ap = argparse.ArgumentParser(description="创建教师账号和班级")
    ap.add_argument("--teacher", required=True, help="教师工号")
    ap.add_argument("--name", required=True, help="教师姓名")
    ap.add_argument("--class", dest="class_name", required=True, help="班级名称")
    ap.add_argument("--term", default="", help="学期，如 2026 秋")
    args = ap.parse_args()
    with SessionLocal() as db:
        teacher = db.scalar(select(User).where(User.login_name == args.teacher))
        password = None
        if teacher is None:
            password = secrets.token_urlsafe(9)
            teacher = User(login_name=args.teacher, display_name=args.name, role="teacher",
                           password_hash=hash_password(password))
            db.add(teacher)
            db.flush()
        elif teacher.role not in ("teacher", "admin"):
            raise SystemExit(f"{args.teacher} 已存在，但不是教师账号")
        cls = Class(name=args.class_name, term=args.term, teacher_id=teacher.id)
        db.add(cls)
        db.flush()
        for group, flags in DEFAULT_FLAGS.items():
            db.add(FeatureFlags(class_id=cls.id, group=group, flags=flags))
        db.commit()
        print(f"班级：{cls.name}（id={cls.id}）；教师：{teacher.login_name}")
        if password:
            print(f"教师初始密码（只显示这一次）：{password}")


if __name__ == "__main__":
    main()
