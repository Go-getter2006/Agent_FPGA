"""题目与错误样本的验收测试（docs/judge.md 第 8 节）。"""
from __future__ import annotations

import pytest

from judge.problem import list_problem_ids, load_problem, read_expected_tags

PROBLEM_IDS = list_problem_ids()
CASES = [
    (pid, path)
    for pid in PROBLEM_IDS
    for path in load_problem(pid).case_paths()
]


def _case_id(item):
    pid, path = item
    return f"{pid}/{path.name}"


def test_problems_exist():
    assert PROBLEM_IDS, "problems/ 下没有题目"


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_reference_is_clean(pid, run_case):
    problem = load_problem(pid)
    result = run_case(problem.ref_path, pid)
    assert result["compile"]["ok"], result["compile"]
    assert result["sim"]["ok"], result["sim"]["first_mismatch"]
    assert result["tags"] == [], f"ref.v 不应带标签：{result['tags']}"


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_reference_ff_count(pid, run_case):
    problem = load_problem(pid)
    result = run_case(problem.ref_path, pid)
    assert result["hardware"]["ff_count"] == problem.meta["expected_ff_count"]


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_problem_meta(pid):
    """problem.yaml 与目录内容一致：预测题、修改题有 starter.v，创作题没有。"""
    problem = load_problem(pid)
    meta = problem.meta
    assert meta["primm_type"] in ("predict", "modify", "make")
    assert meta["difficulty"] in (1, 2, 3)
    if meta["primm_type"] == "make":
        assert meta["starter"] is None
    else:
        assert meta["starter"] == "starter.v" and (problem.dir / "starter.v").is_file()
    if meta["primm_type"] == "modify":
        assert meta["modify_goal"], "修改题要写 modify_goal"
    assert (problem.dir / "spec.md").is_file()


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_predict_points_exist_in_trace(pid, run_case):
    """预测格指向的信号和 STEP 必须在参考答案的轨迹里存在。"""
    problem = load_problem(pid)
    trace = run_case(problem.ref_path, pid)["sim"]["trace"]
    steps = {row["step"]: row["outputs"] for row in trace}
    for point in problem.meta["predict_points"]:
        for step in point["steps"]:
            assert step in steps, f"STEP {step} 不在轨迹里"
            assert point["signal"] in steps[step], f"{point['signal']} 不是输出信号"


@pytest.mark.parametrize("pid", [p for p in PROBLEM_IDS if load_problem(p).meta.get("starter")])
def test_starter_runs(pid, run_case):
    """起始代码要能编译，并跑完整个 testbench；预测题的起始代码本身是正确的。"""
    problem = load_problem(pid)
    starter = run_case(problem.dir / problem.meta["starter"], pid)
    ref = run_case(problem.ref_path, pid)
    assert starter["compile"]["ok"], starter["compile"]
    assert len(starter["sim"]["trace"]) == len(ref["sim"]["trace"])
    if problem.meta["primm_type"] == "predict":
        assert starter["tags"] == []


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_case_set_quality(pid):
    """每题至少 4 个样本、至少 4 种不同的预期标签组合、至少 1 个 fragile_pass。"""
    paths = load_problem(pid).case_paths()
    expected = [frozenset(read_expected_tags(p)) for p in paths]
    assert len(paths) >= 4, f"{pid} 只有 {len(paths)} 个错误样本"
    assert len(set(expected)) >= 4, f"{pid} 的样本只覆盖了 {len(set(expected))} 种标签组合"
    assert any("fragile_pass" in e for e in expected), f"{pid} 没有 fragile_pass 样本"


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_case_tags(case, run_case, extra_tags):
    pid, path = case
    expected = read_expected_tags(path)
    result = run_case(path, pid)
    tags = result["tags"]
    missing = [t for t in expected if t not in tags]
    assert not missing, f"缺少预期标签 {missing}，实际 {tags}"
    extra = [t for t in tags if t not in expected]
    if extra:
        extra_tags.append((f"{pid}/{path.name}", extra))


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_case_catchable_by_own_tb(case, run_case):
    """非 fragile_pass 样本必须让题目自带的 tb 仿真失败，阶段 2 的 testbench 打分才能拿到满分。"""
    pid, path = case
    if "fragile_pass" in read_expected_tags(path):
        result = run_case(path, pid)
        assert result["sim"]["ok"], "fragile_pass 样本的仿真应与参考答案一致"
    else:
        result = run_case(path, pid)
        assert not result["sim"]["ok"], "题目自带的 tb 抓不到这个样本"
