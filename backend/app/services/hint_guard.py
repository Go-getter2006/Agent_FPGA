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
