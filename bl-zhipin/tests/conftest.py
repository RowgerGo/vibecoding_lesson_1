from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.common import password_hash
from app.db import connect
from app.main import create_app

PASSWORD = "TestPass2026!"
HASH = password_hash(PASSWORD)
FIXTURES = Path(__file__).parent / "fixtures"


class Clock:
    def __init__(self):
        self.current = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.current

    def advance(self, **values):
        self.current += timedelta(**values)


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    app = create_app(tmp_path, clock)
    roles = {"admin":"admin", "company":"company", "other_company":"company",
             "seeker":"seeker", "other_seeker":"seeker"}
    with connect(app.state.database) as conn:
        ids = {}
        for username, role in roles.items():
            ids[username] = conn.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                (username, HASH, role, clock().timestamp())).lastrowid
        for username, name in [("company", "Example Studio"), ("other_company", "Other Company")]:
            conn.execute("INSERT INTO companies(user_id,name,normalized_name) VALUES(?,?,?)",
                         (ids[username], name, name.lower()))
        position_id = conn.execute("INSERT INTO positions(name,normalized_name) VALUES('Python 开发','python 开发')").lastrowid
        company_id = conn.execute("SELECT id FROM companies WHERE user_id=?", (ids["company"],)).fetchone()[0]
        job_id = conn.execute("""INSERT INTO jobs(company_id,position_id,description,email,created_at)
            VALUES(?,?,?,'jobs@example.com',?)""", (company_id, position_id, "一起开发 Python API", clock().timestamp())).lastrowid
    with ExitStack() as stack:
        clients = {}

        def client(username=None):
            key = username or "visitor"
            if key not in clients:
                c = stack.enter_context(TestClient(app))
                if username:
                    login = c.post("/api/auth/login", json={"username":username,"password":PASSWORD})
                    assert login.status_code == 200, login.text
                    c.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
                clients[key] = c
            return clients[key]

        def submit(username="seeker", extension="pdf", **fields):
            data = {"name":"测试求职者", "email_address":"candidate@example.com", "phone_number":"13800138000"}
            data.update(fields)
            return client(username).post(f"/api/jobs/{job_id}/applications", data=data,
                files={"resume":(f"resume.{extension}", (FIXTURES / f"resume.{extension}").read_bytes())})

        def invite():
            applied = submit()
            assert applied.status_code == 201, applied.text
            result = client("company").post(f"/api/company/applications/{applied.json()['id']}/invitation")
            assert result.status_code == 200, result.text
            return applied.json()["id"], result.json()

        yield SimpleNamespace(app=app, clock=clock, client=client, submit=submit, invite=invite,
                              job=job_id, position=position_id, ids=ids, path=tmp_path)
