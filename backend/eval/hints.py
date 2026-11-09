"""提示质量评测（docs/llm-deepseek.md 第 12 节）。

    DEEPSEEK_API_KEY=... python -m backend.eval.hints --problems problems/ --prompt hint_v1 --levels 1,2,3

对每道题的每个错误样本，按 1–3 级各生成一条提示，导出 CSV：题目、样本、等级、提示原文、校验结果，
另留出四列人工评分（准确、不泄露答案、引导性、易懂，1–5 分）。不使用大模型给大模型打分。
要比较的方案（思考模式开 / 关、提示词版本）各跑一遍，用 summarize.py 汇总。

- 样本代码去掉开头的注释（// expect 与“错误：……”说明），与学生提交的代码一致
- 没有预测数据，象限默认按仿真结果推定：通过 → fragile，没通过 → concept_gap（可用 --quadrant 指定）
- 调用日志写进一个临时 SQLite 库，不碰正式数据库
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

FIELDS = [
    "problem", "sample", "expected_tags", "judge_tags", "level", "quadrant", "source", "fallback_reason",
    "prompt_version", "model", "thinking", "message", "question", "focus_step", "focus_signal", "focus_lines",
    "validation_ok", "validation_reasons", "retries", "latency_ms", "prompt_tokens", "cache_hit_tokens",
    "completion_tokens", "cost_cny",
    "score_accuracy", "score_no_leak", "score_guidance", "score_clarity", "rater", "note",
]
PROMPTS = {"hint_v1"}


def strip_header(text: str) -> str:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and lines[i].lstrip().startswith("//"):
        i += 1
    return "\n".join(lines[i:]) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="提示质量评测：生成待人工评分的 CSV")
    ap.add_argument("--problems", default="problems/")
    ap.add_argument("--prompt", default="hint_v1", choices=sorted(PROMPTS))
    ap.add_argument("--levels", default="1,2,3")
    ap.add_argument("--quadrant", default="auto", choices=["auto", "mastered", "fragile", "design_gap", "concept_gap"])
    ap.add_argument("--thinking", default="off", choices=["off", "on"])
    ap.add_argument("--only", default="", help="只评测这些题目（逗号分隔）")
    ap.add_argument("--limit", type=int, default=0, help="最多评测多少个样本（0 表示全部）")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    # 调用日志写进临时库（必须在导入后端模块之前设置）
    tmp = Path(tempfile.mkdtemp(prefix="eval_hints_"))
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp / 'eval.db'}"
    os.environ.setdefault("JUDGE_LOG_PATH", str(tmp / "judge.jsonl"))

    from judge import diagnose
    from judge.problem import read_expected_tags
    from backend.app import models  # noqa: F401
    from backend.app.db import Base, SessionLocal, engine
    from backend.app.models import Attempt, Problem
    from backend.app.services.llm import get_llm
    from backend.app.services.llm_hints import HINT_VERSION, generate_hint
    from backend.app.services.problems_sync import sync_knowledge_points

    Base.metadata.create_all(engine)
    llm = get_llm()
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    root = Path(args.problems)
    out = Path(args.out or f"backend/eval/results/hints_{args.prompt}_think-{args.thinking}_{datetime.now():%Y%m%d_%H%M}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        sync_knowledge_points(db)
        db.commit()
        reason = llm.unavailable_reason(db)
        if reason:
            print(f"大模型不可用（{reason}），提示将全部来自规则模板；如需评测大模型，请设置 DEEPSEEK_API_KEY", file=sys.stderr)
        rows = []
        n = 0
        for pdir in sorted(p for p in root.iterdir() if (p / "problem.yaml").is_file()):
            if only and pdir.name not in only:
                continue
            meta = yaml.safe_load((pdir / "problem.yaml").read_text(encoding="utf-8"))
            problem = Problem(id=pdir.name, title=meta["title"], knowledge_points=meta["knowledge_points"],
                              primm_type=meta["primm_type"], difficulty=meta["difficulty"],
                              meta={"spec": (pdir / "spec.md").read_text(encoding="utf-8")})
            for case in sorted((pdir / "cases").glob("*.v")):
                if args.limit and n >= args.limit:
                    break
                n += 1
                code = strip_header(case.read_text(encoding="utf-8"))
                judge = diagnose(code, pdir.name, problems_dir=root, log=False)
                sim_ok = bool(judge["compile"]["ok"] and judge["sim"]["ok"])
                quadrant = args.quadrant if args.quadrant != "auto" else ("fragile" if sim_ok else "concept_gap")
                attempt = Attempt(id=None, user_id=0, problem_id=pdir.name, attempt_no=1, step="run", code=code,
                                  code_hash="", status="done", judge=judge, sim_ok=sim_ok, quadrant=quadrant,
                                  analysis=None)
                for level in levels:
                    res = generate_hint(db, llm, attempt=attempt, problem=problem, level=level, llm_enabled=True,
                                        thinking=args.thinking == "on", purpose="eval_hint")
                    db.commit()
                    from backend.app.models import LlmCall
                    call = db.get(LlmCall, res["llm_call_id"]) if res["llm_call_id"] else None
                    c = res["content"]
                    tokens = (call.tokens or {}) if call else {}
                    validation = (call.validation or {}) if call else {}
                    rows.append({
                        "problem": pdir.name, "sample": case.name,
                        "expected_tags": ",".join(read_expected_tags(case)), "judge_tags": ",".join(judge["tags"]),
                        "level": level, "quadrant": quadrant, "source": res["source"],
                        "fallback_reason": res["fallback_reason"] or "",
                        "prompt_version": HINT_VERSION if res["source"] == "llm" else "fallback_v1",
                        "model": call.model if call and call.model else "", "thinking": args.thinking,
                        "message": c["message"], "question": c["question"],
                        "focus_step": c["focus"].get("step") if c.get("focus") else "",
                        "focus_signal": c["focus"].get("signal") if c.get("focus") else "",
                        "focus_lines": " ".join(str(x) for x in (c.get("focus") or {}).get("lines", [])),
                        "validation_ok": validation.get("ok", "") if call else "",
                        "validation_reasons": "；".join(validation.get("reasons", [])),
                        "retries": call.retries if call else "", "latency_ms": call.latency_ms if call else "",
                        "prompt_tokens": tokens.get("prompt", ""), "cache_hit_tokens": tokens.get("cache_hit", ""),
                        "completion_tokens": tokens.get("completion", ""),
                        "cost_cny": f"{call.cost_cny:.6f}" if call else "",
                    })
                    print(f"{pdir.name}/{case.name} L{level}: {res['source']} {res['fallback_reason'] or ''}", file=sys.stderr)

    with out.open("w", encoding="utf-8-sig", newline="") as f:      # utf-8-sig：Excel 打开不乱码
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"共 {len(rows)} 条提示，已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
