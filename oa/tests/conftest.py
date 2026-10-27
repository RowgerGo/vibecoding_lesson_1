import shutil
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.cli import create_admin
from app.db import connection
from app.main import create_app

PASSWORD = "test-only-password-2026"


class Actor:
    def __init__(self, client, username):
        self.client = client
        response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        self.user = response.json()["user"]
        self.csrf = response.json()["csrf_token"]
        client.headers["X-CSRF-Token"] = self.csrf

    def get(self, path, **kwargs):
        return self.client.get("/api" + path, **kwargs)

    def post(self, path, **kwargs):
        return self.client.post("/api" + path, **kwargs)

    def patch(self, path, **kwargs):
        return self.client.patch("/api" + path, **kwargs)

    def put(self, path, **kwargs):
        return self.client.put("/api" + path, **kwargs)

    def apply(self, department, **overrides):
        body = {"event_date": "2026-10-30", "title": "采购申请", "content": "申请购买办公用品。", "approval_department_id": department}
        body.update(overrides)
        return self.post("/applications", json=body)


@pytest.fixture(scope="session")
def seed(tmp_path_factory):
    path = tmp_path_factory.mktemp("seed") / "oa.sqlite3"
    create_admin(path, "admin", "系统管理员", PASSWORD)
    with TestClient(create_app(path)) as client:
        admin = Actor(client, "admin")
        deps = {}
        for name in ("销售部", "财务部", "人事部", "空部门"):
            response = admin.post("/departments", json={"name": name})
            assert response.status_code == 201
            deps[name] = response.json()["id"]
        users = {}
        for username, name, department in [("sales_head", "销售负责人", "销售部"), ("finance_head", "财务负责人", "财务部"), ("user", "申请人", "销售部"), ("other", "其他成员", "销售部"), ("hr_user", "人事成员", "人事部")]:
            response = admin.post("/users", json={"username": username, "name": name, "password": PASSWORD, "department_id": deps[department]})
            assert response.status_code == 201
            users[username] = response.json()["id"]
        for department, username in [("销售部", "sales_head"), ("财务部", "finance_head")]:
            assert admin.put(f"/departments/{deps[department]}/head", json={"user_id": users[username]}).status_code == 200
    with connection(path, write=True) as db:
        db.execute("DELETE FROM sessions")
    return path, deps, users


@pytest.fixture
def world(tmp_path, seed):
    source, deps, users = seed
    path = tmp_path / "oa.sqlite3"
    shutil.copy2(source, path)
    app = create_app(path)
    with ExitStack() as stack:
        actors = {}

        def actor(username):
            if username not in actors:
                client = stack.enter_context(TestClient(app))
                actors[username] = Actor(client, username)
            return actors[username]

        yield {"actor": actor, "path": path, "departments": deps, "users": users, "app": app}
