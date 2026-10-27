import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, catalog, invitations, recruiting
from .common import ensure_same_origin
from .db import initialize

ROOT = Path(__file__).resolve().parent.parent


def create_app(data_dir=None, clock=None):
    # 提供本地 OpenAPI 契约，不依赖 CDN 加载交互文档的脚本和样式。
    app = FastAPI(title="伯乐直聘 API", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.data_dir = Path(data_dir or os.environ.get("BL_DATA_DIR", ROOT / "data")).resolve()
    app.state.database = initialize(app.state.data_dir)
    app.state.clock = clock or (lambda: datetime.now(timezone.utc))
    app.state.public_url = os.environ.get("BL_PUBLIC_URL", "").rstrip("/")
    app.state.secure_cookie = os.environ.get("BL_SECURE_COOKIE", "0") == "1"

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        message = {"Not Found": "页面或接口不存在", "Method Not Allowed": "不支持此操作"}.get(str(exc.detail), exc.detail)
        return JSONResponse({"message": message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"message": "提交信息不完整或格式不正确，请检查必填项和字段类型"}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse({"message": "服务暂时不可用，请稍后重试"}, status_code=500)

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            try:
                ensure_same_origin(request)
            except HTTPException as exc:
                return JSONResponse({"message": exc.detail}, status_code=exc.status_code)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith(("/api/", "/invite/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    for router in (auth.router, catalog.router, recruiting.router, invitations.router):
        app.include_router(router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/")
    @app.get("/login")
    @app.get("/register")
    @app.get("/jobs/{job_id}")
    @app.get("/company")
    @app.get("/company/applications/{application_id}")
    @app.get("/applications")
    @app.get("/admin")
    @app.get("/invite/{token}")
    def page():
        return FileResponse(ROOT / "static" / "index.html")

    return app
