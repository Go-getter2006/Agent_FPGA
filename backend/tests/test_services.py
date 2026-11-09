"""规则提示、复习调度、题目同步、数据库迁移。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.config import REPO_ROOT
from backend.app.db import SessionLocal
from backend.app.models import Problem, ReviewItem
from backend.app.services import fallback_hints, review_scheduler
from judge import diagnose

PROBLEMS = REPO_ROOT / "problems"


# ---------------------------------------------------------------- 规则提示

def _looks_like_code(text: str) -> bool:
    """与 docs/llm-deepseek.md 5.3 第 3 条相同的“泄露代码”判据。"""
    if "```" in text or ("module" in text and "endmodule" in text):
        return True
    lines = [ln.strip() for ln in text.splitlines()]
    codey = [ln for ln in lines if re.match(r"^(assign|always|reg|wire|if|case)\b", ln) or "<=" in ln]
    return len(codey) >= 2


@pytest.mark.parametrize("tag", list(fallback_hints.TEMPLATES))
def test_every_tag_has_three_levels(tag):
    assert set(fallback_hints.TEMPLATES[tag]) == {1, 2, 3}
    for message, question in fallback_hints.TEMPLATES[tag].values():
        assert question.endswith("？") and len(message) <= 200
        assert not _looks_like_code(message + "\n" + question)


# 每个标签至少一个代表样本（全部样本的标签已在 judge 测试里覆盖）
HINT_CASES = [
    ("seq_detector_101", "c1_no_overlap.v"), ("seq_detector_101", "c3_latch.v"),
    ("seq_detector_101", "c6_fragile_multidrive.v"), ("seq_detector_101", "c7_compile.v"),
    ("prio_encoder4", "c3_fragile_while.v"), ("prio_encoder4", "c4_width.v"),
    ("shift_reg4", "c1_blocking_order.v"), ("adder4", "c4_fragile_latch.v"),
]


def _cases():
    for pid, name in HINT_CASES:
        yield pid, PROBLEMS / pid / "cases" / name


@pytest.fixture(scope="module")
def case_diagnoses():
    out = {}
    for pid, case in _cases():
        code = case.read_text(encoding="utf-8").split("\n", 1)[1]
        out[(pid, case.name)] = diagnose(code, pid, log=False)
    return out


def test_hints_filled_for_every_case_and_level(case_diagnoses):
    seen_tags = set()
    for (pid, name), diag in case_diagnoses.items():
        for level in (1, 2, 3):
            hint = fallback_hints.generate(diag, level, quadrant="concept_gap")
            text = hint["message"] + hint["question"]
            assert "{" not in text and "}" not in text, (pid, name, level, text)
            assert not _looks_like_code(text)
            assert hint["level"] == level
            for line in hint["focus"]["lines"]:
                assert isinstance(line, int) and line >= 1
            seen_tags.add(hint["tag"])
    # 错误样本覆盖了大多数标签对应的模板
    assert {"compile_error", "latch_inferred", "multi_driven", "sim_mismatch", "width_mismatch",
            "non_synthesizable", "blocking_in_seq"} <= seen_tags


def test_sim_mismatch_level1_matches_doc_example(case_diagnoses):
    diag = case_diagnoses[("seq_detector_101", "c1_no_overlap.v")]
    hint = fallback_hints.generate(diag, 1)
    assert hint["message"] == "先看第 5 步的 out：期望 1，实际 0。这一步之前，out 由第 16 行决定。"
    assert hint["question"] == "它们在这个时钟沿做了什么？"
    assert hint["focus"] == {"step": 5, "signal": "out", "lines": [16]}   # 样本去掉了第一行标注


def test_pass_and_prediction_miss_hints():
    diag = {"compile": {"ok": True}, "sim": {"ok": True, "trace": [], "first_mismatch": None},
            "tags": [], "drivers": {"q": [10]}, "lint": [], "hardware": {}, "synth": {"messages": []}}
    assert fallback_hints.generate(diag, 1)["tag"] == "pass"
    evaluation = {"waveform": {"cells": [{"signal": "q", "step": 3, "value": "0", "actual": "1", "correct": False}]},
                  "hardware": {"items": []}}
    hint = fallback_hints.generate(diag, 1, evaluation=evaluation, quadrant="fragile")
    assert hint["tag"] == "pred_miss" and "你预测 0，实际是 1" in hint["message"]
    assert hint["focus"]["lines"] == [10]


# ---------------------------------------------------------------- 复习调度

class _Item:
    def __init__(self, box: int):
        self.box, self.status, self.last_result, self.due_at = box, "active", None, None


NOW = datetime(2026, 11, 9, 4, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("box, correct, new_box, days, status", [
    (1, True, 2, 3, "active"),      # 答对进入下一个盒子：间隔 3 天
    (2, True, 3, 7, "active"),
    (3, True, 4, 14, "active"),
    (4, True, 4, None, "done"),     # 第 4 个盒子答对后移出队列
    (3, False, 1, 1, "active"),     # 答错回到第 1 个盒子
])
def test_review_boxes(box, correct, new_box, days, status):
    item = _Item(box)
    review_scheduler.apply_answer(item, correct, now=NOW)
    assert (item.box, item.status) == (new_box, status)
    if days is not None:
        assert item.due_at == NOW + timedelta(days=days)


def test_review_daily_limit_and_priority(db):
    from backend.tests.conftest import make_user
    user = make_user()
    problem = db.get(Problem, "counter_mod10")
    q = {"kind": "waveform", "predict_points": [], "skeleton": problem.meta["skeleton"], "answer": {}}
    now = datetime.now(timezone.utc)
    for k in range(7):     # 7 条都已到期，到期越久越优先
        db.add(ReviewItem(user_id=user.id, knowledge_point=f"kp{k}", problem_id="counter_mod10", box=1,
                          due_at=now - timedelta(days=k + 1), question=q))
    db.add(ReviewItem(user_id=user.id, knowledge_point="future", problem_id="counter_mod10", box=1,
                      due_at=now + timedelta(days=1), question=q))
    db.commit()
    items, remaining = review_scheduler.due_items(db, user.id)
    assert remaining == 5 and len(items) == 5
    assert [i.knowledge_point for i in items] == ["kp6", "kp5", "kp4", "kp3", "kp2"]


# ---------------------------------------------------------------- 题目同步

def test_problem_sync_meta(db):
    problems = {p.id: p for p in db.scalars(select(Problem)).all()}
    assert set(problems) >= {"seq_detector_101", "swap_regs"}
    p = problems["seq_detector_101"]
    sk = p.meta["skeleton"]
    assert [i["name"] for i in sk["inputs"]] == ["rst", "in"] and len(sk["inputs"][0]["values"]) == len(sk["steps"])
    assert sk["outputs"] == [{"name": "out", "width": 1}]          # 预测前只给输出的名字和位宽
    assert problems["adder4"].meta["starter_eval"]["sim"]["trace"]   # 复习题的标准答案
    assert p.meta["starter_eval"] is None


# ---------------------------------------------------------------- 数据库迁移

def test_alembic_upgrade_matches_models(tmp_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'mig.db'}"}
    cfg = str(REPO_ROOT / "backend" / "alembic.ini")
    up = subprocess.run([sys.executable, "-m", "alembic", "-c", cfg, "upgrade", "head"],
                        cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert up.returncode == 0, up.stderr
    check = subprocess.run([sys.executable, "-m", "alembic", "-c", cfg, "check"],
                           cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
