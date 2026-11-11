"""生成本地开发、演示用的数据：1 名教师、1 个班级、若干学生（不自动布置作业）。

    DEMO_PASSWORD=... python -m backend.scripts.seed_demo [--students 5]

密码只从命令行或环境变量 DEMO_PASSWORD 读取；都没有时随机生成并打印。
"""
from __future__ import annotations

import argparse
import os
import secrets

from sqlalchemy import select

from backend.app import models  # noqa: F401
from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Class, Enrollment, FeatureFlags, User
from backend.app.services.flags import DEFAULT_FLAGS
from backend.app.services.problems_sync import sync_all
from backend.app.services.security import anon_id_for, hash_password


def get_or_create_user(db, login: str, name: str, role: str, password: str) -> User:
    user = db.scalar(select(User).where(User.login_name == login))
    if user is None:
        user = User(login_name=login, display_name=name, role=role, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        user.anon_id = anon_id_for(user.id) if role == "student" else None
    return user


def seed(password: str, n_students: int = 5, create_tables: bool = True) -> dict:
    if create_tables:
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_all(db)
        teacher = get_or_create_user(db, "T001", "王老师", "teacher", password)
        cls = db.scalar(select(Class).where(Class.name == "示例班级 A"))
        if cls is None:
            cls = Class(name="示例班级 A", term="2026 秋", teacher_id=teacher.id)
            db.add(cls)
            db.flush()
            for group, flags in DEFAULT_FLAGS.items():
                db.add(FeatureFlags(class_id=cls.id, group=group, flags=flags))
        logins = []
        surnames = "李张刘陈杨赵黄周吴徐孙胡朱高林何郭马罗梁"
        for i in range(1, n_students + 1):
            login = f"S2026{i:03d}"
            user = get_or_create_user(db, login, f"{surnames[(i - 1) % len(surnames)]}同学", "student", password)
            if db.scalar(select(Enrollment).where(Enrollment.class_id == cls.id, Enrollment.user_id == user.id)) is None:
                db.add(Enrollment(class_id=cls.id, user_id=user.id, group="treatment", consent_status="pending"))
            logins.append(login)
        # 不自动布置作业：学生按题目列表的顺序（入门题在前）自己练；需要的话由教师在“作业与题库”里布置
        db.commit()
        return {"teacher": "T001", "students": logins, "class_id": cls.id}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=5)
    parser.add_argument("--password", default=os.getenv("DEMO_PASSWORD"))
    args = parser.parse_args()
    password = args.password or secrets.token_urlsafe(9)
    info = seed(password, args.students)
    print(f"教师：{info['teacher']}；学生：{', '.join(info['students'])}；密码：{password}")


if __name__ == "__main__":
    main()
