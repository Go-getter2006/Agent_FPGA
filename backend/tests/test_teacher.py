"""阶段 5 验收：用 2 个分组 × 30 名虚拟学生 × 每人 20 次尝试的数据，教师端各页面的数字与直接写 SQL 统计的结果一致。

这里的 SQL 不调用任何后端统计代码，按 docs/learner-model.md 的定义独立计算（窗口函数、json_each）。
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db import SessionLocal
from backend.scripts.gen_test_data import generate

QUADS = "('mastered','fragile','design_gap','concept_gap')"
LOOK = "('waveform.view','waveform.cell_click','investigate.locate_step','investigate.locate_line')"
TAGS = ("latch_inferred", "blocking_in_seq", "nonblocking_in_comb", "width_mismatch", "multi_driven",
        "non_synthesizable", "race_order_sensitive", "fragile_pass")
BJ = timezone(timedelta(hours=8))


def ts(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


def monday(t: datetime) -> datetime:
    local = t.astimezone(BJ)
    return (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def sql(query: str, **params):
    with SessionLocal() as db:
        return db.execute(text(query), params).all()


def approx(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) < 1e-9


@pytest.fixture(scope="module")
def gen(app):
    info = generate(seed=7, create_tables=False)
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"login_name": info["teacher_login"], "password": info["teacher_password"]})
    assert r.status_code == 200
    return {**info, "client": client}


def members(cid: int, group: str | None = None) -> str:
    g = f" AND \"group\" = '{group}'" if group else ""
    return f"(SELECT user_id FROM enrollments WHERE class_id = {cid}{g})"


# ---------------------------------------------------------------- 数据规模

def test_generated_scale(gen):
    cid = gen["class_id"]
    rows = sql(f'SELECT "group", COUNT(*) FROM enrollments WHERE class_id = :cid GROUP BY "group"', cid=cid)
    assert dict(rows) == {"treatment": 30, "control": 30}
    per_student = sql(f"SELECT COUNT(*) FROM attempts WHERE user_id IN {members(cid)} GROUP BY user_id")
    assert len(per_student) == 60 and {n for (n,) in per_student} == {20}


# ---------------------------------------------------------------- T1 班级概览

def class_f_sql(cid: int, before: datetime | None, group: str | None = None) -> float | None:
    cond = f"AND a.created_at < '{ts(before)}'" if before else ""
    (num, den), = sql(f"""
        WITH ak AS (
          SELECT a.id, a.user_id, j.value AS kp, a.created_at, a.sim_ok,
                 CASE WHEN a.pred_accuracy >= 0.8 - 1e-9 THEN 1 ELSE 0 END AS p
          FROM attempts a JOIN problems pr ON pr.id = a.problem_id, json_each(pr.knowledge_points) j
          WHERE a.status = 'done' AND a.quadrant IN {QUADS} AND a.user_id IN {members(cid, group)} {cond}),
        r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id, kp ORDER BY created_at DESC, id DESC) AS rn FROM ak)
        SELECT SUM(CASE WHEN sim_ok = 1 AND p = 0 THEN 1 ELSE 0 END), SUM(sim_ok) FROM r WHERE rn <= 5""")
    return num / den if den else None


def avg_hint_sql(cid: int, start: datetime, end: datetime, group: str | None = None) -> float | None:
    (v,), = sql(f"""
        WITH fp AS (SELECT user_id, problem_id, MIN(created_at) AS t FROM attempts
                    WHERE status = 'done' AND sim_ok = 1 AND user_id IN {members(cid, group)}
                    GROUP BY user_id, problem_id)
        SELECT AVG(COALESCE((SELECT MAX(h.level) FROM hints h JOIN attempts a2 ON a2.id = h.attempt_id
                             WHERE a2.user_id = fp.user_id AND a2.problem_id = fp.problem_id AND h.created_at < fp.t), 0))
        FROM fp WHERE fp.t >= :a AND fp.t < :b""", a=ts(start), b=ts(end))
    return v


def completion_sql(cid: int, at: datetime, group: str | None = None) -> float | None:
    (total, done), = sql(f"""
        SELECT COUNT(*), SUM(CASE WHEN EXISTS (
                 SELECT 1 FROM attempts a WHERE a.user_id = en.user_id AND a.problem_id = j.value
                 AND a.status = 'done' AND a.sim_ok = 1 AND a.created_at < :t) THEN 1 ELSE 0 END)
        FROM assignments asg, json_each(asg.problem_ids) j
        JOIN enrollments en ON en.class_id = asg.class_id
        WHERE asg.class_id = :cid AND asg.open_at <= :t
          AND (asg.group_scope = 'all' OR asg.group_scope = en."group")
          AND en.user_id IN {members(cid, group)}""", cid=cid, t=ts(at))
    return done / total if total else None


@pytest.mark.parametrize("group", [None, "treatment", "control"])
def test_overview_kpis_match_sql(gen, group):
    cid = gen["class_id"]
    data = gen["client"].get(f"/api/teacher/classes/{cid}/overview", params={"group": group} if group else {}).json()
    now = datetime.now(timezone.utc)
    ws = monday(now)
    prev = ws - timedelta(weeks=1)
    k = data["kpis"]
    (active,), = sql(f"SELECT COUNT(DISTINCT user_id) FROM events WHERE user_id IN {members(cid, group)} "
                     "AND ts >= :a AND ts < :b", a=ts(ws), b=ts(now))
    (active_prev,), = sql(f"SELECT COUNT(DISTINCT user_id) FROM events WHERE user_id IN {members(cid, group)} "
                          "AND ts >= :a AND ts < :b", a=ts(prev), b=ts(ws))
    assert (k["active"]["value"], k["active"]["prev"]) == (active, active_prev)
    assert k["active"]["total"] == (60 if group is None else 30)
    assert approx(k["completion"]["value"], completion_sql(cid, now, group))
    assert approx(k["completion"]["prev"], completion_sql(cid, ws, group))
    for key, (a, b) in {"value": (ws, now), "prev": (prev, ws)}.items():
        (acc,), = sql(f"SELECT AVG(pred_accuracy) FROM attempts WHERE status = 'done' AND pred_accuracy IS NOT NULL "
                      f"AND user_id IN {members(cid, group)} AND created_at >= :a AND created_at < :b", a=ts(a), b=ts(b))
        assert approx(k["pred_accuracy"][key], acc)
        assert approx(k["avg_hint"][key], avg_hint_sql(cid, a, b, group))
    assert approx(k["class_f"]["value"], class_f_sql(cid, None, group))
    assert approx(k["class_f"]["prev"], class_f_sql(cid, ws, group))
    # 对照组没有预测：准确率与 F 值都为空
    if group == "control":
        assert k["pred_accuracy"]["value"] is None and k["class_f"]["value"] is None


def test_trend_matches_sql(gen):
    cid = gen["class_id"]
    trend = gen["client"].get(f"/api/teacher/classes/{cid}/overview").json()["trend"]
    assert len(trend) == 8
    for w in trend:
        start = datetime.fromisoformat(w["week"]).replace(tzinfo=BJ)
        end = min(start + timedelta(weeks=1), datetime.now(timezone.utc))
        (acc,), = sql(f"SELECT AVG(pred_accuracy) FROM attempts WHERE status='done' AND pred_accuracy IS NOT NULL "
                      f"AND user_id IN {members(cid)} AND created_at >= :a AND created_at < :b", a=ts(start), b=ts(end))
        assert approx(w["pred_accuracy"], acc)
        assert approx(w["class_f"], class_f_sql(cid, end))


def misconception_students_sql(cid: int) -> dict[str, int]:
    tags = ",".join(f"'{t}'" for t in TAGS)
    rows = sql(f"""
        SELECT code, COUNT(DISTINCT user_id) FROM (
          SELECT a.user_id, j.value AS code FROM attempts a, json_each(json_extract(a.judge, '$.tags')) j
          WHERE a.status='done' AND a.user_id IN {members(cid)} AND j.value IN ({tags})
          UNION ALL
          SELECT a.user_id, j.value FROM attempts a, json_each(json_extract(a.analysis, '$.misconceptions')) j
          WHERE a.status='done' AND a.user_id IN {members(cid)})
        GROUP BY code""")
    return dict(rows)


def test_misconceptions_match_sql(gen):
    cid = gen["client"], gen["class_id"]
    client, cid = cid
    expected = misconception_students_sql(cid)
    items = client.get(f"/api/teacher/classes/{cid}/misconceptions").json()["items"]
    assert {m["code"]: m["students"] for m in items} == expected
    top5 = client.get(f"/api/teacher/classes/{cid}/overview").json()["misconceptions"]
    assert [m["students"] for m in top5] == sorted(expected.values(), reverse=True)[:5]
    assert {m["source"] for m in items} == {"judge", "prediction"}


def test_alerts_match_sql(gen):
    cid = gen["class_id"]
    alerts = gen["client"].get(f"/api/teacher/classes/{cid}/overview").json()["alerts"]
    by_rule = {r: {a["user_id"] for a in alerts if any(x["rule"] == r for x in a["reasons"])} for r in (1, 2, 3, 4)}
    now = datetime.now(timezone.utc)
    # 规则 3：近 7 天没有任何事件
    rows = sql(f"SELECT user_id FROM enrollments WHERE class_id = :cid AND user_id NOT IN "
               f"(SELECT user_id FROM events WHERE ts >= :t AND user_id IS NOT NULL)", cid=cid, t=ts(now - timedelta(days=7)))
    assert by_rule[3] == {u for (u,) in rows} and by_rule[3]
    # 规则 1：2 个及以上核心知识点 F ≥ 0.5（最近 5 次带预测尝试）
    rows = sql(f"""
        WITH ak AS (
          SELECT a.id, a.user_id, j.value AS kp, a.created_at, a.sim_ok,
                 CASE WHEN a.pred_accuracy >= 0.8 - 1e-9 THEN 1 ELSE 0 END AS p
          FROM attempts a JOIN problems pr ON pr.id = a.problem_id, json_each(pr.knowledge_points) j
          WHERE a.status='done' AND a.quadrant IN {QUADS} AND a.user_id IN {members(cid)}
            AND j.value IN ('blocking','sequential','fsm','parallel')),
        r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id, kp ORDER BY created_at DESC, id DESC) rn FROM ak),
        f AS (SELECT user_id, kp, SUM(CASE WHEN sim_ok=1 AND p=0 THEN 1 ELSE 0 END) * 1.0 / SUM(sim_ok) AS fv
              FROM r WHERE rn <= 5 GROUP BY user_id, kp HAVING SUM(sim_ok) > 0)
        SELECT user_id FROM f WHERE fv >= 0.5 GROUP BY user_id HAVING COUNT(*) >= 2""")
    assert by_rule[1] == {u for (u,) in rows}
    # 规则 2：同一知识点最近 3 次带预测的尝试都是概念未通
    rows = sql(f"""
        WITH ak AS (
          SELECT a.id, a.user_id, j.value AS kp, a.created_at, a.quadrant
          FROM attempts a JOIN problems pr ON pr.id = a.problem_id, json_each(pr.knowledge_points) j
          WHERE a.status='done' AND a.quadrant IN {QUADS} AND a.user_id IN {members(cid)}),
        r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id, kp ORDER BY created_at DESC, id DESC) rn FROM ak)
        SELECT DISTINCT user_id FROM r WHERE rn <= 3 GROUP BY user_id, kp
        HAVING COUNT(*) = 3 AND SUM(CASE WHEN quadrant = 'concept_gap' THEN 1 ELSE 0 END) = 3""")
    assert by_rule[2] == {u for (u,) in rows} and by_rule[2]
    # 规则 4：近 10 次重复提交的盲改率 ≥ 0.7
    rows = sql(f"""
        WITH s AS (SELECT a.id, a.user_id, a.problem_id, a.created_at,
                          LAG(a.created_at) OVER (PARTITION BY a.user_id, a.problem_id ORDER BY a.created_at, a.id) AS prev
                   FROM attempts a WHERE a.status='done' AND a.user_id IN {members(cid)}),
        b AS (SELECT user_id, created_at, CASE WHEN EXISTS (
                 SELECT 1 FROM events e WHERE e.user_id = s.user_id AND e.problem_id = s.problem_id
                 AND e.type IN {LOOK} AND e.ts > s.prev AND e.ts < s.created_at) THEN 0 ELSE 1 END AS blind
              FROM s WHERE prev IS NOT NULL),
        r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) rn FROM b)
        SELECT user_id FROM r WHERE rn <= 10 GROUP BY user_id HAVING AVG(blind) >= 0.7""")
    assert by_rule[4] == {u for (u,) in rows} and by_rule[4]


def blind_sql(cid: int, problem: str | None = None, user: int | None = None) -> float | None:
    cond = (f" AND a.problem_id = '{problem}'" if problem else "") + (f" AND a.user_id = {user}" if user else "")
    (n, blind), = sql(f"""
        WITH s AS (SELECT a.id, a.user_id, a.problem_id, a.created_at,
                          LAG(a.created_at) OVER (PARTITION BY a.user_id, a.problem_id ORDER BY a.created_at, a.id) AS prev
                   FROM attempts a WHERE a.status='done' AND a.user_id IN {members(cid)}{cond})
        SELECT COUNT(*), SUM(CASE WHEN EXISTS (
                 SELECT 1 FROM events e WHERE e.user_id = s.user_id AND e.problem_id = s.problem_id
                 AND e.type IN {LOOK} AND e.ts > s.prev AND e.ts < s.created_at) THEN 0 ELSE 1 END)
        FROM s WHERE prev IS NOT NULL""")
    return blind / n if n else None


def test_problem_table_matches_sql(gen):
    cid = gen["class_id"]
    rows = gen["client"].get(f"/api/teacher/classes/{cid}/overview").json()["problems"]
    assert len(rows) == 6
    for r in rows:
        pid = r["problem_id"]
        (tried, passed, n), = sql(f"SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT CASE WHEN sim_ok=1 THEN user_id END), "
                                  f"COUNT(*) FROM attempts WHERE status='done' AND problem_id=:p AND user_id IN {members(cid)}", p=pid)
        assert (r["attempted"], r["passed"]) == (tried, passed)
        assert approx(r["pass_rate"], passed / tried)
        assert approx(r["avg_submissions"], n / tried)
        assert approx(r["blind_rate"], blind_sql(cid, problem=pid))
        (h,), = sql(f"""
            WITH fp AS (SELECT user_id, MIN(created_at) AS t FROM attempts WHERE status='done' AND sim_ok=1
                        AND problem_id=:p AND user_id IN {members(cid)} GROUP BY user_id)
            SELECT AVG(COALESCE((SELECT MAX(h.level) FROM hints h JOIN attempts a2 ON a2.id=h.attempt_id
                       WHERE a2.user_id=fp.user_id AND a2.problem_id=:p AND h.created_at < fp.t), 0)) FROM fp""", p=pid)
        assert approx(r["avg_hint_level"], h)
        # 题目 F：每个学生在这道题上最近 5 次带预测尝试，分子、分母分别求和
        (num, den), = sql(f"""
            WITH r AS (SELECT a.user_id, a.sim_ok, CASE WHEN a.pred_accuracy >= 0.8 - 1e-9 THEN 1 ELSE 0 END p,
                              ROW_NUMBER() OVER (PARTITION BY a.user_id ORDER BY a.created_at DESC, a.id DESC) rn
                       FROM attempts a WHERE a.status='done' AND a.quadrant IN {QUADS} AND a.problem_id=:p
                       AND a.user_id IN {members(cid)})
            SELECT SUM(CASE WHEN sim_ok=1 AND p=0 THEN 1 ELSE 0 END), SUM(sim_ok) FROM r WHERE rn <= 5""", p=pid)
        assert approx(r["f_value"], num / den if den else None)


# ---------------------------------------------------------------- T2 热力图

def test_heatmap_levels_match_sql(gen):
    cid = gen["class_id"]
    data = gen["client"].get(f"/api/teacher/classes/{cid}/heatmap").json()
    assert len(data["rows"]) == 60 and len(data["knowledge_points"]) == 11
    assert all(k["name"] for k in data["knowledge_points"])          # 匿名只去掉学生姓名
    assert all(r["name"] is None and r["alias"].startswith("S") for r in data["rows"])
    rows = sql(f"""
        WITH ak AS (
          SELECT a.id, a.user_id, j.value AS kp, a.created_at, a.sim_ok, a.quadrant,
                 CASE WHEN a.pred_accuracy >= 0.8 - 1e-9 THEN 1 ELSE 0 END AS p
          FROM attempts a JOIN problems pr ON pr.id = a.problem_id, json_each(pr.knowledge_points) j
          WHERE a.status='done' AND a.quadrant IN {QUADS} AND a.user_id IN {members(cid)}),
        r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id, kp ORDER BY created_at DESC, id DESC) rn FROM ak)
        SELECT user_id, kp, AVG(sim_ok), AVG(p), MAX(CASE WHEN rn = 1 THEN quadrant END), COUNT(*)
        FROM r WHERE rn <= 3 GROUP BY user_id, kp""")
    expected = {}
    for uid, kp, r_code, r_pred, last, _n in rows:
        if r_code >= 2 / 3 - 1e-9 and r_pred >= 2 / 3 - 1e-9 and last == "mastered":
            level = "mastered"
        elif r_code >= 2 / 3 - 1e-9:
            level = "fragile"
        else:
            level = "learning"
        expected[(uid, kp)] = level
    seen = 0
    for row in data["rows"]:
        for kp, cell in row["cells"].items():
            assert cell["level"] == expected.get((row["user_id"], kp), "not_started"), (row["alias"], kp)
            seen += cell["level"] != "not_started"
    assert seen == len(expected) > 0
    # 对照组没有预测：所有格子都是“未开始”
    ctrl = gen["client"].get(f"/api/teacher/classes/{cid}/heatmap", params={"group": "control"}).json()["rows"]
    assert len(ctrl) == 30 and all(c["level"] == "not_started" for r in ctrl for c in r["cells"].values())


# ---------------------------------------------------------------- T4 题目分析

def test_problem_analytics_match_sql(gen):
    cid = gen["class_id"]
    pid = "seq_detector_101"
    data = gen["client"].get(f"/api/teacher/classes/{cid}/problems/{pid}/analytics").json()
    rows = sql(f"""SELECT json_extract(judge, '$.sim.first_mismatch.step') s, json_extract(judge, '$.sim.first_mismatch.signal') g,
                   COUNT(*) n FROM attempts WHERE status='done' AND problem_id=:p AND user_id IN {members(cid)}
                   AND json_extract(judge, '$.sim.first_mismatch') IS NOT NULL GROUP BY s, g ORDER BY n DESC, s, g LIMIT 5""", p=pid)
    assert [(c["step"], c["signal"], c["count"]) for c in data["top_mismatch_cells"]] == [tuple(r) for r in rows]
    (ran,), = sql(f"SELECT COUNT(DISTINCT user_id) FROM attempts WHERE problem_id=:p AND user_id IN {members(cid)}", p=pid)
    (made,), = sql(f"SELECT COUNT(DISTINCT user_id) FROM tb_submissions WHERE problem_id=:p AND user_id IN {members(cid)}", p=pid)
    assert data["funnel"]["run"] == ran and data["funnel"]["make"] == made
    rows = sql(f"""
        SELECT h.level, COALESCE(json_extract(h.content, '$.prompt_version'), 'fallback_v1') v, COUNT(*),
               AVG((SELECT a2.sim_ok FROM attempts a2 WHERE a2.user_id = a.user_id AND a2.problem_id = a.problem_id
                    AND a2.status='done' AND a2.created_at > h.created_at ORDER BY a2.created_at, a2.id LIMIT 1))
        FROM hints h JOIN attempts a ON a.id = h.attempt_id
        WHERE a.problem_id = :p AND a.user_id IN {members(cid)}
          AND EXISTS (SELECT 1 FROM attempts a3 WHERE a3.user_id = a.user_id AND a3.problem_id = a.problem_id
                      AND a3.status='done' AND a3.created_at > h.created_at)
        GROUP BY h.level, v ORDER BY h.level, v""", p=pid)
    got = [(r["level"], r["prompt_version"], r["n"]) for r in data["after_hint"]]
    assert got == [(lv, v, n) for lv, v, n, _ in rows]
    for r, (_, _, _, rate) in zip(data["after_hint"], rows):
        assert approx(r["next_pass_rate"], rate)


# ---------------------------------------------------------------- T5 学生详情

def test_student_detail_matches_sql(gen):
    cid = gen["class_id"]
    uid = gen["client"].get(f"/api/teacher/classes/{cid}/heatmap").json()["rows"][3]["user_id"]
    data = gen["client"].get(f"/api/teacher/students/{uid}").json()
    (n,), = sql("SELECT COUNT(*) FROM attempts WHERE status='done' AND user_id=:u", u=uid)
    assert len(data["timeline"]) == n == 20
    assert approx(data["blind_rate"], blind_sql(cid, user=uid))
    assert data["name"] is None and data["alias"].startswith("S")                  # 默认匿名
    named = gen["client"].get(f"/api/teacher/students/{uid}", params={"anonymous": "false"}).json()
    assert named["name"].startswith("虚拟学生")


# ---------------------------------------------------------------- T7 导出

def test_export_only_consented_with_anon_ids(gen):
    client, cid = gen["client"], gen["class_id"]
    r = client.post(f"/api/teacher/classes/{cid}/exports", json={"kinds": ["events", "attempts", "metrics"]})
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "done" and "path" not in job.get("result", {})
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/teacher/exports/{job['id']}/download").content))
    assert set(z.namelist()) == {"events.jsonl", "attempts.csv", "metrics.csv", "data_dictionary.md"}
    consented = {a for (a,) in sql("SELECT u.anon_id FROM enrollments e JOIN users u ON u.id = e.user_id "
                                   "WHERE e.class_id=:c AND e.consent_status='accepted'", c=cid)}
    others = sql("SELECT u.anon_id, u.login_name, u.display_name FROM enrollments e JOIN users u ON u.id = e.user_id "
                 "WHERE e.class_id=:c AND e.consent_status != 'accepted'", c=cid)
    assert 0 < len(consented) < 60 and others
    events = [json.loads(line) for line in z.read("events.jsonl").decode().splitlines()]
    (n_events,), = sql("SELECT COUNT(*) FROM events e JOIN enrollments en ON en.user_id = e.user_id "
                       "WHERE en.class_id=:c AND e.class_id=:c AND en.consent_status='accepted'", c=cid)
    assert len(events) == n_events and {e["anon_id"] for e in events} <= consented
    assert all("user_id" not in e for e in events)
    attempts = z.read("attempts.csv").decode().splitlines()
    (n_attempts,), = sql("SELECT COUNT(*) FROM attempts a JOIN enrollments en ON en.user_id = a.user_id "
                         "WHERE en.class_id=:c AND en.consent_status='accepted' AND a.status='done'", c=cid)
    assert len(attempts) - 1 == n_attempts == len(consented) * 20
    metrics = z.read("metrics.csv").decode().splitlines()
    assert len(metrics) - 1 == len(consented) * 11
    everything = "".join(z.read(n).decode() for n in z.namelist())
    for anon, login, name in others:
        assert anon not in everything and login not in everything and name not in everything
    for (login,) in sql("SELECT u.login_name FROM enrollments e JOIN users u ON u.id = e.user_id WHERE e.class_id=:c", c=cid):
        assert login not in everything                                              # 不含学号


# ---------------------------------------------------------------- 分组与开关、名单

def test_groups_and_flags(gen, app):
    from backend.tests.conftest import login, make_user
    client, cid = gen["client"], gen["class_id"]
    g = client.get(f"/api/teacher/classes/{cid}/groups").json()
    assert g["flags"]["control"]["predict_step"] is False and g["students"][0]["name"] is None
    r = client.put(f"/api/teacher/classes/{cid}/groups", json={"flags": {"control": {"llm_hints": True}}})
    assert r.status_code == 200
    assert client.get(f"/api/teacher/classes/{cid}/groups").json()["flags"]["control"]["llm_hints"] is True
    r = client.put(f"/api/teacher/classes/{cid}/groups", json={"flags": {"control": {"llm_hints": False}}})
    # 名单导入 + 分组 CSV
    r = client.post(f"/api/teacher/classes/{cid}/roster", json={"csv": "学号,姓名\nN900001,新同学甲\nN900002,新同学乙"})
    imported = r.json()["imported"]
    assert len(imported) == 2 and all(x["temp_password"] for x in imported)
    r = client.put(f"/api/teacher/classes/{cid}/groups", json={"csv": "学号,分组\nN900001,treatment\nN900002,control"})
    assert r.json()["changed"] == 2
    roster = client.get(f"/api/teacher/classes/{cid}/roster").json()["students"]
    new = {s["login_name"]: s for s in roster if s["login_name"].startswith("N9000")}
    assert new["N900001"]["group"] == "treatment" and new["N900001"]["consent_status"] == "pending"
    assert new["N900001"]["name"] == "新同学甲"                                      # 名单页显示真实姓名
    # 用临时密码登录
    from fastapi.testclient import TestClient
    s = TestClient(app)
    assert s.post("/api/auth/login", json={"login_name": "N900001", "password": imported[0]["temp_password"]}).status_code == 200
    reset = client.post(f"/api/teacher/students/{new['N900001']['user_id']}/reset_password").json()
    assert s.post("/api/auth/login", json={"login_name": "N900001", "password": reset["temp_password"]}).status_code == 200
    del make_user, login


def test_anonymity_toggle_logs_event(gen):
    client, cid = gen["client"], gen["class_id"]
    client.post(f"/api/teacher/classes/{cid}/anonymity", json={"anonymous": False})
    rows = sql("SELECT payload FROM events WHERE type='teacher.anonymity' AND class_id=:c", c=cid)
    assert rows and json.loads(rows[-1][0]) == {"anonymous": False}


def test_create_assignment(gen):
    client, cid = gen["client"], gen["class_id"]
    r = client.post(f"/api/teacher/classes/{cid}/assignments", json={
        "title": "第 3 次作业", "problem_ids": ["swap_regs"], "group_scope": "treatment",
        "open_at": "2026-11-10T08:00:00", "due_at": "2026-11-17T22:00:00"})
    assert r.status_code == 200
    titles = [a["title"] for a in client.get(f"/api/teacher/classes/{cid}/assignments").json()["assignments"]]
    assert "第 3 次作业" in titles
    r = client.post(f"/api/teacher/classes/{cid}/assignments", json={
        "title": "x", "problem_ids": ["nope"], "open_at": "2026-11-10T08:00:00", "due_at": "2026-11-11T08:00:00"})
    assert r.status_code == 400
