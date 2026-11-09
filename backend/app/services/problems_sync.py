"""把 problems/*/problem.yaml 和 knowledge_points.yaml 同步进数据库（界面只读）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from sqlalchemy.orm import Session as DbSession

from judge import diagnose
from judge.diagnose import reference_trace
from judge.problem import list_problem_ids, load_problem

from ..config import get_settings
from ..db import utcnow
from ..models import KnowledgePoint, Problem

KP_FILE = Path(__file__).resolve().parents[1] / "data" / "knowledge_points.yaml"


def sync_knowledge_points(db: DbSession) -> int:
    items = yaml.safe_load(KP_FILE.read_text(encoding="utf-8")) or []
    for order, item in enumerate(items):
        kp = db.get(KnowledgePoint, item["code"]) or KnowledgePoint(code=item["code"])
        kp.name = item["name"]
        kp.description = item.get("description", "")
        kp.sort_order = order
        db.add(kp)
    return len(items)


def _skeleton(trace: list[dict]) -> dict:
    """波形骨架：STEP 列表、输入信号的值、输出信号名与位宽。不含输出的值（预测前不能泄露）。"""
    first = trace[0]
    return {
        "steps": [row["step"] for row in trace],
        "inputs": [{"name": name, "width": len(first["inputs"][name]),
                    "values": [row["inputs"][name] for row in trace]} for name in first["inputs"]],
        "outputs": [{"name": name, "width": len(first["outputs"][name])} for name in first["outputs"]],
    }


def tb_template(skeleton: dict) -> str:
    """创作题第 ⑤ 步给学生的 testbench 模板：端口已连好，学生只需写激励。"""
    decls, conns = [], []
    for sig in skeleton["inputs"]:
        rng = f"[{sig['width'] - 1}:0] " if sig["width"] > 1 else ""
        decls.append(f"    reg  {rng}{sig['name']};")
        conns.append(f".{sig['name']}({sig['name']})")
    for sig in skeleton["outputs"]:
        rng = f"[{sig['width'] - 1}:0] " if sig["width"] > 1 else ""
        decls.append(f"    wire {rng}{sig['name']};")
        conns.append(f".{sig['name']}({sig['name']})")
    names_in = [s["name"] for s in skeleton["inputs"]]
    names_out = [s["name"] for s in skeleton["outputs"]]
    has_clk = "clk" in names_in or any(s["name"] == "clk" for s in skeleton["inputs"])
    fmt_in = " ".join(f"{n}=%b" for n in names_in if n != "clk")
    fmt_out = " ".join(f"{n}=%b" for n in names_out)
    args = ", ".join([n for n in names_in if n != "clk"] + names_out)
    lines = [
        "// 我的 testbench：设计激励，让错误的电路暴露出来",
        "module my_tb;",
        *decls,
        "",
        f"    top_module dut ({', '.join(conns)});",
        "",
    ]
    if has_clk:
        lines += ["    initial clk = 1'b0;", "    always #5 clk = ~clk;", ""]
    lines += [
        "    integer n = 0;",
        "    // 每个采样点打印一行，格式：STEP <序号> | 输入 | 输出",
        "    task show;",
        "        begin",
        f'            $display("STEP %0d | {fmt_in} | {fmt_out}", n, {args});',
        "            n = n + 1;",
        "        end",
        "    endtask",
        "",
        "    initial begin",
        "        // 在这里给激励。时序电路：改输入 → @(negedge clk) → show；组合电路：改输入 → #1 → show",
        "",
        "        $finish;",
        "    end",
        "endmodule",
        "",
    ]
    return "\n".join(lines)


def sync_problems(db: DbSession, problems_dir: Path | None = None) -> list[str]:
    root = Path(problems_dir or get_settings().problems_dir)
    synced = []
    for pid in list_problem_ids(root):
        p = load_problem(pid, root)
        meta = p.meta
        trace = reference_trace(p)
        starter = None
        if meta.get("starter"):
            starter = (p.dir / meta["starter"]).read_text(encoding="utf-8")
        skeleton = _skeleton(trace)
        row = db.get(Problem, pid) or Problem(id=pid)
        starter_hash = hashlib.sha256(starter.encode("utf-8")).hexdigest() if starter else None
        old_meta = row.meta or {}
        if starter is None:
            starter_eval = None
        elif old_meta.get("starter_hash") == starter_hash and old_meta.get("starter_eval"):
            starter_eval = old_meta["starter_eval"]
        else:
            # 起始代码的工具结果：复习题的标准答案（只在服务端使用）
            d = diagnose(starter, pid, problems_dir=root, log=False)
            starter_eval = {"sim": {"trace": d["sim"]["trace"]}, "hardware": d["hardware"],
                            "drivers": d["drivers"], "tags": d["tags"]}
        row.title = meta["title"]
        row.knowledge_points = list(meta["knowledge_points"])
        row.primm_type = meta["primm_type"]
        row.difficulty = int(meta["difficulty"])
        row.meta = {
            "spec": (p.dir / "spec.md").read_text(encoding="utf-8") if (p.dir / "spec.md").is_file() else "",
            "starter": starter,
            "predict_points": meta["predict_points"],
            "hardware_questions": meta["hardware_questions"],
            "modify_goal": meta.get("modify_goal") or "",
            "skeleton": skeleton,
            "ref_trace": trace,             # 只在学生运行之后作为“期望”返回
            "tb_template": tb_template(skeleton),
            "starter_hash": starter_hash,
            "starter_eval": starter_eval,
        }
        row.synced_at = utcnow()
        db.add(row)
        synced.append(pid)
    return synced


def sync_all(db: DbSession) -> None:
    sync_knowledge_points(db)
    sync_problems(db)
    db.commit()
