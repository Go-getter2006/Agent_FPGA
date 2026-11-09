"""知情同意书：正文来自文件；版本号变了要重新选择（阶段 6）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.services import consent as consent_service
from backend.app.services.consent import current_consent, parse_consent

from .conftest import event_types, login, make_user


def test_parse_front_matter():
    c = parse_consent("---\n# 注释\nversion: v2\n---\n# 标题\n\n正文\n")
    assert c.version == "v2" and c.markdown.startswith("# 标题")
    with pytest.raises(ValueError):
        parse_consent("# 没有文件头\n")
    with pytest.raises(ValueError):
        parse_consent("---\ntitle: x\n---\n正文")


def test_default_file_has_required_sections():
    c = current_consent()
    for heading in ("收集哪些数据", "第三方服务", "你的选择"):
        assert f"## {heading}" in c.markdown


def test_consent_text_endpoint(app):
    user = make_user(consent="pending")
    client = login(app, user)
    body = client.get("/api/auth/consent").json()
    assert body["version"] == current_consent().version and "DeepSeek" in body["markdown"]
    assert TestClient(app).get("/api/auth/consent").status_code == 401


@pytest.fixture
def switch_consent(tmp_path, monkeypatch):
    """把知情同意书换成新版本 v2-test（模拟定稿后改文件、改版本号）。"""
    def switch() -> str:
        path = tmp_path / "consent.md"
        path.write_text("---\nversion: v2-test\n---\n# 新版\n\n改了内容。\n", encoding="utf-8")
        monkeypatch.setenv("CONSENT_FILE", str(path))
        consent_service._cache.clear()
        return "v2-test"
    yield switch
    consent_service._cache.clear()


def test_new_version_requires_reconsent(app, switch_consent):
    user = make_user(consent="accepted")
    client = login(app, user)
    old = client.get("/api/auth/me").json()["consent"]
    assert old["required"] is False
    new = switch_consent()
    me = client.get("/api/auth/me").json()
    assert me["consent"]["required"] is True and me["consent"]["version"] == old["version"] != new
    r = client.get("/api/student/home")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CONSENT_REQUIRED"
    # 拿旧版本号提交会被拒绝
    r = client.post("/api/auth/consent", json={"accept": True, "version": old["version"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "CONSENT_VERSION"
    r = client.post("/api/auth/consent", json={"accept": True, "version": new})
    assert r.json()["consent"] == {"status": "accepted", "version": new, "current_version": new, "required": False}
    assert client.get("/api/student/home").status_code == 200
    assert event_types(user.id).count("consent.accept") == 1


def test_declined_student_also_asked_again(app, switch_consent):
    user = make_user(consent="declined")
    client = login(app, user)
    assert client.get("/api/auth/me").json()["consent"]["required"] is False
    switch_consent()
    assert client.get("/api/auth/me").json()["consent"]["required"] is True
