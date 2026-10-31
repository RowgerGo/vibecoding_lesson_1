# OA 系统验收记录

验收日期：2026 年 10 月 27 日（北京时间）。

## 结论

任务清单 T01—T16 已实现并完成本地验收。最终联合测试结果为 **31 passed，1 warning，23.24 秒**，包括 29 项 API 集成测试和 2 项本地服务／浏览器验收。测试数据库均位于临时目录，没有预置实际业务账号。

本次交付为本地项目文件，未执行 Git 提交、推送或对外部署。

## 环境与执行命令

- Python 3.14.6、SQLite 3.53.3。
- FastAPI 0.162.0、Pydantic 2.14.1、Starlette 1.10.0、Uvicorn 0.54.0。
- pytest 9.1.1、HTTPX 0.28.1、Playwright 1.64.1，浏览器使用本机 Google Chrome 的独立无头实例。

在 `oa/` 执行：

```bash
OA_BROWSER_TEST=1 OA_SCREENSHOT_DIR=docs/screenshots .venv/bin/python -m pytest -q
```

补充检查已通过：

```bash
.venv/bin/python -m compileall -q app tests
node --check app/static/app.js
.venv/bin/python -m pip check
```

第三方提示：Starlette TestClient 提示 HTTPX 适配将在未来弃用，建议后续迁移到 HTTPX2。当前锁定版本的全部测试通过，该提示未被过滤或隐藏。

## 任务证据

| 任务 | 实现位置 | 验收证据 |
| --- | --- | --- |
| T01 项目骨架 | `app/main.py`、依赖清单、`.gitignore` | 独立虚拟环境安装依赖；健康检查、HTML、JS、CSS 返回成功；语法和依赖检查通过 |
| T02 数据库 | `app/db.py` | `test_initialization_static_and_database_constraints` 验证幂等初始化、外键、唯一约束、用户部门约束和密码哈希；持久化测试验证记录保留 |
| T03 管理员初始化 | `app/cli.py`、`app/security.py` | 测试及真实服务通过相同创建入口初始化管理员；重复用户名不覆盖；命令使用隐藏密码输入 |
| T04 登录与密码 | `app/main.py` 的认证端点、前端 `localStorage` 票据 | Bearer 票据返回、无 Cookie 登录、退出、会话过期、CSRF、跨站拒绝、改密及重置后会话失效测试通过；浏览器完成改密和退出 |
| T05 部门管理 | 部门 API 与事务 | 创建、重复名、单级限制、启停、停用条件测试通过；浏览器创建部门并执行空部门启停 |
| T06 用户管理 | 用户 API、输入模型及数据库约束 | 普通用户单部门、管理员例外、不可修改身份、停用与恢复、负责人及最后管理员保护测试通过；浏览器创建用户及第二名管理员 |
| T07 指定负责人 | 负责人 API 与数据库触发器 | 本部门、启用、非管理员、仅首次指定限制及并发指定测试通过；浏览器指定后不再显示指定入口 |
| T08 审批部门 | `/api/approval-departments` | 可选列表仅返回可用部门；无负责人部门的用户可向其他部门提交；浏览器表单展示负责人 |
| T09 提交申请 | 申请创建 API 与表单 | 必填、日期、长度、目标部门校验及伪造申请人／状态／时间字段拒绝；浏览器跨部门提交成功 |
| T10 查询权限 | 共用的 `visible_condition` | 普通用户、负责人、管理员的列表／详情／统计权限、筛选、分页、重复记录检查通过 |
| T11 审批 | 审批端点、事务和条件更新 | 同意、拒绝理由必填、自审、跨部门越权拒绝、并发及重复审批测试通过；完成结果保持不变 |
| T12 公共前端 | `app/static/` | 浏览器完成登录、身份导航、退出、会话失效和密码修改；脚本内容按文本显示，页面无 JavaScript 异常；业务值均通过 `textContent` 渲染 |
| T13 业务页面 | `app/static/app.js` | 浏览器完成申请、详情、拒绝及理由回看、自审同意和状态筛选；检查桌面和手机尺寸截图 |
| T14 管理后台 | 前端部门页、用户页及管理员查询 | 浏览器完成建部门→建用户→指定负责人、查看全局、停用／启用、重置密码；普通用户手工跳转后台被限制 |
| T15 综合验收 | `tests/test_api.py`、`tests/test_browser.py` | 31 项联合测试通过；真实服务进程停止后重新启动、备份恢复均验证原数据一致 |
| T16 使用与交付 | `README.md`、本文及任务清单 | 中文启动命令、管理员创建、配置、API、测试、备份恢复及范围说明完整；文档链接检查通过 |

## 关键业务场景对照

下表对应任务清单中的 AC01—AC14。

| 场景 | 验证方式 | 结果 |
| --- | --- | --- |
| AC01 跨部门路由及可见范围 | `test_cross_department_visibility_and_scope_filters`，加真实浏览器多人身份验证 | 通过 |
| AC02 负责人自审 | `test_self_approval_and_head_own_cross_department`，加浏览器自审 | 通过 |
| AC03 负责人申请交给其他部门 | `test_self_approval_and_head_own_cross_department` | 通过 |
| AC04 拒绝理由不可为空 | `test_rejection_reason_history_and_new_application`，加浏览器空理由拦截 | 通过 |
| AC05 拒绝结果、原单不可编辑、重新发起 | `test_rejection_reason_history_and_new_application`，加浏览器申请人查看理由 | 通过 |
| AC06 所属部门无负责人仍可跨部门申请 | `test_approval_department_options_and_headless_home` | 通过 |
| AC07 越权详情与查询统计 | `test_cross_department_visibility_and_scope_filters` | 通过 |
| AC08 管理员只管理和查看 | `test_admin_and_other_roles_cannot_approve`，加浏览器无申请入口 | 通过 |
| AC09 停用与历史保留 | `test_disable_user_revokes_sessions_and_keeps_history`，加浏览器停用后重新登录页 | 通过 |
| AC10 禁止停用负责人、调部门、更换负责人 | 用户和负责人管理测试，严格请求模型及数据库不可变约束，浏览器负责人停用失败 | 通过 |
| AC11 并发审批 | `test_concurrent_approval_only_one_wins` | 通过 |
| AC12 有成员或待审核申请不能停用部门 | `test_department_creation_and_disable` 验证有启用成员时拒绝；实现同时查询目标部门待审核申请并拒绝停用 | 通过 |
| AC13 合规停用空部门 | 部门 API 测试及浏览器启停空部门 | 通过 |
| AC14 重启后记录持久性 | `test_restart_and_backup_restore_preserve_business_records` 与 `test_real_process_restart_and_backup_restore` | 通过 |

## 页面证据

截图由最终通过的真实浏览器测试生成，使用隔离验收数据，已检查桌面布局及手机布局。手机下表格在表格容器内横向滚动。

- [管理员部门页](screenshots/admin-departments.png)
- [用户工作台](screenshots/member-dashboard.png)
- [负责人审批列表](screenshots/approval-dashboard.png)
- [手机审批列表](screenshots/mobile-inbox.png)

## 已确认的范围限制

不提供调部门、更换负责人、交接、草稿、撤回、提交后修改、多级审批、公开注册和找回密码。现任负责人不能停用。这些是已确认的第一版范围，不是未完成任务。

首次实际使用仍需按 README 创建自己的系统管理员；测试账号仅存在于自动化测试临时数据库，不作为业务账号交付。
