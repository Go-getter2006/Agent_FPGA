"""阶段 4：大模型提示、对话、容错与熔断、预算、调用日志（用模拟的 DeepSeek 服务，不访问网络）。

验收：断网或 Key 无效时，学生端仍能正常做题并拿到规则提示。
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from backend.app.config import REPO_ROOT, get_settings
from backend.app.db import SessionLocal, utcnow
from backend.app.models import ChatMessage, Hint, LlmCall
from backend.app.services import llm as llm_mod
from backend.app.services.llm import CircuitBreaker, LlmClient, set_llm

from .conftest import event_types, login, make_user

PID = "seq_detector_101"
FAKE_KEY = "sk-test-should-never-be-logged"


def case_code(name: str) -> str:
    return (REPO_ROOT / "problems" / PID / "cases" / name).read_text(encoding="utf-8").split("\n", 1)[1]


def completion(content: str, *, hit: int = 70, miss: int = 30, out: int = 20) -> dict:
    return {"id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": hit + miss, "completion_tokens": out, "total_tokens": hit + miss + out,
                      "prompt_cache_hit_tokens": hit, "prompt_cache_miss_tokens": miss}}


def hint_json(level: int = 1, message: str = "先看第 5 步的 out：期望 1，实际 0。", lines=(16,)) -> str:
    return json.dumps({"level": level, "focus": {"step": 5, "signal": "out", "lines": list(lines)},
                       "message": message, "question": "第 16 行在这个时钟沿做了什么？",
                       "concept_tags": ["fsm"]}, ensure_ascii=False)


def sse_body(deltas: list[str]) -> bytes:
    chunks = []
    for d in deltas:
        chunks.append({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "deepseek-flash",
                       "choices": [{"index": 0, "delta": {"content": d}, "finish_reason": None}]})
    chunks.append({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "deepseek-flash",
                   "choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60,
                                            "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 10}})
    text = "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return text.encode("utf-8")


class FakeDeepSeek:
    """按顺序返回预设响应；记录收到的请求。"""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"headers": dict(request.headers), "body": body, "url": str(request.url)})
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            return httpx.Response(item, json={"error": {"message": "fake error"}})
        if isinstance(item, bytes):
            return httpx.Response(200, content=item, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=item)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def fake_llm():
    """装上模拟的 DeepSeek；返回一个函数，用来设置响应序列。"""
    sleeps: list[float] = []
    clock = FakeClock()

    def install(responses: list, **overrides) -> tuple[FakeDeepSeek, LlmClient]:
        server = FakeDeepSeek(responses)
        settings = dataclasses.replace(get_settings(), llm_api_key=FAKE_KEY, **overrides)
        client = LlmClient(settings=settings, http_client=httpx.Client(transport=httpx.MockTransport(server)),
                           sleep=sleeps.append,
                           breaker=CircuitBreaker(settings.llm_breaker_failures, settings.llm_breaker_cooldown, clock))
        set_llm(client)
        return server, client

    install.sleeps = sleeps
    install.clock = clock
    yield install
    set_llm(None)


def submit_attempt(client, code: str) -> int:
    detail = client.get(f"/api/student/problems/{PID}").json()
    cells = [{"signal": p["signal"], "step": s, "value": "0"} for p in detail["predict_points"] for s in p["steps"]]
    r = client.post(f"/api/student/problems/{PID}/predictions",
                    json={"waveform": {"cells": cells}, "hardware": {"ff_count": 2, "latch": False, "ff_signals": ["state"]}})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/student/problems/{PID}/attempts", json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()["attempt_id"]


@pytest.fixture
def attempt(student):
    user, client = student
    return user, client, submit_attempt(client, case_code("c1_no_overlap.v"))


def calls() -> list[LlmCall]:
    with SessionLocal() as db:
        return list(db.scalars(select(LlmCall).order_by(LlmCall.id)).all())


# ---------------------------------------------------------------- 分级提示

def test_llm_hint_valid(fake_llm, attempt):
    server, _ = fake_llm([completion(hint_json())])
    user, client, aid = attempt
    before = len(calls())
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["source"] == "llm" and hint["level"] == 1 and hint["fallback_reason"] is None
    assert hint["prompt_version"] == "hint_v2" and hint["focus"]["lines"] == [16]
    req = server.requests[0]
    body = req["body"]
    # 请求参数：模型名来自配置；关闭思考；JSON Output；system → 本题信息 → 本次诊断
    assert body["model"] == "deepseek-flash" and body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"} and body["temperature"] == 0.3 and body["max_tokens"] == 800
    assert [m["role"] for m in body["messages"]] == ["system", "user", "user"]
    assert body["messages"][1]["content"].startswith("【题目】序列检测器（101）")
    assert "【学生代码（带行号）】" in body["messages"][2]["content"]
    assert '"first_mismatch":{"step":5' in body["messages"][2]["content"]
    assert "【请求】给出 1 级提示" in body["messages"][2]["content"]
    # 调用日志：版本、token、费用；Key 不出现在日志里
    new = calls()[before:]
    assert len(new) == 1
    log = new[0]
    assert log.purpose == "hint" and log.prompt_version == "hint_v2" and log.status == "ok" and log.model == "deepseek-flash"
    assert log.tokens == {"prompt": 100, "completion": 20, "cache_hit": 70, "cache_miss": 30}
    assert log.cost_cny == pytest.approx((70 * 0.04 + 30 * 2 + 20 * 8) / 1e6)
    assert log.validation["ok"] is True
    dumped = json.dumps([log.messages, log.output, log.error, log.validation], ensure_ascii=False)
    assert FAKE_KEY not in dumped
    with SessionLocal() as db:
        h = db.scalar(select(Hint).where(Hint.attempt_id == aid))
        assert h.source == "llm" and h.llm_call_id == log.id
    assert "hint.shown" in event_types(user.id)


def test_invalid_output_retried_once_with_reason(fake_llm, attempt):
    leaky = hint_json(message="改成：\nassign out = (state == S101);\nassign x = 1;")
    server, _ = fake_llm([completion(leaky), completion(hint_json())])
    _, client, aid = attempt
    before = len(calls())
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["source"] == "llm"
    retry_msg = server.requests[1]["body"]["messages"][-1]["content"]
    assert "上次输出违反规则：泄露代码" in retry_msg
    first, second = calls()[before:]
    assert first.status == "invalid" and any("泄露代码" in r for r in first.validation["reasons"])
    assert second.status == "ok"


def test_invalid_twice_falls_back(fake_llm, attempt):
    fake_llm([completion("这不是 json")])
    _, client, aid = attempt
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["source"] == "fallback" and hint["fallback_reason"] == "invalid"
    assert hint["template"] == "sim_mismatch.v2.1" and "对照期望波形" in hint["message"]   # 规则提示：1 级思路
    assert hint["question"].endswith("？")


def test_retry_on_429_and_5xx(fake_llm, attempt):
    server, _ = fake_llm([429, 503, completion(hint_json())])
    _, client, aid = attempt
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["source"] == "llm"
    assert len(server.requests) == 3 and fake_llm.sleeps[-2:] == [1.0, 3.0]
    assert calls()[-1].retries == 2


def test_empty_content_is_retried(fake_llm, attempt):
    server, _ = fake_llm([completion(""), completion(hint_json())])
    _, client, aid = attempt
    assert client.post(f"/api/student/attempts/{aid}/hints").json()["source"] == "llm"
    assert len(server.requests) == 2


def test_invalid_key_falls_back_without_retry(fake_llm, attempt):
    server, _ = fake_llm([401])
    _, client, aid = attempt
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["source"] == "fallback" and hint["fallback_reason"] == "error"
    assert len(server.requests) == 1
    assert calls()[-1].status == "error" and calls()[-1].error == "HTTP 401"


def test_network_down_falls_back(fake_llm, attempt):
    server, _ = fake_llm([httpx.ConnectError("network unreachable")])
    _, client, aid = attempt
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["source"] == "fallback" and hint["fallback_reason"] == "error"
    assert len(server.requests) == 3                      # 首次 + 重试 2 次


def test_circuit_breaker(fake_llm, attempt):
    server, client_llm = fake_llm([500])
    _, client, aid = attempt
    with SessionLocal() as db:
        for _ in range(5):
            assert client_llm.complete_json(db, purpose="hint", prompt_version="t", messages=[]).ok is False
        db.commit()
    sent = len(server.requests)
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["fallback_reason"] == "breaker_open" and len(server.requests) == sent    # 熔断期间不再请求
    fake_llm.clock.t += 121                                                                 # 2 分钟后放行
    server.responses = [completion(hint_json(level=2))]
    with SessionLocal() as db:
        assert client_llm.unavailable_reason(db) is None


def test_daily_budget(fake_llm, attempt):
    server, _ = fake_llm([completion(hint_json())], llm_daily_budget_cny=0.5)
    _, client, aid = attempt
    with SessionLocal() as db:
        db.add(LlmCall(purpose="hint", prompt_version="t", request_hash="x", messages=[], status="ok",
                       cost_cny=0.6, ts=utcnow()))
        db.commit()
    try:
        hint = client.post(f"/api/student/attempts/{aid}/hints").json()
        assert hint["fallback_reason"] == "budget" and server.requests == []
    finally:
        with SessionLocal() as db:
            for c in db.scalars(select(LlmCall).where(LlmCall.cost_cny == 0.6)).all():
                db.delete(c)
            db.commit()


def test_no_key_uses_rule_hints(attempt):
    set_llm(None)                     # 测试环境没有 DEEPSEEK_API_KEY
    _, client, aid = attempt
    hint = client.post(f"/api/student/attempts/{aid}/hints").json()
    assert hint["source"] == "fallback" and hint["fallback_reason"] == "no_key"


def test_control_group_never_calls_llm(fake_llm, app):
    server, _ = fake_llm([completion(hint_json())])
    user = make_user(group="control")
    client = login(app, user)
    r = client.post(f"/api/student/problems/{PID}/attempts", json={"code": case_code("c1_no_overlap.v")})
    hint = client.post(f"/api/student/attempts/{r.json()['attempt_id']}/hints").json()
    assert hint["source"] == "fallback" and hint["fallback_reason"] == "disabled" and server.requests == []
    r = client.post(f"/api/student/problems/{PID}/chat", json={"message": "为什么不对？"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FEATURE_OFF"


# ---------------------------------------------------------------- 验收：真实断网（连接被拒绝）时照常做题

def test_offline_student_still_works(attempt, monkeypatch):
    settings = dataclasses.replace(get_settings(), llm_api_key=FAKE_KEY, llm_base_url="http://127.0.0.1:9",
                                   llm_timeout=2)
    set_llm(LlmClient(settings=settings, sleep=lambda s: None))
    try:
        user, client, aid = attempt
        detail = client.get(f"/api/student/attempts/{aid}").json()
        assert detail["status"] == "done" and detail["judge"]["sim"]["first_mismatch"]["step"] == 5   # 仿真照常
        hint = client.post(f"/api/student/attempts/{aid}/hints").json()
        assert hint["source"] == "fallback" and hint["level"] == 1 and hint["message"]
        r = client.post(f"/api/student/problems/{PID}/chat", json={"message": "第 5 步为什么对不上？"})
        assert "当前为简化提示" in r.text and '"source": "fallback"' in r.text
    finally:
        set_llm(None)


# ---------------------------------------------------------------- 助教对话（SSE）

def _events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_chat_streams_and_logs(fake_llm, attempt):
    server, _ = fake_llm([sse_body(["你在第 16 行", "用的是当前状态。", "第 5 步之前 state 是什么？"])])
    user, client, aid = attempt
    r = client.post(f"/api/student/problems/{PID}/chat", json={"message": "为什么第 5 步不对？", "attempt_id": aid})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _events(r.text)
    assert "".join(e.get("delta", "") for e in evs) == "你在第 16 行用的是当前状态。第 5 步之前 state 是什么？"
    assert evs[-1]["done"] and evs[-1]["source"] == "llm" and evs[-1]["flagged"] is False
    body = server.requests[0]["body"]
    assert body["stream"] is True and body["thinking"] == {"type": "disabled"} and body["max_tokens"] == 600
    roles = [m["role"] for m in body["messages"]]
    assert roles[:3] == ["system", "user", "user"] and roles[-1] == "user"
    assert "【最近一次诊断】" in body["messages"][2]["content"]
    log = calls()[-1]
    assert log.purpose == "chat" and log.prompt_version == "chat_v2" and log.tokens["cache_hit"] == 40
    history = client.get(f"/api/student/problems/{PID}/chat").json()["messages"]
    assert [m["role"] for m in history[-2:]] == ["user", "assistant"]
    assert {"chat.send", "chat.reply"} <= set(event_types(user.id))
    # 第二轮：带上最近的对话
    server.responses = [sse_body(["好的。"])]
    client.post(f"/api/student/problems/{PID}/chat", json={"message": "state 是 S10"})
    roles = [m["role"] for m in server.requests[1]["body"]["messages"]]
    assert roles[3:] == ["user", "assistant", "user"]


def test_chat_stops_when_code_leaks(fake_llm, attempt):
    """第 2 版：原样写出参考答案里的语句就停止转发；没写完的代码行先不发，所以半行也不会漏出去。"""
    fake_llm([sse_body(["看第 16 行。\n", "可以改成：\n```verilog\n", "assign out = (st", "ate == S101);\n```"])])
    _, client, aid = attempt
    evs = _events(client.post(f"/api/student/problems/{PID}/chat", json={"message": "直接告诉我答案"}).text)
    text = "".join(e.get("delta", "") for e in evs)
    assert "assign out" not in text and "S101" not in text
    assert text.endswith("可以在提示区解锁参考答案）")
    assert evs[-1]["flagged"] is True
    with SessionLocal() as db:
        msg = db.scalar(select(ChatMessage).order_by(ChatMessage.id.desc()))
        assert msg.flagged and msg.role == "assistant"
    log = calls()[-1]
    assert log.status == "blocked" and "S101" in log.output        # 原始输出留作研究记录


def test_chat_allows_markdown_and_code_framework(fake_llm, attempt):
    """代码框架（带 ____）和与本题不同的小例子可以给；Markdown 原样转发给前端渲染。"""
    reply = ["**思路**：状态寄存器在时钟沿更新。\n", "```verilog\n", "always @(posedge clk) begin\n",
             "    if (rst) state <= ____;\n", "    else     state <= ____;\n", "end\n```\n", "试试看？"]
    fake_llm([sse_body(reply)])
    _, client, aid = attempt
    evs = _events(client.post(f"/api/student/problems/{PID}/chat", json={"message": "状态寄存器怎么写"}).text)
    assert "".join(e.get("delta", "") for e in evs) == "".join(reply)
    assert evs[-1]["flagged"] is False


def test_chat_hourly_limit(fake_llm, student, monkeypatch):
    fake_llm([sse_body(["好"])], chat_hourly_limit=2)
    monkeypatch.setattr("backend.app.api.student.get_settings",
                        lambda: dataclasses.replace(get_settings(), chat_hourly_limit=2))
    _, client = student
    for _ in range(2):
        assert client.post(f"/api/student/problems/{PID}/chat", json={"message": "问一下"}).status_code == 200
    r = client.post(f"/api/student/problems/{PID}/chat", json={"message": "再问一下"})
    assert r.status_code == 429 and r.json()["error"]["message"] == "先去波形里找找线索吧"


def test_chat_fallback_when_unavailable(attempt):
    set_llm(None)
    _, client, _aid = attempt
    evs = _events(client.post(f"/api/student/problems/{PID}/chat", json={"message": "在吗"}).text)
    assert evs[0]["source"] == "fallback" and "当前为简化提示" in evs[0]["delta"]
