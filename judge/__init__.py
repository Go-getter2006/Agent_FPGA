"""仿真裁判：用 iverilog / yosys / verilator 对学生的 Verilog 代码给出可复现的结构化诊断。

库用法：
    from judge import diagnose, shuffle_test, score_testbench, apply_shuffle
    result = diagnose(code_text, "seq_detector_101", student="a1b2c3d4")
    shuffle = shuffle_test(code_text, "seq_detector_101")
    result = apply_shuffle(result, shuffle)        # 顺序相关时加 race_order_sensitive 标签
    tb_result = score_testbench(tb_text, "seq_detector_101")
    netlist = schematic(code_text)                 # 电路图用的 RTL 级网表（只用于展示）
"""
from .diagnose import diagnose
from .problem import JudgeError
from .schematic import schematic
from .shuffle import apply_shuffle, shuffle_test
from .testbench import score_testbench

__all__ = ["diagnose", "shuffle_test", "score_testbench", "apply_shuffle", "schematic", "JudgeError"]
