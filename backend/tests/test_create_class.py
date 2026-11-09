"""部署脚本 create_class：建教师、班级和分组开关；同一教师再建班级不重设密码。"""
from __future__ import annotations

import sys

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.models import Class, FeatureFlags, User
from backend.app.services.security import verify_password
from backend.scripts import create_class


def run(monkeypatch, capsys, *args: str) -> str:
    monkeypatch.setattr(sys, "argv", ["create_class", *args])
    create_class.main()
    return capsys.readouterr().out


def test_create_teacher_and_classes(monkeypatch, capsys):
    out = run(monkeypatch, capsys, "--teacher", "TDEPLOY", "--name", "王老师", "--class", "实验 1 班", "--term", "2026 秋")
    password = out.split("只显示这一次）：")[1].strip()
    out2 = run(monkeypatch, capsys, "--teacher", "TDEPLOY", "--name", "王老师", "--class", "实验 2 班")
    assert "初始密码" not in out2
    with SessionLocal() as db:
        teacher = db.scalar(select(User).where(User.login_name == "TDEPLOY"))
        assert teacher.role == "teacher" and verify_password(teacher.password_hash, password)
        classes = db.scalars(select(Class).where(Class.teacher_id == teacher.id)).all()
        assert [c.name for c in classes] == ["实验 1 班", "实验 2 班"]
        groups = {f.group for f in db.scalars(select(FeatureFlags).where(FeatureFlags.class_id == classes[0].id))}
        assert groups == {"treatment", "control", "none"}
