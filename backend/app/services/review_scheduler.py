"""提取练习（复习）调度（docs/learner-model.md 第 5 节）。

- 触发：某次尝试落在 fragile 或 concept_gap，就把该题关联知识点的一道预测题加入复习队列，
  优先选同知识点的其他题（有起始代码的预测题、修改题）；没有时用学生自己这次的代码
- 4 个盒子，间隔 1、3、7、14 天；答对进入下一个盒子，答错回到第 1 个，第 4 个盒子答对后移出
- 每天最多推送 5 条，到期越久越优先
- 题目的标准答案来自裁判对那份代码的仿真与综合结果，只存在服务端
- 误区复盘（find_bug，2026-11）：某次提交出现代码层面的问题标签（锁存器、阻塞赋值用错、位宽……），
  就从错误样本库里挑一份“别的题、同样问题”的代码，让学生选出它的问题；每个标签同时最多 1 条
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import utcnow
from judge.problem import list_problem_ids, load_problem, read_expected_tags

from ..models import Attempt, Event, Problem, ReviewItem
from .fallback_hints import TAG_CONCEPTS
from .learner_model import TAG_LABELS, evaluate_prediction, prediction_ok

INTERVAL_DAYS = {1: 1, 2: 3, 3: 7, 4: 14}
TRIGGER_QUADRANTS = ("fragile", "concept_gap")
BEIJING = timezone(timedelta(hours=8))


def _question_from(problem: Problem, code: str, source: str, answer: dict, kind: str) -> dict:
    meta = problem.meta
    return {
        "source": source,
        "kind": kind,
        "code": code,
        "predict_points": meta["predict_points"],
        "hardware_questions": meta["hardware_questions"] if kind == "hardware" else [],
        "skeleton": meta["skeleton"],
        "answer": answer,           # {"sim": {"trace": [...]}, "hardware": {...}}；返回给学生前去掉
    }


def _answer_from_judge(judge: dict) -> dict:
    return {"sim": {"trace": judge["sim"]["trace"]}, "hardware": judge.get("hardware")}


def choose_review(db: DbSession, attempt: Attempt, kp: str, kind: str,
                  exclude: set[str] | frozenset[str] = frozenset()) -> tuple[Problem, dict] | None:
    """exclude：已经在复习队列里的题，换一道（一题关联多个知识点时避免重复）。"""
    candidates = db.scalars(select(Problem).order_by(Problem.id)).all()
    others = [p for p in candidates if kp in p.knowledge_points and p.id != attempt.problem_id
              and p.id not in exclude and p.meta.get("starter") and p.meta.get("starter_eval")]
    if others:
        p = others[0]
        return p, _question_from(p, p.meta["starter"], "starter", p.meta["starter_eval"], kind)
    if attempt.judge and attempt.judge["compile"]["ok"] and attempt.judge["sim"]["trace"]:
        p = db.get(Problem, attempt.problem_id)
        return p, _question_from(p, attempt.code, "attempt", _answer_from_judge(attempt.judge), kind)
    return None


def enqueue_for_attempt(db: DbSession, attempt: Attempt, problem: Problem, misconceptions: list[str],
                        now: datetime | None = None) -> list[ReviewItem]:
    if attempt.quadrant not in TRIGGER_QUADRANTS:
        return []
    now = now or utcnow()
    kind = "hardware" if {"pred_ff_confusion", "pred_latch_blind"} & set(misconceptions) else "waveform"
    added = []
    active = db.scalars(select(ReviewItem).where(ReviewItem.user_id == attempt.user_id,
                                                 ReviewItem.status == "active")).all()
    for kp in problem.knowledge_points:
        # 同一知识点只留 1 条预测类复习；“找 bug”复习单独计（按问题标签）
        if any(i.knowledge_point == kp and i.question.get("kind") != "find_bug" for i in active):
            continue
        queued = {i.problem_id for i in [*active, *added] if i.question.get("kind") != "find_bug"}
        chosen = choose_review(db, attempt, kp, kind, exclude=queued)
        if chosen is None:
            continue
        p, question = chosen
        # 同一道题、同一种预测只留 1 条（一题关联多个知识点时，不同知识点可能选中同一道复习题）
        if any(i.problem_id == p.id and i.question.get("kind") == question["kind"]
               and i.question.get("source") == question["source"] for i in [*active, *added]):
            continue
        item = ReviewItem(user_id=attempt.user_id, knowledge_point=kp, problem_id=p.id, box=1,
                          due_at=now + timedelta(days=INTERVAL_DAYS[1]), status="active",
                          source_attempt_id=attempt.id, question=question)
        db.add(item)
        added.append(item)
    return added


# ---------------------------------------------------------------- 误区复盘：看代码，选出它的问题

# 能出“找 bug”题的标签（代码层面、裁判能直接判出、样本库里有样本）；按优先级排列。
# 不在其中的：race_order_sensitive 来自顺序打乱实验，不是普通判题的标签；nonblocking_in_comb 目前样本库里没有样本
# （加样本会改变该题 testbench 打分用的错误电路集合，需要先确认）
BUG_TAGS = ("latch_inferred", "blocking_in_seq", "multi_driven", "width_mismatch", "non_synthesizable", "compile_error")
BUG_LABELS = {**TAG_LABELS, "compile_error": "语法错误，编译不通过"}
_case_cache: dict[str, list[dict]] = {}


def bug_cases(problems_dir=None) -> list[dict]:
    """错误样本库：每份样本的代码（去掉开头的注释）、预期标签和说明。"""
    key = str(problems_dir or "")
    if key not in _case_cache:
        out = []
        for pid in list_problem_ids(problems_dir):
            prob = load_problem(pid, problems_dir)
            for path in prob.case_paths():
                lines = path.read_text(encoding="utf-8").splitlines()
                head = 0
                while head < len(lines) and lines[head].lstrip().startswith("//"):
                    head += 1
                explain = [ln.lstrip("/ ").strip() for ln in lines[:head] if not ln.lstrip("/ ").startswith("expect")]
                out.append({"id": f"{pid}/{path.name}", "problem_id": pid, "tags": read_expected_tags(path),
                            "code": "\n".join(lines[head:]).strip() + "\n", "explain": "".join(explain)})
        _case_cache[key] = out
    return _case_cache[key]


def _options(case: dict, tag: str, seed: str) -> list[dict]:
    """正确选项 + 3 个干扰项（不含这份样本的其他预期标签），顺序由 seed 决定（确定性）。"""
    import random
    distract = [t for t in BUG_TAGS if t not in case["tags"]]
    rng = random.Random(seed)
    picks = rng.sample(distract, 3) + [tag]
    rng.shuffle(picks)
    return [{"code": t, "label": BUG_LABELS[t]} for t in picks]


def enqueue_find_bug(db: DbSession, attempt: Attempt, now: datetime | None = None) -> ReviewItem | None:
    """这次提交出现了代码层面的问题标签：加一条“找 bug”复习（同一标签同时只有 1 条）。"""
    tags = [t for t in BUG_TAGS if t in ((attempt.judge or {}).get("tags") or [])]
    if not tags:
        return None
    active = db.scalars(select(ReviewItem).where(ReviewItem.user_id == attempt.user_id)).all()
    open_tags = {i.question.get("tag") for i in active if i.status == "active" and i.question.get("kind") == "find_bug"}
    used = {i.question.get("case") for i in active if i.question.get("kind") == "find_bug"}
    for tag in tags:
        if tag in open_tags:
            continue
        cands = [c for c in bug_cases() if tag in c["tags"] and c["problem_id"] != attempt.problem_id]
        cands = [c for c in cands if c["id"] not in used] or cands
        if not cands:
            continue
        case = cands[0]
        problem = db.get(Problem, case["problem_id"])
        if problem is None:
            continue
        now = now or utcnow()
        kp = (TAG_CONCEPTS.get(tag) or problem.knowledge_points)[0]   # 记在这类问题对应的知识点上
        spec = (problem.meta.get("spec") or "").split("\n\n")
        task = next((para for para in spec if para.strip() and not para.startswith("#")), "")
        item = ReviewItem(user_id=attempt.user_id, knowledge_point=kp, problem_id=problem.id, box=1,
                          due_at=now + timedelta(days=INTERVAL_DAYS[1]), status="active", source_attempt_id=attempt.id,
                          question={"kind": "find_bug", "source": "case", "tag": tag, "case": case["id"],
                                    "code": case["code"], "task": task.strip(),
                                    "options": _options(case, tag, f"{attempt.user_id}:{case['id']}"),
                                    "answer": {"tags": case["tags"], "explain": case["explain"]}})
        db.add(item)
        return item
    return None


def start_of_beijing_day(now: datetime) -> datetime:
    local = now.astimezone(BEIJING)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def answered_today(db: DbSession, user_id: int, now: datetime) -> int:
    return db.scalar(select(func.count()).select_from(Event).where(
        Event.user_id == user_id, Event.type == "review.answer",
        Event.ts >= start_of_beijing_day(now))) or 0


def due_items(db: DbSession, user_id: int, now: datetime | None = None) -> tuple[list[ReviewItem], int]:
    """今天还能推送的到期条目（到期越久越优先），以及今天剩余条数。"""
    now = now or utcnow()
    remaining = max(0, get_settings().review_daily_limit - answered_today(db, user_id, now))
    items = db.scalars(select(ReviewItem).where(
        ReviewItem.user_id == user_id, ReviewItem.status == "active", ReviewItem.due_at <= now)
        .order_by(ReviewItem.due_at, ReviewItem.id).limit(remaining)).all()
    return list(items), remaining


def public_question(item: ReviewItem) -> dict:
    q = dict(item.question)
    q.pop("answer", None)
    return q


def grade(item: ReviewItem, answers: dict) -> dict:
    q = item.question
    if q.get("kind") == "find_bug":
        choice = answers.get("choice")
        correct = choice in q["answer"]["tags"]
        right = [o for o in q["options"] if o["code"] in q["answer"]["tags"]]
        return {"correct": correct, "evaluation": {"accuracy": 1.0 if correct else 0.0, "choice": choice,
                                                   "answer": right, "explain": q["answer"]["explain"]}}
    evaluation = evaluate_prediction(
        predict_points=q["predict_points"] if q["kind"] == "waveform" else [],
        hardware_questions=q.get("hardware_questions", []),
        waveform=answers.get("waveform") if q["kind"] == "waveform" else None,
        hardware=answers.get("hardware") if q["kind"] == "hardware" else None,
        diagnosis=q["answer"],
    )
    correct = bool(prediction_ok(evaluation["accuracy"], get_settings().pred_threshold))
    return {"evaluation": evaluation, "correct": correct}


def apply_answer(item: ReviewItem, correct: bool, now: datetime | None = None) -> None:
    now = now or utcnow()
    item.last_result = correct
    if correct:
        if item.box >= 4:
            item.status = "done"
        else:
            item.box += 1
            item.due_at = now + timedelta(days=INTERVAL_DAYS[item.box])
    else:
        item.box = 1
        item.due_at = now + timedelta(days=INTERVAL_DAYS[1])
