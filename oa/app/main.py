import hmac
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import schemas
from .db import connection, database_path, initialize
from .security import hash_password, new_token, token_hash, verify_password

STATIC = Path(__file__).parent / "static"
USER_SQL = """SELECT u.id,u.username,u.name,u.department_id,u.is_admin,u.enabled,
    d.name AS department_name,h.id AS head_department_id
    FROM users u LEFT JOIN departments d ON d.id=u.department_id
    LEFT JOIN departments h ON h.head_user_id=u.id"""
APPLICATION_SQL = """SELECT a.*,u.name AS applicant_name,u.username AS applicant_username,
    d.name AS approval_department_name, r.name AS reviewer_name
    FROM applications a JOIN users u ON u.id=a.applicant_id
    JOIN departments d ON d.id=a.approval_department_id LEFT JOIN users r ON r.id=a.reviewer_id"""


def now():
    return datetime.now(timezone.utc).isoformat()


def same_origin(request: Request, origin: str) -> bool:
    """允许同一协议和主机的 Origin，即使内嵌浏览器省略了非默认端口。"""
    try:
        parsed = urlsplit(origin)
        if parsed.scheme != request.url.scheme or parsed.hostname != request.url.hostname:
            return False
        if parsed.port is None:
            return True
        request_port = request.url.port or (443 if request.url.scheme == "https" else 80)
        return parsed.port == request_port
    except ValueError:
        return False


def configured_origin_matches(origin: str) -> bool:
    """在 HTTPS 反向代理后校验浏览器面对的公网来源。"""
    expected = os.getenv("OA_PUBLIC_ORIGIN", "").strip().rstrip("/")
    if not expected:
        return False
    try:
        actual = urlsplit(origin)
        public = urlsplit(expected)
        if actual.scheme != public.scheme or actual.hostname != public.hostname:
            return False
        if actual.port is None and public.port is None:
            return True
        return (actual.port or (443 if actual.scheme == "https" else 80)) == (public.port or (443 if public.scheme == "https" else 80))
    except ValueError:
        return False


def fail(code, message):
    raise HTTPException(code, message)


def user_view(row):
    user = dict(row)
    user["is_admin"] = bool(user["is_admin"])
    user["enabled"] = bool(user["enabled"])
    user["role"] = "admin" if user["is_admin"] else "head" if user["head_department_id"] else "user"
    return user


def visible_condition(user, scope="visible"):
    if scope == "mine":
        return "a.applicant_id=?", [user["id"]]
    if scope == "inbox":
        if user["role"] != "head":
            fail(403, "只有部门负责人可以查看部门审批列表")
        return "a.approval_department_id=?", [user["head_department_id"]]
    if user["is_admin"]:
        return "1=1", []
    if user["head_department_id"]:
        return "(a.applicant_id=? OR a.approval_department_id=?)", [user["id"], user["head_department_id"]]
    return "a.applicant_id=?", [user["id"]]


def create_app(db_path=None, *, session_seconds=None):
    path = Path(db_path) if db_path is not None else database_path()
    ttl = session_seconds if session_seconds is not None else int(os.getenv("OA_SESSION_HOURS", "12")) * 3600

    @asynccontextmanager
    async def lifespan(app):
        initialize(path)
        yield

    app = FastAPI(title="OA 办公系统 API", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.db_path = path

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error": {"code": exc.status_code, "message": str(exc.detail)}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = [".".join(str(part) for part in item["loc"][1:]) for item in exc.errors()]
        return JSONResponse({"error": {"code": 422, "message": "输入不符合要求，请检查必填项、格式、长度或多余字段", "fields": fields}}, status_code=422)

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse({"error": {"code": 409, "message": "操作与现有记录冲突，请检查重复名称或业务限制"}}, status_code=409)

    @app.middleware("http")
    async def security_headers(request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and not (
            same_origin(request, origin) or configured_origin_matches(origin)
        ):
            return JSONResponse({"error": {"code": 403, "message": "不允许跨站提交"}}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def current(request: Request):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            fail(401, "请先登录，或登录已过期")
        with connection(path) as db:
            session = db.execute("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?", (token_hash(token), int(time.time()))).fetchone()
            if not session:
                fail(401, "请先登录，或登录已过期")
            row = db.execute(USER_SQL + " WHERE u.id=? AND u.enabled=1", (session["user_id"],)).fetchone()
            if not row:
                fail(401, "账号已停用，请联系系统管理员")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(supplied.encode(), session["csrf_token"].encode()):
                fail(403, "请求校验失败，请刷新后重试")
        request.state.csrf_token = session["csrf_token"]
        return user_view(row)

    def admin(user=Depends(current)):
        if not user["is_admin"]:
            fail(403, "仅系统管理员可执行此操作")
        return user

    def require_department(db, department_id):
        row = db.execute("SELECT * FROM departments WHERE id=? AND enabled=1", (department_id,)).fetchone()
        if not row:
            fail(422, "部门不存在或已停用")
        return row

    def eligible_department(db, department_id):
        row = db.execute("""SELECT d.id FROM departments d JOIN users u ON u.id=d.head_user_id
            WHERE d.id=? AND d.enabled=1 AND u.enabled=1""", (department_id,)).fetchone()
        if not row:
            fail(422, "审批部门不存在、已停用或尚未指定负责人")

    @app.get("/api/health")
    def health():
        with connection(path) as db:
            db.execute("SELECT 1 FROM users LIMIT 1")
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(body: schemas.Login):
        with connection(path, write=True) as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
            if not row or not verify_password(body.password, row["password_hash"]) or not row["enabled"]:
                fail(401, "用户名、密码错误或账号已停用")
            token, csrf = new_token(), new_token()
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token_hash(token), row["id"], csrf, int(time.time()) + ttl))
            user = user_view(db.execute(USER_SQL + " WHERE u.id=?", (row["id"],)).fetchone())
        return {"access_token": token, "token_type": "Bearer", "user": user, "csrf_token": csrf, "expires_in": ttl}

    @app.get("/api/auth/me")
    def me(request: Request, user=Depends(current)):
        return {"user": user, "csrf_token": request.state.csrf_token}

    @app.post("/api/auth/logout")
    def logout(request: Request, user=Depends(current)):
        _, _, token = request.headers.get("Authorization", "").partition(" ")
        with connection(path, write=True) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
        return {"message": "已退出登录"}

    @app.post("/api/auth/password")
    def change_password(body: schemas.ChangePassword, user=Depends(current)):
        with connection(path, write=True) as db:
            row = db.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
            if not verify_password(body.old_password, row["password_hash"]):
                fail(422, "原密码错误")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.new_password), user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        return {"message": "密码已修改，请重新登录"}

    @app.get("/api/departments")
    def departments(user=Depends(admin)):
        with connection(path) as db:
            rows = db.execute("""SELECT d.*,u.name AS head_name,
                (SELECT count(*) FROM users m WHERE m.department_id=d.id AND m.enabled=1) AS active_users
                FROM departments d LEFT JOIN users u ON u.id=d.head_user_id ORDER BY d.id""").fetchall()
        return {"items": [dict(row) for row in rows]}

    @app.post("/api/departments", status_code=201)
    def create_department(body: schemas.DepartmentCreate, user=Depends(admin)):
        with connection(path, write=True) as db:
            cursor = db.execute("INSERT INTO departments(name) VALUES(?)", (body.name,))
            return {"id": cursor.lastrowid, "name": body.name}

    @app.patch("/api/departments/{department_id}")
    def department_enabled(department_id: int, body: schemas.Enabled, user=Depends(admin)):
        with connection(path, write=True) as db:
            if not db.execute("SELECT id FROM departments WHERE id=?", (department_id,)).fetchone():
                fail(404, "部门不存在")
            if not body.enabled:
                active = db.execute("SELECT 1 FROM users WHERE department_id=? AND enabled=1", (department_id,)).fetchone()
                pending = db.execute("SELECT 1 FROM applications WHERE approval_department_id=? AND status='pending'", (department_id,)).fetchone()
                if active or pending:
                    fail(409, "部门仍有启用用户或待审核申请，不能停用")
            db.execute("UPDATE departments SET enabled=? WHERE id=?", (body.enabled, department_id))
        return {"message": "部门状态已更新"}

    @app.put("/api/departments/{department_id}/head")
    def assign_head(department_id: int, body: schemas.Head, user=Depends(admin)):
        with connection(path, write=True) as db:
            department = require_department(db, department_id)
            if department["head_user_id"] is not None:
                fail(409, "部门已有负责人，第一版不支持更换或交接")
            candidate = db.execute("SELECT * FROM users WHERE id=? AND department_id=? AND enabled=1 AND is_admin=0", (body.user_id, department_id)).fetchone()
            if not candidate:
                fail(422, "负责人必须是本部门已启用的普通用户")
            db.execute("UPDATE departments SET head_user_id=? WHERE id=?", (body.user_id, department_id))
        return {"message": "负责人已指定"}

    @app.get("/api/users")
    def users(user=Depends(admin)):
        with connection(path) as db:
            rows = db.execute(USER_SQL + " ORDER BY u.id").fetchall()
        return {"items": [user_view(row) for row in rows]}

    @app.post("/api/users", status_code=201)
    def create_user(body: schemas.UserCreate, user=Depends(admin)):
        if not body.is_admin and body.department_id is None:
            fail(422, "普通用户必须且只能属于一个部门")
        with connection(path, write=True) as db:
            if body.department_id is not None:
                require_department(db, body.department_id)
            cursor = db.execute("""INSERT INTO users(username,name,password_hash,department_id,is_admin,enabled)
                VALUES(?,?,?,?,?,?)""", (body.username, body.name, hash_password(body.password), body.department_id, body.is_admin, body.enabled))
            return user_view(db.execute(USER_SQL + " WHERE u.id=?", (cursor.lastrowid,)).fetchone())

    @app.patch("/api/users/{user_id}")
    def user_enabled(user_id: int, body: schemas.Enabled, user=Depends(admin)):
        with connection(path, write=True) as db:
            target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not target:
                fail(404, "用户不存在")
            if not body.enabled:
                if db.execute("SELECT 1 FROM departments WHERE head_user_id=?", (user_id,)).fetchone():
                    fail(409, "现任部门负责人暂时不能停用")
                admins = db.execute("SELECT count(*) FROM users WHERE is_admin=1 AND enabled=1").fetchone()[0]
                if target["is_admin"] and target["enabled"] and admins <= 1:
                    fail(409, "不能停用最后一个启用的系统管理员")
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            elif target["department_id"]:
                require_department(db, target["department_id"])
            db.execute("UPDATE users SET enabled=? WHERE id=?", (body.enabled, user_id))
        return {"message": "用户状态已更新"}

    @app.post("/api/users/{user_id}/reset-password")
    def reset_password(user_id: int, body: schemas.ResetPassword, user=Depends(admin)):
        if user_id == user["id"]:
            fail(422, "请通过修改密码功能修改自己的密码")
        with connection(path, write=True) as db:
            if not db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                fail(404, "用户不存在")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.new_password), user_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return {"message": "密码已重置，该用户需要重新登录"}

    @app.get("/api/approval-departments")
    def approval_departments(user=Depends(current)):
        with connection(path) as db:
            rows = db.execute("""SELECT d.id,d.name,u.name AS head_name FROM departments d
                JOIN users u ON u.id=d.head_user_id WHERE d.enabled=1 AND u.enabled=1 ORDER BY d.id""").fetchall()
        return {"items": [dict(row) for row in rows]}

    @app.post("/api/applications", status_code=201)
    def create_application(body: schemas.ApplicationCreate, user=Depends(current)):
        if user["is_admin"]:
            fail(403, "系统管理员不发起申请")
        with connection(path, write=True) as db:
            eligible_department(db, body.approval_department_id)
            cursor = db.execute("""INSERT INTO applications(applicant_id,approval_department_id,event_date,title,content,submitted_at)
                VALUES(?,?,?,?,?,?)""", (user["id"], body.approval_department_id, body.event_date.isoformat(), body.title, body.content, now()))
            return dict(db.execute(APPLICATION_SQL + " WHERE a.id=?", (cursor.lastrowid,)).fetchone())

    @app.get("/api/applications")
    def applications(
        scope: Literal["visible", "mine", "inbox"] = "visible",
        status: Literal["pending", "approved", "rejected"] | None = None,
        page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), user=Depends(current),
    ):
        condition, params = visible_condition(user, scope)
        if status:
            condition += " AND a.status=?"
            params.append(status)
        with connection(path) as db:
            total = db.execute("SELECT count(*) FROM applications a WHERE " + condition, params).fetchone()[0]
            rows = db.execute(APPLICATION_SQL + " WHERE " + condition + " ORDER BY a.id DESC LIMIT ? OFFSET ?", [*params, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}

    @app.get("/api/applications/{application_id}")
    def application_detail(application_id: int, user=Depends(current)):
        condition, params = visible_condition(user)
        with connection(path) as db:
            row = db.execute(APPLICATION_SQL + " WHERE a.id=? AND " + condition, [application_id, *params]).fetchone()
        if not row:
            fail(404, "申请不存在或无权查看")
        return dict(row)

    @app.post("/api/applications/{application_id}/decision")
    def decide(application_id: int, body: schemas.Decision, user=Depends(current)):
        if user["role"] != "head":
            fail(403, "仅审批部门负责人可审批")
        if body.decision == "rejected" and not body.reason:
            fail(422, "拒绝申请必须填写理由")
        with connection(path, write=True) as db:
            row = db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
            if not row or row["approval_department_id"] != user["head_department_id"]:
                fail(403, "您不是该申请审批部门的负责人")
            cursor = db.execute("""UPDATE applications SET status=?,reviewer_id=?,reviewed_at=?,rejection_reason=?
                WHERE id=? AND status='pending'""", (body.decision, user["id"], now(), body.reason if body.decision == "rejected" else None, application_id))
            if cursor.rowcount != 1:
                fail(409, "该申请已完成审批，不能重复处理")
        return {"message": "审批已完成"}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
