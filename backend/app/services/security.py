"""密码、会话令牌、匿名 ID。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import utcnow
from ..models import Session, User

_hasher = PasswordHasher()
SESSION_COOKIE = "session"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def anon_id_for(user_id: int) -> str:
    """anon_id = HMAC-SHA256(ANON_SALT, user_id) 取前 8 位十六进制（docs/learner-model.md 第 9 节）。"""
    salt = get_settings().salt().encode("utf-8")
    return hmac.new(salt, str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()[:8]


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: DbSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=_token_hash(token), user_id=user.id,
                   expires_at=utcnow() + timedelta(days=get_settings().session_days)))
    return token


def user_for_token(db: DbSession, token: str | None) -> User | None:
    if not token:
        return None
    row = db.scalar(select(Session).where(Session.token_hash == _token_hash(token)))
    if row is None or row.expires_at < utcnow():
        return None
    return db.get(User, row.user_id)


def delete_session(db: DbSession, token: str | None) -> None:
    if token:
        row = db.scalar(select(Session).where(Session.token_hash == _token_hash(token)))
        if row is not None:
            db.delete(row)
