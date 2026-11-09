"""裁判的路径与默认参数。路径都可以用环境变量覆盖。"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 每个外部命令的默认超时（秒）
DEFAULT_TIMEOUT = 10.0

# 学生代码、参考答案、testbench 在临时目录里的固定文件名。
# 用固定的相对文件名，工具输出的信息里就不会出现临时目录路径，保证输出可复现。
STUDENT_FILE = "student.v"
REF_FILE = "ref.v"
TB_FILE = "tb.v"
TB_TOP = "tb"
TOP_MODULE = "top_module"


def problems_dir() -> Path:
    return Path(os.environ.get("JUDGE_PROBLEMS_DIR", "").strip() or REPO_ROOT / "problems")


def log_path() -> Path:
    return Path(os.environ.get("JUDGE_LOG_PATH", "").strip() or REPO_ROOT / "logs" / "judge.jsonl")
