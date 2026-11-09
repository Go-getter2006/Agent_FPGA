"""读取题目目录（problems/<题目ID>/）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config

_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")
_EXPECT_RE = re.compile(r"^\s*//\s*expect\s*:\s*(.*)$")

REQUIRED_KEYS = (
    "id", "title", "knowledge_points", "primm_type", "difficulty",
    "predict_points", "hardware_questions", "expected_ff_count",
)


class JudgeError(Exception):
    """题目或裁判自身的问题（不是学生代码的问题）。"""


@dataclass(frozen=True)
class Problem:
    id: str
    dir: Path
    meta: dict = field(hash=False, compare=False)

    @property
    def ref_path(self) -> Path:
        return self.dir / "ref.v"

    @property
    def tb_path(self) -> Path:
        return self.dir / "tb.v"

    @property
    def cases_dir(self) -> Path:
        return self.dir / "cases"

    def case_paths(self) -> list[Path]:
        if not self.cases_dir.is_dir():
            return []
        return sorted(self.cases_dir.glob("*.v"))


def load_problem(problem_id: str, problems_dir: Path | None = None) -> Problem:
    if not _ID_RE.match(problem_id or ""):
        raise JudgeError(f"题目 ID 不合法：{problem_id!r}")
    root = Path(problems_dir) if problems_dir else config.problems_dir()
    pdir = root / problem_id
    yaml_path = pdir / "problem.yaml"
    if not yaml_path.is_file():
        raise JudgeError(f"找不到题目：{problem_id}（{yaml_path} 不存在）")
    with yaml_path.open(encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}
    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        raise JudgeError(f"{yaml_path} 缺少字段：{', '.join(missing)}")
    if meta["id"] != problem_id:
        raise JudgeError(f"{yaml_path} 里的 id（{meta['id']}）与目录名（{problem_id}）不一致")
    for name in ("ref.v", "tb.v"):
        if not (pdir / name).is_file():
            raise JudgeError(f"题目 {problem_id} 缺少 {name}")
    return Problem(id=problem_id, dir=pdir, meta=meta)


def list_problem_ids(problems_dir: Path | None = None) -> list[str]:
    root = Path(problems_dir) if problems_dir else config.problems_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "problem.yaml").is_file())


def read_expected_tags(case_path: Path) -> list[str]:
    """读取错误样本第一行的 `// expect: a, b`。"""
    with Path(case_path).open(encoding="utf-8") as f:
        first = f.readline()
    m = _EXPECT_RE.match(first)
    if not m:
        raise JudgeError(f"{case_path} 第一行没有写 // expect: <标签>")
    return [t.strip() for t in m.group(1).split(",") if t.strip()]
