"""汇总人工评分（docs/llm-deepseek.md 第 12 节）：各项均分和违规率。

    python -m backend.eval.summarize 评分后的.csv [更多.csv] --by prompt_version,thinking

- 四项评分（准确、不泄露答案、引导性、易懂）取 1–5 分，空着的不计入均分
- 违规率：大模型输出没通过校验（含重试后仍降级为规则提示）的比例
- 降级率：最终显示的是规则提示的比例（含不可用、校验不通过）
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict

SCORES = [("score_accuracy", "准确"), ("score_no_leak", "不泄露答案"), ("score_guidance", "引导性"),
          ("score_clarity", "易懂")]


def _num(v: str) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if 1 <= x <= 5 else None


def summarize(rows: list[dict], by: list[str]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k, "") for k in by)].append(r)
    out = []
    for key, items in sorted(groups.items()):
        entry = {k: v for k, v in zip(by, key)}
        entry["n"] = len(items)
        for col, _ in SCORES:
            vals = [x for x in (_num(r.get(col)) for r in items) if x is not None]
            entry[col] = round(sum(vals) / len(vals), 2) if vals else None
            entry[f"{col}_rated"] = len(vals)
        invalid = [r for r in items if str(r.get("validation_ok")).lower() == "false" or r.get("fallback_reason") == "invalid"]
        entry["violation_rate"] = round(len(invalid) / len(items), 3)
        entry["fallback_rate"] = round(sum(1 for r in items if r.get("source") == "fallback") / len(items), 3)
        costs = [float(r["cost_cny"]) for r in items if r.get("cost_cny")]
        entry["cost_cny_total"] = round(sum(costs), 4)
        lat = [float(r["latency_ms"]) for r in items if r.get("latency_ms")]
        entry["latency_ms_avg"] = round(sum(lat) / len(lat)) if lat else None
        out.append(entry)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="汇总提示质量的人工评分")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--by", default="prompt_version,thinking", help="分组字段，逗号分隔")
    args = ap.parse_args(argv)
    rows = []
    for path in args.files:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows.extend(csv.DictReader(f))
    by = [x.strip() for x in args.by.split(",") if x.strip()]
    result = summarize(rows, by)
    head = by + ["n"] + [name for _, name in SCORES] + ["违规率", "降级率", "费用（元）", "平均耗时（ms）"]
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for e in result:
        cells = [str(e[k]) for k in by] + [str(e["n"])]
        cells += ["—" if e[c] is None else f"{e[c]}（{e[c + '_rated']} 条）" for c, _ in SCORES]
        cells += [f"{e['violation_rate']:.1%}", f"{e['fallback_rate']:.1%}", str(e["cost_cny_total"]),
                  str(e["latency_ms_avg"] or "—")]
        print("| " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
