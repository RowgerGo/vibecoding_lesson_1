import secrets
import sqlite3
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from .common import Input, current_user, email, fail, now, phone, text
from .db import connect
from .files import MAX_FILE_SIZE, MIME_TYPES, filename, validate_file
from .services import APPLICATION_SELECT, JOB_SELECT, application_view, company_application

router = APIRouter(prefix="/api")


class Job(Input):
    position_id: int
    description: str
    email: str


class JobState(Input):
    is_open: bool


@router.get("/jobs")
def public_jobs(request: Request, q: str = "", position_id: int | None = None):
    query, args = JOB_SELECT + " WHERE j.is_open=1", []
    if q.strip():
        # 搜索文本以普通字符串解释，不把 % 和 _ 当作用户提供的通配符。
        search = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query += " AND (p.name LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\' OR j.description LIKE ? ESCAPE '\\')"
        args.extend([search] * 3)
    if position_id is not None:
        query += " AND j.position_id=?"
        args.append(position_id)
    with connect(request.app.state.database) as conn:
        return [dict(r) for r in conn.execute(query + " ORDER BY j.id DESC", args)]


@router.get("/jobs/{job_id}")
def public_job(job_id: int, request: Request):
    with connect(request.app.state.database) as conn:
        row = conn.execute(JOB_SELECT + " WHERE j.id=? AND j.is_open=1", (job_id,)).fetchone()
        if not row:
            fail("招聘不存在或已经关闭，暂时无法投递", 404)
        return dict(row)


@router.get("/company/jobs")
def company_jobs(request: Request):
    user = current_user(request, "company")
    with connect(request.app.state.database) as conn:
        rows = conn.execute(JOB_SELECT + " WHERE j.company_id=? ORDER BY j.id DESC", (user["company_id"],))
        return [dict(r) for r in rows]


def save_job(body, request, job_id=None):
    user = current_user(request, "company", write=True)
    description = text(body.description, "岗位介绍", 20000)
    contact = email(body.email)
    with connect(request.app.state.database) as conn:
        old = None
        if job_id is not None:
            old = conn.execute("SELECT * FROM jobs WHERE id=? AND company_id=?",
                               (job_id, user["company_id"])).fetchone()
            if not old:
                fail("招聘不存在或不属于当前公司", 404)
        position = conn.execute("SELECT * FROM positions WHERE id=?", (body.position_id,)).fetchone()
        if not position or (not position["active"] and (old is None or old["position_id"] != body.position_id)):
            fail("请选择有效的岗位")
        if old is None:
            job_id = conn.execute("""INSERT INTO jobs(company_id,position_id,description,email,created_at)
                                  VALUES(?,?,?,?,?)""",
                                  (user["company_id"], body.position_id, description, contact, now(request))).lastrowid
        else:
            conn.execute("UPDATE jobs SET position_id=?,description=?,email=? WHERE id=?",
                         (body.position_id, description, contact, job_id))
    return {"id": job_id, "message": "招聘已保存"}


@router.post("/company/jobs", status_code=201)
def create_job(body: Job, request: Request):
    return save_job(body, request)


@router.put("/company/jobs/{job_id}")
def update_job(job_id: int, body: Job, request: Request):
    return save_job(body, request, job_id)


@router.patch("/company/jobs/{job_id}/state")
def job_state(job_id: int, body: JobState, request: Request):
    user = current_user(request, "company", write=True)
    with connect(request.app.state.database) as conn:
        changed = conn.execute("UPDATE jobs SET is_open=? WHERE id=? AND company_id=?",
                               (int(body.is_open), job_id, user["company_id"])).rowcount
        if not changed:
            fail("招聘不存在或不属于当前公司", 404)
    return {"message": "招聘已开放" if body.is_open else "招聘已关闭"}


@router.post("/jobs/{job_id}/applications", status_code=201)
async def apply(job_id: int, request: Request, name: str = Form(...), email_address: str = Form(...),
                phone_number: str = Form(""), resume: UploadFile = File(...)):
    user = current_user(request, "seeker", write=True)
    candidate_name = text(name, "姓名", 80)
    candidate_email, candidate_phone = email(email_address), phone(phone_number)
    original = filename(resume.filename)
    extension = Path(original).suffix.lower()
    stored = secrets.token_hex(24) + extension
    path = request.app.state.data_dir / "uploads" / stored
    committed = False
    try:
        size = 0
        with path.open("xb") as output:
            while chunk := await resume.read(64 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    fail("简历大小不能超过 10 MB", 413)
                output.write(chunk)
        if not size:
            fail("简历不能为空文件")
        validate_file(path, extension)
        try:
            with connect(request.app.state.database) as conn:
                job = conn.execute("SELECT is_open FROM jobs WHERE id=?", (job_id,)).fetchone()
                if not job or not job["is_open"]:
                    fail("招聘不存在或已经关闭，暂时无法投递", 409)
                app_id = conn.execute("""INSERT INTO applications
                    (job_id,seeker_id,name,email,phone,original_filename,stored_filename,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (job_id, user["id"], candidate_name, candidate_email, candidate_phone,
                     original, stored, now(request))).lastrowid
        except sqlite3.IntegrityError:
            fail("你已投递过该招聘，不能重复投递", 409)
        committed = True
        return {"id": app_id, "message": "简历投递成功"}
    finally:
        await resume.close()
        if not committed:
            path.unlink(missing_ok=True)


@router.get("/company/applications")
def company_applications(request: Request):
    user = current_user(request, "company")
    with connect(request.app.state.database) as conn:
        rows = conn.execute(APPLICATION_SELECT + " WHERE j.company_id=? ORDER BY a.id DESC", (user["company_id"],)).fetchall()
        return [application_view(conn, row, request) for row in rows]


@router.get("/company/applications/{application_id}")
def company_application_detail(application_id: int, request: Request):
    user = current_user(request, "company")
    with connect(request.app.state.database) as conn:
        row = company_application(conn, application_id, user)
        # GET 详情不修改状态。前端打开详情后显式调用 viewed 写接口。
        return application_view(conn, row, request)


@router.post("/company/applications/{application_id}/viewed")
def view_application(application_id: int, request: Request):
    user = current_user(request, "company", write=True)
    with connect(request.app.state.database) as conn:
        company_application(conn, application_id, user)
        conn.execute("UPDATE applications SET viewed_at=COALESCE(viewed_at,?) WHERE id=?", (now(request), application_id))
    return {"message": "已标记查看"}


@router.get("/company/applications/{application_id}/resume")
def download_resume(application_id: int, request: Request):
    user = current_user(request, "company")
    with connect(request.app.state.database) as conn:
        row = company_application(conn, application_id, user)
    path = request.app.state.data_dir / "uploads" / row["stored_filename"]
    if not path.is_file():
        fail("简历文件暂时不可用，请联系平台维护人员", 404)
    return FileResponse(path, filename=row["original_filename"],
                        media_type=MIME_TYPES[Path(path).suffix], headers={"Cache-Control": "no-store"})


@router.get("/seeker/applications")
def seeker_applications(request: Request):
    user = current_user(request, "seeker")
    with connect(request.app.state.database) as conn:
        rows = conn.execute(APPLICATION_SELECT + " WHERE a.seeker_id=? ORDER BY a.id DESC", (user["id"],)).fetchall()
        return [application_view(conn, row, request) for row in rows]


@router.get("/seeker/applications/{application_id}")
def seeker_application_detail(application_id: int, request: Request):
    user = current_user(request, "seeker")
    with connect(request.app.state.database) as conn:
        row = conn.execute(APPLICATION_SELECT + " WHERE a.id=? AND a.seeker_id=?", (application_id, user["id"])).fetchone()
        if not row:
            fail("投递不存在或不属于当前账号", 404)
        return application_view(conn, row, request)
