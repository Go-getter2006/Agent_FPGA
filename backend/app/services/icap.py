"""离线 ICAP 编码与人工抽检（docs/learner-model.md 第 10 节，docs/llm-deepseek.md 第 10 节）。

- 对象：探究步骤的一句话解释、助教对话中学生的发言；只编码已同意参与研究的学生
- 开启思考模式（reasoning_effort=high）+ JSON Output，每次 20 条；结果存 analysis_labels，标注 AI 编码
- 人工抽检：随机抽 10%（至少 1 条），教师标注后计算 κ；κ < 0.6 提示“一致性偏低，结论需谨慎”
- 结果不进入任何学生端指标
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import AnalysisLabel, Attempt, ChatMessage, ChatSession, Enrollment, Explanation, Problem
from .llm import LlmClient
from .llm_hints import load_prompt

ICAP_VERSION = "icap_v1"
LABELS = ("P", "A", "C", "I")
BATCH = 20


def consented_ids(db: DbSession, class_id: int) -> list[int]:
    return list(db.scalars(select(Enrollment.user_id).where(
        Enrollment.class_id == class_id, Enrollment.consent_status == "accepted")).all())


def collect_items(db: DbSession, class_id: int, start: datetime | None, end: datetime | None) -> list[dict]:
    ids = consented_ids(db, class_id) or [-1]
    done = {(t, i) for t, i in db.execute(select(AnalysisLabel.target_type, AnalysisLabel.target_id).where(
        AnalysisLabel.prompt_version == ICAP_VERSION)).all()}
    titles = {p.id: p.title for p in db.scalars(select(Problem)).all()}
    items = []
    q = select(Explanation, Attempt).join(Attempt, Attempt.id == Explanation.attempt_id).where(Attempt.user_id.in_(ids))
    for e, a in db.execute(q.order_by(Explanation.id)).all():
        if (start and e.created_at < start) or (end and e.created_at >= end) or ("explanation", e.id) in done:
            continue
        items.append({"target_type": "explanation", "target_id": e.id, "id": f"e{e.id}", "context": "探究解释",
                      "problem": titles.get(a.problem_id, a.problem_id), "text": e.text})
    q = select(ChatMessage, ChatSession).join(ChatSession, ChatSession.id == ChatMessage.session_id).where(
        ChatSession.user_id.in_(ids), ChatMessage.role == "user")
    for m, s in db.execute(q.order_by(ChatMessage.id)).all():
        if (start and m.created_at < start) or (end and m.created_at >= end) or ("chat_message", m.id) in done:
            continue
        prev = db.scalar(select(ChatMessage).where(ChatMessage.session_id == s.id, ChatMessage.id < m.id,
                                                   ChatMessage.role == "assistant").order_by(ChatMessage.id.desc()))
        items.append({"target_type": "chat_message", "target_id": m.id, "id": f"m{m.id}", "context": "助教对话",
                      "problem": titles.get(s.problem_id, s.problem_id), "text": m.content,
                      "previous_reply": prev.content if prev else ""})
    return items


def parse_output(raw: str, ids: set[str]) -> dict[str, dict]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    out = {}
    for it in (data.get("items") if isinstance(data, dict) else None) or []:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", "")).strip().upper()[:1]
        if it.get("id") in ids and label in LABELS:
            out[it["id"]] = {"label": label, "rationale": str(it.get("rationale", ""))[:80]}
    return out


def run_icap(db: DbSession, llm: LlmClient, class_id: int, start: datetime | None = None,
             end: datetime | None = None) -> dict:
    reason = llm.unavailable_reason(db)
    if reason:
        raise RuntimeError(f"大模型不可用（{reason}），ICAP 编码需要大模型")
    items = collect_items(db, class_id, start, end)
    system = load_prompt("icap_system_v1.md")
    labeled = failed = 0
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        public = [{k: v for k, v in it.items() if k not in ("target_type", "target_id")} for it in batch]
        pending = {it["id"] for it in batch}
        results: dict[str, dict] = {}
        call = None
        for _ in range(2):                   # 有条目没给出合法标签时，只把这些条目再发一次
            todo = [x for x in public if x["id"] in pending - set(results)]
            if not todo:
                break
            messages = [{"role": "system", "content": system},
                        {"role": "user", "content": json.dumps({"items": todo}, ensure_ascii=False)}]
            res = llm.complete_json(db, purpose="icap", prompt_version=ICAP_VERSION, messages=messages,
                                    max_tokens=4000, thinking=True)
            if not res.ok:
                break
            call = res.call
            results.update(parse_output(res.content, {x["id"] for x in todo}))
        for it in batch:
            r = results.get(it["id"])
            if r is None:
                failed += 1
                continue
            db.add(AnalysisLabel(class_id=class_id, target_type=it["target_type"], target_id=it["target_id"],
                                 label=r["label"], rationale=r["rationale"], model=call.model if call else None,
                                 prompt_version=ICAP_VERSION, llm_call_id=call.id if call else None))
            labeled += 1
        db.commit()
    return {"items": len(items), "labeled": labeled, "failed": failed}


def ensure_sample(db: DbSession, class_id: int, rate: float = 0.1) -> list[AnalysisLabel]:
    """抽检样本：第一次请求时随机抽 10%（至少 1 条）并固定下来；之后新增的编码按同样比例补抽。"""
    rows = list(db.scalars(select(AnalysisLabel).where(AnalysisLabel.class_id == class_id,
                                                       AnalysisLabel.prompt_version == ICAP_VERSION)
                           .order_by(AnalysisLabel.id)).all())
    if not rows:
        return []
    want = max(1, math.ceil(len(rows) * rate))
    have = [r for r in rows if r.sampled]
    if len(have) < want:
        rng = random.Random(class_id * 7919 + len(rows))
        rest = [r for r in rows if not r.sampled]
        for r in rng.sample(rest, min(want - len(have), len(rest))):
            r.sampled = True
        db.commit()
    return [r for r in rows if r.sampled]


def cohen_kappa(pairs: list[tuple[str, str]]) -> dict:
    """κ = (p_o − p_e) / (1 − p_e)；p_e 为按双方各自标签分布算出的偶然一致概率。"""
    n = len(pairs)
    if n == 0:
        return {"n": 0, "p_o": None, "p_e": None, "kappa": None}
    p_o = sum(1 for a, h in pairs if a == h) / n
    p_e = sum((sum(1 for a, _ in pairs if a == k) / n) * (sum(1 for _, h in pairs if h == k) / n) for k in LABELS)
    kappa = None if p_e == 1 else (p_o - p_e) / (1 - p_e)
    return {"n": n, "p_o": p_o, "p_e": p_e, "kappa": kappa}


def target_text(db: DbSession, row: AnalysisLabel) -> dict:
    if row.target_type == "explanation":
        e = db.get(Explanation, row.target_id)
        a = db.get(Attempt, e.attempt_id) if e else None
        return {"text": e.text if e else "", "context": "探究解释", "problem_id": a.problem_id if a else None}
    m = db.get(ChatMessage, row.target_id)
    s = db.get(ChatSession, m.session_id) if m else None
    return {"text": m.content if m else "", "context": "助教对话", "problem_id": s.problem_id if s else None}
