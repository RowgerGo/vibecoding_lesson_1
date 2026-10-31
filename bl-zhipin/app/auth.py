import secrets
import sqlite3

from fastapi import APIRouter, Request

from .common import (Input, current_user, fail, normalized, now, password_hash,
                     password_matches, request_token, text, token_hash)
from .db import connect

router = APIRouter(prefix="/api/auth")


class Register(Input):
    username: str
    password: str
    role: str
    company_name: str = ""


class Login(Input):
    username: str
    password: str


@router.post("/register", status_code=201)
def register(body: Register, request: Request):
    username = text(body.username, "用户名", 40)
    if not 8 <= len(body.password) <= 128:
        fail("密码长度需为 8～128 个字符")
    if body.role not in ("company", "seeker"):
        fail("只能注册公司或求职者账号")
    company_name = text(body.company_name, "公司名称", 100) if body.role == "company" else ""
    hashed = password_hash(body.password)
    try:
        with connect(request.app.state.database) as conn:
            user_id = conn.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                (username, hashed, body.role, now(request)),
            ).lastrowid
            if company_name:
                conn.execute("INSERT INTO companies(user_id,name,normalized_name) VALUES(?,?,?)",
                             (user_id, company_name, normalized(company_name)))
    except sqlite3.IntegrityError:
        fail("用户名或公司名称已注册，请更换后重试", 409)
    return {"message": "注册成功，请登录"}


@router.post("/login")
def login(body: Login, request: Request):
    with connect(request.app.state.database) as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (body.username.strip(),)).fetchone()
        if not user or not password_matches(body.password, user["password_hash"]):
            fail("用户名或密码错误", 401)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now(request),))
        old = request_token(request, required=False)
        if old:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(old),))
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?)",
                     (token_hash(token), user["id"], csrf, now(request) + 7 * 86400))
    return {
        "message": "登录成功",
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 7 * 86400,
        "role": user["role"],
    }


@router.get("/me")
def me(request: Request):
    return current_user(request)


@router.post("/logout")
def logout(request: Request):
    current_user(request, write=True)
    with connect(request.app.state.database) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?",
                     (token_hash(request_token(request)),))
    return {"message": "已退出登录"}
