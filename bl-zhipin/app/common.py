"""请求权限、字段校验和时间转换。"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict

from .db import connect

BEIJING = ZoneInfo("Asia/Shanghai")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=20000)


def fail(message, code=422):
    raise HTTPException(code, message)


def text(value, title, maximum=200):
    result = value.strip()
    if not result or len(result) > maximum:
        fail(f"{title}不能为空且不能超过 {maximum} 个字符")
    return result


def normalized(value):
    return value.strip().lower()


def email(value):
    result = value.strip()
    if len(result) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", result):
        fail("请输入有效的联系邮箱")
    return result


def phone(value, required=False):
    result = re.sub(r"[\s()-]", "", value.strip())
    if not result and not required:
        return ""
    if not re.fullmatch(r"\+?[0-9]{7,15}", result):
        fail("请输入有效的手机号，可包含国家区号")
    return result


def password_hash(value):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 600000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def password_matches(value, encoded):
    _, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 600000).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def now(request):
    return request.app.state.clock().timestamp()


def current_user(request: Request, role=None, write=False):
    token = request.cookies.get("bl_session", "")
    with connect(request.app.state.database) as conn:
        row = conn.execute(
            """SELECT u.id,u.username,u.role,c.id company_id,c.name company_name,s.csrf
            FROM sessions s JOIN users u ON u.id=s.user_id
            LEFT JOIN companies c ON c.user_id=u.id
            WHERE s.token_hash=? AND s.expires_at>?""",
            (token_hash(token), now(request)),
        ).fetchone()
    if not row:
        fail("请先登录", 401)
    user = dict(row)
    if role and user["role"] != role:
        fail("当前账号无权执行此操作", 403)
    if write and not hmac.compare_digest(request.headers.get("x-csrf-token", ""), user["csrf"]):
        fail("请求验证失败，请刷新页面后重试", 403)
    return user


def ensure_same_origin(request):
    origin = request.headers.get("origin")
    if not origin:
        return
    # 生产环境由 Nginx 终止 TLS，再把请求转发到容器内的 HTTP。
    # 使用受控反向代理写入的头恢复浏览器看到的外部来源；直连容器时回退到请求本身。
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    expected_scheme = forwarded_proto or request.url.scheme
    expected_host = forwarded_host or request.headers.get("host") or request.url.netloc
    expected = f"{expected_scheme}://{expected_host}".rstrip("/")
    # 不信任仅在文本中包含本地主机名的来源，并用结构化 URL 比较协议和主机。
    actual = urlsplit(origin.rstrip("/"))
    expected_url = urlsplit(expected)
    if actual.scheme != expected_url.scheme or actual.netloc != expected_url.netloc:
        fail("不允许跨站提交", 403)


def future_time(value, request):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=BEIJING)
        stamp = result.timestamp()
    except (ValueError, OverflowError, OSError):
        fail("请选择有效的预约日期和时间")
    if stamp <= now(request):
        fail("预约时间必须晚于当前时间（北京时间）")
    return stamp


def invitation_state(invite, timestamp):
    if invite["used_at"] is not None:
        return "已预约"
    if invite["revoked_at"] is not None:
        return "已撤销"
    if invite["expires_at"] <= timestamp:
        return "已失效"
    return "待预约"
