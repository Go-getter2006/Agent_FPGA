"""testbench 打分（docs/judge.md 9.3 节）。

学生交一个自己写的 testbench：先用参考答案跑，确认能编译、能打印 STEP 行；
再用 cases/ 里的每个错误样本跑同一个 testbench，轨迹与参考答案不同就算“抓住”了这个 bug。
预期标签含 fragile_pass 的样本仿真输出与参考答案相同，任何激励都抓不到，不计入。
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from . import config
from .log import append_log
from .problem import load_problem, read_expected_tags
from .sim import compile_design, simulate

STUDENT_TB_FILE = "student_tb.v"
DESIGN_FILE = "design.v"

_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_INSTANCE_RE = re.compile(
    r"\btop_module\s+(?:#\s*\(.*?\)\s*)?[A-Za-z_][A-Za-z0-9_$]*\s*(?:\[[^\]]*\]\s*)?\(", re.S
)


def _instantiates_top(tb_code: str) -> bool:
    return bool(_INSTANCE_RE.search(_COMMENT_RE.sub(" ", tb_code)))


def _result(*, ok: bool, steps: int = 0, score: float | None = None,
            caught: list | None = None, missed: list | None = None, excluded: list | None = None,
            message: str | None = None, errors: list | None = None) -> dict:
    return {
        "ok": ok,
        "steps": steps,
        "score": score,
        "caught": caught or [],
        "missed": missed or [],
        "excluded": excluded or [],
        "message": message,
        "errors": errors or [],
    }


def _run(work: Path, design_text: str, timeout: float) -> tuple[dict, list[dict], bool]:
    """用学生的 testbench 仿真一个设计，返回 (compile 字段, 轨迹, 是否超时)。"""
    (work / DESIGN_FILE).write_text(design_text, encoding="utf-8", newline="")
    comp, vvp = compile_design(work, DESIGN_FILE, "tb.vvp", timeout, tb_file=STUDENT_TB_FILE, tb_top=None)
    if not comp["ok"]:
        return comp, [], False
    trace, timed_out = simulate(work, vvp, timeout)
    return comp, trace, timed_out


def score_testbench(
    tb_code: str,
    problem_id: str,
    *,
    student: str | None = None,
    problems_dir: Path | None = None,
    timeout: float = config.DEFAULT_TIMEOUT,
    log: bool = True,
) -> dict:
    problem = load_problem(problem_id, problems_dir)
    result = _score(tb_code, problem, timeout)
    if log:
        append_log({"type": "score_testbench", "problem": problem.id, "student": student, "result": result})
    return result


def _score(tb_code: str, problem, timeout: float) -> dict:
    if not _instantiates_top(tb_code):
        return _result(ok=False, message="testbench 里没有实例化 top_module，无法测试你的电路")

    with tempfile.TemporaryDirectory(prefix="judge_tb_") as tmp:
        work = Path(tmp)
        text = tb_code if tb_code.endswith("\n") else tb_code + "\n"
        (work / STUDENT_TB_FILE).write_text(text, encoding="utf-8", newline="")

        # 1. 先用参考答案跑学生的 testbench
        comp, ref_trace, timed_out = _run(work, problem.ref_path.read_text(encoding="utf-8"), timeout)
        if not comp["ok"]:
            return _result(ok=False, message="testbench 编译失败，请按下面的报错修改", errors=comp["errors"])
        if timed_out:
            return _result(ok=False, message="testbench 运行超时：是不是忘了在最后调用 $finish？")
        if not ref_trace:
            return _result(ok=False, message="testbench 没有打印任何 STEP 行，请按“STEP <序号> | 输入 | 输出”的格式打印采样结果")

        # 2. 再用每个错误样本跑同一个 testbench
        caught, missed, excluded = [], [], []
        for case in problem.case_paths():
            if "fragile_pass" in read_expected_tags(case):
                excluded.append(case.name)
                continue
            comp, trace, timed_out = _run(work, case.read_text(encoding="utf-8"), timeout)
            # 编译失败、超时、轨迹不同，都说明这个 bug 在学生的激励下暴露了出来
            if not comp["ok"] or timed_out or trace != ref_trace:
                caught.append(case.name)
            else:
                missed.append(case.name)

    counted = len(caught) + len(missed)
    score = round(len(caught) / counted, 4) if counted else None
    return _result(ok=True, steps=len(ref_trace), score=score,
                   caught=caught, missed=missed, excluded=excluded)
