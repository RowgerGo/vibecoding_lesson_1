import secrets

from fastapi import APIRouter, Request

from .common import (Input, current_user, fail, future_time, invitation_state,
                     now, phone, text)
from .db import connect
from .services import company_application, invitation_view

router = APIRouter(prefix="/api")


class Booking(Input):
    name: str
    phone: str
    scheduled_at: str


@router.post("/company/applications/{application_id}/invitation")
def create_invitation(application_id: int, request: Request):
    user = current_user(request, "company", write=True)
    with connect(request.app.state.database) as conn:
        company_application(conn, application_id, user)
        latest = conn.execute("SELECT * FROM invitations WHERE application_id=? ORDER BY id DESC LIMIT 1",
                              (application_id,)).fetchone()
        if latest:
            state = invitation_state(latest, now(request))
            if state == "已预约":
                fail("该投递已完成预约，不能再次邀请", 409)
            if state == "待预约":
                return invitation_view(latest, request)
        stamp = now(request)
        invite_id = conn.execute("""INSERT INTO invitations(application_id,token,created_at,expires_at)
                                    VALUES(?,?,?,?)""",
                                 (application_id, secrets.token_urlsafe(32), stamp, stamp + 7 * 86400)).lastrowid
        return invitation_view(conn.execute("SELECT * FROM invitations WHERE id=?", (invite_id,)).fetchone(), request)


@router.post("/company/invitations/{invitation_id}/revoke")
def revoke_invitation(invitation_id: int, request: Request):
    user = current_user(request, "company", write=True)
    with connect(request.app.state.database) as conn:
        invite = conn.execute("SELECT * FROM invitations WHERE id=?", (invitation_id,)).fetchone()
        if invite is None:
            fail("邀请不存在", 404)
        company_application(conn, invite["application_id"], user)
        if invite["used_at"] is not None:
            fail("已经预约的邀请不能撤销", 409)
        conn.execute("UPDATE invitations SET revoked_at=COALESCE(revoked_at,?) WHERE id=?", (now(request), invitation_id))
    return {"message": "邀请已撤销"}


def find_invite(conn, token):
    invite = conn.execute("""SELECT i.*,p.name position_name,c.name company_name
        FROM invitations i JOIN applications a ON a.id=i.application_id
        JOIN jobs j ON j.id=a.job_id JOIN positions p ON p.id=j.position_id
        JOIN companies c ON c.id=j.company_id WHERE i.token=?""", (token,)).fetchone()
    if invite is None:
        fail("邀请链接不存在，请向公司索取有效链接", 404)
    return invite


@router.get("/invitations/{token}")
def public_invitation(token: str, request: Request):
    with connect(request.app.state.database) as conn:
        invite = find_invite(conn, token)
        # 公开视图为白名单，不序列化申请人信息、内部关联 ID 或预约资料。
        return {"company_name": invite["company_name"], "position_name": invite["position_name"],
                "expires_at": invite["expires_at"], "status": invitation_state(invite, now(request))}


@router.post("/invitations/{token}/appointments", status_code=201)
def book(token: str, body: Booking, request: Request):
    candidate_name = text(body.name, "姓名", 80)
    candidate_phone = phone(body.phone, required=True)
    stamp = future_time(body.scheduled_at, request)
    with connect(request.app.state.database) as conn:
        invite = find_invite(conn, token)
        state = invitation_state(invite, now(request))
        if state != "待预约":
            fail(f"邀请{state}，无法再次提交", 409)
        conn.execute("INSERT INTO appointments(invitation_id,name,phone,scheduled_at,created_at) VALUES(?,?,?,?,?)",
                     (invite["id"], candidate_name, candidate_phone, stamp, now(request)))
        conn.execute("UPDATE invitations SET used_at=? WHERE id=?", (now(request), invite["id"]))
    return {"message": "预约成功，公司已收到你的预约", "scheduled_at": stamp, "status": "已预约"}


@router.get("/company/appointments")
def company_appointments(request: Request):
    user = current_user(request, "company")
    with connect(request.app.state.database) as conn:
        rows = conn.execute("""SELECT ap.*,a.id application_id,p.name position_name
            FROM appointments ap JOIN invitations i ON i.id=ap.invitation_id
            JOIN applications a ON a.id=i.application_id JOIN jobs j ON j.id=a.job_id
            JOIN positions p ON p.id=j.position_id WHERE j.company_id=? ORDER BY ap.scheduled_at""",
                            (user["company_id"],)).fetchall()
        return [dict(row) for row in rows]


@router.get("/company/appointments/{appointment_id}")
def appointment_detail(appointment_id: int, request: Request):
    rows = company_appointments(request)
    for row in rows:
        if row["id"] == appointment_id:
            return row
    fail("预约不存在或不属于当前公司", 404)
