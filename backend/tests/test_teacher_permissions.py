"""阶段 5 验收：越权访问测试全部被拒绝；ICAP 编码与 κ。"""
from __future__ import annotations

import dataclasses
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import REPO_ROOT, get_settings
from backend.app.db import SessionLocal
from backend.app.models import AnalysisLabel, Class, Enrollment, Explanation, User
from backend.app.services.icap import cohen_kappa
from backend.app.services.llm import CircuitBreaker, LlmClient, set_llm
from backend.app.services.security import hash_password

from .conftest import PASSWORD, login, make_user


def teacher_of(student: User) -> User:
    with SessionLocal() as db:
        cls = db.scalar(select(Class).join(Enrollment, Enrollment.class_id == Class.id)
                        .where(Enrollment.user_id == student.id))
        return db.get(User, cls.teacher_id)


def class_of(student: User) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Enrollment.class_id).where(Enrollment.user_id == student.id))


@pytest.fixture(scope="module")
def world(app):
    """两个班：A 班有一名做过题的学生；B 班的老师来越权访问 A 班。"""
    student_a = make_user()
    c = login(app, student_a)
    detail = c.get("/api/student/problems/counter_mod10").json()
    c.post("/api/student/problems/counter_mod10/predictions", json={
        "waveform": {"cells": [{"signal": "q", "step": s, "value": "0000"} for s in detail["predict_points"][0]["steps"]]},
        "hardware": {"ff_count": 4, "latch": False, "ff_signals": ["q"]}})
    aid = c.post("/api/student/problems/counter_mod10/attempts",
                 json={"code": (REPO_ROOT / "problems/counter_mod10/ref.v").read_text()}).json()["attempt_id"]
    teacher_a = teacher_of(student_a)
    ta = login(app, teacher_a)
    export_job = ta.post(f"/api/teacher/classes/{class_of(student_a)}/exports", json={}).json()["job_id"]
    student_b = make_user()
    tb = login(app, teacher_of(student_b))
    return {"cid": class_of(student_a), "uid": student_a.id, "aid": aid, "export_job": export_job,
            "teacher_a": ta, "teacher_b": tb, "student_a": c}


CLASS_ENDPOINTS = [
    ("GET", "/api/teacher/classes/{cid}/overview", None),
    ("GET", "/api/teacher/classes/{cid}/heatmap", None),
    ("GET", "/api/teacher/classes/{cid}/heatmap/cell?user_id={uid}&kp=counter", None),
    ("GET", "/api/teacher/classes/{cid}/misconceptions", None),
    ("GET", "/api/teacher/classes/{cid}/misconceptions/latch_inferred", None),
    ("GET", "/api/teacher/classes/{cid}/problems/counter_mod10/analytics", None),
    ("GET", "/api/teacher/classes/{cid}/assignments", None),
    ("POST", "/api/teacher/classes/{cid}/assignments", {"title": "x", "problem_ids": ["adder4"],
                                                         "open_at": "2026-11-10T08:00:00", "due_at": "2026-11-12T08:00:00"}),
    ("GET", "/api/teacher/classes/{cid}/groups", None),
    ("PUT", "/api/teacher/classes/{cid}/groups", {"assignments": []}),
    ("POST", "/api/teacher/classes/{cid}/exports", {}),
    ("POST", "/api/teacher/classes/{cid}/analysis/icap", {}),
    ("GET", "/api/teacher/classes/{cid}/analysis/icap", None),
    ("GET", "/api/teacher/classes/{cid}/analysis/icap/sample", None),
    ("PUT", "/api/teacher/classes/{cid}/analysis/icap/sample", {"labels": []}),
    ("GET", "/api/teacher/classes/{cid}/roster", None),
    ("POST", "/api/teacher/classes/{cid}/roster", {"csv": "X1,冒名"}),
    ("POST", "/api/teacher/classes/{cid}/anonymity", {"anonymous": False}),
    ("GET", "/api/teacher/students/{uid}", None),
    ("POST", "/api/teacher/students/{uid}/notes", {"text": "越权备注"}),
    ("POST", "/api/teacher/students/{uid}/reset_password", None),
    ("GET", "/api/teacher/attempts/{aid}", None),
]


def _call(client: TestClient, method: str, url: str, body):
    return client.request(method, url, json=body) if body is not None else client.request(method, url)


@pytest.mark.parametrize("method, url, body", CLASS_ENDPOINTS, ids=[f"{m} {u}" for m, u, _ in CLASS_ENDPOINTS])
def test_teacher_cannot_access_other_class(world, method, url, body):
    r = _call(world["teacher_b"], method, url.format(**world), body)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("method, url, body", CLASS_ENDPOINTS, ids=[f"{m} {u}" for m, u, _ in CLASS_ENDPOINTS])
def test_student_cannot_use_teacher_api(world, method, url, body):
    r = _call(world["student_a"], method, url.format(**world), body)
    assert r.status_code == 403 and r.json()["error"]["message"] == "只有教师可以访问"


@pytest.mark.parametrize("method, url, body", CLASS_ENDPOINTS[:5], ids=[u for _, u, _ in CLASS_ENDPOINTS[:5]])
def test_anonymous_requests_rejected(app, world, method, url, body):
    r = _call(TestClient(app), method, url.format(**world), body)
    assert r.status_code == 401


def test_owner_teacher_allowed(world):
    for method, url, body in CLASS_ENDPOINTS:
        if method != "GET":
            continue
        r = _call(world["teacher_a"], method, url.format(**world), body)
        assert r.status_code == 200, (url, r.text)


def test_export_download_and_jobs_are_private(world):
    job = world["export_job"]
    assert world["teacher_a"].get(f"/api/teacher/exports/{job}/download").status_code == 200
    assert world["teacher_b"].get(f"/api/teacher/exports/{job}/download").status_code == 404
    assert world["teacher_b"].get(f"/api/jobs/{job}").status_code == 404
    assert world["student_a"].get(f"/api/teacher/exports/{job}/download").status_code == 403


def test_teacher_class_list_only_own(world):
    ids = [c["id"] for c in world["teacher_b"].get("/api/teacher/classes").json()["classes"]]
    assert world["cid"] not in ids


def test_admin_can_access_any_class(app, world):
    with SessionLocal() as db:
        admin = User(login_name=f"ADM{world['cid']}", display_name="管理员", role="admin",
                     password_hash=hash_password(PASSWORD))
        db.add(admin)
        db.commit()
        db.refresh(admin)
    client = login(app, admin)
    assert client.get(f"/api/teacher/classes/{world['cid']}/overview").status_code == 200
    assert client.get(f"/api/teacher/students/{world['uid']}").status_code == 200


# ---------------------------------------------------------------- ICAP

def test_cohen_kappa_by_hand():
    # 10 条：一致 7 条 → p_o = 0.7
    # AI：C×5、A×3、P×2；人工：C×4、A×4、P×2 → p_e = 0.5×0.4 + 0.3×0.4 + 0.2×0.2 = 0.36
    # κ = (0.7 − 0.36) / (1 − 0.36) = 0.53125
    pairs = [("C", "C")] * 3 + [("C", "A")] * 2 + [("A", "A")] * 2 + [("A", "C")] + [("P", "P")] * 2
    k = cohen_kappa(pairs)
    assert k["n"] == 10 and k["p_o"] == pytest.approx(0.7) and k["p_e"] == pytest.approx(0.36)
    assert k["kappa"] == pytest.approx(0.53125)
    assert cohen_kappa([]) == {"n": 0, "p_o": None, "p_e": None, "kappa": None}


def _icap_server(requests: list):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        items = json.loads(body["messages"][1]["content"])["items"]
        labels = {"e": "C", "m": "A"}
        out = {"items": [{"id": it["id"], "label": labels[it["id"][0]], "rationale": "测试"} for it in items]}
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(out)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}})
    return handler


def test_icap_job_sampling_and_kappa(app):
    accepted = make_user()
    cid = class_of(accepted)
    declined = make_user(class_id=cid, consent="declined")
    teacher = login(app, teacher_of(accepted))
    for user, n in ((accepted, 23), (declined, 2)):
        c = login(app, user)
        lines = (REPO_ROOT / "problems/counter_mod10/ref.v").read_text()
        detail = c.get("/api/student/problems/counter_mod10").json()
        c.post("/api/student/problems/counter_mod10/predictions", json={
            "waveform": {"cells": [{"signal": "q", "step": s, "value": "0000"} for s in detail["predict_points"][0]["steps"]]},
            "hardware": {"ff_count": 4, "latch": False, "ff_signals": ["q"]}})
        aid = c.post("/api/student/problems/counter_mod10/attempts", json={"code": lines}).json()["attempt_id"]
        with SessionLocal() as db:
            for k in range(n):
                db.add(Explanation(attempt_id=aid, text=f"因为计数到 9 就回到 0，所以第 {k} 步是这个值"))
            db.commit()
    requests: list = []
    settings = dataclasses.replace(get_settings(), llm_api_key="sk-test")
    set_llm(LlmClient(settings=settings, http_client=httpx.Client(transport=httpx.MockTransport(_icap_server(requests))),
                      sleep=lambda s: None, breaker=CircuitBreaker(5, 120)))
    try:
        job = teacher.post(f"/api/teacher/classes/{cid}/analysis/icap", json={}).json()["job_id"]
        result = teacher.get(f"/api/jobs/{job}").json()
        assert result["status"] == "done" and result["result"] == {"items": 23, "labeled": 23, "failed": 0}
    finally:
        set_llm(None)
    # 每批最多 20 条；开启思考模式；只编码已同意的学生
    assert [len(json.loads(b["messages"][1]["content"])["items"]) for b in requests] == [20, 3]
    assert requests[0]["thinking"] == {"type": "enabled"} and requests[0]["reasoning_effort"] == "high"
    summary = teacher.get(f"/api/teacher/classes/{cid}/analysis/icap").json()
    assert summary["total"] == 23 and summary["by_label"]["C"] == 23
    # 抽检：10%（23 条 → 3 条），人工标注时看不到 AI 的标签
    sample = teacher.get(f"/api/teacher/classes/{cid}/analysis/icap/sample").json()["items"]
    assert len(sample) == 3 and all("label" not in s for s in sample)
    labels = [{"id": sample[0]["id"], "human_label": "C"}, {"id": sample[1]["id"], "human_label": "C"},
              {"id": sample[2]["id"], "human_label": "A"}]
    k = teacher.put(f"/api/teacher/classes/{cid}/analysis/icap/sample", json={"labels": labels}).json()
    # AI 全是 C；人工 C、C、A → p_o = 2/3，p_e = 1×2/3 = 2/3 → κ = 0
    assert k["p_o"] == pytest.approx(2 / 3) and k["kappa"] == pytest.approx(0.0)
    assert k["low_agreement"] is True and k["message"] == "一致性偏低，结论需谨慎"
    # 学生详情里显示“AI 编码，已人工抽检 / 待人工抽检”
    detail = teacher.get(f"/api/teacher/students/{accepted.id}").json()
    assert len(detail["icap"]) == 23 and any("待人工抽检" in x["note"] for x in detail["icap"])
    # 拒绝参与研究的学生的解释没有被编码
    from backend.app.models import Attempt
    with SessionLocal() as db:
        declined_ids = set(db.scalars(select(Explanation.id).join(Attempt, Attempt.id == Explanation.attempt_id)
                                      .where(Attempt.user_id == declined.id)).all())
        coded = set(db.scalars(select(AnalysisLabel.target_id).where(AnalysisLabel.class_id == cid)).all())
    assert len(declined_ids) == 2 and not (declined_ids & coded)


def test_icap_requires_llm(app):
    student = make_user()
    teacher = login(app, teacher_of(student))
    set_llm(None)
    job = teacher.post(f"/api/teacher/classes/{class_of(student)}/analysis/icap", json={}).json()["job_id"]
    assert teacher.get(f"/api/jobs/{job}").json()["status"] == "error"
