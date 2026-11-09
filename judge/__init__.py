"""仿真裁判：用 iverilog / yosys / verilator 对学生的 Verilog 代码给出可复现的结构化诊断。

库用法：
    from judge import diagnose, score_testbench
    result = diagnose(code_text, "seq_detector_101", student="a1b2c3d4")
    tb_result = score_testbench(tb_text, "seq_detector_101", student="a1b2c3d4")
"""
from .diagnose import diagnose
from .problem import JudgeError
from .testbench import score_testbench

__all__ = ["diagnose", "score_testbench", "JudgeError"]
