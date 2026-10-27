import sqlite3

from fastapi import APIRouter, Request

from .common import Input, current_user, fail, normalized, text
from .db import connect

router = APIRouter(prefix="/api")


class Position(Input):
    name: str
    active: bool = True


@router.get("/positions")
def positions(request: Request):
    with connect(request.app.state.database) as conn:
        return [dict(r) for r in conn.execute("SELECT id,name FROM positions WHERE active=1 ORDER BY id DESC")]


@router.get("/admin/positions")
def admin_positions(request: Request):
    current_user(request, "admin")
    with connect(request.app.state.database) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM positions ORDER BY id DESC")]


def save_position(body, request, position_id=None):
    current_user(request, "admin", write=True)
    name = text(body.name, "岗位名称", 100)
    try:
        with connect(request.app.state.database) as conn:
            if position_id is None:
                position_id = conn.execute("INSERT INTO positions(name,normalized_name,active) VALUES(?,?,?)",
                                           (name, normalized(name), int(body.active))).lastrowid
            else:
                changed = conn.execute("UPDATE positions SET name=?,normalized_name=?,active=? WHERE id=?",
                                       (name, normalized(name), int(body.active), position_id)).rowcount
                if not changed:
                    fail("岗位不存在", 404)
    except sqlite3.IntegrityError:
        fail("岗位名称已存在", 409)
    return {"id": position_id, "message": "岗位已保存"}


@router.post("/admin/positions", status_code=201)
def create_position(body: Position, request: Request):
    return save_position(body, request)


@router.put("/admin/positions/{position_id}")
def update_position(position_id: int, body: Position, request: Request):
    return save_position(body, request, position_id)
