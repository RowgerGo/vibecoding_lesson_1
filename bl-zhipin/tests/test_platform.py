import io
import sqlite3
import os
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import connect, initialize
from app.files import MAX_FILE_SIZE
from app.main import create_app
from conftest import FIXTURES, PASSWORD


def booking(**changes):
    result = {"name":"预约测试", "phone":"13800138000", "scheduled_at":"2026-11-10T10:30"}
    result.update(changes)
    return result


def test_routes_assets_and_private_storage(env):
    visitor = env.client()
    for route in ["/", "/login", "/register", "/company", "/applications", "/admin", "/invite/example", "/static/styles.css", "/static/app.js"]:
        assert visitor.get(route).status_code == 200
    assert visitor.get("/api/health").json() == {"status":"ok"}
    assert "/api/jobs" in visitor.get("/api/openapi.json").json()["paths"]
    assert visitor.get("/api/unknown").json() == {"message":"页面或接口不存在"}
    for route in ["/data/platform.sqlite3", "/static/../data/platform.sqlite3", "/uploads/resume.pdf"]:
        assert visitor.get(route).status_code == 404
    headers = visitor.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_registration_uniqueness_and_rollback(env):
    c = env.client()
    body = {"username":"new-company", "password":PASSWORD, "role":"company", "company_name":" ACME "}
    assert c.post("/api/auth/register", json=body).status_code == 201
    assert c.post("/api/auth/register", json={**body,"username":"duplicate-company","company_name":"acme"}).status_code == 409
    assert c.post("/api/auth/register", json={**body,"company_name":"Different"}).status_code == 409
    with connect(env.app.state.database) as conn:
        assert conn.execute("SELECT 1 FROM users WHERE username='duplicate-company'").fetchone() is None
        assert conn.execute("SELECT normalized_name FROM companies WHERE name='ACME'").fetchone()[0] == "acme"
        assert conn.execute("SELECT password_hash FROM users WHERE username='new-company'").fetchone()[0] != PASSWORD
    for change in [{"role":"admin"},{"company_name":" "},{"password":"short"},{"username":" "},{"role":"seeker","unknown":"x"}]:
        assert c.post("/api/auth/register", json={**body, **change}).status_code == 422
    assert c.post("/api/auth/register", json={"username":"new-seeker", "password":PASSWORD,"role":"seeker"}).status_code == 201


def test_login_logout_csrf_and_fixed_role(env):
    c = env.client("seeker")
    assert c.get("/api/auth/me").json()["role"] == "seeker"
    cookie = c.cookies.get("bl_session")
    assert c.post("/api/auth/logout", headers={"X-CSRF-Token":"wrong"}).status_code == 403
    assert c.post("/api/auth/logout", headers={"Origin":"https://evil.invalid"}).status_code == 403
    assert c.patch("/api/auth/me", json={"role":"admin"}).status_code == 405
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    c.cookies.set("bl_session", cookie)
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"username":"seeker","password":"incorrect"}).status_code == 401
    assert env.client().post("/api/auth/login", json={"username":"seeker","password":PASSWORD}, headers={"Origin":"http://testserver.evil.invalid"}).status_code == 403


def test_https_reverse_proxy_origin_is_allowed(env):
    response = env.client().post(
        "/api/auth/login",
        json={"username":"seeker", "password":"incorrect"},
        headers={
            "Origin":"https://zhipin.1024web.cn",
            "X-Forwarded-Proto":"https",
            "X-Forwarded-Host":"zhipin.1024web.cn",
        },
    )
    # 来源校验通过后才会进入账号校验；错误密码应得到 401，而不是跨站 403。
    assert response.status_code == 401


def test_position_management_and_role_isolation(env):
    admin = env.client("admin")
    created = admin.post("/api/admin/positions", json={"name":" Designer "})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert admin.post("/api/admin/positions", json={"name":"designer"}).status_code == 409
    assert admin.post("/api/admin/positions", json={"name":" "}).status_code == 422
    assert admin.put(f"/api/admin/positions/{pid}", json={"name":"Design Lead","active":False}).status_code == 200
    assert pid not in [p["id"] for p in env.client().get("/api/positions").json()]
    for role, code in [(None,401),("company",403),("seeker",403)]:
        assert env.client(role).post("/api/admin/positions", json={"name":"Unauthorized"}).status_code == code
        assert env.client(role).get("/api/admin/positions").status_code == code


def test_company_jobs_edit_close_reopen_and_disabled_position(env):
    c, admin = env.client("company"), env.client("admin")
    body = {"position_id":env.position,"description":"新的岗位介绍","email":"jobs@example.com"}
    created = c.post("/api/company/jobs", json=body)
    assert created.status_code == 201
    jid = created.json()["id"]
    assert c.put(f"/api/company/jobs/{jid}", json={**body,"description":"已编辑"}).status_code == 200
    assert env.client().get(f"/api/jobs/{jid}").json()["description"] == "已编辑"
    assert c.post("/api/company/jobs", json={**body,"email":"wrong"}).status_code == 422
    assert c.post("/api/company/jobs", json={**body,"description":" "}).status_code == 422
    assert env.client("other_company").put(f"/api/company/jobs/{jid}", json=body).status_code == 404
    assert c.patch(f"/api/company/jobs/{env.job}/state", json={"is_open":False}).status_code == 200
    assert env.client().get(f"/api/jobs/{env.job}").status_code == 404
    assert env.submit().status_code == 409
    assert c.patch(f"/api/company/jobs/{env.job}/state", json={"is_open":True}).status_code == 200
    assert env.submit().status_code == 201
    assert admin.put(f"/api/admin/positions/{env.position}", json={"name":"高级开发","active":False}).status_code == 200
    assert env.client().get(f"/api/jobs/{env.job}").json()["position_name"] == "高级开发"
    assert c.post("/api/company/jobs", json=body).status_code == 422
    assert c.put(f"/api/company/jobs/{jid}", json=body).status_code == 200
    assert env.client("seeker").get("/api/seeker/applications").json()[0]["position_name"] == "高级开发"
    assert c.delete(f"/api/company/jobs/{jid}").status_code == 405


@pytest.mark.parametrize("role,code", [(None,401),("seeker",403),("admin",403)])
def test_only_company_can_publish(env, role, code):
    assert env.client(role).post("/api/company/jobs",json={"position_id":env.position,"description":"test","email":"x@y.com"}).status_code == code


def test_search_filters_and_user_text(env):
    visitor = env.client()
    for q in ["Python", "Example", "API"]:
        assert visitor.get("/api/jobs", params={"q":q,"position_id":env.position}).json()[0]["id"] == env.job
    for query in [{"q":"not-found"},{"position_id":999},{"q":"%' OR 1=1 --"},{"q":"%"}]:
        assert visitor.get("/api/jobs", params=query).json() == []
    assert "stored_filename" not in visitor.get(f"/api/jobs/{env.job}").json()


@pytest.mark.parametrize("extension", ["pdf","doc","docx"])
def test_real_resume_formats_download_and_viewed_state(env, extension):
    response = env.submit(extension=extension)
    assert response.status_code == 201, response.text
    aid = response.json()["id"]
    company, seeker = env.client("company"), env.client("seeker")
    assert company.get("/api/company/applications").json()[0]["status"] == "已投递"
    assert seeker.get("/api/seeker/applications").json()[0]["status"] == "已投递"
    assert "stored_filename" not in company.get(f"/api/company/applications/{aid}").json()
    assert company.post(f"/api/company/applications/{aid}/viewed").status_code == 200
    assert seeker.get(f"/api/seeker/applications/{aid}").json()["status"] == "已查看"
    download = company.get(f"/api/company/applications/{aid}/resume")
    assert download.content == (FIXTURES / f"resume.{extension}").read_bytes()
    assert "attachment" in download.headers["content-disposition"]
    assert env.submit(extension=extension).status_code == 409
    assert len(list((env.path / "uploads").iterdir())) == 1
    assert len(seeker.get("/api/seeker/applications").json()) == 1


def test_resume_and_application_permissions(env):
    aid = env.submit().json()["id"]
    for role, code in [(None,401),("admin",403),("seeker",403),("other_company",404)]:
        c = env.client(role)
        assert c.get(f"/api/company/applications/{aid}/resume").status_code == code
        assert c.get(f"/api/company/applications/{aid}").status_code == code
        assert c.post(f"/api/company/applications/{aid}/viewed").status_code == code
    assert env.client("other_seeker").get(f"/api/seeker/applications/{aid}").status_code == 404
    assert env.client("other_seeker").get("/api/seeker/applications").json() == []
    assert env.client("other_company").get("/api/company/applications").json() == []
    for role,code in [(None,401),("company",403),("admin",403)]:
        c = env.client(role)
        assert c.post(f"/api/jobs/{env.job}/applications", data={"name":"X","email_address":"x@y.com"},
                      files={"resume":("resume.pdf",(FIXTURES/"resume.pdf").read_bytes())}).status_code == code


@pytest.mark.parametrize("filename,content,code", [("x.exe",b"MZ",422),("x.pdf",b"",422),("x.pdf",b"fake",422),
    ("x.doc",b"not a doc",422),("x.docx",b"not a zip",422),("x.pdf",b"a"*(MAX_FILE_SIZE+1),413)])
def test_invalid_uploads_leave_no_files(env, filename, content, code):
    result = env.client("seeker").post(f"/api/jobs/{env.job}/applications", data={"name":"X","email_address":"x@y.com"}, files={"resume":(filename,content)})
    assert result.status_code == code, result.text
    assert list((env.path/"uploads").iterdir()) == []
    assert env.client("seeker").get("/api/seeker/applications").json() == []


def test_exact_size_boundary_and_path_filename(env):
    content = (FIXTURES/"resume.pdf").read_bytes()
    # PDF 可在 EOF 前插入注释，保留完整原始对象及交叉引用偏移。
    padded = content.replace(b"%%EOF", b"%" + b" "*(MAX_FILE_SIZE-len(content)-2) + b"\n%%EOF")
    assert len(padded) == MAX_FILE_SIZE
    result = env.client("seeker").post(f"/api/jobs/{env.job}/applications", data={"name":"X","email_address":"x@y.com"}, files={"resume":("../../resume.pdf",padded)})
    assert result.status_code == 201, result.text
    row = env.client("seeker").get("/api/seeker/applications").json()[0]
    assert row["original_filename"] == "resume.pdf"
    assert len(list((env.path/"uploads").iterdir())) == 1


def test_invalid_contact_fields_and_closed_history(env):
    assert env.submit(email_address="invalid").status_code == 422
    assert env.submit(name=" ").status_code == 422
    assert env.submit(phone_number="invalid").status_code == 422
    assert env.submit(phone_number="").status_code == 201
    env.client("company").patch(f"/api/company/jobs/{env.job}/state",json={"is_open":False})
    assert len(env.client("seeker").get("/api/seeker/applications").json()) == 1
    assert len(env.client("company").get("/api/company/applications").json()) == 1


def test_invitation_booking_without_login_privacy_and_both_results(env):
    aid, invite = env.invite()
    public = env.client()
    view = public.get(f"/api/invitations/{invite['token']}")
    assert set(view.json()) == {"company_name","position_name","expires_at","status"}
    assert view.json()["status"] == "待预约"
    assert public.get(f"/invite/{invite['token']}").status_code == 200
    result = public.post(f"/api/invitations/{invite['token']}/appointments", json=booking())
    assert result.status_code == 201, result.text
    assert result.json()["scheduled_at"] == datetime(2026,11,10,2,30,tzinfo=timezone.utc).timestamp()
    assert public.post(f"/api/invitations/{invite['token']}/appointments", json=booking()).status_code == 409
    assert public.get(f"/api/invitations/{invite['token']}").json()["status"] == "已预约"
    company = env.client("company")
    appointments = company.get("/api/company/appointments").json()
    assert appointments[0]["name"] == "预约测试"
    assert env.client("seeker").get(f"/api/seeker/applications/{aid}").json()["appointment"]["phone"] == "13800138000"
    assert env.client("other_company").get(f"/api/company/appointments/{appointments[0]['id']}").status_code == 404
    assert env.client("other_company").get("/api/company/appointments").json() == []
    assert company.post(f"/api/company/invitations/{invite['id']}/revoke").status_code == 409
    assert company.post(f"/api/company/applications/{aid}/invitation").status_code == 409
    assert "预约测试" not in public.get(f"/api/invitations/{invite['token']}").text


def test_invitation_idempotent_revoke_reissue_and_permissions(env):
    aid, invite = env.invite()
    c = env.client("company")
    assert c.post(f"/api/company/applications/{aid}/invitation").json()["token"] == invite["token"]
    for role, code in [(None,401),("seeker",403),("admin",403),("other_company",404)]:
        assert env.client(role).post(f"/api/company/applications/{aid}/invitation").status_code == code
        assert env.client(role).post(f"/api/company/invitations/{invite['id']}/revoke").status_code == code
    assert c.post(f"/api/company/invitations/{invite['id']}/revoke").status_code == 200
    assert env.client().get(f"/api/invitations/{invite['token']}").json()["status"] == "已撤销"
    assert env.client().post(f"/api/invitations/{invite['token']}/appointments",json=booking()).status_code == 409
    new = c.post(f"/api/company/applications/{aid}/invitation").json()
    assert new["token"] != invite["token"]
    assert env.client().post(f"/api/invitations/{invite['token']}/appointments",json=booking()).status_code == 409
    assert env.client("seeker").get(f"/api/seeker/applications/{aid}").json()["invitation"]["token"] == new["token"]


def test_seven_day_expiry_exact_boundary_and_reissue(env):
    aid, invite = env.invite()
    public = env.client()
    env.clock.advance(days=7,seconds=-1)
    assert public.get(f"/api/invitations/{invite['token']}").json()["status"] == "待预约"
    env.clock.advance(seconds=1)
    assert public.get(f"/api/invitations/{invite['token']}").json()["status"] == "已失效"
    assert public.post(f"/api/invitations/{invite['token']}/appointments",json=booking()).status_code == 409
    # 会话也满 7 天到期，重新登录后重发。
    c = env.client("company")
    assert c.get("/api/auth/me").status_code == 401
    logged = c.post("/api/auth/login",json={"username":"company","password":PASSWORD}).json()
    c.headers["X-CSRF-Token"] = logged["csrf"]
    new = c.post(f"/api/company/applications/{aid}/invitation").json()
    assert new["token"] != invite["token"]
    assert public.post(f"/api/invitations/{invite['token']}/appointments",json=booking()).status_code == 409


@pytest.mark.parametrize("change", [{"name":" "},{"phone":""},{"phone":"abc"},{"scheduled_at":"2026-10-27T20:00"},
    {"scheduled_at":"2026-10-26T10:00"},{"scheduled_at":"not-a-date"},{"extra":"unexpected"}])
def test_invalid_booking_values(env, change):
    _, invite = env.invite()
    result = env.client().post(f"/api/invitations/{invite['token']}/appointments",json=booking(**change))
    assert result.status_code == 422, result.text
    assert env.client().get(f"/api/invitations/{invite['token']}").json()["status"] == "待预约"


def test_concurrent_booking_only_once_and_simultaneous_slots_allowed(env):
    _, invite = env.invite()
    url = f"/api/invitations/{invite['token']}/appointments"
    def send(_):
        with TestClient(env.app) as c:
            return c.post(url,json=booking()).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(send, range(4)))
    assert statuses.count(201) == 1
    assert statuses.count(409) == 3
    second = env.submit("other_seeker").json()["id"]
    another = env.client("company").post(f"/api/company/applications/{second}/invitation").json()
    assert env.client().post(f"/api/invitations/{another['token']}/appointments",json=booking()).status_code == 201
    assert len(env.client("company").get("/api/company/appointments").json()) == 2


def test_concurrent_application_only_once(env):
    c = env.client("seeker")
    cookies, headers = dict(c.cookies), dict(c.headers)
    def send(_):
        with TestClient(env.app) as client:
            client.cookies.update(cookies)
            return client.post(f"/api/jobs/{env.job}/applications",headers=headers,
                data={"name":"X","email_address":"x@y.com"},files={"resume":("resume.pdf",(FIXTURES/"resume.pdf").read_bytes())}).status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        statuses = list(pool.map(send, range(3)))
    assert statuses.count(201) == 1
    assert statuses.count(409) == 2
    assert len(list((env.path/"uploads").iterdir())) == 1


def test_restart_persistence_missing_file_and_database_constraints(env):
    aid, invite = env.invite()
    env.client().post(f"/api/invitations/{invite['token']}/appointments",json=booking())
    initialize(env.path)
    restarted = create_app(env.path, env.clock)
    with TestClient(restarted) as c:
        r = c.post("/api/auth/login", json={"username":"company","password":PASSWORD})
        assert r.status_code == 200
        assert c.get("/api/company/jobs").json()[0]["id"] == env.job
        assert len(c.get("/api/company/appointments").json()) == 1
        assert c.get(f"/api/company/applications/{aid}/resume").status_code == 200
        for file in (env.path/"uploads").iterdir():
            file.unlink()
        assert c.get(f"/api/company/applications/{aid}/resume").status_code == 404
    with connect(env.app.state.database) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO companies(user_id,name,normalized_name) VALUES(?,?,?)", (env.ids["company"],"Another","another"))
    assert env.client().get("/api/invitations/nonexistent").status_code == 404


def test_docx_without_word_document_is_rejected(env):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("README.txt", "This is a zip, not a Word document.")
    result = env.client("seeker").post(f"/api/jobs/{env.job}/applications",
        data={"name":"X","email_address":"x@y.com"}, files={"resume":("fake.docx",data.getvalue())})
    assert result.status_code == 422
    assert not list((env.path/"uploads").iterdir())


def test_admin_cli_creation_duplicate_and_password_confirmation(tmp_path):
    environment = {**os.environ,"BL_DATA_DIR":str(tmp_path)}
    command = [sys.executable,"-m","app.cli","create-admin","--username","cli_admin"]
    first = subprocess.run(command,input=f"{PASSWORD}\n{PASSWORD}\n",text=True,capture_output=True,env=environment)
    assert first.returncode == 0, first.stderr
    assert "创建成功" in first.stdout
    with connect(tmp_path/"platform.sqlite3") as conn:
        stored = dict(conn.execute("SELECT * FROM users WHERE username='cli_admin'").fetchone())
    duplicate = subprocess.run(command,input="DifferentPass1!\nDifferentPass1!\n",text=True,capture_output=True,env=environment)
    assert duplicate.returncode != 0
    assert "用户名已存在" in duplicate.stderr
    with connect(tmp_path/"platform.sqlite3") as conn:
        assert dict(conn.execute("SELECT * FROM users WHERE username='cli_admin'").fetchone()) == stored
    mismatch = subprocess.run(command,input="TestPass1!\nDifferentPass1!\n",text=True,capture_output=True,env=environment)
    assert mismatch.returncode != 0
    assert "两次密码不一致" in mismatch.stderr
