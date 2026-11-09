"""信号 → 代码行映射（docs/judge.md 9.1 节）与 Verilog 结构扫描。"""
from __future__ import annotations

import pytest

from judge import diagnose
from judge.problem import list_problem_ids, load_problem
from judge.vparse import ParseError, parse_top


# ---------- 验收：参考答案的 drivers 与 expected_drivers 一致 ----------

@pytest.mark.parametrize("pid", list_problem_ids())
def test_reference_drivers_match_expected(pid, run_case):
    problem = load_problem(pid)
    result = run_case(problem.ref_path, pid)
    expected = problem.meta["expected_drivers"]
    assert result["drivers_granularity"] == "statement"
    for signal, lines in expected.items():
        assert result["drivers"].get(signal) == lines, signal
    # 每个输出端口都要在 expected_drivers 里
    outputs = set(result["sim"]["trace"][0]["outputs"])
    assert outputs <= set(expected), f"expected_drivers 缺少 {outputs - set(expected)}"


# ---------- 具体写法 ----------

def _drivers(code: str, pid: str = "seq_detector_101") -> tuple[dict, str]:
    result = diagnose(code, pid, log=False)
    assert result["compile"]["ok"], result["compile"]
    return result["drivers"], result["drivers_granularity"]


FSM_PORTS = """module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output wire out
);
"""


def test_register_lines_are_statements_not_whole_block():
    code = FSM_PORTS + """    reg r;
    always @(posedge clk) begin
        if (rst)
            r <= 1'b0;
        else
            r <= in;
    end
    assign out = r;
endmodule
"""
    drivers, granularity = _drivers(code)
    assert granularity == "statement"
    assert drivers["r"] == [10, 12]      # 两条赋值语句，不含 always / if / end 行
    assert drivers["out"] == [14]        # 直接连线：取 assign 那一行


def test_concat_lhs_and_bit_select():
    code = """module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output reg  [3:0] sum,
    output reg        cout
);
    always @(*) begin
        sum[0] = a[0] ^ b[0] ^ cin;
        {cout, sum[3:1]} = a[3:1] + b[3:1] + (a[0] & b[0] | cin & (a[0] ^ b[0]));
    end
endmodule
"""
    drivers, _ = _drivers(code, "adder4")
    assert drivers["sum"] == [9, 10]
    assert drivers["cout"] == [10]


def test_multiline_statement_uses_lhs_line():
    code = FSM_PORTS + """    assign out =
        in &
        rst;
endmodule
"""
    drivers, _ = _drivers(code)
    assert drivers["out"] == [7]


def test_falls_back_to_block_when_scan_fails(monkeypatch):
    import judge.drivers as drv

    def boom(*args, **kwargs):
        raise ParseError("测试用")

    monkeypatch.setattr(drv, "parse_top", boom)
    problem = load_problem("counter_mod10")
    result = diagnose(problem.ref_path.read_text(encoding="utf-8"), "counter_mod10", log=False)
    assert result["drivers_granularity"] == "block"
    assert result["drivers"]["q"] == list(range(8, 17))   # 整个 always 块


def test_drivers_without_yosys_use_scan_only(run_case):
    # while 循环不可综合，yosys 读不进来；仍然给出逐句的行号
    problem = load_problem("prio_encoder4")
    result = run_case(problem.cases_dir / "c3_fragile_while.v", "prio_encoder4")
    assert result["drivers"]["pos"] == [17]
    assert result["drivers"]["valid"] == [11]


# ---------- vparse ----------

def test_parse_always_blocks_and_assignments():
    code = """module top_module(input clk, input [1:0] s, output reg [1:0] y, output reg z);
    // 注释里的 always 不算：always @(posedge clk) y <= 0;
    always @(posedge clk) if (s == 2'd0) y <= 2'd1; else y <= 2'd2;
    always @* begin : comb
        case (s)
            2'd0, 2'd1: z = 1'b1;
            default z = 1'b0;
        endcase
    end
endmodule
"""
    info = parse_top(code)
    assert [(b.first_line, b.last_line) for b in info.always_blocks] == [(3, 3), (4, 9)]
    lines = {(tuple(a.targets), a.line) for a in info.assignments}
    assert (("y",), 3) in lines and (("z",), 6) in lines and (("z",), 7) in lines


def test_parse_ignores_comparison_in_condition():
    code = "module top_module(input [3:0] a, output reg y);\n" \
           "    always @(*) if (a <= 4'd3) y = 1'b1; else y = 1'b0;\nendmodule\n"
    info = parse_top(code)
    assert [a.targets for a in info.assignments] == [["y"], ["y"]]


def test_parse_missing_top_module():
    with pytest.raises(ParseError):
        parse_top("module other; endmodule\n")
