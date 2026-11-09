"""DeepSeek 客户端封装（docs/llm-deepseek.md 第 3、7、9 节）。

- 后端编排、单轮调用、不用函数调用；模型名、地址、Key 都从环境变量读取
- 重试：429、5xx、超时、连接失败、空 content，间隔 1 秒、3 秒，最多 LLM_MAX_RETRIES 次
- 熔断：连续 5 次失败后 2 分钟内不再请求，全部改用规则提示
- 预算：当天（北京时间）累计费用超过 LLM_DAILY_BUDGET_CNY 时，当天剩余时间只用规则提示
- 每次调用写一行 llm_calls；API Key 不出现在任何日志里
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..config import Settings, get_settings
from ..models import LlmCall
from .review_scheduler import start_of_beijing_day
from ..db import utcnow

RETRY_DELAYS = (1.0, 3.0)


class EmptyContent(Exception):
    pass


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError, EmptyContent)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _describe(exc: Exception) -> str:
    if isinstance(exc, APIStatusError):
        return f"HTTP {exc.status_code}"
    if isinstance(exc, APITimeoutError):
        return "timeout"
    if isinstance(exc, APIConnectionError):
        return "connection_error"
    if isinstance(exc, EmptyContent):
        return "empty_content"
    return type(exc).__name__


class CircuitBreaker:
    """连续失败达到阈值后打开，冷却期内拒绝请求；冷却期过后放行，再失败满阈值才重新打开。"""

    def __init__(self, threshold: int, cooldown: float, clock: Callable[[], float] = time.monotonic):
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.failures = 0
        self.open_until: float | None = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            return self.open_until is None or self.clock() >= self.open_until

    def success(self) -> None:
        with self._lock:
            self.failures = 0
            self.open_until = None

    def failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.open_until = self.clock() + self.cooldown
                self.failures = 0


@dataclass
class LlmResult:
    ok: bool
    content: str | None = None
    call: LlmCall | None = None
    reason: str | None = None          # 不可用或失败的原因
    retries: int = 0


def request_hash(messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def usage_tokens(usage) -> dict | None:
    if usage is None:
        return None
    data = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
    prompt = data.get("prompt_tokens") or 0
    hit = data.get("prompt_cache_hit_tokens")
    miss = data.get("prompt_cache_miss_tokens")
    if hit is None and miss is None:
        hit, miss = 0, prompt
    return {"prompt": prompt, "completion": data.get("completion_tokens") or 0,
            "cache_hit": hit or 0, "cache_miss": miss or 0}


def cost_cny(tokens: dict | None, s: Settings) -> float:
    """C = (T_hit·p_hit + T_miss·p_miss + T_out·p_out) / 10^6（docs/llm-deepseek.md 第 11 节）"""
    if not tokens:
        return 0.0
    return (tokens["cache_hit"] * s.llm_price_hit + tokens["cache_miss"] * s.llm_price_miss
            + tokens["completion"] * s.llm_price_out) / 1e6


def spent_today(db: DbSession) -> float:
    since = start_of_beijing_day(utcnow())
    return float(db.scalar(select(func.coalesce(func.sum(LlmCall.cost_cny), 0.0)).where(LlmCall.ts >= since)) or 0.0)


@dataclass
class LlmClient:
    settings: Settings = field(default_factory=get_settings)
    http_client: httpx.Client | None = None
    sleep: Callable[[float], None] = time.sleep
    breaker: CircuitBreaker | None = None
    _client: OpenAI | None = None

    def __post_init__(self):
        if self.breaker is None:
            self.breaker = CircuitBreaker(self.settings.llm_breaker_failures, self.settings.llm_breaker_cooldown)

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.llm_api_key, base_url=self.settings.llm_base_url,
                                  timeout=self.settings.llm_timeout, max_retries=0,   # 重试由我们自己控制
                                  http_client=self.http_client)
        return self._client

    def unavailable_reason(self, db: DbSession) -> str | None:
        if not self.settings.llm_api_key:
            return "no_key"
        if not self.breaker.allow():
            return "breaker_open"
        if spent_today(db) >= self.settings.llm_daily_budget_cny:
            return "budget"
        return None

    def _log(self, db: DbSession, *, purpose: str, prompt_version: str, messages: list[dict], status: str,
             output: str | None = None, model: str | None = None, tokens: dict | None = None,
             latency_ms: int | None = None, retries: int = 0, error: str | None = None,
             user_id: int | None = None) -> LlmCall:
        call = LlmCall(purpose=purpose, prompt_version=prompt_version, model=model,
                       request_hash=request_hash(messages), messages=messages, output=output, tokens=tokens,
                       latency_ms=latency_ms, status=status, retries=retries,
                       cost_cny=cost_cny(tokens, self.settings), error=error, user_id=user_id)
        db.add(call)
        db.flush()
        return call

    def _params(self, *, thinking: bool, temperature: float, max_tokens: int, json_output: bool) -> dict:
        params: dict = {"model": self.settings.llm_model, "max_tokens": max_tokens}
        if json_output:
            params["response_format"] = {"type": "json_object"}
        if thinking:
            params["reasoning_effort"] = "high"
            params["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            params["temperature"] = temperature
            params["extra_body"] = {"thinking": {"type": "disabled"}}
        return params

    def complete_json(self, db: DbSession, *, purpose: str, prompt_version: str, messages: list[dict],
                      temperature: float = 0.3, max_tokens: int = 800, thinking: bool = False,
                      user_id: int | None = None) -> LlmResult:
        """JSON Output 调用（分级提示、离线编码）。失败时返回 ok=False，由调用方降级。"""
        reason = self.unavailable_reason(db)
        if reason:
            return LlmResult(ok=False, reason=reason)
        params = self._params(thinking=thinking, temperature=temperature, max_tokens=max_tokens, json_output=True)
        last_error = None
        attempt = 0
        start = time.monotonic()
        while True:
            try:
                resp = self.client.chat.completions.create(messages=messages, **params)
                content = resp.choices[0].message.content if resp.choices else None
                if not content or not content.strip():
                    raise EmptyContent()
                tokens = usage_tokens(resp.usage)
                call = self._log(db, purpose=purpose, prompt_version=prompt_version, messages=messages,
                                 status="ok", output=content, model=resp.model, tokens=tokens,
                                 latency_ms=int((time.monotonic() - start) * 1000), retries=attempt,
                                 user_id=user_id)
                self.breaker.success()
                return LlmResult(ok=True, content=content, call=call, retries=attempt)
            except Exception as exc:  # noqa: BLE001  任何异常都不能让学生端出错
                last_error = exc
                if _retryable(exc) and attempt < min(self.settings.llm_max_retries, len(RETRY_DELAYS)):
                    self.sleep(RETRY_DELAYS[attempt])
                    attempt += 1
                    continue
                break
        self.breaker.failure()
        call = self._log(db, purpose=purpose, prompt_version=prompt_version, messages=messages, status="error",
                         latency_ms=int((time.monotonic() - start) * 1000), retries=attempt,
                         error=_describe(last_error), user_id=user_id)
        return LlmResult(ok=False, call=call, reason="error", retries=attempt)

    def open_stream(self, *, messages: list[dict], temperature: float = 0.5, max_tokens: int = 600):
        """建立流式对话（只在拿到第一个响应之前重试）。返回 (stream, retries)；失败抛出最后一个异常。"""
        params = self._params(thinking=False, temperature=temperature, max_tokens=max_tokens, json_output=False)
        attempt = 0
        while True:
            try:
                stream = self.client.chat.completions.create(
                    messages=messages, stream=True, stream_options={"include_usage": True}, **params)
                return stream, attempt
            except Exception as exc:  # noqa: BLE001
                if _retryable(exc) and attempt < min(self.settings.llm_max_retries, len(RETRY_DELAYS)):
                    self.sleep(RETRY_DELAYS[attempt])
                    attempt += 1
                    continue
                raise

    @staticmethod
    def iter_stream(stream) -> Iterator[tuple[str | None, object, str | None]]:
        """逐块产出 (文本增量, usage, model)。"""
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            yield delta, getattr(chunk, "usage", None), getattr(chunk, "model", None)


_shared: LlmClient | None = None
_lock = threading.Lock()


def get_llm() -> LlmClient:
    """进程内共享一个客户端（熔断状态在进程内共享）。测试时用 set_llm 替换。"""
    global _shared
    with _lock:
        if _shared is None:
            _shared = LlmClient()
        return _shared


def set_llm(client: LlmClient | None) -> None:
    global _shared
    with _lock:
        _shared = client
