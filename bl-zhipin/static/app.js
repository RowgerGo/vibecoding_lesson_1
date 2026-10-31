/* 原生 HTML + fetch；所有动态文本均转义，业务权限由 API 决定。 */
"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const all = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ACCESS_TOKEN_KEY = "bl_access_token";
const date = stamp => stamp == null ? "—" : new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(stamp * 1000));
const badge = (text, kind = "") => `<span class="tag ${kind}">${esc(text)}</span>`;
const statusBadge = status => badge(status, status === "已预约" || status === "已查看" ? "green" : status === "已撤销" || status === "已失效" ? "gray" : "");
const errorBox = '<p class="form-error" role="alert" data-error></p>';
let user = null;
let toastTimer;

function toast(message) {
  const element = $("#toast"); element.textContent = message; element.classList.add("visible");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => element.classList.remove("visible"), 4500);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json"); options.body = JSON.stringify(options.body);
  }
  let response;
  try { response = await fetch(`/api${path}`, {...options, headers, credentials:"omit"}); }
  catch { throw new Error("网络连接失败，请检查服务是否运行后重试"); }
  let data;
  try { data = await response.json(); } catch { throw new Error("服务响应异常，请稍后重试"); }
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      user = null;
      nav();
    }
    const error = new Error(data.message || "操作失败，请重试"); error.status = response.status; throw error;
  }
  return data;
}

function form(id, handler) {
  const element = $(id);
  element.addEventListener("submit", async event => {
    event.preventDefault();
    const button = event.submitter || $('button[type="submit"]', element);
    const label = button.textContent;
    const feedback = $("[data-error]", element); feedback.textContent = "";
    button.disabled = true; button.textContent = "提交中…";
    try { await handler(new FormData(element), element); }
    catch (error) { feedback.textContent = error.message; }
    finally { button.disabled = false; button.textContent = label; }
  });
}

function action(button, handler) {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try { await handler(); } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  });
}

function empty(title, detail, link = "", label = "") {
  return `<div class="empty"><span class="empty-icon" aria-hidden="true">↗</span><h3>${esc(title)}</h3><p>${esc(detail)}</p>${link ? `<a class="btn light" href="${esc(link)}">${esc(label)}</a>` : ""}</div>`;
}

function shell(content) { $("#main").innerHTML = content; }
function needRole(role) {
  if (user?.role === role) return true;
  shell(`<div class="container">${empty(user ? "当前账号无法访问此页面" : "登录后继续", user ? "请使用对应角色账号登录。" : "你的资料与记录将得到妥善保存。", user ? "/" : `/login?next=${encodeURIComponent(location.pathname)}`, user ? "返回首页" : "前往登录")}</div>`);
  return false;
}

function nav() {
  const roleLink = user?.role === "company" ? '<a href="/company">公司工作台</a>' : user?.role === "seeker" ? '<a href="/applications">我的投递</a>' : user?.role === "admin" ? '<a href="/admin">岗位管理</a>' : "";
  $("#nav").innerHTML = `<a href="/" ${location.pathname === "/" ? 'class="active"' : ""}>发现机会</a>${roleLink}${user ? `<span class="user-pill" title="${esc(user.company_name || user.username)}">${esc(user.company_name || user.username)}</span><button class="text-button" id="logout">退出</button>` : '<a href="/login">登录</a><a class="btn small" href="/register">免费注册 ↗</a>'}`;
  if (user) action($("#logout"), async () => {
    try { await api("/auth/logout", {method:"POST"}); }
    finally { localStorage.removeItem(ACCESS_TOKEN_KEY); location.href = "/"; }
  });
}

const steps = `<div class="step"><span>01</span><div><strong>发现合适的机会</strong><p>浏览真实招聘，与值得奔赴的公司相遇。</p></div></div><div class="step"><span>02</span><div><strong>让简历替你说话</strong><p>上传 PDF 或 Word，迈出下一步。</p></div></div><div class="step"><span>03</span><div><strong>赴一场新的可能</strong><p>收到公司邀请，预约你的见面时间。</p></div></div>`;

async function home() {
  const params = new URLSearchParams(location.search);
  const [jobs, positions] = await Promise.all([api(`/jobs?${params}`), api("/positions")]);
  const options = new Map(positions.map(p => [p.id, p.name]));
  jobs.forEach(j => options.set(j.position_id, j.position_name));
  shell(`<section class="hero"><div class="hero-inner"><div><div class="eyebrow"><span class="dot"></span> 每一份热爱，都值得被看见</div><h1>下一份热爱，<br><span>在这里发生。</span></h1><p>连接优秀的你，与值得奔赴的机会。<br>从一次投递开始，找到属于你的下一站。</p></div><div class="hero-art" aria-hidden="true"><div class="orbit"></div><div class="center-symbol"><span>B.</span></div><div class="float-card one"><i>↗</i><div><strong>新的机会，正在发生</strong><span class="muted">让每一步，都更接近理想</span></div></div><div class="float-card two"><i>✓</i><div><strong>你好，未来的同事</strong><span class="muted">从一次相遇，到共同成长</span></div></div><span class="art-label">FIND YOUR NEXT CHAPTER</span></div></div></section>
  <div class="container"><form class="search-bar" action="/" method="get" role="search"><input name="q" aria-label="搜索岗位、公司或关键词" placeholder="搜索岗位、公司或关键词" value="${esc(params.get("q") || "")}" maxlength="200"><select name="position_id" aria-label="筛选岗位"><option value="">全部岗位</option>${[...options].map(([id,name]) => `<option value="${id}" ${String(id) === params.get("position_id") ? "selected" : ""}>${esc(name)}</option>`).join("")}</select><button class="btn" type="submit">搜索机会 ↗</button></form><p class="filter-label">清晰的岗位信息 · 便捷的简历投递 · 直接的预约邀请 ${location.search ? '<a href="/">清空筛选</a>' : ""}</p>
  <div class="section-top"><div><p class="eyebrow">OPPORTUNITIES</p><h2>发现新的可能</h2></div><span class="count-label">找到 <strong>${jobs.length}</strong> 个机会</span></div><div class="jobs-layout"><div class="job-list">${jobs.length ? jobs.map(j => `<article class="job-card"><div><h3><a href="/jobs/${j.id}">${esc(j.position_name)}</a></h3><div class="company-line"><span class="company-icon">${esc(j.company_name.slice(0,1))}</span>${esc(j.company_name)}</div><p class="description">${esc(j.description)}</p></div><div class="job-side">${badge("正在招聘", "green")}<a class="btn light small" href="/jobs/${j.id}">查看机会 ↗</a></div></article>`).join("") : empty("暂时没有匹配的机会", "可以调整搜索条件，或稍后再来看看。")}</div><aside class="side-card"><p class="eyebrow">YOUR NEXT STEP</p><h3>让求职，简单一点</h3>${steps}</aside></div></div>`);
  // 空筛选值不发送为整数查询参数。
  $(".search-bar").addEventListener("submit", event => {
    event.preventDefault(); const data = new FormData(event.currentTarget); const query = new URLSearchParams();
    for (const [key, value] of data) if (value.trim()) query.set(key, value.trim());
    location.href = query.size ? `/?${query}` : "/";
  });
}

async function authPage(register) {
  const next = new URLSearchParams(location.search).get("next");
  shell(`<div class="container"><div class="auth-layout"><div class="auth-intro"><p class="eyebrow">YOUR NEXT CHAPTER</p><h1>${register ? "每一个新的开始，<br>都充满可能。" : "欢迎回来，<br>继续你的下一步。"}</h1><p class="muted">无论你在寻找机会，还是寻找同行者，<br>我们都在这里，为相遇搭一座桥。</p><div class="steps">${steps}</div></div><section class="panel auth-panel"><h2>${register ? "创建你的账号" : "登录伯乐直聘"}</h2><p class="muted">${register ? "选择身份，开启你的新旅程。" : "使用用户名和密码登录。"}</p><form id="auth-form">${register ? '<div class="role-switch"><label class="role-option"><input type="radio" name="role" value="seeker" checked>我要求职</label><label class="role-option"><input type="radio" name="role" value="company">我要招聘</label></div>' : '<hr>'}<div class="field"><label for="username">用户名</label><input id="username" name="username" autocomplete="username" maxlength="40" placeholder="输入你的用户名" required></div><div class="field" id="company-field" hidden><label for="company-name">公司名称</label><input id="company-name" name="company_name" maxlength="100" placeholder="填写完整的公司名称"><span class="hint">每家公司仅能注册一个账号，请确认名称准确。</span></div><div class="field"><label for="password">密码</label><input id="password" name="password" type="password" autocomplete="${register ? "new-password" : "current-password"}" ${register ? 'minlength="8"' : ""} maxlength="128" placeholder="${register ? "设置 8～128 位密码" : "输入密码"}" required></div>${errorBox}<button class="btn wide" type="submit">${register ? "创建账号" : "登录"} ↗</button></form><p class="form-foot">${register ? '已有账号？<a href="/login">立即登录</a>' : '还没有账号？<a href="/register">免费注册</a>'}</p></section></div></div>`);
  if (register) all('[name="role"]').forEach(radio => radio.addEventListener("change", () => {
    const company = $('[name="role"]:checked').value === "company";
    $("#company-field").hidden = !company; $("#company-name").required = company;
  }));
  form("#auth-form", async data => {
    if (register) {
      await api("/auth/register", {method:"POST", body:Object.fromEntries(data)});
      sessionStorage.setItem("flash", "注册成功，请登录"); location.href = "/login";
    } else {
      const result = await api("/auth/login", {method:"POST", body:{username:data.get("username"),password:data.get("password")}});
      localStorage.setItem(ACCESS_TOKEN_KEY, result.access_token);
      location.href = next && /^\/(?!\/)/.test(next) ? next : result.role === "company" ? "/company" : result.role === "admin" ? "/admin" : "/";
    }
  });
}

async function jobPage(id) {
  const job = await api(`/jobs/${id}`);
  let existing = null;
  if (user?.role === "seeker") existing = (await api("/seeker/applications")).find(a => a.job_id === Number(id));
  shell(`<div class="container"><a class="back" href="/">← 返回全部机会</a><div class="detail-grid"><div><section class="panel detail-title">${badge("正在招聘", "green")}<h1>${esc(job.position_name)}</h1><div class="company-line"><span class="company-icon">${esc(job.company_name.slice(0,1))}</span>${esc(job.company_name)}</div><hr><div class="detail-meta"><span>发布时间 <strong>${date(job.created_at)}</strong></span><span>联系方式 <a class="contact-email" href="mailto:${esc(job.email)}">${esc(job.email)}</a></span></div></section><section class="panel"><h2>关于这份机会</h2><div class="prose">${esc(job.description)}</div></section></div><aside class="panel"><p class="eyebrow">TAKE YOUR NEXT STEP</p><h2>向新机会，迈一步</h2>${user?.role === "seeker" ? existing ? `<div class="notice success">你已经投递过这份招聘。</div><a class="btn wide" href="/applications">查看我的投递 ↗</a>` : `<p class="hint">填写联系信息，上传你的简历。每份招聘仅能投递一次。</p><form id="apply-form"><div class="field"><label for="candidate-name">姓名</label><input id="candidate-name" name="name" maxlength="80" required></div><div class="field"><label for="candidate-email">联系邮箱</label><input id="candidate-email" type="email" name="email_address" required></div><div class="field"><label for="candidate-phone">手机号<em>选填</em></label><input id="candidate-phone" type="tel" name="phone_number" maxlength="25"></div><div class="field"><label for="resume">上传简历</label><input id="resume" type="file" name="resume" accept=".pdf,.doc,.docx" required><span class="hint">PDF / DOC / DOCX，最大 10 MB。提交后无法修改或撤回。</span></div>${errorBox}<button class="btn wide" type="submit">投递简历 ↗</button></form>` : `<p class="hint">让我们从一份简历开始，认识优秀的你。</p>${user ? '<div class="notice">仅求职者账号可投递简历。</div>' : `<a class="btn wide" href="/login?next=/jobs/${job.id}">登录后投递 ↗</a><p class="form-foot">没有账号？<a href="/register">免费注册</a></p>`}`}</aside></div></div>`);
  if ($("#apply-form")) form("#apply-form", async data => {
    if (data.get("resume").size > 10_000_000) throw new Error("简历大小不能超过 10 MB");
    await api(`/jobs/${id}/applications`, {method:"POST", body:data});
    sessionStorage.setItem("flash", "简历投递成功，祝你收获好消息"); location.href = "/applications";
  });
}

function modal(title, fields, handler) {
  $("#editor")?.remove();
  const dialog = document.createElement("dialog"); dialog.id = "editor";
  dialog.innerHTML = `<div class="dialog-head"><h2>${esc(title)}</h2><button class="text-button" id="close-dialog" aria-label="关闭窗口" type="button">×</button></div><form id="editor-form">${fields}${errorBox}<button class="btn wide" type="submit">保存</button></form>`;
  document.body.append(dialog); $("#close-dialog").onclick = () => dialog.close();
  form("#editor-form", async (data, element) => { await handler(data, element); dialog.close(); });
  dialog.showModal();
}

async function adminPage() {
  if (!needRole("admin")) return;
  const positions = await api("/admin/positions");
  shell(`<div class="container"><div class="section-top page-heading"><div><p class="eyebrow">PLATFORM / ADMIN</p><h1>岗位目录</h1><p>统一维护岗位名称，让招聘信息更清晰。</p></div><button class="btn" id="new-position">＋ 新增岗位</button></div><div class="notice">岗位改名将同步到关联招聘。停用后不能用于发布新招聘，已有招聘和投递记录仍会保留。</div>${positions.length ? `<div class="table-wrap"><table><thead><tr><th>岗位名称</th><th>状态</th><th>管理</th></tr></thead><tbody>${positions.map(p => `<tr><td><strong>${esc(p.name)}</strong><span class="muted">岗位 #${p.id}</span></td><td>${badge(p.active ? "使用中" : "已停用", p.active ? "green" : "gray")}</td><td><button class="btn secondary small" data-edit="${p.id}">编辑岗位</button></td></tr>`).join("")}</tbody></table></div>` : empty("还没有岗位", "点击新增岗位，公司即可选择岗位发布招聘。")}</div>`);
  const editor = p => modal(p ? "编辑岗位" : "新增岗位", `<div class="field"><label for="position-name">岗位名称</label><input id="position-name" name="name" maxlength="100" value="${esc(p?.name || "")}" required></div>${p ? `<div class="field"><label for="position-active">岗位状态</label><select id="position-active" name="active"><option value="true" ${p.active ? "selected" : ""}>使用中</option><option value="false" ${!p.active ? "selected" : ""}>已停用</option></select></div>` : ""}`, async data => {
    await api(`/admin/positions${p ? `/${p.id}` : ""}`, {method:p ? "PUT" : "POST", body:{name:data.get("name"), active:data.get("active") !== "false"}});
    await adminPage(); toast("岗位已保存");
  });
  $("#new-position").onclick = () => editor(null);
  all("[data-edit]").forEach(b => b.onclick = () => editor(positions.find(p => p.id === Number(b.dataset.edit))));
}

function table(headers, rows) { return `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`; }

async function companyPage(tab = location.hash.slice(1) || "jobs") {
  if (!needRole("company")) return;
  const [jobs, applications, appointments] = await Promise.all([api("/company/jobs"),api("/company/applications"),api("/company/appointments")]);
  let content;
  if (tab === "applications") content = applications.length ? table(["求职者", "投递岗位", "投递状态", "邀请状态", "操作"], applications.map(a => `<tr><td><strong>${esc(a.name)}</strong><span class="muted">${date(a.created_at)}</span></td><td>${esc(a.position_name)}</td><td>${statusBadge(a.status)}</td><td>${a.invitation ? statusBadge(a.invitation.status) : '<span class="muted">尚未邀请</span>'}</td><td><a class="btn light small" href="/company/applications/${a.id}">查看投递 ↗</a></td></tr>`)) : empty("还没有收到简历", "发布招聘后，求职者的投递会出现在这里。");
  else if (tab === "appointments") content = appointments.length ? table(["预约姓名", "手机号", "岗位", "预约时间 · 北京时间", "关联投递"], appointments.map(a => `<tr><td><strong>${esc(a.name)}</strong>${badge("已预约", "green")}</td><td>${esc(a.phone)}</td><td>${esc(a.position_name)}</td><td class="nowrap">${date(a.scheduled_at)}</td><td><a href="/company/applications/${a.application_id}">查看投递 ↗</a></td></tr>`)) : empty("暂时没有预约", "向求职者发出邀请，对方提交表单后即可在此查看。");
  else content = jobs.length ? table(["招聘岗位", "状态", "联系邮箱", "管理"], jobs.map(j => `<tr><td><strong>${esc(j.position_name)}</strong><span class="muted">发布于 ${date(j.created_at)}</span></td><td>${badge(j.is_open ? "招聘中" : "已关闭", j.is_open ? "green" : "gray")}</td><td>${esc(j.email)}</td><td><div class="actions"><button class="btn secondary small" data-edit="${j.id}">编辑</button><button class="btn ${j.is_open ? "secondary" : "light"} small" data-toggle="${j.id}">${j.is_open ? "关闭招聘" : "重新开放"}</button></div></td></tr>`)) : empty("发布你的第一份招聘", "从一个清晰的岗位介绍开始，找到同行的人。");
  shell(`<div class="container"><div class="section-top page-heading"><div><p class="eyebrow">COMPANY WORKSPACE</p><h1>你好，${esc(user.company_name)}</h1><p>管理机会，连接人才，让下一次合作发生。</p></div><button class="btn" id="new-job">＋ 发布招聘</button></div><div class="stats"><div class="stat"><span>开放中的招聘</span><strong>${jobs.filter(j => j.is_open).length}<small> 个</small></strong></div><div class="stat"><span>收到的简历</span><strong>${applications.length}<small> 份</small></strong></div><div class="stat"><span>成功预约</span><strong>${appointments.length}<small> 次</small></strong></div></div><div class="tabs" aria-label="工作台栏目"><button class="tab ${tab === "jobs" ? "active" : ""}" data-tab="jobs">招聘管理</button><button class="tab ${tab === "applications" ? "active" : ""}" data-tab="applications">收到的简历</button><button class="tab ${tab === "appointments" ? "active" : ""}" data-tab="appointments">预约安排</button></div>${content}</div>`);
  all("[data-tab]").forEach(b => action(b, async () => { history.replaceState(null,"",`#${b.dataset.tab}`); await companyPage(b.dataset.tab); }));
  const editor = async j => {
    const positions = await api("/positions");
    if (j && !positions.some(p => p.id === j.position_id)) positions.push({id:j.position_id,name:`${j.position_name}（已停用，保留当前岗位）`});
    if (!positions.length) { toast("暂无可用岗位，请联系管理员添加"); return; }
    modal(j ? "编辑招聘" : "发布新的机会", `<div class="field"><label for="job-position">岗位名称</label><select id="job-position" name="position_id" required>${positions.map(p => `<option value="${p.id}" ${p.id === j?.position_id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div><div class="field"><label for="job-description">岗位介绍</label><textarea id="job-description" name="description" maxlength="20000" placeholder="介绍岗位职责、任职要求，以及你们希望遇见怎样的同行者。" required>${esc(j?.description || "")}</textarea></div><div class="field"><label for="job-email">联系邮箱</label><input id="job-email" type="email" name="email" value="${esc(j?.email || "")}" maxlength="254" required></div>`, async data => {
      await api(`/company/jobs${j ? `/${j.id}` : ""}`, {method:j ? "PUT" : "POST", body:{position_id:Number(data.get("position_id")),description:data.get("description"),email:data.get("email")}});
      await companyPage("jobs"); toast("招聘已保存");
    });
  };
  action($("#new-job"), () => editor(null));
  all("[data-edit]").forEach(b => action(b, () => editor(jobs.find(j => j.id === Number(b.dataset.edit)))));
  all("[data-toggle]").forEach(b => action(b, async () => {
    const job = jobs.find(j => j.id === Number(b.dataset.toggle));
    await api(`/company/jobs/${job.id}/state`, {method:"PATCH", body:{is_open:!job.is_open}}); await companyPage("jobs"); toast(job.is_open ? "招聘已关闭，历史记录已保留" : "招聘已重新开放");
  }));
}

async function applicationDetail(id) {
  if (!needRole("company")) return;
  const a = await api(`/company/applications/${id}`);
  await api(`/company/applications/${id}/viewed`, {method:"POST"});
  const invite = a.invitation, booking = a.appointment;
  shell(`<div class="container"><a class="back" href="/company#applications">← 返回收到的简历</a><div class="section-top"><div><p class="eyebrow">APPLICATION / ${a.id}</p><h1>${esc(a.name)}的投递</h1><p class="muted small">${esc(a.position_name)} · 投递于 ${date(a.created_at)}</p></div>${badge("已查看", "green")}</div><div class="detail-grid"><section class="panel"><h2>求职资料</h2><dl class="definition"><dt>姓名</dt><dd>${esc(a.name)}</dd><dt>联系邮箱</dt><dd>${esc(a.email)}</dd><dt>手机号</dt><dd>${esc(a.phone || "未填写")}</dd><dt>简历文件</dt><dd>${esc(a.original_filename)}</dd></dl><hr><a class="btn light" href="/api/company/applications/${a.id}/resume">↓ 下载简历</a></section><aside class="panel"><p class="eyebrow">LET'S MEET</p><h2>邀请见面</h2>${invite ? `${statusBadge(invite.status)}${booking ? `<div class="notice success"><strong>${esc(booking.name)}</strong><br>${esc(booking.phone)}<br>${date(booking.scheduled_at)}（北京时间）</div>` : `<p class="invite-note">链接有效期至 ${date(invite.expires_at)}</p>`}${invite.status === "待预约" ? `<div class="link-box" id="invite-link">${esc(invite.url)}</div><div class="actions"><button class="btn light small" id="copy-link">复制链接</button><button class="btn secondary small" id="revoke-link">撤销邀请</button></div>` : invite.status !== "已预约" ? '<button class="btn wide" id="create-invite">重新生成邀请 ↗</button>' : ""}` : '<p class="hint">生成专属邀请，求职者可以直接打开表单预约时间。</p><button class="btn wide" id="create-invite">生成邀请链接 ↗</button>'}<p class="invite-note">邀请在生成后 7 天有效，求职者也能在“我的投递”中查看。</p></aside></div></div>`);
  if ($("#create-invite")) action($("#create-invite"), async () => { await api(`/company/applications/${id}/invitation`, {method:"POST"}); await applicationDetail(id); toast("邀请已生成"); });
  if ($("#revoke-link")) action($("#revoke-link"), async () => { await api(`/company/invitations/${invite.id}/revoke`, {method:"POST"}); await applicationDetail(id); toast("邀请已撤销，原链接不能使用"); });
  if ($("#copy-link")) action($("#copy-link"), async () => {
    try { await navigator.clipboard.writeText(invite.url); toast("链接已复制，可自行发送给求职者"); }
    catch { const range = document.createRange(); range.selectNodeContents($("#invite-link")); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); toast("请复制上方已选中的链接"); }
  });
}

async function myApplications() {
  if (!needRole("seeker")) return;
  const records = await api("/seeker/applications");
  shell(`<div class="container"><div class="page-heading"><p class="eyebrow">MY JOURNEY</p><h1>每一步，都算数。</h1><p>在这里查看你的投递进展，与下一次见面。</p></div><div class="record-list">${records.length ? records.map(a => `<article class="record"><div class="record-top"><div><h3>${a.is_open ? `<a href="/jobs/${a.job_id}">${esc(a.position_name)}</a>` : esc(a.position_name)}</h3><span class="muted small">${esc(a.company_name)}${!a.is_open ? " · 招聘已关闭" : ""}</span></div>${statusBadge(a.status)}</div><div class="record-info"><span>投递于 ${date(a.created_at)}</span><span>简历 ${esc(a.original_filename)}</span></div><details class="small"><summary class="invite-note">查看提交资料</summary><p class="muted">${esc(a.name)} · ${esc(a.email)} · ${esc(a.phone || "未填写手机号")}</p></details>${a.invitation ? `<div class="invitation-strip"><div><strong class="small">${a.appointment ? "预约已安排" : "公司的见面邀请"}</strong><p class="invite-note">${a.appointment ? `${esc(a.appointment.name)} · ${esc(a.appointment.phone)}<br>${date(a.appointment.scheduled_at)}（北京时间）` : `链接有效期至 ${date(a.invitation.expires_at)}`}</p></div><div class="actions">${statusBadge(a.invitation.status)}${a.invitation.status === "待预约" ? `<a class="btn light small" href="/invite/${esc(a.invitation.token)}">预约时间 ↗</a>` : ""}</div></div>` : '<p class="invite-note">有新邀请时，会显示在这条投递记录中。</p>'}</article>`).join("") : empty("你的下一步，从这里开始", "找到感兴趣的招聘，投递你的第一份简历。", "/", "发现机会 ↗")}</div></div>`);
}

async function invitationPage(token) {
  const invite = await api(`/invitations/${encodeURIComponent(token)}`);
  const open = invite.status === "待预约";
  shell(`<div class="container"><div class="booking-wrap"><section class="panel"><div class="booking-top"><p class="eyebrow">YOU'RE INVITED</p>${statusBadge(invite.status)}<h1>好机会，值得见一面。</h1><p class="muted small">${esc(invite.company_name)} · ${esc(invite.position_name)}</p></div>${open ? `<p class="hint">填写下方信息，选择一个适合你的时间。提交后即预约成功，无需登录。</p><form id="booking-form"><div class="field"><label for="booking-name">姓名</label><input id="booking-name" name="name" maxlength="80" autocomplete="name" required></div><div class="field"><label for="booking-phone">手机号</label><input id="booking-phone" name="phone" type="tel" maxlength="25" autocomplete="tel" required></div><div class="field"><label for="booking-time">预约时间<em>北京时间 · Asia/Shanghai</em></label><input id="booking-time" name="scheduled_at" type="datetime-local" required><span class="hint">请选择未来的日期与时间，提交后不能重复预约。</span></div><div class="notice">链接有效期至 ${date(invite.expires_at)}。提交后，公司即可看到你的预约信息。</div>${errorBox}<button class="btn wide" type="submit">确认预约 ↗</button></form>` : `<div class="success-content"><h2>${invite.status === "已预约" ? "这份邀请已完成预约" : `邀请${esc(invite.status)}`}</h2><p>${invite.status === "已预约" ? "请按已提交的预约时间与公司联系。" : "请联系公司，索取新的预约链接。"}</p><a class="btn light" href="/">返回招聘首页</a></div>`}</section><p class="hint small">伯乐直聘 · 连接每一次值得期待的相遇</p></div></div>`);
  if (open) form("#booking-form", async data => {
    const result = await api(`/invitations/${encodeURIComponent(token)}/appointments`, {method:"POST", body:Object.fromEntries(data)});
    $(".booking-wrap .panel").innerHTML = `<div class="success-content"><div class="success-icon">✓</div><p class="eyebrow">SEE YOU SOON</p><h1>预约成功</h1><p>${esc(invite.company_name)}已收到你的预约。<br>期待与你见面。</p><div class="success-time">${date(result.scheduled_at)}<p class="small">北京时间 · Asia/Shanghai</p></div><a class="btn wide" href="/applications">查看我的投递 ↗</a><p class="hint">无需再次提交，请保留你的预约时间。</p></div>`;
  });
}

async function start() {
  try { user = await api("/auth/me"); } catch (error) { if (error.status !== 401) throw error; }
  nav();
  const path = location.pathname;
  if (path === "/") await home();
  else if (path === "/login" || path === "/register") await authPage(path === "/register");
  else if (/^\/jobs\/\d+$/.test(path)) await jobPage(path.split("/")[2]);
  else if (path === "/admin") await adminPage();
  else if (path === "/company") await companyPage();
  else if (/^\/company\/applications\/\d+$/.test(path)) await applicationDetail(path.split("/")[3]);
  else if (path === "/applications") await myApplications();
  else if (path.startsWith("/invite/")) await invitationPage(path.split("/")[2]);
  else shell(`<div class="container">${empty("页面不存在", "可以返回首页继续寻找机会。", "/", "返回首页")}</div>`);
  const flash = sessionStorage.getItem("flash");
  if (flash) { sessionStorage.removeItem("flash"); toast(flash); }
}
start().catch(error => shell(`<div class="container">${empty("暂时无法显示此页面", error.message, "/", "返回首页")}</div>`));
