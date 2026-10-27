import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.cli import create_admin
from app.db import connection, initialize
from app.main import create_app
from conftest import Actor, PASSWORD


def test_initialization_static_and_database_constraints(world):
    initialize(world["path"])
    with TestClient(world["app"]) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200
        assert client.get("/api/users").status_code == 401
        assert client.get("/").headers["x-frame-options"] == "DENY"
    with connection(world["path"]) as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 6
        assert PASSWORD not in db.execute("SELECT password_hash FROM users LIMIT 1").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO users(username,name,password_hash) VALUES('missing','无部门','hash')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO users(username,name,password_hash,department_id) VALUES('bad','无效部门','hash',999)")
    with pytest.raises(sqlite3.IntegrityError):
        create_admin(world["path"], "admin", "重复", PASSWORD)


def test_login_cookie_logout_and_session_expiry(world):
    actor = world["actor"]("user")
    response = actor.get("/auth/me")
    assert response.status_code == 200
    assert "password_hash" not in response.text and "token_hash" not in response.text
    raw_cookie = actor.client.cookies.get("oa_session")
    with TestClient(world["app"]) as client:
        login = client.post("/api/auth/login", json={"username": "user", "password": PASSWORD})
        cookie = login.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert client.post("/api/auth/login", json={"username": "user", "password": "wrong"}).status_code == 401
    assert actor.post("/auth/logout").status_code == 200
    actor.client.cookies.set("oa_session", raw_cookie)
    assert actor.get("/auth/me").status_code == 401
    with TestClient(create_app(world["path"], session_seconds=-1)) as client:
        assert client.post("/api/auth/login", json={"username": "user", "password": PASSWORD}).status_code == 200
        assert client.get("/api/auth/me").status_code == 401


def test_csrf_and_cross_origin_protection(world):
    actor = world["actor"]("admin")
    assert actor.post("/departments", json={"name": "失败"}, headers={"X-CSRF-Token": ""}).status_code == 403
    assert actor.post("/departments", json={"name": "失败"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert actor.post("/departments", json={"name": "同源"}, headers={"Origin": "http://testserver"}).status_code == 201


@pytest.mark.parametrize("username", ["user", "sales_head", "finance_head"])
def test_admin_apis_are_protected(world, username):
    actor = world["actor"](username)
    for path in ("/users", "/departments"):
        assert actor.get(path).status_code == 403
    assert actor.post("/departments", json={"name": "越权"}).status_code == 403
    assert actor.post("/users", json={"username": "hacked", "name": "越权", "password": PASSWORD, "department_id": 1}).status_code == 403
    assert actor.post(f'/users/{world["users"]["user"]}/reset-password', json={"new_password": PASSWORD}).status_code == 403


def test_department_creation_and_disable(world):
    admin = world["actor"]("admin")
    deps = world["departments"]
    assert admin.post("/departments", json={"name": "销售部"}).status_code == 409
    assert admin.post("/departments", json={"name": "  "}).status_code == 422
    assert admin.post("/departments", json={"name": "子部门", "parent_id": 1}).status_code == 422
    assert admin.patch(f'/departments/{deps["销售部"]}', json={"enabled": False}).status_code == 409
    assert admin.patch(f'/departments/{deps["空部门"]}', json={"enabled": False}).status_code == 200
    assert any(row["id"] == deps["空部门"] and not row["enabled"] for row in admin.get("/departments").json()["items"])
    assert admin.patch(f'/departments/{deps["空部门"]}', json={"enabled": True}).status_code == 200
    assert admin.patch("/departments/9999", json={"enabled": False}).status_code == 404


def test_user_creation_and_immutable_identity(world):
    admin = world["actor"]("admin")
    department = world["departments"]["销售部"]
    body = {"username": "new_user", "name": "新成员", "password": PASSWORD, "department_id": department}
    created = admin.post("/users", json=body)
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert "password" not in created.json()
    assert admin.post("/users", json=body).status_code == 409
    assert admin.post("/users", json={**body, "username": "missing", "department_id": None}).status_code == 422
    assert admin.post("/users", json={**body, "username": "multi", "department_id": [1, 2]}).status_code == 422
    assert admin.patch(f"/users/{user_id}", json={"enabled": True, "department_id": 2}).status_code == 422
    assert admin.patch(f"/users/{user_id}", json={"enabled": True, "username": "changed"}).status_code == 422
    assert admin.post("/users", json={**body, "username": "admin2", "is_admin": True, "department_id": None}).status_code == 201
    assert admin.patch(f'/users/{admin.user["id"]}', json={"enabled": False}).status_code == 200  # 仍有第二名管理员


def test_last_admin_cannot_be_disabled(world):
    admin = world["actor"]("admin")
    assert admin.patch(f'/users/{admin.user["id"]}', json={"enabled": False}).status_code == 409


def test_first_head_assignment_rules(world):
    admin = world["actor"]("admin")
    deps, users = world["departments"], world["users"]
    assert admin.put(f'/departments/{deps["销售部"]}/head', json={"user_id": users["other"]}).status_code == 409
    assert admin.put(f'/departments/{deps["人事部"]}/head', json={"user_id": users["other"]}).status_code == 422
    assert admin.put(f'/departments/{deps["人事部"]}/head', json={"user_id": admin.user["id"]}).status_code == 422
    admin.patch(f'/users/{users["hr_user"]}', json={"enabled": False})
    assert admin.put(f'/departments/{deps["人事部"]}/head', json={"user_id": users["hr_user"]}).status_code == 422
    admin.patch(f'/users/{users["hr_user"]}', json={"enabled": True})
    assert admin.put(f'/departments/{deps["人事部"]}/head', json={"user_id": users["hr_user"]}).status_code == 200
    assert world["actor"]("hr_user").get("/auth/me").json()["user"]["role"] == "head"
    assert admin.patch(f'/users/{users["hr_user"]}', json={"enabled": False}).status_code == 409


def test_concurrent_first_head_assignment_only_one_wins(world):
    admin = world["actor"]("admin")
    department = world["departments"]["人事部"]
    response = admin.post("/users", json={"username": "hr_candidate", "name": "第二候选人", "password": PASSWORD, "department_id": department})
    candidates = [world["users"]["hr_user"], response.json()["id"]]
    def assign(user_id):
        return admin.put(f"/departments/{department}/head", json={"user_id": user_id}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(assign, candidates))
    assert sorted(codes) == [200, 409]
    record = next(dep for dep in admin.get("/departments").json()["items"] if dep["id"] == department)
    assert record["head_user_id"] in candidates


def test_approval_department_options_and_headless_home(world):
    actor = world["actor"]("hr_user")
    deps = world["departments"]
    ids = {item["id"] for item in actor.get("/approval-departments").json()["items"]}
    assert ids == {deps["销售部"], deps["财务部"]}
    assert actor.apply(deps["财务部"]).status_code == 201
    assert actor.apply(deps["人事部"]).status_code == 422
    assert actor.apply(999).status_code == 422


@pytest.mark.parametrize("override", [
    {"title": "  "}, {"content": "\n "}, {"event_date": "2026-02-30"}, {"title": "x" * 201},
    {"applicant_id": 999}, {"status": "approved"}, {"submitted_at": "fake"}, {"reviewer_id": 1},
])
def test_application_validation_does_not_create_records(world, override):
    actor = world["actor"]("user")
    assert actor.apply(world["departments"]["财务部"], **override).status_code == 422
    assert actor.get("/applications").json()["total"] == 0


def test_cross_department_visibility_and_scope_filters(world):
    actors = {name: world["actor"](name) for name in ("user", "other", "sales_head", "finance_head", "admin")}
    record = actors["user"].apply(world["departments"]["财务部"]).json()
    assert record["status"] == "pending"
    for name in ("user", "finance_head", "admin"):
        assert actors[name].get(f'/applications/{record["id"]}').status_code == 200
        assert actors[name].get("/applications?status=pending&page_size=1").json()["total"] == 1
    for name in ("other", "sales_head"):
        assert actors[name].get(f'/applications/{record["id"]}').status_code == 404
        for query in ("", "?status=pending", "?page=99", "?scope=mine"):
            data = actors[name].get("/applications" + query).json()
            assert data["total"] == 0 and data["items"] == []
    assert actors["other"].get("/applications?scope=inbox").status_code == 403
    assert actors["user"].get("/applications?scope=all").status_code == 422
    assert actors["user"].get("/applications?page=0").status_code == 422
    assert actors["user"].get("/applications?page_size=101").status_code == 422


def test_self_approval_and_head_own_cross_department(world):
    sales = world["actor"]("sales_head")
    deps = world["departments"]
    own = sales.apply(deps["销售部"]).json()
    assert sales.get("/applications").json()["total"] == 1  # 自己提交且审批，仍只有一条
    assert sales.post(f'/applications/{own["id"]}/decision', json={"decision": "approved"}).status_code == 200
    detail = sales.get(f'/applications/{own["id"]}').json()
    assert detail["reviewer_id"] == sales.user["id"] and detail["reviewed_at"]
    other = sales.apply(deps["财务部"]).json()
    assert sales.get(f'/applications/{other["id"]}').status_code == 200
    assert sales.post(f'/applications/{other["id"]}/decision', json={"decision": "approved"}).status_code == 403
    assert world["actor"]("finance_head").post(f'/applications/{other["id"]}/decision', json={"decision": "approved"}).status_code == 200


def test_rejection_reason_history_and_new_application(world):
    user, reviewer = world["actor"]("user"), world["actor"]("finance_head")
    item = user.apply(world["departments"]["财务部"]).json()
    path = f'/applications/{item["id"]}'
    for reason in (None, "", " \n "):
        assert reviewer.post(path + "/decision", json={"decision": "rejected", "reason": reason}).status_code == 422
        assert user.get(path).json()["status"] == "pending"
    assert reviewer.post(path + "/decision", json={"decision": "rejected", "reason": "预算不足"}).status_code == 200
    rejected = user.get(path).json()
    assert rejected["rejection_reason"] == "预算不足" and rejected["reviewer_name"] == "财务负责人"
    assert reviewer.post(path + "/decision", json={"decision": "approved"}).status_code == 409
    assert user.client.patch("/api" + path, json={"title": "改写"}).status_code == 405
    assert user.client.delete("/api" + path).status_code == 405
    assert user.apply(world["departments"]["财务部"]).status_code == 201
    assert user.get(path).json() == rejected


def test_admin_and_other_roles_cannot_approve(world):
    user = world["actor"]("user")
    department = world["departments"]["财务部"]
    record = user.apply(department).json()
    for username in ("admin", "user", "other", "sales_head"):
        actor = world["actor"](username)
        assert actor.post(f'/applications/{record["id"]}/decision', json={"decision": "approved"}).status_code == 403
    assert world["actor"]("admin").apply(department).status_code == 403


def test_concurrent_approval_only_one_wins(world):
    reviewer = world["actor"]("finance_head")
    item = world["actor"]("user").apply(world["departments"]["财务部"]).json()
    def decide(status):
        return reviewer.post(f'/applications/{item["id"]}/decision', json={"decision": status, "reason": "并发拒绝"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(decide, ["approved", "rejected"]))
    assert sorted(codes) == [200, 409]
    before = reviewer.get(f'/applications/{item["id"]}').json()
    assert reviewer.post(f'/applications/{item["id"]}/decision', json={"decision": "approved"}).status_code == 409
    assert reviewer.get(f'/applications/{item["id"]}').json() == before


def test_disable_user_revokes_sessions_and_keeps_history(world):
    admin, user = world["actor"]("admin"), world["actor"]("user")
    item = user.apply(world["departments"]["财务部"]).json()
    assert admin.patch(f'/users/{user.user["id"]}', json={"enabled": False}).status_code == 200
    assert user.get("/auth/me").status_code == 401
    assert user.post("/auth/login", json={"username": "user", "password": PASSWORD}).status_code == 401
    assert admin.get(f'/applications/{item["id"]}').status_code == 200
    assert admin.patch(f'/users/{user.user["id"]}', json={"enabled": True}).status_code == 200
    assert user.post("/auth/login", json={"username": "user", "password": PASSWORD}).status_code == 200
    assert admin.patch(f'/users/{world["users"]["sales_head"]}', json={"enabled": False}).status_code == 409


def test_password_change_and_admin_reset_revoke_sessions(world):
    user, admin = world["actor"]("user"), world["actor"]("admin")
    assert user.post("/auth/password", json={"old_password": "wrong", "new_password": "changed-password"}).status_code == 422
    assert user.post("/auth/password", json={"old_password": PASSWORD, "new_password": "changed-password"}).status_code == 200
    assert user.get("/auth/me").status_code == 401
    assert user.post("/auth/login", json={"username": "user", "password": PASSWORD}).status_code == 401
    changed = user.post("/auth/login", json={"username": "user", "password": "changed-password"})
    assert changed.status_code == 200
    assert admin.post(f'/users/{user.user["id"]}/reset-password', json={"new_password": "reset-password"}).status_code == 200
    assert user.get("/auth/me").status_code == 401
    assert user.post("/auth/login", json={"username": "user", "password": "changed-password"}).status_code == 401
    assert user.post("/auth/login", json={"username": "user", "password": "reset-password"}).status_code == 200


def test_restart_and_backup_restore_preserve_business_records(world, tmp_path):
    user, reviewer = world["actor"]("user"), world["actor"]("finance_head")
    item = user.apply(world["departments"]["财务部"]).json()
    path = f'/applications/{item["id"]}'
    reviewer.post(path + "/decision", json={"decision": "rejected", "reason": "请补充预算"})
    expected = user.get(path).json()
    restored = tmp_path / "restored.sqlite3"
    shutil.copy2(world["path"], restored)
    for database in (world["path"], restored):
        with TestClient(create_app(database)) as client:
            actor = Actor(client, "user")
            assert actor.get(path).json() == expected
            admin = Actor(client, "admin")
            assert len(admin.get("/users").json()["items"]) == 6
            assert len(admin.get("/departments").json()["items"]) == 4


def test_pagination_is_stable(world):
    actor = world["actor"]("user")
    for i in range(3):
        assert actor.apply(world["departments"]["财务部"], title=f"申请{i}").status_code == 201
    first = actor.get("/applications?page_size=2").json()
    second = actor.get("/applications?page_size=2&page=2").json()
    assert first["total"] == second["total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert first["items"][0]["id"] > first["items"][1]["id"] > second["items"][0]["id"]
