"""带超时和资源限制的外部命令执行。

- 超时时杀掉整个进程组（iverilog 会再起 ivlpp、ivl 子进程）
- 在 Linux 上用 util-linux 的 prlimit 给学生代码相关的进程加上限：CPU 时间、内存（地址空间）、
  写文件大小。stdout / stderr 先写到临时文件，所以“写文件大小”也限制了输出量：
  例如学生代码里 `always $display(...)` 这样的零延迟死循环，输出到上限就被系统终止，
  不会把判题进程的内存撑满。超出 CPU 或输出上限按超时处理（结果一样可复现）。
- 上限可用环境变量调整：JUDGE_MEMORY_MB（默认 2048）、JUDGE_OUTPUT_MB（默认 32）；
  JUDGE_RLIMITS=0 关闭（没有 prlimit 的系统，如 macOS，自动不加限制）
"""
from __future__ import annotations

import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_LIMIT_SIGNALS = {-signal.SIGXCPU, -signal.SIGXFSZ}


@dataclass(frozen=True)
class CmdResult:
    returncode: int | None
    stdout: str
    stderr: str
    timeout: bool
    limit_exceeded: bool = False     # 超出 CPU 时间或输出上限（timeout 同时为 True）

    @property
    def ok(self) -> bool:
        return not self.timeout and self.returncode == 0

    @property
    def output(self) -> str:
        """stdout 与 stderr 合在一起，便于按行解析工具信息。"""
        if self.stdout and self.stderr:
            return self.stdout + "\n" + self.stderr
        return self.stdout or self.stderr


class ToolNotFound(RuntimeError):
    pass


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def limit_prefix(timeout: float) -> list[str]:
    """prlimit 前缀；不支持或已关闭时返回空列表。"""
    if not sys.platform.startswith("linux") or os.environ.get("JUDGE_RLIMITS", "").strip() == "0":
        return []
    prlimit = shutil.which("prlimit")
    if prlimit is None:
        return []
    cpu = math.ceil(timeout) + 5          # 墙钟超时是主要限制；CPU 上限兜底防止子进程逃逸
    mem = _env_int("JUDGE_MEMORY_MB", 2048) * 1024 * 1024
    out = _env_int("JUDGE_OUTPUT_MB", 32) * 1024 * 1024
    return [prlimit, f"--cpu={cpu}", f"--as={mem}", f"--fsize={out}", "--"]


def _read(f) -> str:
    f.seek(0)
    return f.read().decode("utf-8", errors="replace")


def run(cmd: list[str], cwd: Path, timeout: float) -> CmdResult:
    prefix = limit_prefix(timeout)
    if prefix and shutil.which(cmd[0]) is None:
        raise ToolNotFound(f"找不到外部工具：{cmd[0]}（请先安装 iverilog / yosys / verilator）")
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(
                prefix + cmd,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise ToolNotFound(f"找不到外部工具：{cmd[0]}（请先安装 iverilog / yosys / verilator）") from exc

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            # 超时时丢弃已有输出：缓冲区里有多少内容不可控，丢弃才能保证结果可复现
            return CmdResult(returncode=None, stdout="", stderr="", timeout=True)
        if proc.returncode in _LIMIT_SIGNALS:
            return CmdResult(returncode=proc.returncode, stdout="", stderr="", timeout=True, limit_exceeded=True)
        return CmdResult(returncode=proc.returncode, stdout=_read(out), stderr=_read(err), timeout=False)
