"""真实浏览器验收：OA_BROWSER_TEST=1 python -m pytest -m browser -q。"""

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

import pytest

from app.cli import create_admin
from conftest import PASSWORD

pytestmark = [pytest.mark.browser, pytest.mark.skipif(os.getenv("OA_BROWSER_TEST") != "1", reason="设置 OA_BROWSER_TEST=1 启用真实浏览器验收")]


@pytest.fixture
def running_server(tmp_path):
    database = tmp_path / "browser.sqlite3"
    create_admin(database, "admin", "验收管理员", PASSWORD)
    with serve(database, tmp_path) as base:
        yield base


@contextmanager
def serve(database, tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "OA_DB_PATH": str(database)}
    with (tmp_path / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=Path(__file__).resolve().parents[1], env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError((tmp_path / "server.log").read_text())
                try:
                    with urlopen(base + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("验收服务启动超时")
            yield base
        finally:
            server.terminate()
            server.wait(timeout=10)


def test_complete_browser_workflow(running_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    screenshots = Path(os.getenv("OA_SCREENSHOT_DIR", str(tmp_path / "screenshots")))
    screenshots.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.getenv("OA_BROWSER_CHANNEL", "chrome"), headless=True)
        contexts = []

        def login(username):
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            contexts.append(context)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(running_server)
            page.get_by_label("用户名", exact=True).fill(username)
            page.get_by_label("密码", exact=True).fill(PASSWORD)
            page.get_by_role("button", name="登录 →", exact=True).click()
            expect(page.get_by_role("heading", name="最近申请")).to_be_visible()
            return page

        def toast(page, text):
            expect(page.locator("#toast")).to_contain_text(text)

        def create_department(page, name):
            page.get_by_role("button", name="＋ 创建部门", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_label("部门名称").fill(name)
            dialog.get_by_role("button", name="创建部门", exact=True).click()
            expect(dialog).not_to_be_visible()
            expect(page.get_by_role("cell", name=name, exact=True)).to_be_visible()

        def create_user(page, username, name, department, admin=False):
            page.get_by_role("button", name="＋ 创建用户", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_label("用户名", exact=True).fill(username)
            dialog.get_by_label("姓名", exact=True).fill(name)
            dialog.get_by_label("初始密码").fill(PASSWORD)
            dialog.get_by_label("角色", exact=True).select_option("true" if admin else "false")
            if department:
                dialog.get_by_label("所属部门", exact=True).select_option(label=department)
            dialog.get_by_role("button", name="创建用户", exact=True).click()
            expect(dialog).not_to_be_visible()
            expect(page.get_by_text(username, exact=True)).to_be_visible()

        def apply(page, title, department, content="申请购买日常办公用品。"):
            page.get_by_role("button", name="＋ 发起申请", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_label("事项日期").fill("2026-10-30")
            dialog.get_by_label("审批部门", exact=True).select_option(label=department)
            dialog.get_by_label("标题", exact=True).fill(title)
            dialog.get_by_label("申请内容").fill(content)
            dialog.get_by_role("button", name="提交申请", exact=True).click()
            expect(dialog.get_by_role("heading", name=title, exact=True)).to_be_visible()
            return dialog

        try:
            admin = login("admin")
            admin.get_by_role("link", name="部门管理", exact=True).click()
            for name in ("销售部", "财务部", "空部门"):
                create_department(admin, name)
            admin.get_by_role("link", name="用户管理", exact=True).click()
            for username, name, department in [("sales", "销售负责人", "销售部"), ("finance", "财务负责人", "财务部"), ("member", "销售成员", "销售部"), ("observer", "旁观成员", "销售部")]:
                create_user(admin, username, name, department)
            create_user(admin, "second_admin", "第二管理员", None, admin=True)
            admin.get_by_role("link", name="部门管理", exact=True).click()
            for department, head in [("销售部", "销售负责人（sales）"), ("财务部", "财务负责人（finance）")]:
                target = admin.get_by_role("row").filter(has=admin.get_by_role("cell", name=department, exact=True))
                target.get_by_role("button", name="指定负责人", exact=True).click()
                dialog = admin.get_by_role("dialog")
                dialog.get_by_label("负责人", exact=True).select_option(label=head)
                dialog.get_by_role("button", name="确认指定").click()
                expect(dialog).not_to_be_visible()
                expect(target.get_by_role("button", name="指定负责人", exact=True)).to_have_count(0)
            empty_department = admin.get_by_role("row").filter(has=admin.get_by_role("cell", name="空部门", exact=True))
            empty_department.get_by_role("button", name="停用", exact=True).click()
            expect(empty_department.get_by_text("已停用")).to_be_visible()
            empty_department.get_by_role("button", name="启用", exact=True).click()
            expect(empty_department.get_by_text("已启用")).to_be_visible()
            expect(admin.locator("#toast")).to_be_hidden(timeout=6000)
            admin.screenshot(path=str(screenshots / "admin-departments.png"), full_page=True)

            member, finance, sales, observer = [login(name) for name in ("member", "finance", "sales", "observer")]
            content = '<script>window.oaXss=true</script> 申请购买办公用品。'
            dialog = apply(member, "跨部门采购申请", "财务部", content)
            expect(dialog.get_by_text(content, exact=True)).to_be_visible()
            assert member.evaluate("window.oaXss") is None
            member.get_by_role("button", name="关闭弹窗").click()
            sales.get_by_role("link", name="部门审批", exact=True).click()
            expect(sales.get_by_text("跨部门采购申请", exact=True)).to_have_count(0)
            observer.get_by_role("link", name="我的申请", exact=True).click()
            expect(observer.get_by_text("跨部门采购申请", exact=True)).to_have_count(0)
            finance.get_by_role("link", name="部门审批", exact=True).click()
            finance.get_by_role("row").filter(has_text="跨部门采购申请").get_by_role("button", name="查看详情 →").click()
            finance.get_by_role("button", name="拒绝申请", exact=True).click()
            toast(finance, "拒绝申请必须填写理由")
            finance.get_by_label("拒绝理由", exact=True).fill("请补充预算明细")
            finance.get_by_role("button", name="拒绝申请", exact=True).click()
            dialog = finance.get_by_role("dialog")
            expect(dialog.get_by_text("请补充预算明细", exact=True)).to_be_visible()
            expect(dialog.get_by_role("button", name="同意申请")).to_have_count(0)
            finance.get_by_role("button", name="关闭弹窗").click()
            member.reload()
            member.get_by_role("row").filter(has_text="跨部门采购申请").get_by_role("button", name="查看详情 →").click()
            expect(member.get_by_role("dialog").get_by_text("请补充预算明细", exact=True)).to_be_visible()
            member.get_by_role("button", name="关闭弹窗").click()

            dialog = apply(finance, "负责人自审申请", "财务部")
            dialog.get_by_role("button", name="同意申请", exact=True).click()
            expect(dialog.get_by_text("已同意", exact=True)).to_be_visible()
            expect(dialog.get_by_role("button", name="同意申请")).to_have_count(0)
            finance.get_by_role("button", name="关闭弹窗").click()
            expect(finance.locator("#toast")).to_be_hidden(timeout=6000)
            finance.screenshot(path=str(screenshots / "approval-dashboard.png"), full_page=True)
            member.screenshot(path=str(screenshots / "member-dashboard.png"), full_page=True)
            admin.get_by_role("link", name="全部申请", exact=True).click()
            expect(admin.get_by_text("跨部门采购申请", exact=True)).to_be_visible()
            expect(admin.get_by_text("负责人自审申请", exact=True)).to_be_visible()
            expect(admin.get_by_role("button", name="＋ 发起申请")).to_have_count(0)

            # 管理限制与用户停用、重新启用、重置密码。
            admin.get_by_role("link", name="用户管理", exact=True).click()
            head_row = admin.get_by_role("row").filter(has=admin.get_by_text("sales", exact=True))
            head_row.get_by_role("button", name="停用", exact=True).click()
            toast(admin, "现任部门负责人暂时不能停用")
            member_row = admin.get_by_role("row").filter(has=admin.get_by_text("member", exact=True))
            member_row.get_by_role("button", name="停用", exact=True).click()
            expect(member_row.get_by_text("已停用")).to_be_visible()
            member.reload()
            expect(member.get_by_role("heading", name="登录工作空间")).to_be_visible()
            member_row.get_by_role("button", name="启用", exact=True).click()
            expect(member_row.get_by_text("已启用")).to_be_visible()
            member_row.get_by_role("button", name="重置密码", exact=True).click()
            dialog = admin.get_by_role("dialog")
            dialog.get_by_label("新密码", exact=True).fill("browser-reset-password")
            dialog.get_by_role("button", name="确认重置").click()
            expect(dialog).not_to_be_visible()
            member.get_by_label("用户名", exact=True).fill("member")
            member.get_by_label("密码", exact=True).fill("browser-reset-password")
            member.get_by_role("button", name="登录 →", exact=True).click()
            expect(member.get_by_role("heading", name="最近申请")).to_be_visible()

            # 普通用户手工跳转后台无法获取管理界面；账户设置与退出。
            member.goto(running_server + "/#users")
            expect(member.get_by_role("heading", name="最近申请")).to_be_visible()
            expect(member.get_by_role("button", name="＋ 创建用户")).to_have_count(0)
            member.get_by_role("link", name="账户设置", exact=True).click()
            member.get_by_label("原密码", exact=True).fill("browser-reset-password")
            member.get_by_label("新密码", exact=True).fill("browser-changed-password")
            member.get_by_role("button", name="修改密码", exact=True).click()
            expect(member.get_by_role("heading", name="登录工作空间")).to_be_visible()
            member.get_by_label("用户名", exact=True).fill("member")
            member.get_by_label("密码", exact=True).fill("browser-changed-password")
            member.get_by_role("button", name="登录 →", exact=True).click()
            expect(member.get_by_role("heading", name="账户设置", exact=True)).to_be_visible()
            member.get_by_role("button", name="退出登录", exact=True).click()
            expect(member.get_by_role("heading", name="登录工作空间")).to_be_visible()

            # 手机尺寸布局与分页/状态筛选。
            finance.set_viewport_size({"width": 390, "height": 844})
            finance.get_by_role("link", name="部门审批", exact=True).click()
            finance.get_by_label("筛选申请状态").select_option("approved")
            expect(finance.locator("#main").get_by_text("负责人自审申请", exact=True)).to_be_visible()
            expect(finance.locator("#main").get_by_text("跨部门采购申请", exact=True)).to_have_count(0)
            finance.screenshot(path=str(screenshots / "mobile-inbox.png"), full_page=True)
            assert not errors, errors
        finally:
            for context in contexts:
                context.close()
            browser.close()


def test_real_process_restart_and_backup_restore(tmp_path):
    import shutil
    import httpx

    database = tmp_path / "persistent.sqlite3"
    create_admin(database, "admin", "持久化验收管理员", PASSWORD)
    with serve(database, tmp_path) as base, httpx.Client(base_url=base) as client:
        result = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD}).json()
        client.headers["X-CSRF-Token"] = result["csrf_token"]
        department = client.post("/api/departments", json={"name": "持久化部门"}).json()["id"]
        user = client.post("/api/users", json={"username": "reviewer", "name": "持久化负责人", "password": PASSWORD, "department_id": department}).json()["id"]
        assert client.put(f"/api/departments/{department}/head", json={"user_id": user}).status_code == 200
        result = client.post("/api/auth/login", json={"username": "reviewer", "password": PASSWORD}).json()
        client.headers["X-CSRF-Token"] = result["csrf_token"]
        created = client.post("/api/applications", json={"title": "重启与恢复验收", "content": "测试原始内容", "event_date": "2026-10-30", "approval_department_id": department})
        assert created.status_code == 201
        application_id = created.json()["id"]
        assert client.post(f"/api/applications/{application_id}/decision", json={"decision": "rejected", "reason": "备份验收理由"}).status_code == 200
        expected = client.get(f"/api/applications/{application_id}").json()
    # 所有服务进程已停止，按 README 说明复制数据库备份并恢复到另一文件。
    backup = tmp_path / "oa-backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    shutil.copy2(database, backup)
    shutil.copy2(backup, restored)
    for source in (database, restored):
        with serve(source, tmp_path) as base, httpx.Client(base_url=base) as client:
            result = client.post("/api/auth/login", json={"username": "reviewer", "password": PASSWORD})
            assert result.status_code == 200
            assert client.get(f"/api/applications/{application_id}").json() == expected
            client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
            assert len(client.get("/api/users").json()["items"]) == 2
            assert client.get("/api/departments").json()["items"][0]["head_user_id"] == user
