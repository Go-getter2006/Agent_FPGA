"""testbench 打分（docs/judge.md 9.3 节）。"""
from __future__ import annotations

import json

import pytest

from judge import score_testbench
from judge.problem import list_problem_ids, load_problem, read_expected_tags

ADDER_HEADER = """
module my_test;
    reg  [3:0] a, b;
    reg        cin;
    wire [3:0] sum;
    wire       cout;
    top_module u (.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));
"""


def _adder_tb(vectors: list[tuple[int, int, int]], finish: bool = True) -> str:
    body = "".join(
        f"        a = {x}; b = {y}; cin = {c}; #1;\n"
        f'        $display("STEP {i} | a=%b b=%b cin=%b | sum=%b cout=%b", a, b, cin, sum, cout);\n'
        f"        #9;\n"
        for i, (x, y, c) in enumerate(vectors)
    )
    end = "        $finish;\n" if finish else ""
    return ADDER_HEADER + "    initial begin\n" + body + end + "    end\nendmodule\n"


@pytest.mark.parametrize("pid", list_problem_ids())
def test_own_tb_scores_full(pid):
    """验收：题目自带的 tb.v 当作学生 tb，得分必须是 1.0。"""
    problem = load_problem(pid)
    result = score_testbench(problem.tb_path.read_text(encoding="utf-8"), pid, log=False)
    assert result["ok"], result["message"]
    assert result["score"] == 1.0
    assert result["missed"] == []
    excluded = sorted(p.name for p in problem.case_paths()
                      if {"fragile_pass", "compile_error"} & set(read_expected_tags(p)))
    assert result["excluded"] == excluded
    assert result["steps"] > 0


def test_weak_tb_misses_bug():
    # cin 始终为 0：抓不住“忘了加 cin”的错误
    tb = _adder_tb([(1, 2, 0), (8, 8, 0), (15, 15, 0)])
    result = score_testbench(tb, "adder4", log=False)
    assert result["ok"]
    assert result["missed"] == ["c1_no_cin.v"]
    assert result["caught"] == ["c2_cout_shift.v", "c3_leftover_assign.v"]
    assert result["excluded"] == ["c4_fragile_latch.v", "c5_compile.v"]
    assert result["score"] == 0.6667
    assert result["steps"] == 3


def test_compile_error_case_gives_no_free_points():
    # 只测 1 + 2：一个真正的 bug 都抓不到，得分应为 0（编译错误样本不计入）
    result = score_testbench(_adder_tb([(1, 2, 0)]), "adder4", log=False)
    assert result["score"] == 0.0
    assert result["caught"] == []


def test_output_keys():
    result = score_testbench(_adder_tb([(1, 2, 1)]), "adder4", log=False)
    assert list(result) == ["ok", "steps", "score", "caught", "missed", "excluded", "message", "errors"]


def test_tb_compile_error():
    tb = _adder_tb([(1, 2, 0)]).replace("    initial begin\n", "    initial begin\n        a = ;\n")
    result = score_testbench(tb, "adder4", log=False)
    assert not result["ok"]
    assert "编译失败" in result["message"]
    assert result["errors"] and result["errors"][0]["file"] == "student_tb.v"
    assert result["score"] is None


def test_tb_without_step_lines():
    tb = _adder_tb([(1, 2, 0)]).replace('$display("STEP', '$display("STAGE')
    result = score_testbench(tb, "adder4", log=False)
    assert not result["ok"] and "STEP" in result["message"]


def test_tb_without_instance():
    tb = "module my_test;\n    initial begin $display(\"STEP 0 | a=0 | y=0\"); $finish; end\nendmodule\n"
    result = score_testbench(tb, "adder4", log=False)
    assert not result["ok"] and "top_module" in result["message"]


def test_tb_instance_in_comment_does_not_count():
    tb = "// top_module u (.a(a));\nmodule my_test;\n    initial $finish;\nendmodule\n"
    result = score_testbench(tb, "adder4", log=False)
    assert not result["ok"] and "top_module" in result["message"]


def test_tb_without_finish_times_out():
    tb = _adder_tb([(1, 2, 0)], finish=False).replace(
        "    initial begin", "    reg clk = 0;\n    always #5 clk = ~clk;\n    initial begin"
    )
    result = score_testbench(tb, "adder4", timeout=2, log=False)
    assert not result["ok"] and "$finish" in result["message"]


def test_score_is_logged(tmp_path, monkeypatch):
    log_file = tmp_path / "judge.jsonl"
    monkeypatch.setenv("JUDGE_LOG_PATH", str(log_file))
    result = score_testbench(_adder_tb([(1, 2, 1)]), "adder4", student="a1b2c3d4")
    record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert record["type"] == "score_testbench"
    assert record["student"] == "a1b2c3d4" and record["result"] == result
