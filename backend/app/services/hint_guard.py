"""大模型输出校验（docs/llm-deepseek.md 5.3 节，确定性规则）。

1. JSON 能解析，字段齐全；level 等于请求的等级
2. message ≤ 200 字符，question 以“？”结尾
3. 出现以下任一情况判为“泄露代码”：含 ```；同时含 module 和 endmodule；有 2 行及以上以
   assign、always、reg、wire、if、case 开头或含 <= 的代码样式行
   （实现补充：else、begin、end*、input、output、localparam、parameter 开头的行，以及形如
   “x = …;”、“S0: x = …;” 的赋值语句行也算代码样式行；只放宽了识别范围，阈值仍是 2 行）
4. focus.lines 必须在学生代码的行号范围内，且优先落在 drivers 里（不在 drivers 里只记警告）
"""
from __future__ import annotations

import json
import re

REQUIRED = ("level", "focus", "message", "question", "concept_tags")
_CODE_LINE = re.compile(
    r"^\s*(assign|always|reg|wire|if|case|casez|casex|else|begin|end\w*|input|output|localparam|parameter)\b"
    r"|^\s*([A-Za-z_][\w$]*\s*:\s*)?[A-Za-z_{][\w$\[\]:, {}]*\s*=\s*[^=].*;\s*$")
LEAK_NOTICE = "助教不能直接给出代码，换个问法试试看"


def leak_reason(text: str) -> str | None:
    """文本是否在泄露代码；返回原因或 None。"""
    if "```" in text:
        return "含代码块标记 ```"
    if re.search(r"\bmodule\b", text) and re.search(r"\bendmodule\b", text):
        return "同时出现 module 和 endmodule"
    lines = [ln for ln in text.splitlines() if _CODE_LINE.match(ln) or "<=" in ln]
    if len(lines) >= 2:
        return f"有 {len(lines)} 行代码样式的内容"
    return None


def validate_hint(raw: str, *, level: int, code_lines: int, drivers: dict[str, list[int]] | None = None) -> dict:
    """返回 {"ok", "reasons", "warnings", "hint"}；hint 是规整后的提示（只在 ok 时可用）。"""
    reasons: list[str] = []
    warnings: list[str] = []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {"ok": False, "reasons": ["不是合法的 json"], "warnings": [], "hint": None}
    if not isinstance(data, dict):
        return {"ok": False, "reasons": ["json 顶层不是对象"], "warnings": [], "hint": None}
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        reasons.append(f"缺少字段：{', '.join(missing)}")
    if data.get("level") != level:
        reasons.append(f"level 应为 {level}")
    message = data.get("message") if isinstance(data.get("message"), str) else ""
    question = data.get("question") if isinstance(data.get("question"), str) else ""
    question = question.strip()
    if question.endswith("?"):
        question = question[:-1] + "？"
    if not message.strip():
        reasons.append("message 为空")
    if len(message) > 200:
        reasons.append(f"message 超过 200 字符（{len(message)}）")
    if not question.endswith("？"):
        reasons.append("question 不是以“？”结尾")
    leak = leak_reason(f"{message}\n{question}") or leak_reason(raw)
    if leak:
        reasons.append(f"泄露代码：{leak}")

    focus = data.get("focus") if isinstance(data.get("focus"), dict) else {}
    lines = focus.get("lines") or []
    if not isinstance(lines, list) or not all(isinstance(x, int) for x in lines):
        reasons.append("focus.lines 不是整数列表")
        lines = []
    out_of_range = [x for x in lines if x < 1 or x > code_lines]
    if out_of_range:
        reasons.append(f"focus.lines 超出代码行号范围：{out_of_range}")
    if drivers and lines:
        driver_lines = {x for ls in drivers.values() for x in ls}
        if not set(lines) & driver_lines:
            warnings.append("focus.lines 没有落在 drivers 里")
    tags = data.get("concept_tags") if isinstance(data.get("concept_tags"), list) else []

    hint = {
        "level": level,
        "focus": {"step": focus.get("step"), "signal": focus.get("signal"), "lines": lines},
        "message": message.strip(),
        "question": question,
        "concept_tags": [str(t) for t in tags][:5],
    }
    return {"ok": not reasons, "reasons": reasons, "warnings": warnings, "hint": hint if not reasons else None}


# ---------------------------------------------------------------- 第 2 版（4 级提示：思路 / 定位 / 代码提示 / 参考答案）
# docs/llm-deepseek.md 5.3 节第 2 版：
# - 1、2 级：沿用上面的规则，不给代码；message 里可以有 Markdown 的加粗和行内代码
# - 3 级：code 字段可以给代码框架或小例子，最多 8 行；不能出现完整模块（module…endmodule），
#   也不能原样写出参考答案里的“答案行”（含 = 的语句，去掉注释和空白后逐行比较；只赋常数的行如 q <= 0; 除外）
# - 助教对话：学生看过参考答案之前，适用同样的“完整模块 / 答案行”规则，每个代码块最多 12 行

MAX_CODE_LINES = 8
MAX_CHAT_BLOCK_LINES = 12
_CONST_ASSIGN = re.compile(r"^[A-Za-z_][\w$\[\]:]*<?=[0-9'bBhHdDoOxXzZ_]+;$")


def _norm(line: str) -> str:
    return re.sub(r"\s+", "", line.split("//", 1)[0].replace("`", ""))


def answer_lines(ref_code: str) -> set[str]:
    """参考答案里的“答案行”：去掉注释、空白后含 = 的语句；只给常数赋值的行（复位、默认值）不算。"""
    out = set()
    for ln in ref_code.splitlines():
        n = _norm(ln)
        if "=" in n and len(n) >= 4 and not _CONST_ASSIGN.match(n):
            out.add(n)
    return out


def reveals_answer(text: str, ref_code: str | None) -> str | None:
    if re.search(r"\bmodule\b", text) and re.search(r"\bendmodule\b", text):
        return "写出了完整的模块（module…endmodule）"
    if ref_code:
        lines = answer_lines(ref_code)
        for ln in text.splitlines():
            if _norm(ln) in lines:
                return "原样写出了参考答案里的语句"
    return None


def _strip_fence(code: str) -> str:
    code = code.strip("\n")
    m = re.match(r"^```[\w-]*\n(.*?)\n?```\s*$", code, re.S)
    return m.group(1) if m else code


def chat_leak_reason(text: str, ref_code: str | None, answer_revealed: bool) -> str | None:
    """助教对话第 2 版：看过参考答案之后不限制；之前不能写出完整模块、答案行或过长的代码块。"""
    if answer_revealed:
        return None
    reason = reveals_answer(text, ref_code)
    if reason:
        return reason
    for block in re.findall(r"```[^\n]*\n(.*?)(?:```|$)", text, re.S):
        n = len([ln for ln in block.splitlines() if ln.strip()])
        if n > MAX_CHAT_BLOCK_LINES:
            return f"代码块有 {n} 行，超过 {MAX_CHAT_BLOCK_LINES} 行"
    return None


def validate_hint_v2(raw: str, *, level: int, code_lines: int, drivers: dict[str, list[int]] | None = None,
                     ref_code: str | None = None) -> dict:
    """第 2 版分级提示的校验；返回格式与 validate_hint 相同，hint 多一个 code 字段。"""
    reasons: list[str] = []
    warnings: list[str] = []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {"ok": False, "reasons": ["不是合法的 json"], "warnings": [], "hint": None}
    if not isinstance(data, dict):
        return {"ok": False, "reasons": ["json 顶层不是对象"], "warnings": [], "hint": None}
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        reasons.append(f"缺少字段：{', '.join(missing)}")
    if data.get("level") != level:
        reasons.append(f"level 应为 {level}")
    message = data.get("message") if isinstance(data.get("message"), str) else ""
    question = (data.get("question") if isinstance(data.get("question"), str) else "").strip()
    if question.endswith("?"):
        question = question[:-1] + "？"
    code = _strip_fence(data.get("code")) if isinstance(data.get("code"), str) else ""
    if not message.strip():
        reasons.append("message 为空")
    if len(message) > 300:
        reasons.append(f"message 超过 300 字符（{len(message)}）")
    if not question.endswith("？"):
        reasons.append("question 不是以“？”结尾")
    prose = f"{message}\n{question}"
    if "```" in prose:
        reasons.append("message / question 里有代码块（代码要放在 code 字段）")
    elif leak_reason(prose):
        reasons.append(f"泄露代码：{leak_reason(prose)}")
    if level < 3 and code.strip():
        warnings.append(f"{level} 级提示不应给代码，已去掉 code")
        code = ""
    if level == 3:
        if not code.strip():
            reasons.append("3 级提示缺少 code")
        n = len([ln for ln in code.splitlines() if ln.strip()])
        if n > MAX_CODE_LINES:
            reasons.append(f"code 有 {n} 行，超过 {MAX_CODE_LINES} 行")
    reveal = reveals_answer(f"{prose}\n{code}", ref_code)
    if reveal:
        reasons.append(f"泄露答案：{reveal}")

    focus = data.get("focus") if isinstance(data.get("focus"), dict) else {}
    lines = focus.get("lines") or []
    if not isinstance(lines, list) or not all(isinstance(x, int) for x in lines):
        reasons.append("focus.lines 不是整数列表")
        lines = []
    out_of_range = [x for x in lines if x < 1 or x > code_lines]
    if out_of_range:
        reasons.append(f"focus.lines 超出代码行号范围：{out_of_range}")
    if drivers and lines:
        driver_lines = {x for ls in drivers.values() for x in ls}
        if not set(lines) & driver_lines:
            warnings.append("focus.lines 没有落在 drivers 里")
    tags = data.get("concept_tags") if isinstance(data.get("concept_tags"), list) else []
    hint = {
        "level": level,
        "focus": {"step": focus.get("step"), "signal": focus.get("signal"), "lines": lines},
        "message": message.strip(),
        "question": question,
        "concept_tags": [str(t) for t in tags],
        "code": code,
    }
    return {"ok": not reasons, "reasons": reasons, "warnings": warnings, "hint": hint if not reasons else None}
