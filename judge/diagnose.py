"""诊断流程（docs/judge.md 第 5 节）。"""
from __future__ import annotations

import fcntl
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .lint import run_lint
from .problem import JudgeError, Problem, load_problem
from .sim import compile_design, simulate
from .synth import has_multi_driver, hardware_stats, null_hardware, synth_check
from .tags import compute_tags
from .trace import first_mismatch

_REF_TRACE_CACHE: dict[str, list[dict]] = {}


def _write(path: Path, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8", newline="")


def reference_trace(problem: Problem, timeout: float = config.DEFAULT_TIMEOUT) -> list[dict]:
    """参考答案的轨迹。按 ref.v + tb.v 的内容缓存。"""
    ref_text = problem.ref_path.read_text(encoding="utf-8")
    tb_text = problem.tb_path.read_text(encoding="utf-8")
    key = hashlib.sha256((ref_text + "\0" + tb_text).encode("utf-8")).hexdigest()
    if key in _REF_TRACE_CACHE:
        return _REF_TRACE_CACHE[key]
    with tempfile.TemporaryDirectory(prefix="judge_ref_") as tmp:
        work = Path(tmp)
        _write(work / config.REF_FILE, ref_text)
        _write(work / config.TB_FILE, tb_text)
        comp, vvp = compile_design(work, config.REF_FILE, "ref.vvp", timeout)
        if not comp["ok"]:
            raise JudgeError(f"题目 {problem.id} 的参考答案编译失败：{comp['errors']}")
        trace, timed_out = simulate(work, vvp, timeout)
    if timed_out:
        raise JudgeError(f"题目 {problem.id} 的参考答案仿真超时")
    if not trace:
        raise JudgeError(f"题目 {problem.id} 的 testbench 没有打印任何 STEP 行")
    _REF_TRACE_CACHE[key] = trace
    return trace


def diagnose(
    code: str,
    problem_id: str,
    *,
    student: str | None = None,
    problems_dir: Path | None = None,
    timeout: float = config.DEFAULT_TIMEOUT,
    log: bool = True,
) -> dict:
    """对一份学生代码做完整诊断，返回第 6 节格式的字典。

    同一输入多次调用，返回值完全一致；时间戳只写进日志。
    """
    problem = load_problem(problem_id, problems_dir)
    ref_trace = reference_trace(problem, timeout)

    with tempfile.TemporaryDirectory(prefix="judge_") as tmp:
        work = Path(tmp)
        _write(work / config.STUDENT_FILE, code)
        _write(work / config.TB_FILE, problem.tb_path.read_text(encoding="utf-8"))

        # 1. 编译
        compile_result, vvp = compile_design(work, config.STUDENT_FILE, "student.vvp", timeout)

        if not compile_result["ok"]:
            sim = {"ok": False, "timeout": False, "trace": [], "first_mismatch": None}
            synth = {"ok": None, "timeout": False, "messages": []}   # 编译失败，未综合
            hardware = null_hardware()
            lint: list[dict] = []
            multi = False
        else:
            # 2. 仿真并与参考答案比较
            trace, timed_out = simulate(work, vvp, timeout)
            mismatch = None if timed_out else first_mismatch(ref_trace, trace)
            sim = {
                "ok": not timed_out and mismatch is None,
                "timeout": timed_out,
                "trace": trace,
                "first_mismatch": mismatch,
            }
            # 3. 综合检查
            synth = synth_check(work, config.STUDENT_FILE, timeout)
            multi = has_multi_driver(synth)
            # 4. 硬件统计（综合失败时各字段为 null）
            hardware = hardware_stats(work, config.STUDENT_FILE, timeout) if synth["ok"] else null_hardware()
            # 5. 静态检查
            lint = run_lint(work, config.STUDENT_FILE, timeout)

    # 6. 标签
    tags = compute_tags(
        compile_ok=compile_result["ok"], sim=sim, synth=synth,
        hardware=hardware, lint=lint, yosys_multi_driven=multi,
    )
    result = {
        "problem": problem.id,
        "compile": compile_result,
        "sim": sim,
        "synth": synth,
        "hardware": hardware,
        "lint": lint,
        "drivers": {},          # 阶段 2 填写
        "tags": tags,
    }
    if log:
        append_log(result, student)
    return result


def append_log(result: dict, student: str | None, path: Path | None = None) -> None:
    path = Path(path) if path else config.log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "problem": result["problem"],
        "student": student,
        "diagnosis": result,
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)     # 多个 worker 同时写时不互相穿插
        try:
            f.write(line)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def to_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
