"""知情同意书：正文和版本号都在一个 Markdown 文件里（默认 backend/app/data/consent.md）。

换文本时改这个文件（或用环境变量 CONSENT_FILE 指向部署方自己的文件），并同时改文件头里的 version；
版本号一变，所有学生下次进入学生端都会被要求重新阅读并选择。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import get_settings
from ..models import Enrollment


@dataclass(frozen=True)
class ConsentText:
    version: str
    markdown: str


_cache: dict[tuple[str, float], ConsentText] = {}


def parse_consent(text: str) -> ConsentText:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("知情同意书缺少文件头（--- version: ... ---）")
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError("知情同意书文件头没有结束的 ---")
    meta = yaml.safe_load(head) or {}
    version = str(meta.get("version") or "").strip()
    if not version:
        raise ValueError("知情同意书文件头缺少 version")
    return ConsentText(version=version, markdown=body.strip() + "\n")


def current_consent() -> ConsentText:
    path = Path(get_settings().consent_file)
    key = (str(path), path.stat().st_mtime)
    if key not in _cache:
        _cache.clear()
        _cache[key] = parse_consent(path.read_text(encoding="utf-8"))
    return _cache[key]


def consent_required(enrollment: Enrollment | None) -> bool:
    """还没选过，或者选的时候看的是旧版本，都要重新选。"""
    if enrollment is None:
        return False
    if enrollment.consent_status == "pending":
        return True
    return enrollment.consent_version != current_consent().version
