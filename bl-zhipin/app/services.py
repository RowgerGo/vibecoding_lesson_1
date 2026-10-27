"""投递归属检查与对账号可见的业务视图。"""

from .common import fail, invitation_state, now

JOB_SELECT = """SELECT j.*,p.name position_name,p.active position_active,c.name company_name
    FROM jobs j JOIN positions p ON p.id=j.position_id
    JOIN companies c ON c.id=j.company_id"""

APPLICATION_SELECT = """SELECT a.*,j.company_id,j.is_open,p.name position_name,c.name company_name
    FROM applications a JOIN jobs j ON j.id=a.job_id
    JOIN positions p ON p.id=j.position_id JOIN companies c ON c.id=j.company_id"""


def company_application(conn, application_id, user):
    row = conn.execute(APPLICATION_SELECT + " WHERE a.id=? AND j.company_id=?",
                       (application_id, user["company_id"])).fetchone()
    if row is None:
        fail("投递不存在或不属于当前公司", 404)
    return row


def invitation_view(row, request):
    result = dict(row)
    result["status"] = invitation_state(row, now(request))
    base = request.app.state.public_url or str(request.base_url).rstrip("/")
    result["url"] = f"{base}/invite/{row['token']}"
    return result


def application_view(conn, row, request):
    result = dict(row)
    result.pop("stored_filename", None)
    result["status"] = "已查看" if row["viewed_at"] is not None else "已投递"
    invite = conn.execute("SELECT * FROM invitations WHERE application_id=? ORDER BY id DESC LIMIT 1",
                          (row["id"],)).fetchone()
    result["invitation"] = invitation_view(invite, request) if invite else None
    booking = conn.execute("""SELECT ap.* FROM appointments ap JOIN invitations i ON i.id=ap.invitation_id
                            WHERE i.application_id=?""", (row["id"],)).fetchone()
    result["appointment"] = dict(booking) if booking else None
    return result
