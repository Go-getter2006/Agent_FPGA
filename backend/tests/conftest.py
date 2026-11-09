"""后端测试：独立的临时 SQLite 库，任务在请求里同步执行（JOBS_INLINE=1）。"""
from __future__ import annotations

import itertools
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="backend_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["JOBS_INLINE"] = "1"
os.environ["ANON_SALT"] = "test-salt"
os.environ["JUDGE_LOG_PATH"] = str(_TMP / "judge.jsonl")
os.environ["HINT_INTERVAL_SECONDS"] = "30"
os.environ["EXPORTS_DIR"] = str(_TMP / "exports")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from backend.app import models  # noqa: E402,F401
from backend.app.db import Base, SessionLocal, engine  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.models import Class, Enrollment, FeatureFlags, User  # noqa: E402
from backend.app.services.flags import DEFAULT_FLAGS  # noqa: E402
from backend.app.services.problems_sync import sync_all  # noqa: E402
from backend.app.services.security import anon_id_for, hash_password  # noqa: E402

PASSWORD = "test-password"
_counter = itertools.count(1)


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_all(db)
    yield


@pytest.fixture(scope="session")
def app():
    return create_app(sync_on_startup=False)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_user(role: str = "student", group: str = "treatment", consent: str = "accepted",
              class_id: int | None = None) -> User:
    n = next(_counter)
    with SessionLocal() as db:
        if role == "student" and class_id is None:
            teacher = User(login_name=f"T{n:05d}", display_name="老师", role="teacher",
                           password_hash=hash_password(PASSWORD))
            db.add(teacher)
            db.flush()
            cls = Class(name=f"班级{n}", term="2026 秋", teacher_id=teacher.id)
            db.add(cls)
            db.flush()
            for g, flags in DEFAULT_FLAGS.items():
                db.add(FeatureFlags(class_id=cls.id, group=g, flags=flags))
            class_id = cls.id
        user = User(login_name=f"{role[0].upper()}{n:05d}", display_name=f"测试{n}", role=role,
                    password_hash=hash_password(PASSWORD))
        db.add(user)
        db.flush()
        if role == "student":
            user.anon_id = anon_id_for(user.id)
            db.add(Enrollment(class_id=class_id, user_id=user.id, group=group, consent_status=consent))
        db.commit()
        db.refresh(user)
        return user


def login(app, user: User) -> TestClient:
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"login_name": user.login_name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def student(app):
    user = make_user()
    return user, login(app, user)


def event_types(user_id: int) -> list[str]:
    from backend.app.models import Event
    with SessionLocal() as db:
        return [e.type for e in db.scalars(select(Event).where(Event.user_id == user_id).order_by(Event.ts)).all()]
