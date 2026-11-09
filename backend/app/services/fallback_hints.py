"""规则提示（docs/llm-deepseek.md 第 8 节）：按“标签 × 等级”的模板，变量全部从裁判诊断里取。

大模型不可用时使用，也是对照组的基础反馈。模板里只有中文说明、信号名、行号和工具原话，
不包含任何代码，满足“面向学生的输出不能包含正确代码”。
输出格式与大模型分级提示相同：{level, focus, message, question, concept_tags}，另带 tag 与 template 便于研究分析。
"""
from __future__ import annotations

from .learner_model import TAG_LABELS

# 选择提示针对哪个标签：越靠前越优先
TAG_PRIORITY = (
    "compile_error", "non_synthesizable", "race_order_sensitive", "latch_inferred", "multi_driven",
    "blocking_in_seq", "nonblocking_in_comb", "width_mismatch", "sim_mismatch", "fragile_pass",
)

TAG_CONCEPTS = {
    "compile_error": [], "non_synthesizable": ["comb_always"], "race_order_sensitive": ["parallel", "blocking"],
    "latch_inferred": ["comb_always"], "multi_driven": ["sequential"], "blocking_in_seq": ["blocking", "sequential"],
    "nonblocking_in_comb": ["blocking", "comb_always"], "width_mismatch": ["width"],
    "sim_mismatch": [], "fragile_pass": [], "pred_miss": ["sequential"], "pass": [],
}

# (message, question)。{变量} 由 _context 填写
TEMPLATES: dict[str, dict[int, tuple[str, str]]] = {
    "compile_error": {
        1: ("第 {error_line} 行附近没有通过编译，工具的原话是：“{error_message}”。先看这一行和它的上一行。",
            "这里是不是少了分号或括号，或者把 reg 和 wire 用混了？"),
        2: ("编译器按语法一句一句地读代码，报错的行号常常落在真正出错位置的下一行。"
            "在 always 块里被赋值的信号要声明成 reg，用 assign 驱动的信号要声明成 wire。",
            "报错涉及的信号是在哪里被赋值的？它的声明和赋值方式对得上吗？"),
        3: ("这就像写中文时漏了句号：读的人会把两句话连在一起读，到下一句才发现读不通。",
            "从报错的那一行往上找一句，哪一句像是“没写完”？"),
    },
    "non_synthesizable": {
        1: ("仿真能跑，但 Yosys 综合时报错：“{synth_error}”。",
            "这段代码里，有没有哪种写法只有在“一步一步执行的程序”里才说得通？"),
        2: ("综合是把代码变成一块固定的电路，电路有多大在综合时就要确定，所以循环的次数必须是常数；"
            "像“一直找到满足条件为止”这样的循环，只能在仿真里执行，变不成电路。",
            "你的循环要转几圈，是写死的，还是取决于输入？"),
        3: ("就像盖房子前必须先定下有几层楼，不能边住边决定要不要再加一层。",
            "能不能把“找到为止”的写法，改成把每一种情况都直接列出来？"),
    },
    "race_order_sensitive": {
        1: ("顺序打乱实验显示：交换 always 块的先后之后，第 {shuffle_step} 步的 {shuffle_signal} 从 {shuffle_base} 变成了 {shuffle_variant}。",
            "哪两个 always 块在同一个时钟沿读写了同一个信号？"),
        2: ("交换 always 块的先后，结果就变了，而真实电路里的各个部分是同时工作的，没有先后。",
            "哪两个块在同一个时钟沿读写了同一个信号？它们读到的是旧值还是新值？"),
        3: ("想象两个人交换手里的卡片：如果一个人先放下卡片、另一个人再去拿，结果就看谁动作快；"
            "真实的触发器像是两人先看清对方手里的卡片，等口令一响再同时交换。",
            "哪一种赋值方式对应“先看清、再一起换”？"),
    },
    "latch_inferred": {
        1: ("Yosys 说 {latch_signals} 被综合成了锁存器。",
            "在组合 always 块里，有没有哪种情况没给它赋值？"),
        2: ("组合逻辑的输出必须在每一种输入下都有确定的值；漏掉的分支会让电路“记住”旧值，这就是锁存器。",
            "你的 if 或 case 覆盖了所有情况吗？"),
        3: ("就像一张查分表，只写了 60 分以上对应的等级，没写 60 分以下；查到没写的那一行，只好沿用上一个人的结果。",
            "你的代码里，哪一种情况相当于“表里没写”？"),
    },
    "multi_driven": {
        1: ("Yosys 发现同一个信号有多个驱动源：{multi_signals}。",
            "这个信号在几个地方被赋值了？分别在哪几行？"),
        2: ("电路里一根导线只能由一个地方驱动。两个 always 块（或两条 assign）同时驱动它，"
            "就像两个人同时往一根线上送不同的电压。",
            "能不能把对这个信号的所有赋值放进同一个 always 块里？"),
        3: ("一块黑板同一时间只能由一个人负责写；两个人各写各的，最后黑板上是什么就说不清了。",
            "这个信号真正该“听”哪一处赋值？"),
    },
    "blocking_in_seq": {
        1: ("Verilator 提示第 {lint_lines} 行在时序 always 块里用了 =（阻塞赋值）。",
            "这几行执行完之后，后面的语句读到的是旧值还是新值？"),
        2: ("时序 always 块里用 = 时，后面的语句会马上读到新值；真实的触发器是在同一个时钟沿同时采样的。",
            "你觉得这里该用哪种赋值？"),
        3: ("排队传话时，如果每个人一听到就立刻改口，最后一个人听到的已经是被改过好几次的话；"
            "触发器像是大家先记下自己听到的，等口令响起再一起改。",
            "你的代码里，谁“听”到的已经是别人刚改过的值？"),
    },
    "nonblocking_in_comb": {
        1: ("Verilator 提示第 {lint_lines} 行在组合 always 块里用了 <=（非阻塞赋值）。",
            "组合逻辑的输出应该在什么时候跟着输入变化？"),
        2: ("组合逻辑没有时钟，输出应该随输入立即变化；块里算出的中间结果要马上能被后面的语句用到，所以组合块里用 =。",
            "如果后一条语句要用前一条刚算出的结果，<= 能做到吗？"),
        3: ("算账时先算小计、再算总计；如果小计要等到“明天”才更新，今天的总计就会用错数。",
            "你的组合块里，哪个中间结果被“推迟”了？"),
    },
    "width_mismatch": {
        1: ("Verilator 提示第 {lint_lines} 行位宽对不上：{lint_message}",
            "这一行左右两边各有几位？多出来或缺少的那几位去哪了？"),
        2: ("Verilog 先按表达式里最宽的操作数决定用几位来算，赋值时多出的高位会被截掉、不够的补 0；进位和状态编码最容易在这里丢。",
            "这个信号需要几位，才能装下它所有可能的值？"),
        3: ("就像用两位数的计数器给 100 个人编号，编到 99 之后再加 1，就回到了 00。",
            "你的信号会不会遇到“装不下”的那一刻？"),
    },
    "sim_mismatch": {
        1: ("先看第 {step} 步的 {signal}：期望 {expected}，实际 {actual}。这一步之前，{signal} 由第 {lines} 行决定。",
            "它们在{moment}做了什么？"),
        2: ("{quadrant_lead}对照期望波形，看你的电路是从哪一步开始“走偏”的：是更新的时机不对（早了或晚了一拍），还是更新出来的值不对？",
            "第 {step} 步的输入是 {inputs}，按题目说明，这时 {signal} 为什么应该是 {expected}？"),
        3: ("调试就像查账：从第一笔对不上的账往前翻，找到最后一笔还对得上的，问题就在这两笔之间。",
            "第 {prev_step} 步还对得上吗？从第 {prev_step} 步到第 {step} 步，你的代码做了什么？"),
    },
    "fragile_pass": {
        1: ("仿真结果和期望一致，但工具还发现了隐患：{risk}。",
            "这个隐患在这次仿真里为什么没有暴露出来？"),
        2: ("仿真只检查了 testbench 给出的这些输入；综合出来的真实电路要在所有输入、所有时刻都正确。",
            "如果换一组输入，或者把电路放到真实芯片上，这个隐患会造成什么后果？"),
        3: ("就像一座桥晴天走得过去，不代表下雨天也安全。",
            "要让它在“下雨天”也安全，代码要怎样写？"),
    },
    "pred_miss": {
        1: ("代码已经对了，但你的预测有 {miss_count} 格没对上。先看第 {pstep} 步的 {psignal}：你预测 {pvalue}，实际是 {pactual}。",
            "不改代码，你能说清楚为什么实际是 {pactual} 吗？"),
        2: ("预测没对上，常常是没想清楚信号在什么时刻更新：时序逻辑在时钟沿之后才变，组合逻辑随输入立刻变。",
            "{psignal} 是时序逻辑还是组合逻辑？在第 {pstep} 步之前，它经历了什么？"),
        3: ("就像看天气：知道今天下雨不难，难的是说清楚为什么会下雨。",
            "如果把第 {pstep} 步的输入换一下，{psignal} 会变成什么？"),
    },
    "pass": {
        1: ("代码和预测都对了。",
            "你能说出这个设计里哪些信号是触发器、为什么吗？"),
        2: ("进阶一点：功能不变，能不能用更少的触发器实现？或者换一种写法，结果还一样吗？",
            "如果去掉其中一个寄存器，哪一步的波形会先变？"),
        3: ("真正的掌握，是能在别人的代码里一眼看出同样的问题。",
            "如果同学把这里的 <= 改成 =，你能预测哪一步会先对不上吗？"),
    },
}

QUADRANT_LEAD = {
    "design_gap": "你对自己代码的预测是对的，说明代码读懂了，问题出在设计思路上。回到题目说明，",
    "concept_gap": "你的电路实际做的事和你预想的也不一样，先弄清代码真正做了什么。",
}


def _fmt_lines(lines: list[int]) -> str:
    if not lines:
        return "相关的几"
    if len(lines) > 1 and lines == list(range(lines[0], lines[-1] + 1)):
        return f"{lines[0]}–{lines[-1]}"
    return "、".join(str(n) for n in lines)


def primary_tag(diagnosis: dict, evaluation: dict | None) -> str:
    tags = diagnosis.get("tags", [])
    for tag in TAG_PRIORITY:
        if tag in tags:
            return tag
    cells = ((evaluation or {}).get("waveform") or {}).get("cells", [])
    items = ((evaluation or {}).get("hardware") or {}).get("items", [])
    if any(c["correct"] is False for c in cells + items):
        return "pred_miss"
    return "pass"


def _context(diagnosis: dict, evaluation: dict | None, quadrant: str | None, shuffle: dict | None) -> dict:
    sim = diagnosis.get("sim") or {}
    trace = sim.get("trace") or []
    mm = sim.get("first_mismatch") or {}
    drivers = diagnosis.get("drivers") or {}
    lint = diagnosis.get("lint") or []
    compile_errors = (diagnosis.get("compile") or {}).get("errors") or []
    synth_msgs = (diagnosis.get("synth") or {}).get("messages") or []
    hw = diagnosis.get("hardware") or {}
    has_clk = bool(trace and "clk" in trace[0]["inputs"]) or any("rst" in r["inputs"] for r in trace[:1])

    def lint_for(codes):
        items = [i for i in lint if i["code"] in codes]
        return _fmt_lines(sorted({i["line"] for i in items if i["line"]})), (items[0]["message"] if items else "")

    blk_lines, _ = lint_for({"BLKSEQ"})
    comb_lines, _ = lint_for({"COMBDLY"})
    width_lines, width_msg = lint_for({"WIDTH", "WIDTHTRUNC", "WIDTHEXPAND", "WIDTHCONCAT", "WIDTHXZEXPAND"})

    cells = ((evaluation or {}).get("waveform") or {}).get("cells", [])
    wrong = sorted((c for c in cells if c["correct"] is False), key=lambda c: (c["step"], c["signal"]))
    first_wrong = wrong[0] if wrong else {}

    variant = next((v for v in (shuffle or {}).get("variants", []) if v.get("first_diff")), None)
    diff = (variant or {}).get("first_diff") or {}

    multi = [m.split("for ", 1)[-1] for m in synth_msgs if "multiple conflicting drivers" in m]
    risk = "、".join(TAG_LABELS[t] for t in ("latch_inferred", "non_synthesizable", "multi_driven")
                    if t in diagnosis.get("tags", []))
    err = compile_errors[0] if compile_errors else {}
    signal = mm.get("signal")
    step = mm.get("step")
    return {
        "step": step, "signal": signal, "expected": mm.get("expected"), "actual": mm.get("actual"),
        "inputs": "、".join(f"{k}={v}" for k, v in (mm.get("inputs") or {}).items()),
        "lines": _fmt_lines(drivers.get(signal, [])) if signal else "相关的几",
        "prev_step": (step - 1) if isinstance(step, int) and step > 0 else 0,
        "moment": "这个时钟沿" if has_clk else "这一步的输入下",
        "quadrant_lead": QUADRANT_LEAD.get(quadrant or "", ""),
        "error_line": err.get("line") or "报错", "error_message": err.get("message", ""),
        "synth_error": next((m for m in synth_msgs if "ERROR" in m), synth_msgs[0] if synth_msgs else ""),
        "latch_signals": "、".join(hw.get("latch_signals") or []) or "某些信号",
        "multi_signals": "、".join(dict.fromkeys(multi)) or "某些信号",
        "lint_lines": blk_lines if blk_lines != "相关的几" else (comb_lines if comb_lines != "相关的几" else width_lines),
        "lint_message": width_msg,
        "risk": risk or "电路描述有隐患",
        "miss_count": len(wrong),
        "pstep": first_wrong.get("step"), "psignal": first_wrong.get("signal"),
        "pvalue": first_wrong.get("value"), "pactual": first_wrong.get("actual"),
        "shuffle_step": diff.get("step"), "shuffle_signal": diff.get("signal"),
        "shuffle_base": diff.get("base"), "shuffle_variant": diff.get("variant"),
        "_lint_lines": {"blocking_in_seq": blk_lines, "nonblocking_in_comb": comb_lines, "width_mismatch": width_lines},
    }


def _focus(tag: str, ctx: dict, diagnosis: dict) -> dict:
    drivers = diagnosis.get("drivers") or {}
    if tag in ("sim_mismatch",):
        return {"step": ctx["step"], "signal": ctx["signal"], "lines": drivers.get(ctx["signal"], [])}
    if tag == "pred_miss":
        return {"step": ctx["pstep"], "signal": ctx["psignal"], "lines": drivers.get(ctx["psignal"], [])}
    if tag == "compile_error":
        line = ctx["error_line"]
        return {"step": None, "signal": None, "lines": [line] if isinstance(line, int) else []}
    if tag in ("blocking_in_seq", "nonblocking_in_comb", "width_mismatch"):
        codes = {"blocking_in_seq": {"BLKSEQ"}, "nonblocking_in_comb": {"COMBDLY"},
                 "width_mismatch": {"WIDTH", "WIDTHTRUNC", "WIDTHEXPAND", "WIDTHCONCAT"}}[tag]
        lines = sorted({i["line"] for i in diagnosis.get("lint", []) if i["code"] in codes and i["line"]})
        return {"step": None, "signal": None, "lines": lines}
    if tag == "latch_inferred":
        sigs = (diagnosis.get("hardware") or {}).get("latch_signals") or []
        return {"step": None, "signal": sigs[0] if sigs else None,
                "lines": drivers.get(sigs[0], []) if sigs else []}
    if tag == "race_order_sensitive":
        return {"step": ctx["shuffle_step"], "signal": ctx["shuffle_signal"],
                "lines": drivers.get(ctx["shuffle_signal"], []) if ctx["shuffle_signal"] else []}
    return {"step": None, "signal": None, "lines": []}


class _SafeDict(dict):
    def __missing__(self, key):
        return "…"


def generate(diagnosis: dict, level: int, *, evaluation: dict | None = None, quadrant: str | None = None,
             shuffle: dict | None = None, problem_kps: list[str] | None = None) -> dict:
    level = max(1, min(3, int(level)))
    if shuffle and shuffle.get("order_sensitive") and "race_order_sensitive" not in diagnosis.get("tags", []):
        diagnosis = {**diagnosis, "tags": [*diagnosis.get("tags", []), "race_order_sensitive"]}
    tag = primary_tag(diagnosis, evaluation)
    ctx = _context(diagnosis, evaluation, quadrant, shuffle)
    if tag in ctx["_lint_lines"]:
        ctx["lint_lines"] = ctx["_lint_lines"][tag]
    message, question = TEMPLATES[tag][level]
    values = _SafeDict({k: ("…" if v is None else v) for k, v in ctx.items() if not k.startswith("_")})
    concept = TAG_CONCEPTS.get(tag) or []
    if not concept and problem_kps:
        concept = problem_kps[:1]
    return {
        "level": level,
        "focus": _focus(tag, ctx, diagnosis),
        "message": message.format_map(values),
        "question": question.format_map(values),
        "concept_tags": concept,
        "tag": tag,
        "template": f"{tag}.{level}",
    }
