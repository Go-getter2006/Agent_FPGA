"""助教对话（docs/llm-deepseek.md 第 6 节）：流式输出（SSE），服务端边收边查。

- 上下文：system + 本题信息 + 最近一次诊断摘要 + 学生象限 + 最近 8 轮对话
- 第 2 版（chat_v2）：回答用 Markdown，可以给代码片段和框架；学生看过参考答案之前，
  一旦写出完整模块、参考答案里的语句或过长的代码块（hint_guard.chat_leak_reason），立即停止转发，补一句提示并记录违规。
  看起来像代码、还没写完的那一行先不转发，等整行写完检查过再发
- 每个学生每小时最多 30 条，超过后提示“先去波形里找找线索吧”
- 大模型不可用时回复固定的简化说明，学生照常做题
"""
from __future__ import annotations

import json
import re
import time
from datetime import timedelta
from typing import Iterator

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..db import SessionLocal, utcnow
from ..models import Attempt, ChatMessage, ChatSession, Problem, User
from .events import log_event
from . import answer as answer_service
from .hint_guard import chat_leak_reason
from .llm import LlmClient, _describe, usage_tokens
from .llm_hints import judge_compact, load_prompt, numbered, problem_segment

CHAT_VERSION = "chat_v2"
LEAK_NOTICE = "（这里差不多就是答案了，先按上面的思路自己试试；实在不会，可以在提示区解锁参考答案）"
MAX_TURNS = 8
FALLBACK_REPLY = ("当前为简化提示，不影响仿真和判定。助教暂时不能对话，"
                  "可以先用上面的提示阶梯，或者回到波形里找第一个对不上的格子。")
RATE_LIMITED = "先去波形里找找线索吧"


def get_session(db: DbSession, user_id: int, problem_id: str) -> ChatSession:
    s = db.scalar(select(ChatSession).where(ChatSession.user_id == user_id, ChatSession.problem_id == problem_id))
    if s is None:
        s = ChatSession(user_id=user_id, problem_id=problem_id)
        db.add(s)
        db.flush()
    return s


def sent_last_hour(db: DbSession, user_id: int) -> int:
    since = utcnow() - timedelta(hours=1)
    return db.scalar(select(func.count()).select_from(ChatMessage).join(ChatSession).where(
        ChatSession.user_id == user_id, ChatMessage.role == "user", ChatMessage.created_at >= since)) or 0


def history(db: DbSession, session: ChatSession, limit: int = 50) -> list[ChatMessage]:
    rows = db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id)
                      .order_by(ChatMessage.id.desc()).limit(limit)).all()
    return list(reversed(rows))


def build_messages(db: DbSession, problem: Problem, attempt: Attempt | None, session: ChatSession,
                   new_message_id: int) -> list[dict]:
    ans = answer_service.status(db, session.user_id, problem)
    ans_text = ("学生已看过参考答案" if ans["revealed"] else "参考答案已解锁" if ans["unlocked"]
                else "参考答案未解锁")
    if attempt is not None and attempt.status == "done":
        state = (f"【最近一次诊断】{judge_compact(attempt.judge or {})}\n"
                 f"【学生代码（带行号）】\n{numbered(attempt.code)}\n"
                 f"【学生状态】象限：{attempt.quadrant or 'none'}；{ans_text}")
    else:
        state = f"【最近一次诊断】学生还没有运行过仿真\n【学生状态】{ans_text}"
    if ans["revealed"]:
        state += f"\n【参考答案】\n{problem.meta.get('ref_code') or ''}"
    turns = [m for m in history(db, session, limit=MAX_TURNS * 2 + 1) if m.id != new_message_id][-MAX_TURNS * 2:]
    new = db.get(ChatMessage, new_message_id)
    return [
        {"role": "system", "content": load_prompt("chat_system_v2.md")},
        {"role": "user", "content": problem_segment(db, problem)},
        {"role": "user", "content": state},
        *[{"role": m.role, "content": m.content} for m in turns],
        {"role": "user", "content": new.content},
    ]


_CODEISH = re.compile(r"[=;<`]|^\s*(assign|always|if|else|case|begin|end|reg|wire)\b")


def safe_prefix(text: str) -> int:
    """可以先转发的长度：已写完的行全部可以；最后一行没写完时，看起来像代码（或在代码块里）就先留着。"""
    cut = text.rfind("\n") + 1
    tail = text[cut:]
    in_fence = text[:cut].count("```") % 2 == 1
    if tail and not in_fence and not _CODEISH.search(tail):
        return len(text)
    return cut


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_reply(llm: LlmClient, *, user_id: int, session_id: int, message_id: int,
                 attempt_id: int | None) -> Iterator[str]:
    """SSE 生成器。自己开数据库会话（请求的会话在流式返回前就关闭了）。"""
    with SessionLocal() as db:
        user = db.get(User, user_id)
        session = db.get(ChatSession, session_id)
        problem = db.get(Problem, session.problem_id)
        attempt = db.get(Attempt, attempt_id) if attempt_id else None
        if attempt is not None and attempt.user_id != user_id:
            attempt = None

        def finish(text: str, *, source: str, flagged: bool = False, call_id: int | None = None) -> Iterator[str]:
            msg = ChatMessage(session_id=session.id, role="assistant", content=text, source=source,
                              attempt_id=attempt.id if attempt else None, llm_call_id=call_id, flagged=flagged)
            db.add(msg)
            db.flush()
            log_event(db, user, "chat.reply", problem_id=problem.id, attempt_id=attempt.id if attempt else None,
                      payload={"session_id": session.id, "length": len(text), "llm_call_id": call_id,
                               "flagged": flagged, "source": source})
            db.commit()
            yield _sse({"done": True, "message_id": msg.id, "source": source, "flagged": flagged})

        reason = llm.unavailable_reason(db)
        if reason:
            yield _sse({"delta": FALLBACK_REPLY, "source": "fallback"})
            yield from finish(FALLBACK_REPLY, source="fallback")
            return

        messages = build_messages(db, problem, attempt, session, message_id)
        start = time.monotonic()
        try:
            stream, retries = llm.open_stream(messages=messages)
        except Exception as exc:  # noqa: BLE001
            llm.breaker.failure()
            call = llm._log(db, purpose="chat", prompt_version=CHAT_VERSION, messages=messages, status="error",
                            latency_ms=int((time.monotonic() - start) * 1000),
                            retries=llm.settings.llm_max_retries, error=_describe(exc), user_id=user_id)
            yield _sse({"delta": FALLBACK_REPLY, "source": "fallback"})
            yield from finish(FALLBACK_REPLY, source="fallback", call_id=call.id)
            return

        received = ""          # 模型输出的全部文本（研究用）
        forwarded = ""         # 实际转发给学生的文本
        ans = answer_service.status(db, user_id, problem)
        ref_code = problem.meta.get("ref_code")

        def check(text: str) -> str | None:
            return chat_leak_reason(text, ref_code, ans["revealed"])
        usage = None
        model = None
        blocked = None
        error = None
        try:
            for delta, chunk_usage, chunk_model in llm.iter_stream(stream):
                usage = chunk_usage or usage
                model = chunk_model or model
                if not delta or blocked:
                    continue
                received += delta
                ready = received[:safe_prefix(received)]
                blocked = check(ready)
                if blocked:
                    break
                if len(ready) > len(forwarded):
                    piece = ready[len(forwarded):]
                    forwarded = ready
                    yield _sse({"delta": piece, "source": "llm"})
        except Exception as exc:  # noqa: BLE001  网络中途断开
            error = _describe(exc)
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

        if not blocked and len(received) > len(forwarded):      # 最后一行：整段检查过再发
            blocked = check(received)
            if not blocked:
                piece = received[len(forwarded):]
                forwarded = received
                yield _sse({"delta": piece, "source": "llm"})
        status = "blocked" if blocked else ("error" if error else "ok")
        call = llm._log(db, purpose="chat", prompt_version=CHAT_VERSION, messages=messages, status=status,
                        output=received, model=model, tokens=usage_tokens(usage),
                        latency_ms=int((time.monotonic() - start) * 1000), retries=retries,
                        error=error, user_id=user_id)
        if blocked:
            call.validation = {"ok": False, "reasons": [f"泄露代码：{blocked}"]}
        if error and not forwarded:
            llm.breaker.failure()
            yield _sse({"delta": FALLBACK_REPLY, "source": "fallback"})
            yield from finish(FALLBACK_REPLY, source="fallback", call_id=call.id)
            return
        llm.breaker.success()
        text = forwarded
        if blocked:
            notice = ("\n" if forwarded else "") + LEAK_NOTICE
            text += notice
            yield _sse({"delta": notice, "source": "llm", "flagged": True})
        elif error:
            text += "（连接中断，可以再问一次）"
            yield _sse({"delta": "（连接中断，可以再问一次）", "source": "llm"})
        yield from finish(text, source="llm", flagged=bool(blocked), call_id=call.id)
