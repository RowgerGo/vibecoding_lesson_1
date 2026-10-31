# 伯乐直聘

一个本地运行的招聘平台：Python FastAPI 提供 API 和页面，原生 HTML / CSS / JavaScript 通过 API 交互，SQLite 与简历文件保存在本地。

支持求职者、公司和管理员三种角色，覆盖岗位目录维护、招聘发布、PDF / Word 简历投递、专属邀请链接和免登录预约。

## 安装与启动

### Docker Compose 部署

服务器安装 Docker 和 Docker Compose 后，在 `bl-zhipin/` 目录执行：

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/api/health
```

默认通过 `http://服务器地址:8000` 访问，SQLite 数据库和简历保存在 Docker named volume `bl_zhipin_data` 中。可通过 `.env` 覆盖端口和邀请链接：

```dotenv
BL_PORT=8000
BL_PUBLIC_URL=http://服务器地址:8000
BL_SECURE_COOKIE=0
```

如果前面使用 Nginx 或其他反向代理提供 HTTPS，应将 `BL_PUBLIC_URL` 设置为浏览器实际访问的 HTTPS 地址，并将 `BL_SECURE_COOKIE=1`；代理需要转发 `Host`、`X-Forwarded-Host` 和 `X-Forwarded-Proto`。

查看日志使用 `docker compose logs -f bl-zhipin`，停止服务使用 `docker compose down`。不要使用 `docker compose down -v`，否则会删除数据库和简历。

建议使用 Python 3.13。项目使用的依赖版本固定在 `requirements.txt`，其中包含验收测试工具。

在仓库根目录执行：

```bash
cd bl-zhipin
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Windows 激活虚拟环境时，使用 `.venv\Scripts\activate` 替代 `source` 命令。

打开 [本地首页](http://127.0.0.1:8000)。服务同时提供 HTML 页面、静态资源和 `/api/` 接口，无需单独启动前端服务。停止服务使用 `Ctrl+C`。

如果安装了 `uv`，也可以用 `uv venv .venv --python 3.13` 和 `uv pip install --python .venv/bin/python -r requirements.txt` 创建环境和安装依赖。

## 创建管理员

在 `bl-zhipin/` 中、虚拟环境已激活时执行：

```bash
python -m app.cli create-admin --username admin
```

按提示两次输入 8～128 个字符的密码。输入不回显；重复用户名会报错，不覆盖已有账号。项目不提供默认管理员和默认密码。

管理员登录后进入岗位管理页面，先新增岗位；公司才能从目录选择岗位发布招聘。公开注册页面仅支持公司和求职者，注册后角色固定。

## 完整使用流程

1. 创建管理员，登录后新增岗位，例如“Python 开发工程师”。
2. 退出管理员，注册公司账号，填写唯一公司名称，登录公司工作台。
3. 发布招聘，选择岗位并填写岗位介绍、联系邮箱。
4. 退出公司账号，注册求职者账号，在首页搜索并打开招聘详情。
5. 填写姓名、联系邮箱、可选手机号，上传 PDF、DOC 或 DOCX 简历。单文件最大 10 MB，即 10,000,000 字节；同一条招聘只能投递一次，提交后不能修改或撤回。
6. 公司在“收到的简历”中打开投递详情、下载简历，生成邀请链接。打开详情会把投递标记为“已查看”。
7. 求职者在“我的投递”查看邀请；公司也可以复制链接自行发送。平台不自动发送邮件或短信。
8. 无需登录即可打开邀请，填写姓名、手机号和未来的预约时间。时间统一按北京时间解释，提交即预约成功；公司在“预约安排”、求职者在“我的投递”查看结果。

手机号支持 7～15 位数字及可选国家区号；输入中的空格、括号和短横线会被标准化。姓名和预约手机号可以与原投递资料不同，原始投递快照始终保留。

公司只能查看投给自己的简历和预约，求职者只能查看自己的投递。管理员只维护岗位目录，无权读取简历。访客可浏览开放招聘和联系邮箱。

## 招聘与邀请规则

- 公司名称、岗位名称去除首尾空格并忽略英文大小写后必须唯一。公司注册不验证资质，因此公司名称唯一不代表公司身份已经核验。
- 岗位改名会同步到关联招聘；停用岗位不能用于新招聘，已有招聘和投递保留。
- 招聘可以编辑、关闭、重新开放，不提供删除。关闭时停止新投递，已有投递和预约邀请保留。
- 邀请状态为“待预约、已预约、已失效、已撤销”，与“已投递、已查看”的投递状态分别展示。
- 邀请从生成时起 7 天有效，只能成功预约一次；公司可以撤销尚未使用的邀请，在失效或撤销后重新生成。旧链接保持无效。
- 待预约邀请重复生成时返回当前链接；已经预约后不能再次生成邀请。
- 求职者自由选择未来时间，不设可预约时段，不限制同一时间的预约人数，由公司协调安排。
- 邀请链接的持有人具有填写权限，无需登录。公开表单不展示既有个人资料或简历；已使用链接不公开预约中的个人资料。

## 本地数据与配置

默认数据路径固定在项目目录内，不随启动命令的当前工作目录变化：

```text
bl-zhipin/
├── app/                     # 后端与管理命令
├── static/                  # HTML、CSS、JavaScript
├── data/                    # 首次启动时自动创建，Git 忽略
│   ├── platform.sqlite3     # SQLite 数据库，可能附带 WAL/SHM 文件
│   └── uploads/             # 私有简历文件，随机文件名
├── tests/                   # 集成测试与虚构简历样本
└── docs/                    # 需求、任务、决策及验收记录
```

重启服务会保留数据。备份时先停止服务，再整体复制 `data/`，数据库与简历目录需一起保存。数据库及上传文件不通过静态资源公开，下载接口校验公司归属。

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `BL_DATA_DIR` | 数据库存储与简历目录，建议使用绝对路径 | 项目内 `data/` |
| `BL_PUBLIC_URL` | 公司复制的邀请链接使用的完整服务地址 | 当前请求的访问地址 |
| `BL_SECURE_COOKIE` | 通过 HTTPS 访问时设为 `1`，启用 Secure 会话 Cookie | `0`，用于本地 HTTP |

初始化管理员与启动服务时，应使用相同的 `BL_DATA_DIR`。

本机的 `127.0.0.1` 和 `localhost` 地址只供本机访问。如果需要在同一局域网的另一台设备打开邀请链接，应使用运行服务主机的局域网地址，例如：

```bash
BL_PUBLIC_URL=http://192.168.1.10:8000 python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

将示例 IP 替换为本机实际地址，其他设备须能连接该地址和端口；服务也须保持运行。该命令仅用于本地网络使用，不涉及公网部署。

## 验收测试

在 `bl-zhipin/`、虚拟环境已激活时执行：

```bash
python -m pytest -q
node --check static/app.js
```

Python 测试使用临时数据库和上传目录，不连接默认 `data/`。Word 样本已经保存为真实 DOC、DOCX 文件，运行测试无需 macOS 或 Word 软件。

测试覆盖注册唯一性、角色和资源权限、招聘开关、简历格式与大小、重复和同时投递、私有下载、邀请 7 天边界、撤销重发、重复和同时预约、北京时间转换、相同时段多预约及服务重建后的持久化。

浏览器人工验收过程和任务对应证据见 [验收记录](docs/verification.md)，功能范围见 [需求文档](docs/requirements.md)，开发进度见 [任务清单](docs/tasks.md)。

## 主要 API

写操作使用 JSON，简历投递使用 `multipart/form-data`。登录返回会话 Cookie，`GET /api/auth/me` 返回当前账号与 CSRF 凭证；登录后的写请求应携带 `X-CSRF-Token`。公开邀请预约无需账号或会话。

完整接口契约由 `GET /api/openapi.json` 提供，无需加载外部 CDN 资源。

| 模块 | 接口示例 |
| --- | --- |
| 账号 | `POST /api/auth/register`、`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me` |
| 岗位 | `GET /api/positions`、`GET/POST /api/admin/positions`、`PUT /api/admin/positions/{id}` |
| 公开招聘 | `GET /api/jobs?q=Python&position_id=1`、`GET /api/jobs/{id}` |
| 公司招聘 | `GET/POST /api/company/jobs`、`PUT /api/company/jobs/{id}`、`PATCH /api/company/jobs/{id}/state` |
| 简历投递 | `POST /api/jobs/{id}/applications`，字段为 `name`、`email_address`、`phone_number`、`resume` |
| 求职者记录 | `GET /api/seeker/applications`、`GET /api/seeker/applications/{id}` |
| 公司投递 | `GET /api/company/applications`、`GET /api/company/applications/{id}`、`POST /api/company/applications/{id}/viewed` |
| 私有下载 | `GET /api/company/applications/{id}/resume` |
| 邀请管理 | `POST /api/company/applications/{id}/invitation`、`POST /api/company/invitations/{id}/revoke` |
| 公开预约 | `GET /api/invitations/{token}`、`POST /api/invitations/{token}/appointments`，字段为 `name`、`phone`、`scheduled_at` |
| 公司预约 | `GET /api/company/appointments`、`GET /api/company/appointments/{id}` |

输入错误返回 422，文件超限返回 413，未登录返回 401，角色或请求验证失败返回 403，不存在或无归属的记录返回 404，重复或状态冲突返回 409；错误 JSON 中的 `message` 为中文提示。
