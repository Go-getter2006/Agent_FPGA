"""裁判本身的单元测试：轨迹解析、比较、超时、可复现、命令行、日志。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from judge import JudgeError, diagnose
from judge.config import REPO_ROOT
from judge.sim import parse_compile_errors
from judge.tags import lint_tag
from judge.runner import CmdResult
from judge.trace import first_mismatch, parse_trace

from .conftest import FIXTURES

PID = "seq_detector_101"
CASES = REPO_ROOT / "problems" / PID / "cases"


# ---------- 轨迹解析与比较 ----------

def test_parse_trace_ignores_other_lines():
    out = (
        "STEP 0 | rst=1 in=0 | out=0\n"
        "hello from $display\n"
        "STEP 1 | rst=0 in=1 | out=x\n"
        "tb.v:30: $finish called at 20 (1s)\n"
    )
    assert parse_trace(out) == [
        {"step": 0, "inputs": {"rst": "1", "in": "0"}, "outputs": {"out": "0"}},
        {"step": 1, "inputs": {"rst": "0", "in": "1"}, "outputs": {"out": "x"}},
    ]


def _row(step, out, **inputs):
    return {"step": step, "inputs": inputs, "outputs": {"out": out}}


def test_first_mismatch_none_when_equal():
    ref = [_row(0, "0", a="1"), _row(1, "1", a="0")]
    assert first_mismatch(ref, [dict(r) for r in ref]) is None


def test_first_mismatch_reports_step_signal_and_inputs():
    ref = [_row(0, "0", a="1"), _row(1, "1", a="0"), _row(2, "0", a="1")]
    stu = [_row(0, "0", a="1"), _row(1, "x", a="0"), _row(2, "1", a="1")]
    assert first_mismatch(ref, stu) == {
        "step": 1, "signal": "out", "expected": "1", "actual": "x", "inputs": {"a": "0"},
    }


def test_first_mismatch_short_trace():
    ref = [_row(0, "0"), _row(1, "1")]
    mm = first_mismatch(ref, [_row(0, "0")])
    assert mm["step"] == 1 and mm["actual"] is None


def test_compile_error_parsing_drops_warnings():
    res = CmdResult(returncode=1, stdout="", timeout=False, stderr=(
        "student.v:3: warning: implicit definition of wire 'z'.\n"
        "student.v:4: syntax error\n"
        "I give up.\n"
    ))
    assert parse_compile_errors(res) == [{"file": "student.v", "line": 4, "message": "syntax error"}]


# ---------- 标签 ----------

def _lint(code, message):
    return {"code": code, "line": 1, "message": message}


def test_widthexpand_of_one_bit_operand_is_not_a_tag():
    # a + b + cin：1 位的 cin 被扩展，教材标准写法，不算误区
    item = _lint("WIDTHEXPAND", "Operator ADD expects 5 bits on the RHS, but RHS's VARREF 'cin' generates 1 bits.")
    assert lint_tag(item) is None


def test_widthexpand_of_multibit_operand_is_a_tag():
    item = _lint("WIDTHEXPAND", "Operator EQ expects 4 bits on the LHS, but LHS's VARREF 'cnt' generates 3 bits.")
    assert lint_tag(item) == "width_mismatch"


def test_other_lint_mappings():
    assert lint_tag(_lint("WIDTHTRUNC", "... generates 1 bits.")) == "width_mismatch"
    assert lint_tag(_lint("BLKSEQ", "Blocking assignment '=' in sequential logic process")) == "blocking_in_seq"
    assert lint_tag(_lint("COMBDLY", "Non-blocking assignment '<=' in combinational logic process")) == "nonblocking_in_comb"
    assert lint_tag(_lint("UNUSEDSIGNAL", "Signal is not used: 'rst'")) is None


def test_lint_tags_blocking_and_nonblocking():
    result = diagnose((FIXTURES / "blk_nonblk.v").read_text(encoding="utf-8"), PID, log=False)
    assert result["sim"]["ok"]
    assert result["tags"] == ["blocking_in_seq", "nonblocking_in_comb"]
    codes = {item["code"] for item in result["lint"]}
    assert {"BLKSEQ", "COMBDLY"} <= codes


def test_compile_error_skips_later_stages(run_case):
    result = run_case(CASES / "c7_compile.v", PID)
    assert result["tags"] == ["compile_error"]
    assert result["sim"] == {"ok": False, "timeout": False, "trace": [], "first_mismatch": None}
    assert result["synth"]["ok"] is None
    assert result["drivers"] == {} and result["drivers_granularity"] is None
    assert result["hardware"] == {"ff_signals": None, "latch_signals": None, "ff_count": None, "lut_count": None}
    err = result["compile"]["errors"][0]
    assert err["file"] == "student.v" and isinstance(err["line"], int)


def test_hardware_fields(run_case):
    result = run_case(CASES / "c5_fragile_latch.v", PID)
    assert result["hardware"]["ff_signals"] == ["state"]
    assert result["hardware"]["latch_signals"] == ["out"]


def test_output_keys_and_order(run_case):
    result = run_case(REPO_ROOT / "problems" / PID / "ref.v", PID)
    assert list(result) == ["problem", "compile", "sim", "synth", "hardware", "lint",
                            "drivers", "drivers_granularity", "tags"]
    assert list(result["sim"]) == ["ok", "timeout", "trace", "first_mismatch"]
    assert list(result["hardware"]) == ["ff_signals", "latch_signals", "ff_count", "lut_count"]


# ---------- 超时 ----------

def test_simulation_timeout_does_not_crash():
    result = diagnose((FIXTURES / "comb_loop.v").read_text(encoding="utf-8"), PID, timeout=5, log=False)
    assert result["sim"]["timeout"] is True
    assert result["sim"]["ok"] is False
    assert result["sim"]["trace"] == []
    assert "sim_mismatch" in result["tags"]


# ---------- 可复现 / 命令行 / 日志 ----------

def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "judge", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, env=os.environ.copy(),
    )


def test_cli_output_is_reproducible():
    case = str(CASES / "c3_latch.v")
    first = _cli(case, PID, "--no-log")
    second = _cli(case, PID, "--no-log")
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    data = json.loads(first.stdout)
    assert data["problem"] == PID and "latch_inferred" in data["tags"]


def test_cli_unknown_problem():
    res = _cli(str(CASES / "c1_no_overlap.v"), "no_such_problem", "--no-log")
    assert res.returncode == 2
    assert "找不到题目" in res.stderr


def test_unknown_problem_raises():
    with pytest.raises(JudgeError):
        diagnose("module top_module; endmodule", "../etc", log=False)


def test_log_line_written(tmp_path, monkeypatch):
    log_file = tmp_path / "judge.jsonl"
    monkeypatch.setenv("JUDGE_LOG_PATH", str(log_file))
    code = (CASES / "c1_no_overlap.v").read_text(encoding="utf-8")
    result = diagnose(code, PID, student="a1b2c3d4")
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["problem"] == PID and record["student"] == "a1b2c3d4"
    assert record["ts"].endswith("+00:00")
    assert record["diagnosis"] == result
    assert "ts" not in result  # 时间戳只进日志
