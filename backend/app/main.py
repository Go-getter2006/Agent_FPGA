"""FastAPI 应用：uvicorn backend.app.main:app"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import auth, jobs, student, teacher
from .api.deps import ApiError
from .config import APP_VERSION
from .db import SessionLocal
from .services.problems_sync import sync_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    if app.state.sync_on_startup:
        with SessionLocal() as db:
            sync_all(db)
    yield


def create_app(sync_on_startup: bool = True) -> FastAPI:
    app = FastAPI(title="Verilog 学习平台", version=APP_VERSION, lifespan=lifespan)
    app.state.sync_on_startup = sync_on_startup

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"error": {"code": "INVALID_INPUT", "message": "提交的内容格式不对"}})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        message = {404: "找不到这个地址"}.get(exc.status_code, str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": message}})

    for router in (auth.router, student.router, teacher.router, jobs.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": APP_VERSION}

    return app


app = create_app()
