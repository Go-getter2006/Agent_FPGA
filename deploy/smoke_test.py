"""部署后的冒烟测试（只用 Python 标准库）：学生登录 → 同意 → 预测 → 提交 → 等判题结果；教师端总览。

    python3 deploy/smoke_test.py http://localhost:8080 <演示密码>

用的是 deploy/quickstart.sh 导入的演示账号 S2026005 和 TGEN。全部通过时退出码为 0。
"""
from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise SystemExit(f"失败：{method} {path} → {e.code} {e.read().decode(errors='replace')[:300]}")


def main() -> None:
    base, password = sys.argv[1], sys.argv[2]
    s = Client(base)
    print("health:", s.call("GET", "/api/health"))
    s.call("POST", "/api/auth/login", {"login_name": "S2026005", "password": password})
    version = s.call("GET", "/api/auth/consent")["version"]
    s.call("POST", "/api/auth/consent", {"accept": True, "version": version})
    pid = "seq_detector_101"
    d = s.call("GET", f"/api/student/problems/{pid}")
    widths = {o["name"]: o["width"] for o in d["skeleton"]["outputs"]}
    cells = [{"signal": p["signal"], "step": st, "value": "0".rjust(widths[p["signal"]], "0")}
             for p in d["predict_points"] for st in p["steps"]]
    s.call("POST", f"/api/student/problems/{pid}/predictions",
           {"waveform": {"cells": cells}, "hardware": {"ff_count": 2, "latch": False, "ff_signals": []}})
    code = (ROOT / "problems" / pid / "ref.v").read_text(encoding="utf-8")
    aid = s.call("POST", f"/api/student/problems/{pid}/attempts", {"code": code})["attempt_id"]
    t0 = time.time()
    while True:
        a = s.call("GET", f"/api/student/attempts/{aid}")
        if a["status"] not in ("queued", "running") or time.time() - t0 > 120:
            break
        time.sleep(1)
    print(f"判题：{a['status']}，仿真通过={a.get('sim_ok')}，用时 {time.time() - t0:.1f} 秒")
    if a["status"] != "done" or a.get("sim_ok") is not True:
        raise SystemExit("失败：参考答案应当判为通过")
    t = Client(base)
    t.call("POST", "/api/auth/login", {"login_name": "TGEN", "password": password})
    cid = t.call("GET", "/api/teacher/classes")["classes"][0]["id"]
    overview = t.call("GET", f"/api/teacher/classes/{cid}/overview")
    print("教师端总览：活跃人数", overview["kpis"]["active"])
    print("冒烟测试通过")


if __name__ == "__main__":
    main()
