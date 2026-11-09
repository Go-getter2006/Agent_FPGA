"""接口公共部分：错误格式、当前用户、权限。"""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import User
from ..services.consent import consent_required
from ..services.events import primary_enrollment
from ..services.security import SESSION_COOKIE, user_for_token


class ApiError(Exception):
    """统一错误：{"error": {"code": ..., "message": ...}}"""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def not_found(what: str = "内容") -> ApiError:
    return ApiError(404, "NOT_FOUND", f"找不到{what}")


def current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    user = user_for_token(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "请先登录")
    return user


def student_user(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> User:
    if user.role != "student":
        raise ApiError(403, "FORBIDDEN", "只有学生可以访问")
    enrollment = primary_enrollment(db, user.id)
    if consent_required(enrollment):
        raise ApiError(403, "CONSENT_REQUIRED", "请先阅读并选择是否参与研究（知情同意书有新版本时需要重新选择）")
    return user
