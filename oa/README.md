# 行知 OA

一个本地运行的办公申请与审批系统。后端使用 Python FastAPI，前端使用原生 HTML、CSS、JavaScript，通过同源 JSON API 交互，数据保存到 SQLite。

## 本地启动

需要 Python 3.11 或更高版本。当前验证环境为 Python 3.14.6。以下命令在项目的 `oa/` 目录执行。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.cli init
python -m app.cli create-admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

管理员创建命令会提示输入用户名、姓名和密码，密码不会回显。用户名为 1—40 位字母、数字、下划线、点或短横线，密码长度为 8—128 位。没有预置账号或默认密码；同名账号不会被覆盖。

浏览器打开 [本地 OA](http://127.0.0.1:8000)，使用刚创建的账号登录。关闭服务时在终端按 `Ctrl+C`。

服务首次启动也会自动创建缺失的数据库表，重复初始化不会清空已有数据。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OA_DB_PATH` | `oa/data/oa.sqlite3`，相对项目文件位置确定 | SQLite 文件路径，可使用绝对路径；默认不受启动目录影响 |
| `OA_SESSION_HOURS` | `12` | 会话有效小时数 |
| `OA_COOKIE_SECURE` | 未设置 | 通过 HTTPS 使用时设为 `1`，让会话 Cookie 仅经 HTTPS 发送；本机 HTTP 保持默认 |
| `OA_PUBLIC_ORIGIN` | 未设置 | HTTPS 反向代理部署时填写浏览器访问的完整来源，例如 `https://oa.1024web.cn`，用于登录写请求的来源校验 |

示例：

```bash
export OA_DB_PATH="$PWD/data/team.sqlite3"
export OA_PUBLIC_ORIGIN="https://oa.1024web.cn"
export OA_COOKIE_SECURE=1
python -m app.cli init
python -m app.cli create-admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

初始化、创建管理员、启动服务和维护数据库时应使用同一配置。小团队内网使用可将监听地址改为 `0.0.0.0`，通过部署机器的内网地址访问。

## 操作流程

### 系统管理员

1. 在“部门管理”创建单级部门。
2. 在“用户管理”创建用户，为普通用户指定唯一所属部门，也可创建其他系统管理员。
3. 回到“部门管理”，从本部门启用的普通用户中首次指定一名负责人。
4. 在“全部申请”查看全局申请及审批记录。
5. 根据需要启停普通用户或重置他人密码。系统管理员自身通过“账户设置”修改密码。

现任负责人不能停用，最后一个启用的系统管理员也不能停用。部门存在启用用户或接收的待审核申请时不能停用。界面会显示具体限制原因。

### 普通用户

1. 点击“发起申请”，填写事项日期、标题、内容并选择审批部门。
2. 可选部门覆盖所有启用且有负责人的部门，与自己的所属部门无关。
3. 在“我的申请”查看状态、审批人、审批时间和拒绝理由。
4. 被拒绝后可以另发新申请，原申请记录保留。

### 部门负责人

- 具备普通用户的申请能力。
- 在“部门审批”处理指定本部门审批的申请，可以同意或拒绝；拒绝理由必填。
- 可以审批自己提交给本部门的申请。
- 可以查看自己的申请和指定本部门审批的申请；本部门成员提交给其他部门的申请，不因此对自己可见。

系统管理员只负责管理和查看，不提交申请、不参与审批。审批完成后结果不可覆盖，申请提交后不可编辑、撤回或删除。所有时间戳由后端生成，页面以北京时间显示；事项日期由申请人填写。

## 测试

安装开发依赖后运行 API 集成测试：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q -m "not browser"
```

真实浏览器验收默认使用本机 Google Chrome，独立启动无头浏览器与本地测试服务，不使用个人浏览器资料和实际业务数据库：

```bash
OA_BROWSER_TEST=1 python -m pytest -q -m browser
```

也可安装 Playwright Chromium 并切换浏览器：

```bash
python -m playwright install chromium
OA_BROWSER_TEST=1 OA_BROWSER_CHANNEL=chromium python -m pytest -q -m browser
```

截图默认保存到 pytest 临时目录；指定 `OA_SCREENSHOT_DIR=test-results/screenshots` 可保存在项目忽略目录中。数据库均为每次测试独立创建；测试账号密码仅用于隔离测试环境。

实际测试结果与证据见 [验收记录](docs/verification.md)，任务状态见 [任务清单](docs/tasks.md)。

## 数据备份与恢复

以下步骤针对默认数据库路径。若设置了 `OA_DB_PATH`，请替换为实际路径。

1. 按 `Ctrl+C` 停止全部 OA 服务进程，确保不再写入数据库。
2. 备份 SQLite 文件：

   ```bash
   mkdir -p data/backups
   cp data/oa.sqlite3 data/backups/oa-backup.sqlite3
   ```

3. 恢复时同样先停止服务，保留现有数据库副本，再复制备份：

   ```bash
   cp data/oa.sqlite3 data/oa-before-restore.sqlite3
   cp data/backups/oa-backup.sqlite3 data/oa.sqlite3
   ```

4. 使用原配置重新启动服务，登录后检查部门、用户、申请及审批结果。

当前连接使用 SQLite 默认日志模式，停止全部进程后复制数据库文件即可。备份含账号密码哈希、业务数据和会话记录，按与原数据库相同方式保管。数据目录已加入 Git 忽略规则。

## 项目结构

```text
oa/
├── app/
│   ├── cli.py          # 数据库初始化和管理员创建
│   ├── db.py           # 表结构、事务及数据库约束
│   ├── main.py         # API、鉴权、业务规则及页面服务
│   ├── schemas.py      # 请求模型和字段验证
│   ├── security.py     # 密码哈希与会话令牌
│   └── static/         # HTML、CSS、JavaScript
├── tests/              # API 集成和真实浏览器测试
├── docs/               # 需求、任务与验收证据
├── GLOSSARY.md
├── requirements.txt
└── requirements-dev.txt
```

## API 约定

请求和响应使用 JSON。错误响应统一为 `{"error":{"code":422,"message":"说明"}}`，参数校验错误另带字段列表。未登录为 401，无权限为 403，不存在或无权查看的申请详情为 404，业务冲突为 409，输入不合法为 422。

登录成功后，API 返回 `access_token` 和 `csrf_token`。前端将两者保存在浏览器 `localStorage` 的 `oa_auth` 项中，后续请求使用 `Authorization: Bearer <access_token>` 和 `X-CSRF-Token` 请求头；`GET /api/auth/me` 可恢复当前身份。页面请求不携带 Cookie，退出登录或会话失效时会清理本地票据。密码修改、重置、账号停用会使该用户已有会话失效。页面和 API 同源部署。

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/auth/login` | 登录 |
| GET | `/api/auth/me` | 当前用户和 CSRF 令牌 |
| POST | `/api/auth/logout` | 退出 |
| POST | `/api/auth/password` | 修改自己的密码 |
| GET / POST | `/api/departments` | 管理员查询 / 创建部门 |
| PATCH | `/api/departments/{id}` | 管理员启停部门 |
| PUT | `/api/departments/{id}/head` | 管理员首次指定负责人 |
| GET / POST | `/api/users` | 管理员查询 / 创建用户 |
| PATCH | `/api/users/{id}` | 管理员启停用户 |
| POST | `/api/users/{id}/reset-password` | 管理员重置他人密码 |
| GET | `/api/approval-departments` | 查询可选审批部门 |
| POST | `/api/applications` | 提交申请 |
| GET | `/api/applications` | 分页查询，支持 `scope`、`status`、`page`、`page_size` |
| GET | `/api/applications/{id}` | 按权限查看详情 |
| POST | `/api/applications/{id}/decision` | 同意或拒绝 |

`scope` 为 `visible`（当前身份可见）、`mine`（本人提交）或 `inbox`（负责人接收）；状态为 `pending`、`approved`、`rejected`；`page_size` 为 1—100，默认 10。未知请求体字段会被拒绝，不能伪造申请人、提交时间或审批结果。

## 第一版范围

不包含调部门、更换负责人、交接、草稿、撤回、提交后修改、多级审批、公开注册、手机号、邮箱及找回密码。需求依据见 [需求文档](docs/requirements.md)，核心业务词汇见 [术语表](GLOSSARY.md)。

框架用法参照 [FastAPI 测试文档](https://fastapi.tiangolo.com/tutorial/testing/)及 [Lifespan 文档](https://fastapi.tiangolo.com/advanced/events/)。
