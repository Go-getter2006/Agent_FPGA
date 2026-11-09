"""学生端接口：三种题型的完整流程、事件日志、越权访问、频率限制。"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.config import REPO_ROOT
from backend.app.db import SessionLocal, utcnow
from backend.app.models import Attempt, Event, Hint, ReviewItem
from backend.app.models import AppendOnlyError

from .conftest import event_types, login, make_user

PROBLEMS = REPO_ROOT / "problems"


def case_code(pid: str, name: str) -> str:
    """错误样本去掉第一行的 // expect 标注。"""
    text = (PROBLEMS / pid / "cases" / name).read_text(encoding="utf-8")
    return text.split("\n", 1)[1]


def ref_code(pid: str) -> str:
    return (PROBLEMS / pid / "ref.v").read_text(encoding="utf-8")


def lock(client, pid: str, value: str = "0", hardware: dict | None = None):
    detail = client.get(f"/api/student/problems/{pid}").json()
    widths = {o["name"]: o["width"] for o in detail["skeleton"]["outputs"]}
    pad = (lambda v, w: v.rjust(w, "0")) if set(value) <= {"0", "1"} else (lambda v, w: v)
    cells = [{"signal": p["signal"], "step": s, "value": pad(value, widths[p["signal"]])}
             for p in detail["predict_points"] for s in p["steps"]]
    hw = hardware or {"ff_count": 0, "latch": False, "ff_signals": []}
    r = client.post(f"/api/student/problems/{pid}/predictions", json={"waveform": {"cells": cells}, "hardware": hw})
    assert r.status_code == 200, r.text
    return r.json()


def submit(client, pid: str, code: str) -> dict:
    r = client.post(f"/api/student/problems/{pid}/attempts", json={"code": code})
    assert r.status_code == 200, r.text
    attempt = client.get(f"/api/student/attempts/{r.json()['attempt_id']}").json()
    assert attempt["status"] == "done", attempt
    return attempt


def finish_investigation(client, attempt: dict) -> dict:
    inv = attempt["investigation"]
    target = inv["target"]
    aid = attempt["id"]
    if inv["locate_step"]["required"]:
        r = client.post(f"/api/student/attempts/{aid}/investigations",
                        json={"kind": "locate_step", "chosen": {"step": target["step"], "signal": target["signal"]}})
        assert r.json()["correct"], r.json()
    if inv["locate_line"]["required"]:
        line = attempt["judge"]["drivers"][target["signal"]][0]
        r = client.post(f"/api/student/attempts/{aid}/investigations",
                        json={"kind": "locate_line", "chosen": {"line": line}})
        assert r.json()["correct"]
    r = client.post(f"/api/student/attempts/{aid}/explanations", json={"text": "因为这一拍的值来自上一拍"})
    assert r.status_code == 200
    return r.json()["investigation"]


def step_of(client, pid: str) -> str:
    return client.get(f"/api/student/problems/{pid}").json()["progress"]["step"]


# ---------------------------------------------------------------- 创作题：从登录走完全部步骤

def test_make_problem_full_flow(student):
    user, client = student
    pid = "seq_detector_101"
    detail = client.get(f"/api/student/problems/{pid}").json()
    assert detail["progress"]["step"] == "predict" and detail["editable"] and detail["code"] == ""
    assert detail["steps"] == ["predict", "run", "investigate", "make"]
    assert "outputs" in detail["skeleton"] and "values" not in detail["skeleton"]["outputs"][0]  # 预测前不给输出值
    client.post("/api/student/events", json={"events": [
        {"type": "problem.open", "problem_id": pid}, {"type": "step.enter", "problem_id": pid,
                                                      "payload": {"step": "predict"}}]})

    # ① 预测 → ② 运行：先交一份不允许重叠的错误设计
    lock(client, pid, "0", {"ff_count": 2, "latch": False, "ff_signals": ["state"]})
    assert step_of(client, pid) == "run"
    attempt = submit(client, pid, case_code(pid, "c1_no_overlap.v"))
    assert attempt["sim_ok"] is False and attempt["judge"]["sim"]["first_mismatch"]["step"] == 5
    assert attempt["expected"] and attempt["quadrant"] in ("design_gap", "concept_gap")
    assert step_of(client, pid) == "investigate"
    client.post("/api/student/events", json={"events": [
        {"type": "waveform.view", "problem_id": pid, "attempt_id": attempt["id"]}]})

    # ③ 探究：先点错，再点对
    aid = attempt["id"]
    r = client.post(f"/api/student/attempts/{aid}/investigations",
                    json={"kind": "locate_step", "chosen": {"step": 3, "signal": "out"}})
    assert r.json() == {**r.json(), "correct": False, "message": "再看看"}
    r = client.post(f"/api/student/attempts/{aid}/investigations",
                    json={"kind": "locate_line", "chosen": {"line": 1}})
    assert r.json()["correct"] is False
    status = finish_investigation(client, attempt)
    assert status["complete"]
    assert step_of(client, pid) == "predict"            # 设计还没通过：重新预测并仿真

    # 再预测、再运行正确的设计 → 进入 ⑤ 创作
    lock(client, pid, "0", {"ff_count": 2, "latch": False, "ff_signals": ["state"]})
    attempt2 = submit(client, pid, ref_code(pid))
    assert attempt2["sim_ok"] is True and attempt2["previous"]["id"] == aid
    assert step_of(client, pid) == "make"

    # ⑤ 写 testbench 并打分
    detail = client.get(f"/api/student/problems/{pid}").json()
    assert "top_module dut" in detail["tb_template"]
    tb = (PROBLEMS / pid / "tb.v").read_text(encoding="utf-8")
    r = client.post(f"/api/student/problems/{pid}/testbench", json={"code": tb})
    assert r.status_code == 200, r.text
    sub = client.get(f"/api/student/testbench/{r.json()['tb_submission_id']}").json()
    assert sub["status"] == "done" and sub["score"] == 1.0
    detail = client.get(f"/api/student/problems/{pid}").json()
    assert detail["progress"]["step"] == "done"
    assert set(detail["progress"]["completed"]) == {"predict", "run", "investigate", "make"}

    # 每一步都有事件日志
    types = event_types(user.id)
    for needed in ("auth.login", "problem.open", "step.enter", "predict.submit", "code.submit", "judge.done",
                   "waveform.view", "investigate.locate_step", "investigate.locate_line", "explain.submit",
                   "tb.submit"):
        assert needed in types, needed
    assert types.count("code.submit") == 2 and types.count("judge.done") == 2
    assert types.count("predict.submit") == 4           # 两次预测，每次波形 + 硬件各一条

    # 我的学情：状态机知识点有了尝试
    report = client.get("/api/student/report").json()
    fsm = next(m for m in report["mastery"] if m["code"] == "fsm")
    assert fsm["attempts"] == 2 and fsm["level"] != "not_started"
    assert report["kpis"]["tb"]["score"] == 1.0
    assert {"code": "tb_full", "label": "testbench 满分 ×1"} in report["badges"]


def test_event_rows_have_research_fields(student):
    user, client = student
    with SessionLocal() as db:
        ev = db.scalar(select(Event).where(Event.user_id == user.id, Event.type == "auth.login"))
    assert ev.anon_id == user.anon_id and ev.class_id and ev.group == "treatment" and ev.app_version


# ---------------------------------------------------------------- 预测题、修改题

def test_predict_problem_flow(student):
    _, client = student
    pid = "prio_encoder4"
    detail = client.get(f"/api/student/problems/{pid}").json()
    assert not detail["editable"] and detail["code"] == detail["starter"]
    lock(client, pid, "0")
    attempt = submit(client, pid, "这段代码会被替换成起始代码")     # 预测题运行的永远是起始代码
    assert attempt["code"] == detail["starter"] and attempt["sim_ok"] is True
    assert attempt["quadrant"] == "fragile"            # 代码对，但全填 0 的预测不达标
    assert attempt["investigation"]["target"]["kind"] == "pred"
    finish_investigation(client, attempt)
    assert step_of(client, pid) == "done"


def test_modify_problem_flow(student):
    _, client = student
    pid = "adder4"
    lock(client, pid, "0")
    attempt = submit(client, pid, "")
    assert attempt["sim_ok"] is False                   # 起始代码没有进位
    finish_investigation(client, attempt)
    detail = client.get(f"/api/student/problems/{pid}").json()
    assert detail["progress"]["step"] == "modify" and detail["editable"]
    # ④ 修改：先预测变化，再运行
    r = client.post(f"/api/student/problems/{pid}/attempts", json={"code": ref_code(pid)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PREDICTION_REQUIRED"
    lock(client, pid, "1")
    assert step_of(client, pid) == "modify"
    attempt2 = submit(client, pid, ref_code(pid))
    assert attempt2["sim_ok"] is True and attempt2["step"] == "modify"
    detail = client.get(f"/api/student/problems/{pid}").json()
    assert detail["progress"]["step"] == "done" and "modify" in detail["progress"]["completed"]


def test_compile_error_returns_to_predict(student):
    _, client = student
    pid = "counter_mod10"
    lock(client, pid)
    attempt = submit(client, pid, case_code(pid, "c5_compile.v"))
    assert attempt["quadrant"] == "none" and attempt["judge"]["tags"] == ["compile_error"]
    assert attempt["investigation"] is None
    assert step_of(client, pid) == "predict"


# ---------------------------------------------------------------- 预测校验

def test_prediction_validation(student):
    _, client = student
    pid = "counter_mod10"
    r = client.post(f"/api/student/problems/{pid}/predictions", json={"waveform": {"cells": []}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "PREDICTION_INCOMPLETE"
    lock(client, pid, "0xA")
    r = client.post(f"/api/student/problems/{pid}/predictions", json={"waveform": {"cells": []}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PREDICTION_LOCKED"


# ---------------------------------------------------------------- 提示阶梯

def test_hint_ladder_and_interval(student):
    _, client = student
    pid = "seq_detector_101"          # 创作题：提交的就是学生自己的代码
    lock(client, pid)
    attempt = submit(client, pid, case_code(pid, "c3_latch.v"))
    aid = attempt["id"]
    h1 = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert h1["level"] == 1 and h1["source"] == "fallback" and h1["question"].endswith("？")
    # 第 2 版：1 级思路（概念 + 类比，不点代码）→ 2 级定位 → 3 级代码提示
    assert h1["tag"] == "latch_inferred" and "锁存器" in h1["message"] and h1["code"] == ""
    r = client.post(f"/api/student/attempts/{aid}/hints")
    assert r.status_code == 429 and r.json()["error"]["code"] == "HINT_TOO_SOON"
    # 中间做了一次定位操作，就可以要下一级
    client.post(f"/api/student/attempts/{aid}/investigations",
                json={"kind": "locate_step", "chosen": {"step": 0, "signal": "out"}})
    h2 = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert h2["level"] == 2 and "next_state" in h2["message"]
    with SessionLocal() as db:   # 把上一条提示的时间往前拨，模拟过了 30 秒
        for h in db.scalars(select(Hint).where(Hint.attempt_id == aid)).all():
            h.created_at = utcnow() - timedelta(seconds=60)
        db.commit()
    h3 = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert h3["level"] == 3 and "____" in h3["code"] and "endmodule" not in h3["code"]
    r = client.post(f"/api/student/attempts/{aid}/hints")
    assert r.status_code == 409 and r.json()["error"]["code"] == "HINT_MAX"
    detail = client.get(f"/api/student/attempts/{aid}").json()
    assert [h["level"] for h in detail["hints"]] == [1, 2, 3]


# ---------------------------------------------------------------- 顺序打乱实验

def test_shuffle_experiment_marks_race(student):
    user, client = student
    pid = "swap_regs"
    lock(client, pid)
    attempt = submit(client, pid, "")                  # 起始代码：两个块都用阻塞赋值
    r = client.post(f"/api/student/attempts/{attempt['id']}/shuffle", json={"prediction": "same"})
    assert r.status_code == 200, r.text
    detail = client.get(f"/api/student/attempts/{attempt['id']}").json()
    assert detail["shuffle"]["result"]["order_sensitive"] is True
    assert "race_order_sensitive" in detail["judge"]["tags"]
    assert {"code": "pred_order_belief", "label": "以为结果取决于代码先后"} in detail["misconceptions"]
    assert "shuffle.run" in event_types(user.id)


# ---------------------------------------------------------------- 对照组

def test_control_group_runs_without_prediction(app):
    user = make_user(group="control")
    client = login(app, user)
    pid = "counter_mod10"
    me = client.get("/api/auth/me").json()
    assert me["flags"]["predict_step"] is False
    assert client.get(f"/api/student/problems/{pid}").json()["progress"]["step"] == "run"
    attempt = submit(client, pid, ref_code(pid))
    assert attempt["sim_ok"] is True and attempt["quadrant"] == "none" and attempt["pred_accuracy"] is None
    r = client.post(f"/api/student/problems/{pid}/predictions", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FEATURE_OFF"


# ---------------------------------------------------------------- 复习

def test_review_enqueued_and_answered(student):
    user, client = student
    pid = "counter_mod10"
    lock(client, pid, "0", {"ff_count": 4, "latch": False, "ff_signals": ["q"]})
    attempt = submit(client, pid, ref_code(pid))       # 代码对，波形全填 0 → fragile
    assert attempt["quadrant"] == "fragile"
    assert client.get("/api/student/review").json()["items"] == []     # 明天才到期
    with SessionLocal() as db:
        items = db.scalars(select(ReviewItem).where(ReviewItem.user_id == user.id)).all()
        assert {i.knowledge_point for i in items} == {"counter", "sequential", "reset"}
        for i in items:
            assert "answer" in i.question
            i.due_at = utcnow() - timedelta(hours=1)
        db.commit()
    review = client.get("/api/student/review").json()
    assert review["remaining_today"] == 5 and len(review["items"]) == 3
    item = review["items"][0]
    assert "answer" not in item["question"]            # 标准答案不下发
    q = item["question"]
    # 用服务端的标准答案拼出全对的答卷（测试里直接读库）
    with SessionLocal() as db:
        answer = db.get(ReviewItem, item["id"]).question["answer"]
    trace = {row["step"]: row["outputs"] for row in answer["sim"]["trace"]}
    if q["kind"] == "waveform":
        body = {"waveform": {"cells": [{"signal": p["signal"], "step": s, "value": trace[s][p["signal"]]}
                                       for p in q["predict_points"] for s in p["steps"]]}}
    else:
        hw = answer["hardware"]
        body = {"hardware": {"ff_count": hw["ff_count"], "latch": bool(hw["latch_signals"]),
                             "ff_signals": hw["ff_signals"]}}
    r = client.post(f"/api/student/review/{item['id']}/answer", json=body).json()
    assert r["correct"] is True and r["box"] == 2
    assert client.get("/api/student/review").json()["remaining_today"] == 4
    assert "review.answer" in event_types(user.id)


# ---------------------------------------------------------------- 越权与登录

@pytest.fixture
def other_attempt(app):
    owner = make_user()
    client = login(app, owner)
    lock(client, "counter_mod10")
    return submit(client, "counter_mod10", ref_code("counter_mod10"))


def test_student_cannot_access_others_attempt(student, other_attempt):
    _, client = student
    aid = other_attempt["id"]
    assert client.get(f"/api/student/attempts/{aid}").status_code == 404
    assert client.post(f"/api/student/attempts/{aid}/investigations",
                       json={"kind": "locate_line", "chosen": {"line": 1}}).status_code == 404
    assert client.post(f"/api/student/attempts/{aid}/explanations", json={"text": "偷看别人的"}).status_code == 404
    assert client.post(f"/api/student/attempts/{aid}/hints").status_code == 404
    assert client.post(f"/api/student/attempts/{aid}/shuffle", json={}).status_code == 404
    with SessionLocal() as db:
        job_id = db.scalar(select(Attempt).where(Attempt.id == aid)).id
    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 404
    # 上报事件时冒用别人的 attempt_id：事件照收，但 attempt_id 被清空
    client.post("/api/student/events", json={"events": [{"type": "waveform.view", "attempt_id": aid}]})
    with SessionLocal() as db:
        assert db.scalar(select(Event).where(Event.attempt_id == aid, Event.type == "waveform.view")) is None


def test_teacher_cannot_use_student_api(app):
    teacher = make_user(role="teacher")
    client = login(app, teacher)
    r = client.get("/api/student/home")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_requires_login(app):
    from fastapi.testclient import TestClient
    r = TestClient(app).get("/api/student/home")
    assert r.status_code == 401 and r.json() == {"error": {"code": "UNAUTHORIZED", "message": "请先登录"}}


def test_bad_password(app):
    from fastapi.testclient import TestClient
    user = make_user()
    r = TestClient(app).post("/api/auth/login", json={"login_name": user.login_name, "password": "wrong"})
    assert r.status_code == 401 and "联系任课教师" in r.json()["error"]["message"]


def test_consent_required_before_other_pages(app):
    user = make_user(consent="pending")
    client = login(app, user)
    me = client.get("/api/auth/me").json()
    assert me["consent"]["required"] is True
    r = client.get("/api/student/home")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CONSENT_REQUIRED"
    r = client.post("/api/auth/consent", json={"accept": False, "version": me["consent"]["current_version"]})
    assert r.json()["consent"]["status"] == "declined"
    assert client.get("/api/student/home").status_code == 200     # 不参与研究也照常使用
    assert "consent.decline" in event_types(user.id)


def test_rate_limit(student):
    user, client = student
    with SessionLocal() as db:
        for i in range(20):
            db.add(Attempt(user_id=user.id, problem_id="adder4", attempt_no=i + 1, step="run", code="x",
                           code_hash="x", status="done"))
        db.commit()
    r = client.post("/api/student/problems/adder4/attempts", json={"code": "module top_module; endmodule"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"


def test_events_are_append_only(student):
    user, _ = student
    with SessionLocal() as db:
        ev = db.scalar(select(Event).where(Event.user_id == user.id))
        ev.type = "tampered"
        with pytest.raises(AppendOnlyError):
            db.commit()
        db.rollback()
        ev = db.scalar(select(Event).where(Event.user_id == user.id))
        db.delete(ev)
        with pytest.raises(AppendOnlyError):
            db.commit()


def test_client_cannot_forge_server_events(student):
    user, client = student
    r = client.post("/api/student/events", json={"events": [{"type": "judge.done"}, {"type": "page.view"}]})
    assert r.json()["accepted"] == 1
    assert "judge.done" not in event_types(user.id)


def test_problem_list_and_home(student):
    _, client = student
    data = client.get("/api/student/problems").json()
    ids = [p["id"] for p in data["items"]]
    assert {"prio_encoder4", "adder4", "counter_mod10", "shift_reg4", "seq_detector_101", "swap_regs"} <= set(ids)
    assert all(p["status"] == "not_started" for p in data["items"])
    fsm_only = client.get("/api/student/problems", params={"kp": "fsm"}).json()["items"]
    assert [p["id"] for p in fsm_only] == ["seq_detector_101"]
    home = client.get("/api/student/home").json()
    assert len(home["mastery"]) == 11 and home["review_due"] == 0
