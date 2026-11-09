from __future__ import annotations

import functools
from pathlib import Path

import pytest

from judge import diagnose

FIXTURES = Path(__file__).parent / "fixtures"

# 错误样本里“预期之外多出来的标签”，在测试结束时统一列出，供人工检查
EXTRA_TAGS: list[tuple[str, list[str]]] = []


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path, monkeypatch):
    """测试不写真正的 logs/judge.jsonl。"""
    monkeypatch.setenv("JUDGE_LOG_PATH", str(tmp_path / "judge.jsonl"))


@functools.lru_cache(maxsize=None)
def _cached(path: str, problem_id: str) -> dict:
    return diagnose(Path(path).read_text(encoding="utf-8"), problem_id, log=False)


@pytest.fixture
def run_case():
    """同一文件在一次测试会话里只诊断一次（裁判结果是确定的）。"""
    def _run(path: Path, problem_id: str) -> dict:
        return _cached(str(path), problem_id)
    return _run


@pytest.fixture
def extra_tags():
    return EXTRA_TAGS


def pytest_terminal_summary(terminalreporter):
    tr = terminalreporter
    tr.section("错误样本中预期之外的标签")
    if not EXTRA_TAGS:
        tr.write_line("（无）")
        return
    for case, tags in sorted(EXTRA_TAGS):
        tr.write_line(f"{case}: {', '.join(tags)}")
