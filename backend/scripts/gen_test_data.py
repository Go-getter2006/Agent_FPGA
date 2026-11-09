"""阶段 5 验收用的测试数据：2 个分组、各 30 名虚拟学生、每人 20 次尝试，分布在最近 8 周。

    python -m backend.scripts.gen_test_data [--seed 2026]

裁判结果不是编出来的：先用真实裁判诊断每道题的参考答案、起始代码和全部错误样本，
再按概率把这些诊断分给虚拟学生的尝试；预测、象限、误区都用 learner_model 里的同一套函数计算。
事件、提示、解释、对话、testbench、顺序打乱实验都带上与尝试一致的时间戳。

刻意安排了几类情况，让教师端预警规则都有命中：
- 一些学生近 7 天没有任何操作；一些学生反复提交但从不看波形（盲改）
- 一些学生在同一知识点上连续“概念未通”；少数学生拒绝参与研究或还没选择
"""
from __future__ import annotations

import argparse
import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from judge import diagnose
from judge.problem import load_problem

from backend.app import models  # noqa: F401
from backend.app.config import get_settings
from backend.app.db import Base, SessionLocal, engine, utcnow
from backend.app.models import (Assignment, Attempt, ChatMessage, ChatSession, Class, Enrollment, Explanation,
                                FeatureFlags, Hint, Investigation, Prediction, Problem, Progress, ShuffleRun,
                                TbSubmission, User)
from backend.app.services import fallback_hints
from backend.app.services.events import log_event
from backend.app.services.flags import DEFAULT_FLAGS
from backend.app.services.learner_model import (evaluate_prediction, prediction_misconceptions, prediction_ok,
                                                quadrant)
from backend.app.services.problems_sync import sync_all
from backend.app.services.security import anon_id_for, hash_password

PROBLEM_ORDER = ["prio_encoder4", "adder4", "counter_mod10", "shift_reg4", "seq_detector_101", "swap_regs"]
EXPLANATIONS = [
    "因为 out 写在时钟沿的块里，所以晚了一拍",
    "第 5 步对不上",
    "我把 = 改成 <= 了",
    "我猜是 case 没写 default，组合块里会保持旧值变成锁存器",
    "懂了",
    "S101 收到 0 应该回到 S10，我写成了 S0，所以重叠的 101 漏掉了",
    "阻塞赋值让后面的语句读到了新值，四位都变成了 d",
    "看了波形，进位没有加上",
]
CHATS = ["为什么第 5 步对不上？", "直接告诉我答案吧", "是不是复位的问题？", "那我应该看哪一行？",
         "你说的时钟沿之前是 S10，那我前面理解错了，应该是 S10 收到 1 之后去错了状态"]


def strip_header(text: str) -> str:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and lines[i].lstrip().startswith("//"):
        i += 1
    return "\n".join(lines[i:]) + "\n"


def variants(problems_dir: Path) -> dict[str, dict[str, tuple[str, dict]]]:
    """每道题的代码变体（ref / starter / 各错误样本）及其真实诊断。并行跑裁判。"""
    jobs = []
    for pid in PROBLEM_ORDER:
        p = load_problem(pid, problems_dir)
        jobs.append((pid, "ref", p.ref_path.read_text(encoding="utf-8")))
        if p.meta.get("starter"):
            jobs.append((pid, "starter", (p.dir / p.meta["starter"]).read_text(encoding="utf-8")))
        for case in p.case_paths():
            jobs.append((pid, case.stem, strip_header(case.read_text(encoding="utf-8"))))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda j: (j[0], j[1], j[2], diagnose(j[2], j[0], problems_dir=problems_dir, log=False)),
                                jobs))
    out: dict[str, dict[str, tuple[str, dict]]] = {}
    for pid, name, code, diag in results:
        out.setdefault(pid, {})[name] = (code, diag)
    return out


def fake_prediction(rng: random.Random, problem: Problem, diag: dict, skill: float) -> tuple[dict, dict]:
    """按“能力”概率生成预测：能力越高，每格预测对的概率越高。"""
    trace = {r["step"]: r["outputs"] for r in diag["sim"]["trace"]}
    widths = {o["name"]: o["width"] for o in problem.meta["skeleton"]["outputs"]}
    cells = []
    for point in problem.meta["predict_points"]:
        for step in point["steps"]:
            actual = trace.get(step, {}).get(point["signal"])
            w = widths[point["signal"]]
            if actual and set(actual) <= {"0", "1"} and rng.random() < skill:
                value = actual
            else:
                value = format(rng.randrange(2 ** w), f"0{w}b")
            cells.append({"signal": point["signal"], "step": step, "value": value})
    hw = diag.get("hardware") or {}
    right = rng.random() < skill
    hardware = {
        "ff_count": hw.get("ff_count") if right and hw.get("ff_count") is not None else rng.randrange(0, 9),
        "latch": bool(hw.get("latch_signals")) if right and hw.get("latch_signals") is not None else rng.random() < 0.3,
        "ff_signals": sorted(hw.get("ff_signals") or []) if rng.random() < skill else ["state"],
    }
    return {"cells": cells}, hardware


def generate(seed: int = 2026, per_group: int = 30, attempts_each: int = 20, weeks: int = 8,
             now: datetime | None = None, problems_dir: Path | None = None, create_tables: bool = True) -> dict:
    rng = random.Random(seed)
    now = now or utcnow()
    problems_dir = problems_dir or get_settings().problems_dir
    if create_tables:
        Base.metadata.create_all(engine)
    vs = variants(problems_dir)
    theta = get_settings().pred_threshold
    with SessionLocal() as db:
        sync_all(db)
        problems = {p.id: p for p in db.scalars(select(Problem)).all()}
        tag = hashlib.sha1(f"{seed}{now.isoformat()}".encode()).hexdigest()[:6]
        teacher = User(login_name=f"TG{tag}", display_name="生成数据教师", role="teacher",
                       password_hash=hash_password("generated-teacher"))
        db.add(teacher)
        db.flush()
        cls = Class(name=f"测试班级（生成 {tag}）", term="2026 秋", teacher_id=teacher.id)
        db.add(cls)
        db.flush()
        for g, flags in DEFAULT_FLAGS.items():
            db.add(FeatureFlags(class_id=cls.id, group=g, flags=flags))
        start = now - timedelta(weeks=weeks)
        db.add(Assignment(class_id=cls.id, title="作业 1：组合逻辑", group_scope="all",
                          problem_ids=PROBLEM_ORDER[:3], open_at=start, due_at=start + timedelta(weeks=3)))
        db.add(Assignment(class_id=cls.id, title="作业 2：时序与状态机", group_scope="all",
                          problem_ids=PROBLEM_ORDER[3:], open_at=start + timedelta(weeks=3), due_at=now + timedelta(days=3)))

        students = []
        for gi, group in enumerate(("treatment", "control")):
            for k in range(per_group):
                idx = gi * per_group + k + 1
                u = User(login_name=f"G{tag}{idx:03d}", display_name=f"虚拟学生{idx:02d}", role="student",
                         password_hash="!")       # 生成的学生不能登录
                db.add(u)
                db.flush()
                u.anon_id = anon_id_for(u.id)
                consent = "declined" if idx % 7 == 0 else ("pending" if idx % 13 == 0 else "accepted")
                db.add(Enrollment(class_id=cls.id, user_id=u.id, group=group, consent_status=consent,
                                  consent_version="v1-draft" if consent != "pending" else None,
                                  consent_at=start if consent != "pending" else None))
                students.append((u, group, idx))
        db.flush()

        counts = {"attempts": 0, "hints": 0, "explanations": 0, "chat": 0, "tb": 0, "shuffle": 0}
        for u, group, idx in students:
            treated = group == "treatment"
            inactive = idx % 9 == 0            # 近 7 天不活跃
            blind = idx % 11 == 0              # 从不看波形
            stuck = idx % 10 == 0              # 同一题反复概念未通
            span = (weeks * 7 - (8 if inactive else 0)) * 24 * 60 - 15
            # 最后一次操作也在“现在”30 分钟之前，事件时间不会超过当前时间
            times = sorted(start + timedelta(minutes=rng.randrange(60, span - 30)) for _ in range(attempts_each))
            per_problem: dict[str, int] = {}
            progress: dict[str, dict] = {}
            base_skill = rng.uniform(0.3, 0.8)
            for i, t in enumerate(times):
                frac = i / max(1, attempts_each - 1)
                pid = PROBLEM_ORDER[min(len(PROBLEM_ORDER) - 1, int(frac * len(PROBLEM_ORDER) + rng.random() * 0.8))]
                if stuck and i >= attempts_each - 4:
                    pid = "seq_detector_101"
                p = problems[pid]
                options = vs[pid]
                first = pid not in per_problem
                if p.primm_type in ("predict", "modify") and first:
                    name = "starter"
                elif stuck and i >= attempts_each - 4:
                    name = "c1_no_overlap"
                elif rng.random() < 0.35 + 0.5 * frac:
                    name = "ref"
                else:
                    name = rng.choice([n for n in options if n not in ("ref", "starter")])
                code, diag = options[name]
                per_problem[pid] = per_problem.get(pid, 0) + 1
                st = progress.setdefault(pid, {"predicted": False, "ran": False, "investigated": False,
                                               "passed": False, "modify_phase": False, "modify_done": False,
                                               "tb_done": False})
                if first:
                    log_event(db, u, "problem.open", problem_id=pid, ts=t - timedelta(minutes=rng.randrange(3, 20)))
                compiled = diag["compile"]["ok"]
                waveform = hardware = evaluation = None
                skill = 0.05 if stuck and i >= attempts_each - 4 else min(0.95, base_skill + 0.3 * frac)
                if treated:
                    waveform, hardware = fake_prediction(rng, p, diag, skill)
                    log_event(db, u, "predict.submit", problem_id=pid, ts=t - timedelta(seconds=40),
                              payload={"kind": "waveform", "cells": len(waveform["cells"]), "answers": waveform})
                    log_event(db, u, "predict.submit", problem_id=pid, ts=t - timedelta(seconds=30),
                              payload={"kind": "hardware", "cells": 3, "answers": hardware})
                    st["predicted"] = True
                    if compiled:
                        evaluation = evaluate_prediction(predict_points=p.meta["predict_points"],
                                                         hardware_questions=p.meta["hardware_questions"],
                                                         waveform=waveform, hardware=hardware, diagnosis=diag)
                sim_ok = bool(compiled and diag["sim"]["ok"])
                acc = evaluation["accuracy"] if evaluation else None
                q = quadrant(sim_ok, prediction_ok(acc, theta), compiled)
                step = "modify" if st["modify_phase"] else "run"
                a = Attempt(user_id=u.id, problem_id=pid, attempt_no=per_problem[pid], step=step, code=code,
                            code_hash=hashlib.sha256(code.encode()).hexdigest(), created_at=t,
                            finished_at=t + timedelta(seconds=4), status="done", judge=diag, sim_ok=sim_ok,
                            pred_accuracy=acc, quadrant=q,
                            analysis={"evaluation": evaluation,
                                      "misconceptions": prediction_misconceptions(evaluation, diag) if evaluation else []})
                db.add(a)
                db.flush()
                counts["attempts"] += 1
                if treated:
                    for kind, ans in (("waveform", waveform), ("hardware", hardware)):
                        db.add(Prediction(user_id=u.id, problem_id=pid, attempt_id=a.id, kind=kind, answers=ans,
                                          locked_at=t - timedelta(seconds=30),
                                          accuracy=(evaluation or {}).get(kind, {}).get("accuracy") if evaluation else None,
                                          result=(evaluation or {}).get(kind) if evaluation else None))
                log_event(db, u, "code.submit", problem_id=pid, attempt_id=a.id, ts=t,
                          payload={"attempt_id": a.id, "code_hash": a.code_hash, "lines": code.count("\n") + 1})
                log_event(db, u, "judge.done", problem_id=pid, attempt_id=a.id, ts=t + timedelta(seconds=4),
                          payload={"attempt_id": a.id, "sim_ok": sim_ok, "tags": diag["tags"], "quadrant": q,
                                   "pred_accuracy": acc})
                st["ran"] = True
                st["passed"] = st["passed"] or sim_ok
                # 看波形、探究
                if compiled and not blind and rng.random() < 0.75:
                    log_event(db, u, "waveform.view", problem_id=pid, attempt_id=a.id, ts=t + timedelta(seconds=20))
                    if rng.random() < 0.5:
                        log_event(db, u, "waveform.cell_click", problem_id=pid, attempt_id=a.id,
                                  ts=t + timedelta(seconds=35), payload={"step": 1, "signal": "out", "is_mismatch": False})
                if compiled and not blind and treated and not st["investigated"] and rng.random() < 0.7:
                    db.add(Investigation(attempt_id=a.id, kind="locate_step", chosen={"step": 1, "signal": "x"},
                                         correct=True, created_at=t + timedelta(minutes=1)))
                    log_event(db, u, "investigate.locate_step", problem_id=pid, attempt_id=a.id,
                              ts=t + timedelta(minutes=1), payload={"attempt_id": a.id, "correct": True})
                    text = rng.choice(EXPLANATIONS)
                    db.add(Explanation(attempt_id=a.id, text=text, created_at=t + timedelta(minutes=2)))
                    log_event(db, u, "explain.submit", problem_id=pid, attempt_id=a.id, ts=t + timedelta(minutes=2),
                              payload={"attempt_id": a.id, "length": len(text)})
                    counts["explanations"] += 1
                    st["investigated"] = True
                    if p.primm_type == "modify":
                        st["modify_phase"] = True
                if p.primm_type == "modify" and st["modify_phase"] and sim_ok and step == "modify":
                    st["modify_done"] = True
                # 提示阶梯
                if not sim_ok and rng.random() < 0.6:
                    for level in range(1, rng.randrange(2, 5)):
                        ht = t + timedelta(minutes=2 + level)
                        content = fallback_hints.generate(diag, level, evaluation=evaluation, quadrant=q)
                        content["fallback_reason"] = "no_key"
                        h = Hint(attempt_id=a.id, level=level, source="fallback", content=content, created_at=ht)
                        db.add(h)
                        db.flush()
                        log_event(db, u, "hint.request", problem_id=pid, attempt_id=a.id, ts=ht,
                                  payload={"attempt_id": a.id, "level": level})
                        log_event(db, u, "hint.shown", problem_id=pid, attempt_id=a.id, ts=ht,
                                  payload={"attempt_id": a.id, "level": level, "source": "fallback", "hint_id": h.id})
                        counts["hints"] += 1
                # 助教对话（实验组）
                if treated and rng.random() < 0.25:
                    s = db.scalar(select(ChatSession).where(ChatSession.user_id == u.id, ChatSession.problem_id == pid))
                    if s is None:
                        s = ChatSession(user_id=u.id, problem_id=pid, created_at=t)
                        db.add(s)
                        db.flush()
                    ct = t + timedelta(minutes=6)
                    text = rng.choice(CHATS)
                    db.add(ChatMessage(session_id=s.id, role="user", content=text, attempt_id=a.id, created_at=ct))
                    db.add(ChatMessage(session_id=s.id, role="assistant", content="先看看第一个对不上的周期。",
                                       source="fallback", attempt_id=a.id, created_at=ct + timedelta(seconds=2)))
                    log_event(db, u, "chat.send", problem_id=pid, attempt_id=a.id, ts=ct,
                              payload={"session_id": s.id, "length": len(text)})
                    counts["chat"] += 1
                # 顺序打乱实验
                if pid == "swap_regs" and compiled and rng.random() < 0.5:
                    sensitive = "blocking_in_seq" in diag["tags"]
                    db.add(ShuffleRun(attempt_id=a.id, prediction=rng.choice(["change", "same"]), status="done",
                                      result={"ok": True, "order_sensitive": sensitive, "blocks": 2, "variants": []},
                                      created_at=t + timedelta(minutes=8)))
                    log_event(db, u, "shuffle.run", problem_id=pid, attempt_id=a.id, ts=t + timedelta(minutes=8),
                              payload={"attempt_id": a.id, "order_sensitive": sensitive})
                    counts["shuffle"] += 1
                # 创作题通过后写 testbench
                if p.primm_type == "make" and sim_ok and st["investigated"] and not st["tb_done"] and rng.random() < 0.8:
                    caught = rng.randrange(1, 5)
                    score = caught / 4
                    db.add(TbSubmission(user_id=u.id, problem_id=pid, code="// tb", status="done", score=score,
                                        result={"ok": True, "score": score, "caught": [f"c{k}" for k in range(caught)],
                                                "missed": [f"m{k}" for k in range(4 - caught)], "excluded": []},
                                        created_at=t + timedelta(minutes=12)))
                    log_event(db, u, "tb.submit", problem_id=pid, ts=t + timedelta(minutes=12),
                              payload={"score": score, "caught": caught, "missed": 4 - caught})
                    st["tb_done"] = True
                    counts["tb"] += 1
            for pid, st in progress.items():
                p = problems[pid]
                done = (p.primm_type == "predict" and st["investigated"]) or st["modify_done"] or st["tb_done"]
                db.add(Progress(user_id=u.id, problem_id=pid, step="done" if done else "predict", state=st))
        db.commit()
        return {"class_id": cls.id, "teacher_login": teacher.login_name, "teacher_password": "generated-teacher",
                "students": len(students), **counts}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    info = generate(seed=args.seed)
    print(info)


if __name__ == "__main__":
    main()
