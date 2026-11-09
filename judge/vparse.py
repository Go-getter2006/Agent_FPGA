"""极简 Verilog 结构扫描：只回答两个问题，不做语义分析。

1. 模块里有哪些顶层 always 块，各自在源码中的起止位置（顺序打乱实验用）
2. 每条赋值语句给哪些信号赋值、在第几行（信号 → 代码行映射用）

只在代码已经通过 iverilog 编译之后调用；遇到认不出的写法抛 ParseError，由调用方退回保守做法。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class ParseError(Exception):
    pass


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    start: int   # 在源码中的字符偏移
    end: int


@dataclass
class Assignment:
    targets: list[str]          # 被赋值的信号名（去掉位选择）
    line: int                   # 左边第一个记号所在的行
    kind: str                   # continuous / procedural / net_decl


@dataclass
class AlwaysBlock:
    start: int                  # 字符偏移：always 关键字开头
    end: int                    # 字符偏移：块最后一个记号之后
    first_line: int
    last_line: int


@dataclass
class ModuleInfo:
    name: str
    always_blocks: list[AlwaysBlock] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:\\.|[^"\\])*")
  | (?P<directive>`[A-Za-z_][A-Za-z0-9_]*[^\n]*)
  | (?P<number>(?:\d[\d_]*)?\s*'[sS]?[bBoOdDhH]\s*[0-9a-fA-FxXzZ?_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<ident>\\\S+|\$?[A-Za-z_][A-Za-z0-9_$]*)
  | (?P<op><<<|>>>|===|!==|<=|>=|==|!=|&&|\|\||<<|>>|\*\*|->|\+:|-:|~&|~\||~\^|\^~|[^\s])
    """,
    re.S | re.X,
)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    line = 1
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise ParseError(f"第 {line} 行有无法识别的字符")
        kind = m.lastgroup
        chunk = m.group()
        if kind not in ("ws", "comment", "string", "directive"):
            tokens.append(Token(chunk, line, m.start(), m.end()))
        elif kind == "string":
            tokens.append(Token('""', line, m.start(), m.end()))
        line += chunk.count("\n")
        pos = m.end()
    return tokens


_BLOCK_PAIRS = {"begin": "end", "fork": "join", "case": "endcase", "casez": "endcase",
                "casex": "endcase", "generate": "endgenerate", "function": "endfunction",
                "task": "endtask", "specify": "endspecify"}
_JOIN = {"join", "join_any", "join_none"}
_DECL_NET = {"wire", "tri", "wand", "wor", "supply0", "supply1"}
_SKIP_ITEMS = {"function", "task", "generate", "specify"}


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.t = tokens
        self.assignments: list[Assignment] = []

    # ---------- 基础 ----------
    def text(self, i: int) -> str:
        if i >= len(self.t):
            raise ParseError("代码意外结束")
        return self.t[i].text

    def skip_group(self, i: int) -> int:
        """i 指向 ( [ {，返回配对括号之后的位置。"""
        pairs = {"(": ")", "[": "]", "{": "}"}
        stack = [pairs[self.text(i)]]
        i += 1
        while stack:
            tok = self.text(i)
            if tok in pairs:
                stack.append(pairs[tok])
            elif tok in (")", "]", "}"):
                if tok != stack.pop():
                    raise ParseError(f"第 {self.t[i].line} 行括号不配对")
            i += 1
        return i

    def skip_until_end_keyword(self, i: int, open_kw: str) -> int:
        """跳过 function / task / generate 等整段，返回结束关键字之后的位置。"""
        close = _BLOCK_PAIRS[open_kw]
        depth = 0
        while True:
            tok = self.text(i)
            if tok == open_kw:
                depth += 1
            elif tok == close:
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1

    # ---------- 赋值语句 ----------
    def record_assignment(self, lhs: list[Token], kind: str) -> None:
        names = _lvalue_names(lhs)
        if names:
            self.assignments.append(Assignment(names, lhs[0].line, kind))

    def simple_statement(self, i: int) -> int:
        """到分号为止的简单语句；若是赋值则记录左边的信号。"""
        start = i
        op_at = None
        while self.text(i) != ";":
            tok = self.text(i)
            if tok in ("(", "[", "{"):
                i = self.skip_group(i)
                continue
            if op_at is None and tok in ("=", "<="):
                op_at = i
            i += 1
        if op_at is not None and op_at > start:
            self.record_assignment(self.t[start:op_at], "procedural")
        return i + 1

    # ---------- 过程语句 ----------
    def statement(self, i: int) -> int:
        tok = self.text(i)
        if tok == ";":
            return i + 1
        if tok in ("begin", "fork"):
            i += 1
            if self.text(i) == ":":
                i += 2
            closers = {"end"} if tok == "begin" else _JOIN
            while self.text(i) not in closers:
                i = self.statement(i)
            i += 1
            if i < len(self.t) and self.text(i) == ":":
                i += 2
            return i
        if tok == "if":
            i = self.skip_group(i + 1)
            i = self.statement(i)
            if i < len(self.t) and self.text(i) == "else":
                i = self.statement(i + 1)
            return i
        if tok in ("case", "casez", "casex"):
            i = self.skip_group(i + 1)
            while self.text(i) != "endcase":
                if self.text(i) == "default":
                    i += 1
                    if self.text(i) == ":":
                        i += 1
                else:
                    while self.text(i) != ":":
                        i = self.skip_group(i) if self.text(i) in ("(", "[", "{") else i + 1
                    i += 1
                i = self.statement(i)
            return i + 1
        if tok == "for":
            i += 1
            if self.text(i) != "(":
                raise ParseError(f"第 {self.t[i].line} 行 for 后面缺少括号")
            close = self.skip_group(i)
            header = self.t[i + 1:close - 1]
            for part in _split_top(header, ";")[::2]:   # 初始化与步进两段
                op = next((k for k, t in enumerate(part) if t.text == "="), None)
                if op:
                    self.record_assignment(part[:op], "procedural")
            return self.statement(close)
        if tok in ("while", "repeat", "wait"):
            return self.statement(self.skip_group(i + 1))
        if tok == "forever":
            return self.statement(i + 1)
        if tok in ("@", "#"):
            i += 1
            if self.text(i) == "(":
                i = self.skip_group(i)
            else:
                i += 1   # @* / @clk / #5 / #DELAY
            return self.statement(i)
        return self.simple_statement(i)

    # ---------- 模块 ----------
    def module(self, i: int) -> tuple[ModuleInfo, int]:
        name = self.text(i + 1)
        info = ModuleInfo(name=name)
        i += 2
        # 端口表、参数表直到第一个分号
        while self.text(i) != ";":
            i = self.skip_group(i) if self.text(i) in ("(", "[", "{") else i + 1
        i += 1
        while self.text(i) != "endmodule":
            tok = self.text(i)
            if tok == "always":
                start_tok = self.t[i]
                before = len(self.assignments)
                end = self.statement(i + 1)
                last = self.t[end - 1]
                info.always_blocks.append(
                    AlwaysBlock(start_tok.start, last.end, start_tok.line, last.line))
                for a in self.assignments[before:]:
                    a.kind = "procedural"
                i = end
            elif tok == "initial":
                i = self.statement(i + 1)
            elif tok == "assign":
                i = self.continuous(i + 1, "continuous")
            elif tok in _DECL_NET:
                i = self.continuous(i + 1, "net_decl", declaration=True)
            elif tok in _SKIP_ITEMS:
                i = self.skip_until_end_keyword(i, tok)
            else:
                # 其他模块项（reg 声明、参数、例化……）：跳到分号
                while self.text(i) != ";":
                    i = self.skip_group(i) if self.text(i) in ("(", "[", "{") else i + 1
                i += 1
        info.assignments = self.assignments
        self.assignments = []
        return info, i + 1

    def continuous(self, i: int, kind: str, declaration: bool = False) -> int:
        """assign a = ..., b = ...;  或  wire [3:0] t = ...;"""
        end = i
        while self.text(end) != ";":
            end = self.skip_group(end) if self.text(end) in ("(", "[", "{") else end + 1
        for part in _split_top(self.t[i:end], ","):
            op = next((k for k, t in enumerate(part) if t.text == "="), None)
            if op is None:
                continue
            lhs = part[:op]
            if declaration:
                # 去掉类型、位宽、强度等前缀，只留最后的信号名
                lhs = [t for t in lhs if re.match(r"^[A-Za-z_\\]", t.text)][-1:]
            self.record_assignment(lhs, kind)
        return end + 1


def _split_top(tokens: list[Token], sep: str) -> list[list[Token]]:
    parts: list[list[Token]] = [[]]
    depth = 0
    for t in tokens:
        if t.text in ("(", "[", "{"):
            depth += 1
        elif t.text in (")", "]", "}"):
            depth -= 1
        if t.text == sep and depth == 0:
            parts.append([])
        else:
            parts[-1].append(t)
    return parts


_KEYWORDS = {"assign", "wire", "reg", "signed", "integer", "begin", "end", "if", "else"}


def _lvalue_names(lhs: list[Token]) -> list[str]:
    """左值里的信号名：a、a[3]、a[3:0]、{a, b[1]} 都可以；位选择里的表达式不算。"""
    names: list[str] = []
    depth_bracket = 0
    for t in lhs:
        if t.text == "[":
            depth_bracket += 1
        elif t.text == "]":
            depth_bracket -= 1
        elif depth_bracket == 0 and re.match(r"^(\\\S+|[A-Za-z_][A-Za-z0-9_$]*)$", t.text) \
                and t.text not in _KEYWORDS:
            name = t.text[1:] if t.text.startswith("\\") else t.text
            if name not in names:
                names.append(name)
    return names


def parse_modules(text: str) -> dict[str, ModuleInfo]:
    tokens = tokenize(text)
    parser = _Parser(tokens)
    modules: dict[str, ModuleInfo] = {}
    i = 0
    while i < len(tokens):
        if tokens[i].text in ("module", "macromodule"):
            info, i = parser.module(i)
            modules[info.name] = info
        else:
            i += 1
    return modules


def parse_top(text: str, top: str = "top_module") -> ModuleInfo:
    modules = parse_modules(text)
    if top not in modules:
        raise ParseError(f"找不到模块 {top}")
    return modules[top]
