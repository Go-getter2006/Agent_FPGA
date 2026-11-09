"""认证：/api/auth/*"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import APP_VERSION, get_settings
from ..db import get_db, utcnow
from ..models import Class, Enrollment, User
from ..services.consent import consent_required, current_consent
from ..services.events import log_event
from ..services.flags import flags_for
from ..services.security import (SESSION_COOKIE, create_session, delete_session, user_for_token,
                                 verify_password)
from .deps import ApiError, current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    login_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ConsentIn(BaseModel):
    accept: bool
    version: str = Field(min_length=1, max_length=32)   # 学生看到的版本；与当前版本不一致就拒绝


def me_payload(db: DbSession, user: User) -> dict:
    enrollments = db.execute(
        select(Enrollment, Class).join(Class, Class.id == Enrollment.class_id)
        .where(Enrollment.user_id == user.id).order_by(Enrollment.id)).all()
    classes = [{"id": c.id, "name": c.name, "term": c.term, "group": e.group} for e, c in enrollments]
    primary = enrollments[0][0] if enrollments else None
    if user.role == "student":
        consent = {
            "status": primary.consent_status if primary else "accepted",
            "version": primary.consent_version if primary else None,
            "current_version": current_consent().version,
            "required": consent_required(primary),
        }
        flags = flags_for(db, primary.class_id if primary else None, primary.group if primary else None)
    else:
        consent, flags = None, {}
    return {
        "user": {"id": user.id, "role": user.role, "login_name": user.login_name,
                 "display_name": user.display_name},
        "classes": classes,
        "group": primary.group if primary else None,
        "flags": flags,
        "consent": consent,
        "app_version": APP_VERSION,
    }


@router.post("/login")
def login(body: LoginIn, response: Response, db: DbSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.login_name == body.login_name.strip()))
    if user is None or not verify_password(user.password_hash, body.password):
        raise ApiError(401, "BAD_CREDENTIALS", "学号或密码不对；忘记密码请联系任课教师重置")
    token = create_session(db, user)
    log_event(db, user, "auth.login", payload={"version": APP_VERSION})
    db.commit()
    s = get_settings()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=s.cookie_secure,
                        max_age=s.session_days * 86400, path="/")
    return me_payload(db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)):
    delete_session(db, request.cookies.get(SESSION_COOKIE))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: DbSession = Depends(get_db)):
    return me_payload(db, user)


@router.get("/consent")
def consent_text(user: User = Depends(current_user)):
    """知情同意书正文（Markdown）和版本号。"""
    c = current_consent()
    return {"version": c.version, "markdown": c.markdown}


@router.post("/consent")
def consent(body: ConsentIn, user: User = Depends(current_user), db: DbSession = Depends(get_db)):
    if user.role != "student":
        raise ApiError(403, "FORBIDDEN", "只有学生需要选择是否参与研究")
    if body.version != current_consent().version:
        raise ApiError(400, "CONSENT_VERSION", "知情同意书已更新，请刷新页面后重新阅读")
    status = "accepted" if body.accept else "declined"
    for e in db.scalars(select(Enrollment).where(Enrollment.user_id == user.id)).all():
        e.consent_status = status
        e.consent_version = body.version
        e.consent_at = utcnow()
    log_event(db, user, "consent.accept" if body.accept else "consent.decline", payload={"version": body.version})
    db.commit()
    return me_payload(db, user)


def optional_user(request: Request, db: DbSession) -> User | None:
    return user_for_token(db, request.cookies.get(SESSION_COOKIE))
