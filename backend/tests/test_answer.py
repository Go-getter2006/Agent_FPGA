"""第 2 版提示：3 级代码提示的校验；4 级参考答案的解锁、查看、对学情的影响。"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from backend.app.db import SessionLocal, utcnow
from backend.app.models import Hint
from backend.app.services import mastery
from backend.app.services.hint_guard import answer_lines, chat_leak_reason, validate_hint_v2

from .conftest import event_types
from .test_api_flow import PROBLEMS, case_code, lock, ref_code, submit

REF = (PROBLEMS / "seq_detector_101" / "ref.v").read_text(encoding="utf-8")


def raw(level=3, code="always @(posedge clk) begin\n    state <= ____;\nend", message="状态寄存器在时钟沿更新。"):
    return json.dumps({"level": level, "focus": {"step": 5, "signal": "out", "lines": [16]}, "message": message,
                       "question": "这里该填什么？", "concept_tags": ["fsm"], "code": code}, ensure_ascii=False)


# ---------------------------------------------------------------- 校验

def test_answer_lines_skip_constants_and_comments():
    lines = answer_lines(REF)
    assert "assignout=(state==S101);" in lines and "elsestate<=next_state;" in lines
    assert "default:next_state=S0;" in lines and not any("//" in x for x in lines)


def test_level3_code_framework_passes():
    r = validate_hint_v2(raw(), level=3, code_lines=30, ref_code=REF)
    assert r["ok"], r["reasons"]
    assert r["hint"]["code"].startswith("always @(posedge clk)")


def test_level3_rejects_answer_line_full_module_and_long_code():
    leak = validate_hint_v2(raw(code="assign out = (state == S101);"), level=3, code_lines=30, ref_code=REF)
    assert not leak["ok"] and any("泄露答案" in r for r in leak["reasons"])
    module = validate_hint_v2(raw(code="module top_module();\nendmodule"), level=3, code_lines=30, ref_code=REF)
    assert not module["ok"]
    long = validate_hint_v2(raw(code="\n".join(f"x{i} = ____;" for i in range(9))), level=3, code_lines=30, ref_code=REF)
    assert any("超过 8 行" in r for r in long["reasons"])
    assert any("缺少 code" in r for r in validate_hint_v2(raw(code=""), level=3, code_lines=30)["reasons"])
    fenced = validate_hint_v2(raw(code="```verilog\nq <= ____;\n```"), level=3, code_lines=30, ref_code=REF)
    assert fenced["ok"] and fenced["hint"]["code"] == "q <= ____;"


def test_level1_code_is_dropped_and_prose_code_blocked():
    r = validate_hint_v2(raw(level=1), level=1, code_lines=30, ref_code=REF)
    assert r["ok"] and r["hint"]["code"] == "" and r["warnings"]
    r = validate_hint_v2(raw(level=2, code="", message="改成：\n```\nx\n```"), level=2, code_lines=30)
    assert not r["ok"]


def test_chat_guard_relaxed_after_reveal():
    text = "参考答案这一行：\n```verilog\nassign out = (state == S101);\n```"
    assert chat_leak_reason(text, REF, answer_revealed=False)
    assert chat_leak_reason(text, REF, answer_revealed=True) is None
    long = "```\n" + "\n".join(f"a{i} = ____;" for i in range(13)) + "\n```"
    assert "超过 12 行" in chat_leak_reason(long, REF, answer_revealed=False)


# ---------------------------------------------------------------- 解锁与查看

def _hint(client, aid):
    r = client.post(f"/api/student/attempts/{aid}/hints")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:            # 跳过 30 秒间隔
        for h in db.scalars(select(Hint).where(Hint.attempt_id == aid)).all():
            h.created_at = utcnow() - timedelta(seconds=60)
        db.commit()
    return r.json()


def _fail(client, pid):
    lock(client, pid)
    return submit(client, pid, case_code(pid, "c1_no_overlap.v"))


def test_answer_unlock_reveal_and_mastery(student):
    user, client = student
    pid = "seq_detector_101"
    st = client.get(f"/api/student/problems/{pid}").json()["answer"]
    assert st["available"] and not st["unlocked"] and "再提交 3 次" in st["message"]
    r = client.post(f"/api/student/problems/{pid}/answer")
    assert r.status_code == 403 and r.json()["error"]["code"] == "ANSWER_LOCKED"

    attempts = [_fail(client, pid) for _ in range(3)]
    st = client.get(f"/api/student/problems/{pid}").json()["answer"]
    assert not st["unlocked"] and st["failed"] == 3 and st["message"].startswith("先看第 3 级代码提示")
    aid = attempts[-1]["id"]
    for level in (1, 2, 3):
        assert _hint(client, aid)["level"] == level
    st = client.get(f"/api/student/problems/{pid}").json()["answer"]
    assert st["unlocked"] and not st["revealed"]

    r = client.post(f"/api/student/problems/{pid}/answer").json()
    assert r["first_time"] and "assign out = (state == S101);" in r["code"] and r["answer"]["revealed"]
    assert "answer.reveal" in event_types(user.id)
    # 4 级记在最近一次尝试上，但不出现在提示阶梯里；再看一次只记事件
    detail = client.get(f"/api/student/attempts/{aid}").json()
    assert [h["level"] for h in detail["hints"]] == [1, 2, 3]
    with SessionLocal() as db:
        assert db.scalar(select(Hint).where(Hint.attempt_id == aid, Hint.level == 4)).source == "answer"
    assert client.post(f"/api/student/problems/{pid}/answer").json()["first_time"] is False
    assert "answer.view" in event_types(user.id)
    r = client.post(f"/api/student/attempts/{aid}/hints")
    assert r.status_code == 409 and r.json()["error"]["code"] == "HINT_MAX"

    # 看过答案之后的提交不计入掌握度
    with SessionLocal() as db:
        before = len(mastery.attempt_views(db, user.id))
    lock(client, pid)
    passed = submit(client, pid, ref_code(pid))
    assert passed["sim_ok"] is True
    with SessionLocal() as db:
        assert len(mastery.attempt_views(db, user.id)) == before


def test_answer_after_pass_and_not_for_predict_problems(student):
    _, client = student
    pid = "counter_mod10"
    lock(client, pid)
    assert submit(client, pid, ref_code(pid))["sim_ok"] is True
    st = client.get(f"/api/student/problems/{pid}").json()["answer"]
    assert st["unlocked"] and "对照" in st["message"]
    assert client.post(f"/api/student/problems/{pid}/answer").status_code == 200
    predict = [p["id"] for p in client.get("/api/student/problems").json()["items"] if p["primm_type"] == "predict"]
    if predict:
        assert client.get(f"/api/student/problems/{predict[0]}").json()["answer"]["available"] is False
        assert client.post(f"/api/student/problems/{predict[0]}/answer").status_code == 409
