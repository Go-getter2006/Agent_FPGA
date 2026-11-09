"""大模型分级提示（docs/llm-deepseek.md 第 4、5 节）：组织提示词 → 调用 → 校验 → 不通过重试一次 → 仍不通过降级为规则提示。

消息顺序固定为 system → user 第一段（本题信息，同题所有学生相同，能命中缓存）→ user 第二段（本次诊断）。
第 2 版（hint_v2）：1 思路 → 2 定位 → 3 代码提示（code 字段给代码框架）；第 4 级参考答案见 services/answer.py。
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..models import Attempt, Hint, KnowledgePoint, Problem
from . import fallback_hints
from .hint_guard import validate_hint_v2
from .llm import LlmClient

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
HINT_VERSION = "hint_v2"
LEVEL_NAMES = {1: "思路", 2: "定位", 3: "代码提示"}
MAX_SPEC_CHARS = 1500


def load_prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8").strip()


def _strip_comments(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("<!--")).strip()


def problem_segment(db: DbSession, problem: Problem) -> str:
    names = {k.code: k.name for k in db.scalars(select(KnowledgePoint)).all()}
    kps = "、".join(names.get(k, k) for k in problem.knowledge_points)
    spec = problem.meta.get("spec", "").strip()[:MAX_SPEC_CHARS]
    return f"【题目】{problem.title}（知识点：{kps}）\n【题目说明】{spec}"


def numbered(code: str) -> str:
    return "\n".join(f"{i:>3} | {line}" for i, line in enumerate(code.splitlines(), start=1))


def judge_compact(judge: dict) -> str:
    sim = judge.get("sim") or {}
    compact = {
        "compile": judge.get("compile"),
        "sim_ok": sim.get("ok"),
        "timeout": sim.get("timeout"),
        "first_mismatch": sim.get("first_mismatch"),
        "hardware": judge.get("hardware"),
        "tags": judge.get("tags"),
        "drivers": judge.get("drivers"),
    }
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


def prediction_diff(evaluation: dict | None) -> str:
    if not evaluation:
        return "（本次没有预测）"
    parts = []
    for c in evaluation["waveform"]["cells"]:
        state = "无法判定" if c["correct"] is None else ("一致" if c["correct"] else "不一致")
        parts.append(f"{c['signal']} STEP {c['step']}：预测 {c['value']}，实际 {c['actual']}，{state}")
    for it in evaluation["hardware"]["items"]:
        state = "无法判定" if it["correct"] is None else ("一致" if it["correct"] else "不一致")
        parts.append(f"{it['question']}：预测 {it['value']}，实际 {it['actual']}，{state}")
    return "；".join(parts) if parts else "（本次没有预测）"


def student_segment(db: DbSession, attempt: Attempt, level: int) -> str:
    max_level = db.scalar(select(func.max(Hint.level)).join(Attempt, Attempt.id == Hint.attempt_id).where(
        Attempt.user_id == attempt.user_id, Attempt.problem_id == attempt.problem_id)) or 0
    recent = db.scalars(select(Attempt).where(
        Attempt.user_id == attempt.user_id, Attempt.status == "done", Attempt.id != attempt.id)
        .order_by(Attempt.id.desc()).limit(3)).all()
    recent_tags = sorted({t for a in recent for t in (a.judge or {}).get("tags", [])}) or ["无"]
    return "\n".join([
        "【学生代码（带行号）】",
        numbered(attempt.code),
        f"【诊断】{judge_compact(attempt.judge or {})}",
        f"【预测对照】{prediction_diff((attempt.analysis or {}).get('evaluation'))}",
        f"【学生状态】象限：{attempt.quadrant or 'none'}；本题已用最高提示等级：{max_level}；最近误区：{'、'.join(recent_tags)}",
        f"【请求】给出 {level} 级提示（{LEVEL_NAMES.get(level, '')}）",
    ])


def _clocked(problem: Problem) -> bool:
    names = {i["name"] for i in (problem.meta.get("skeleton") or {}).get("inputs", [])}
    return bool(names & {"clk", "rst"})


def build_messages(db: DbSession, problem: Problem, attempt: Attempt, level: int) -> list[dict]:
    return [
        {"role": "system", "content": load_prompt("hint_system_v2.md")},
        {"role": "user", "content": problem_segment(db, problem)},
        {"role": "user", "content": student_segment(db, attempt, level)},
    ]


def generate_hint(db: DbSession, llm: LlmClient, *, attempt: Attempt, problem: Problem, level: int,
                  llm_enabled: bool, shuffle: dict | None = None, thinking: bool = False,
                  purpose: str = "hint") -> dict:
    """返回 {"content", "source", "llm_call_id", "fallback_reason"}。任何失败都降级为规则提示。"""
    def fallback(reason: str, call_id: int | None = None) -> dict:
        content = fallback_hints.generate_v2(attempt.judge or {}, level,
                                             evaluation=(attempt.analysis or {}).get("evaluation"),
                                             quadrant=attempt.quadrant, shuffle=shuffle,
                                             problem_kps=problem.knowledge_points,
                                             skeleton=problem.meta.get("code_skeleton"),
                                             clocked=_clocked(problem))
        return {"content": content, "source": "fallback", "llm_call_id": call_id, "fallback_reason": reason}

    if not llm_enabled:
        return fallback("disabled")
    messages = build_messages(db, problem, attempt, level)
    code_lines = len(attempt.code.splitlines())
    drivers = (attempt.judge or {}).get("drivers") or {}
    last_call = None
    for round_ in range(2):          # 不通过：追加违规原因重试 1 次
        result = llm.complete_json(db, purpose=purpose, prompt_version=HINT_VERSION, messages=messages,
                                   temperature=0.3, max_tokens=4000 if thinking else 800, thinking=thinking,
                                   user_id=attempt.user_id)
        if not result.ok:
            return fallback(result.reason or "error", result.call.id if result.call else None)
        last_call = result.call
        check = validate_hint_v2(result.content, level=level, code_lines=code_lines, drivers=drivers,
                                 ref_code=problem.meta.get("ref_code"))
        last_call.validation = {"ok": check["ok"], "reasons": check["reasons"], "warnings": check["warnings"],
                                "round": round_ + 1}
        if check["ok"]:
            content = {**check["hint"], "prompt_version": HINT_VERSION, "model": last_call.model}
            return {"content": content, "source": "llm", "llm_call_id": last_call.id, "fallback_reason": None}
        last_call.status = "invalid"
        messages = [*messages[:-1], {"role": "user", "content": messages[-1]["content"]
                                     + f"\n上次输出违反规则：{'；'.join(check['reasons'])}，请重新生成"}]
    return fallback("invalid", last_call.id if last_call else None)
