"""命令行：
    python -m judge <学生代码.v> <题目ID> [--student <匿名ID>]
    python -m judge <学生testbench.v> <题目ID> --testbench     # testbench 打分
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .diagnose import diagnose, to_json
from .testbench import score_testbench
from .problem import JudgeError
from .runner import ToolNotFound


def _read_code(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # 中文 Windows 上写的文件常是 GBK 编码
        return data.decode("gb18030", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m judge", description="Verilog 仿真裁判")
    parser.add_argument("code", type=Path, help="学生代码文件（.v）")
    parser.add_argument("problem", help="题目 ID，对应 problems/<题目ID>/")
    parser.add_argument("--student", default=None, help="学生匿名 ID，只写进日志")
    parser.add_argument("--problems-dir", type=Path, default=None, help="题目目录（默认 problems/）")
    parser.add_argument("--timeout", type=float, default=config.DEFAULT_TIMEOUT, help="每个外部命令的超时秒数")
    parser.add_argument("--no-log", action="store_true", help="不写 logs/judge.jsonl")
    parser.add_argument("--testbench", action="store_true", help="把文件当作学生的 testbench，给它打分")
    args = parser.parse_args(argv)

    if not args.code.is_file():
        print(f"找不到学生代码文件：{args.code}", file=sys.stderr)
        return 2
    try:
        run = score_testbench if args.testbench else diagnose
        result = run(
            _read_code(args.code), args.problem,
            student=args.student, problems_dir=args.problems_dir,
            timeout=args.timeout, log=not args.no_log,
        )
    except (JudgeError, ToolNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(to_json(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
