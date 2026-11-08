"""带超时的外部命令执行。超时时杀掉整个进程组（iverilog 会再起 ivlpp、ivl 子进程）。"""
from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CmdResult:
    returncode: int | None
    stdout: str
    stderr: str
    timeout: bool

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


def run(cmd: list[str], cwd: Path, timeout: float) -> CmdResult:
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise ToolNotFound(f"找不到外部工具：{cmd[0]}（请先安装 iverilog / yosys / verilator）") from exc

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        # 超时时丢弃已有输出：缓冲区里有多少内容不可控，丢弃才能保证结果可复现
        return CmdResult(returncode=None, stdout="", stderr="", timeout=True)
    return CmdResult(returncode=proc.returncode, stdout=stdout, stderr=stderr, timeout=False)
