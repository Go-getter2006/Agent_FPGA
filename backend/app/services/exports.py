"""研究导出（docs/data-api.md 第 5 节）：只含已同意的学生，一律用匿名 ID，不含姓名和学号。"""
from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import REPO_ROOT
from ..models import Enrollment, Event
from . import teacher_analytics as ta

KINDS = ("events", "attempts", "metrics")

DATA_DICTIONARY = """# 数据字典

本导出只包含已同意参与研究的学生；一律使用匿名 ID（anon_id = HMAC-SHA256(盐, user_id) 的前 8 位十六进制），不含姓名和学号。时间均为 UTC，ISO 8601 格式。

## events.jsonl（一行一条事件）
| 字段 | 含义 |
|---|---|
| id | 事件 ID（UUID） |
| ts | 发生时间 |
| anon_id | 学生匿名 ID |
| class_id | 班级 ID |
| group | 实验分组：treatment（实验组）/ control（对照组）/ none |
| type | 事件类型，见 docs/learner-model.md 第 7 节 |
| problem_id | 题目 ID |
| attempt_id | 尝试（一次提交仿真）ID |
| payload | 事件详情（JSON） |
| app_version | 平台版本 |

## attempts.csv（一行一次提交仿真）
| 字段 | 含义 |
|---|---|
| anon_id, group | 同上 |
| problem_id | 题目 ID |
| attempt_no | 该学生在这道题上的第几次提交 |
| created_at | 提交时间 |
| sim_ok | 仿真是否与参考答案一致（代码通过 c） |
| pred_accuracy | 预测准确率 A_pred；没有预测时为空 |
| quadrant | 四象限：mastered / fragile / design_gap / concept_gap；编译失败或没有预测为 none |
| tags | 裁判标签，分号分隔 |
| max_hint_level_before | 这次提交之前在这道题上请求过的最高提示等级（0–3） |

## metrics.csv（一行一个学生 × 知识点）
| 字段 | 含义 |
|---|---|
| anon_id, group | 同上 |
| knowledge_point | 知识点代码 |
| level | 掌握等级：mastered / fragile / learning / not_started |
| r_code, r_pred | 最近 3 次带预测尝试中代码通过、预测达标的比例 |
| f_value | 脆弱率 F（最近 5 次）；分母为 0 时为空 |
| B | 该学生的盲改率（全部题目） |
| H | 该学生的提示依赖度 |
| tb_score | 该学生各创作题最近一次 testbench 得分的平均值 |
"""


def exports_dir() -> Path:
    return Path(os.getenv("EXPORTS_DIR", "").strip() or REPO_ROOT / "backend" / "exports")


def _iso(t) -> str:
    return t.isoformat() if t else ""


def build_export(db: DbSession, class_id: int, kinds: list[str], out_path: Path) -> dict:
    consented = {e.user_id for e in db.scalars(select(Enrollment).where(
        Enrollment.class_id == class_id, Enrollment.consent_status == "accepted")).all()}
    cd = ta.load(db, class_id)
    students = [s for s in cd.students if s.user_id in consented]
    anon = {s.user_id: s.anon_id for s in students}
    group = {s.user_id: s.group for s in students}
    counts = {"students": len(students)}
    files: dict[str, str] = {"data_dictionary.md": DATA_DICTIONARY}

    if "events" in kinds:
        lines = []
        rows = db.scalars(select(Event).where(Event.user_id.in_(list(consented) or [-1]), Event.class_id == class_id)
                          .order_by(Event.ts, Event.id)).all()
        for e in rows:
            lines.append(json.dumps({"id": e.id, "ts": _iso(e.ts), "anon_id": e.anon_id, "class_id": e.class_id,
                                     "group": e.group, "type": e.type, "problem_id": e.problem_id,
                                     "attempt_id": e.attempt_id, "payload": e.payload,
                                     "app_version": e.app_version}, ensure_ascii=False))
        files["events.jsonl"] = "\n".join(lines) + ("\n" if lines else "")
        counts["events"] = len(lines)

    if "attempts" in kinds:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["anon_id", "group", "problem_id", "attempt_no", "created_at", "sim_ok", "pred_accuracy",
                    "quadrant", "tags", "max_hint_level_before"])
        n = 0
        for a in cd.attempts:
            if a.user_id not in consented:
                continue
            w.writerow([anon[a.user_id], group[a.user_id], a.problem_id, a.attempt_no, _iso(a.created_at),
                        int(bool(a.sim_ok)), "" if a.pred_accuracy is None else f"{a.pred_accuracy:.4f}",
                        a.quadrant or "none", ";".join((a.judge or {}).get("tags", [])),
                        ta.hint_level_before(cd, a.user_id, a.problem_id, a.created_at)])
            n += 1
        files["attempts.csv"] = buf.getvalue()
        counts["attempts"] = n

    if "metrics" in kinds:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["anon_id", "group", "knowledge_point", "level", "r_code", "r_pred", "f_value", "B", "H", "tb_score"])
        fmt = lambda v: "" if v is None else f"{v:.4f}"  # noqa: E731
        n = 0
        heat = {r["user_id"]: r["cells"] for r in ta.heatmap(cd, None, None, None)["rows"]}
        for s in students:
            cells = heat[s.user_id]
            b, _, _ = ta.blind(cd, {s.user_id})
            h = ta.avg_hint_level(cd, {s.user_id})
            latest = {}
            for t in cd.tbs:
                if t.user_id == s.user_id and t.score is not None:
                    latest[t.problem_id] = t.score
            tb = sum(latest.values()) / len(latest) if latest else None
            for kp in cd.kps:
                c = cells[kp.code]
                w.writerow([s.anon_id, s.group, kp.code, c["level"], fmt(c["r_code"]), fmt(c["r_pred"]),
                            fmt(c["f_value"]), fmt(b), fmt(h), fmt(tb)])
                n += 1
        files["metrics.csv"] = buf.getvalue()
        counts["metrics"] = n

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return counts

