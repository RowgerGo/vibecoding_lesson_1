"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const state = {user: null, csrf: "", tab: "overview", page: 1, status: "", sequence: 0};
const roles = {admin: "系统管理员", head: "部门负责人", user: "普通用户"};
const statuses = {pending: "待审核", approved: "已同意", rejected: "已拒绝"};
let toastTimer;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notify(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 5000);
}
function showLogin() {
  state.user = null;
  state.csrf = "";
  state.sequence++;
  $("#workspace").hidden = true;
  $("#login-view").hidden = false;
  $("#modal").close();
  $("#login-form").reset();
}
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...options,
    headers: {"Content-Type": "application/json", "X-CSRF-Token": state.csrf, ...options.headers},
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") showLogin();
    throw new Error(data.error?.message || "操作失败，请重试");
  }
  return data;
}
async function run(action, button) {
  const old = button?.textContent;
  if (button) { button.disabled = true; button.textContent = "处理中…"; }
  try { await action(); } catch (error) { notify(error.message || "连接失败，请检查网络后重试"); }
  finally { if (button) { button.disabled = false; button.textContent = old; } }
}
function bindForm(form, callback) {
  form.addEventListener("submit", event => {
    event.preventDefault();
    run(() => callback(new FormData(form)), $("button[type=submit]", form));
  });
}
function button(text, action, className = "link-button") {
  const node = el("button", text, className);
  node.type = "button";
  node.addEventListener("click", () => run(action, node));
  return node;
}
function badge(value) {
  return el("span", statuses[value] || (value === "enabled" ? "已启用" : "已停用"), `badge ${value}`);
}
function option(select, value, label) {
  const node = el("option", label);
  node.value = value;
  select.append(node);
}
function dateTime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", {timeZone: "Asia/Shanghai", hour12: false}) : "—";
}
function openModal(title, html = "") {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html; // 仅接收下方代码中的固定模板，业务内容通过 textContent 填入。
  if (!$("#modal").open) $("#modal").showModal();
  return $("#modal-body");
}
$("#modal-close").addEventListener("click", () => $("#modal").close());

const tabs = {
  overview: ["工作台", "◫"], mine: ["我的申请", "▤"], inbox: ["部门审批", "✓"],
  departments: ["部门管理", "▦"], users: ["用户管理", "♙"], all: ["全部申请", "▤"], password: ["账户设置", "⚙"],
};
function allowedTabs() {
  return state.user.role === "admin" ? ["overview", "departments", "users", "all", "password"]
    : state.user.role === "head" ? ["overview", "mine", "inbox", "password"] : ["overview", "mine", "password"];
}
function enterWorkspace() {
  $("#login-view").hidden = true;
  $("#workspace").hidden = false;
  $("#profile-name").textContent = state.user.name;
  $("#profile-avatar").textContent = state.user.name.slice(0, 1);
  $("#profile-role").textContent = `${roles[state.user.role]}${state.user.department_name ? ` · ${state.user.department_name}` : ""}`;
  $("#nav").replaceChildren();
  for (const name of allowedTabs()) {
    const link = el("a", undefined, "nav-item");
    link.href = `#${name}`;
    link.dataset.tab = name;
    const symbol = el("span", tabs[name][1], "nav-symbol");
    symbol.setAttribute("aria-hidden", "true");
    link.append(symbol, el("span", tabs[name][0]));
    $("#nav").append(link);
  }
  return route();
}
async function route() {
  if (!state.user) return;
  const name = location.hash.slice(1) || "overview";
  if (!allowedTabs().includes(name)) {
    notify("无权访问该页面");
    location.hash = "overview";
    return;
  }
  state.tab = name; state.page = 1; state.status = "";
  document.querySelectorAll(".nav-item").forEach(link => {
    link.classList.toggle("active", link.dataset.tab === name);
    if (link.dataset.tab === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("#breadcrumb").textContent = `工作空间 / ${tabs[name][0]}`;
  await render();
}
window.addEventListener("hashchange", () => run(route));
function heading(title, subtitle, action) {
  const node = el("div", undefined, "page-heading");
  const text = el("div");
  text.append(el("h1", title), el("p", subtitle));
  node.append(text);
  if (action) node.append(action);
  $("#main").append(node);
}
function tablePanel(title, subtitle, headings) {
  const panel = el("section", undefined, "panel");
  const head = el("div", undefined, "panel-heading");
  const text = el("div"); text.append(el("h2", title));
  if (subtitle) text.append(el("p", subtitle));
  head.append(text); panel.append(head);
  const wrap = el("div", undefined, "table-wrap"), table = el("table"), thead = el("thead"), tr = el("tr");
  for (const label of headings) tr.append(el("th", label));
  thead.append(tr); table.append(thead);
  const body = el("tbody"); table.append(body); wrap.append(table); panel.append(wrap);
  $("#main").append(panel);
  return {panel, head, body};
}
function row(body, cells) {
  const tr = el("tr");
  for (const item of cells) {
    const td = el("td");
    if (item instanceof Node) td.append(item); else td.textContent = item ?? "—";
    tr.append(td);
  }
  body.append(tr);
}
function empty(panel, message) {
  const node = el("div", undefined, "empty");
  node.append(el("strong", "暂时没有记录"), el("span", message));
  panel.append(node);
}
async function render() {
  $("#main").replaceChildren();
  const seq = ++state.sequence;
  if (["overview", "mine", "inbox", "all"].includes(state.tab)) await renderApplications(seq);
  else if (state.tab === "departments") await renderDepartments(seq);
  else if (state.tab === "users") await renderUsers(seq);
  else renderPassword();
}
async function renderApplications(seq) {
  const tab = state.tab;
  const scope = tab === "mine" ? "mine" : tab === "inbox" ? "inbox" : "visible";
  const scopeForDashboard = state.user.role === "admin" ? "visible" : "mine";
  const actualScope = tab === "overview" ? scopeForDashboard : scope;
  const query = new URLSearchParams({scope: actualScope, page: state.page, page_size: "10"});
  if (state.status) query.set("status", state.status);
  const result = await api(`/applications?${query}`);
  let counts;
  if (tab === "overview") counts = await Promise.all(Object.keys(statuses).map(status => api(`/applications?scope=${actualScope}&status=${status}&page_size=1`)));
  if (seq !== state.sequence) return;
  const action = state.user.role !== "admin" ? button("＋ 发起申请", newApplication, "primary") : el("span", "管理部门与用户，查看全局申请", "date-note");
  heading(tab === "overview" ? `${state.user.name}，欢迎回来` : tabs[tab][0],
    tab === "inbox" ? "处理指定本部门审批的申请，让协作及时向前。" : tab === "all" ? "查看全部申请及审批记录。" : "每一项工作，都有迹可循。", action);
  if (counts) {
    const stats = el("div", undefined, "stats");
    Object.entries(statuses).forEach(([key, label], index) => {
      const card = el("div", undefined, "stat-card"), info = el("div");
      info.append(el("div", `${state.user.role === "admin" ? "全部" : "我的"}${label}`, "stat-label"), el("div", String(counts[index].total), "stat-number"));
      card.append(info, el("div", ["◷", "✓", "×"][index], "stat-symbol")); stats.append(card);
    });
    $("#main").append(stats);
  }
  const table = tablePanel(tab === "overview" ? "最近申请" : "申请列表", `共 ${result.total} 条记录`, ["申请事项", "申请人", "审批部门", "事项日期", "状态", "操作"]);
  const filter = el("select"); filter.setAttribute("aria-label", "筛选申请状态");
  option(filter, "", "全部状态"); Object.entries(statuses).forEach(([value, text]) => option(filter, value, text));
  filter.value = state.status;
  filter.addEventListener("change", () => { state.status = filter.value; state.page = 1; run(render); });
  const tools = el("div", undefined, "toolbar"); tools.append(filter); table.head.append(tools);
  for (const item of result.items) {
    const title = el("div", undefined, "table-title"); title.title = item.title;
    title.append(el("div", item.title), el("div", `#${item.id} · ${dateTime(item.submitted_at)}`, "table-sub"));
    row(table.body, [title, item.applicant_name, item.approval_department_name, item.event_date, badge(item.status), button("查看详情 →", () => detail(item.id))]);
  }
  if (!result.items.length) empty(table.panel, tab === "inbox" ? "指定本部门审批的申请会出现在这里。" : "提交申请后，可以在这里查看处理进度。");
  const pages = Math.max(1, Math.ceil(result.total / 10));
  const pager = el("div", undefined, "pagination"), controls = el("div", undefined, "inline-actions");
  const prev = button("上一页", () => { state.page--; return render(); }); prev.disabled = state.page <= 1;
  const next = button("下一页", () => { state.page++; return render(); }); next.disabled = state.page >= pages;
  controls.append(prev, next); pager.append(el("span", `第 ${state.page} / ${pages} 页`), controls); table.panel.append(pager);
  if (tab === "overview") $("#main").append(el("div", "协作提示：提交申请时选择审批部门，申请将由该部门负责人处理。审批结果和拒绝理由会保留在申请详情中。", "notice"));
}
async function newApplication() {
  const data = await api("/approval-departments");
  if (!data.items.length) { notify("暂无可用审批部门，请联系系统管理员配置负责人。"); return; }
  const body = openModal("发起申请", `<form id="application-form">
    <label>事项日期<input name="event_date" type="date" required></label>
    <label>审批部门<select name="approval_department_id" aria-label="审批部门" required></select></label><p id="head-hint" class="hint"></p>
    <label>标题<input name="title" required maxlength="200" placeholder="简明描述你的申请事项"></label>
    <label>申请内容<textarea name="content" required maxlength="10000" placeholder="请说明申请内容及相关信息"></textarea></label>
    <p class="hint">提交后不可修改或撤回，请确认填写无误。</p><div class="form-actions"><button type="submit" class="primary">提交申请</button></div></form>`);
  const select = $("select", body);
  for (const dep of data.items) option(select, dep.id, dep.name);
  function updateHint() { $("#head-hint").textContent = `审批负责人：${data.items.find(dep => dep.id === Number(select.value)).head_name}`; }
  select.addEventListener("change", updateHint); updateHint();
  bindForm($("form", body), async form => {
    const result = await api("/applications", {method: "POST", body: {...Object.fromEntries(form), approval_department_id: Number(form.get("approval_department_id"))}});
    $("#modal").close(); notify("申请已提交"); await render(); await detail(result.id);
  });
}
async function detail(id) {
  const item = await api(`/applications/${id}`);
  const body = openModal(item.title);
  body.append(badge(item.status));
  const grid = el("dl", undefined, "detail-grid");
  for (const [key, value] of [["申请人", item.applicant_name], ["审批部门", item.approval_department_name], ["事项日期", item.event_date], ["提交时间（北京时间）", dateTime(item.submitted_at)]]) {
    const cell = el("div"); cell.append(el("dt", key), el("dd", value)); grid.append(cell);
  }
  body.append(grid, el("h3", "申请内容"), el("div", item.content, "detail-content"));
  if (item.status !== "pending") {
    const section = el("div", undefined, "detail-section");
    section.append(el("h3", "审批记录"), el("p", `${item.reviewer_name} · ${statuses[item.status]} · ${dateTime(item.reviewed_at)}`));
    if (item.rejection_reason) section.append(el("div", item.rejection_reason, "detail-content"));
    body.append(section);
  }
  if (state.user.role === "head" && state.user.head_department_id === item.approval_department_id && item.status === "pending") {
    const section = el("div", undefined, "detail-section");
    section.innerHTML = `<form><label>拒绝理由<textarea name="reason" maxlength="2000" placeholder="拒绝时必填"></textarea></label><div class="form-actions"><button type="button" class="danger">拒绝申请</button><button type="submit" class="primary">同意申请</button></div></form>`;
    body.append(section);
    let deciding = false;
    async function decide(decision) {
      if (deciding) return;
      const reason = $("textarea", section).value.trim();
      if (decision === "rejected" && !reason) throw new Error("拒绝申请必须填写理由");
      deciding = true;
      const controls = section.querySelectorAll("button"); controls.forEach(node => { node.disabled = true; });
      try {
        await api(`/applications/${id}/decision`, {method: "POST", body: {decision, reason: decision === "rejected" ? reason : null}});
        notify("审批已完成"); await render(); await detail(id);
      } finally { deciding = false; controls.forEach(node => { node.disabled = false; }); }
    }
    $("button.danger", section).addEventListener("click", () => run(() => decide("rejected")));
    bindForm($("form", section), () => decide("approved"));
  }
}
async function renderDepartments(seq) {
  const [departments, users] = await Promise.all([api("/departments"), api("/users")]);
  if (seq !== state.sequence) return;
  heading("部门管理", "维护单级部门，指定各部门的审批负责人。", button("＋ 创建部门", () => {
    const body = openModal("创建部门", `<form><label>部门名称<input name="name" maxlength="80" required placeholder="例如：财务部"></label><div class="form-actions"><button type="submit" class="primary">创建部门</button></div></form>`);
    bindForm($("form", body), async data => { await api("/departments", {method: "POST", body: Object.fromEntries(data)}); $("#modal").close(); notify("部门已创建，可继续创建成员并指定负责人"); await render(); });
  }, "primary"));
  const table = tablePanel("部门列表", "负责人仅可首次指定，第一版不提供更换和交接。", ["部门名称", "负责人", "启用成员", "状态", "操作"]);
  for (const dep of departments.items) {
    const actions = el("div", undefined, "inline-actions");
    if (!dep.head_user_id && dep.enabled) actions.append(button("指定负责人", () => {
      const candidates = users.items.filter(user => user.department_id === dep.id && user.enabled && !user.is_admin);
      if (!candidates.length) { notify("请先在用户管理中为该部门创建启用的普通用户。"); return; }
      const body = openModal("首次指定负责人", `<form><p class="hint">指定后不可更换，负责人暂时不能停用。</p><label>负责人<select name="user_id" aria-label="负责人" required></select></label><div class="form-actions"><button type="submit" class="primary">确认指定</button></div></form>`);
      for (const user of candidates) option($("select", body), user.id, `${user.name}（${user.username}）`);
      bindForm($("form", body), async data => { await api(`/departments/${dep.id}/head`, {method: "PUT", body: {user_id: Number(data.get("user_id"))}}); $("#modal").close(); notify("负责人已指定"); await render(); });
    }));
    actions.append(button(dep.enabled ? "停用" : "启用", async () => { await api(`/departments/${dep.id}`, {method: "PATCH", body: {enabled: !dep.enabled}}); notify("部门状态已更新"); await render(); }));
    row(table.body, [dep.name, dep.head_name || "尚未指定", dep.active_users, badge(dep.enabled ? "enabled" : "disabled"), actions]);
  }
  if (!departments.items.length) empty(table.panel, "先创建部门，再创建成员并指定负责人。");
}
async function renderUsers(seq) {
  const [users, departments] = await Promise.all([api("/users"), api("/departments")]);
  if (seq !== state.sequence) return;
  heading("用户管理", "账号由管理员统一创建，所属部门创建后不可变更。", button("＋ 创建用户", () => {
    const body = openModal("创建用户", `<form>
      <label>用户名<input name="username" required maxlength="40" pattern="[a-zA-Z0-9_.-]+" autocomplete="off"></label><p class="hint">支持字母、数字、下划线、点和短横线；创建后不可修改。</p>
      <label>姓名<input name="name" required maxlength="80"></label>
      <label>初始密码<input name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password"></label>
      <label>角色<select name="is_admin" aria-label="角色"><option value="false">普通用户</option><option value="true">系统管理员</option></select></label>
      <label>所属部门<select name="department_id" aria-label="所属部门" required></select></label>
      <label class="checkbox-label"><input type="checkbox" name="enabled" checked>创建后启用</label>
      <div class="form-actions"><button type="submit" class="primary">创建用户</button></div></form>`);
    const select = $("select[name=department_id]", body); option(select, "", "请选择部门");
    for (const dep of departments.items.filter(dep => dep.enabled)) option(select, dep.id, dep.name);
    $("select[name=is_admin]", body).addEventListener("change", event => { select.required = event.target.value !== "true"; });
    bindForm($("form", body), async data => {
      await api("/users", {method: "POST", body: {username: data.get("username"), name: data.get("name"), password: data.get("password"), is_admin: data.get("is_admin") === "true", department_id: data.get("department_id") ? Number(data.get("department_id")) : null, enabled: data.has("enabled")}});
      $("#modal").close(); notify("用户已创建"); await render();
    });
  }, "primary"));
  const table = tablePanel("用户列表", "现任负责人不可停用，账号停用后保留历史记录。", ["姓名 / 用户名", "所属部门", "角色", "状态", "操作"]);
  for (const user of users.items) {
    const name = el("div"); name.append(el("div", user.name), el("div", user.username, "table-sub"));
    const actions = el("div", undefined, "inline-actions");
    actions.append(button(user.enabled ? "停用" : "启用", async () => { await api(`/users/${user.id}`, {method: "PATCH", body: {enabled: !user.enabled}}); notify("用户状态已更新"); await render(); }));
    if (user.id !== state.user.id) actions.append(button("重置密码", () => {
      const body = openModal("重置密码", `<form><p class="hint">重置后，该用户已有登录会话将失效。</p><label>新密码<input name="new_password" type="password" required minlength="8" maxlength="128" autocomplete="new-password"></label><div class="form-actions"><button type="submit" class="primary">确认重置</button></div></form>`);
      bindForm($("form", body), async data => { await api(`/users/${user.id}/reset-password`, {method: "POST", body: Object.fromEntries(data)}); $("#modal").close(); notify("密码已重置"); });
    }));
    row(table.body, [name, user.department_name || "—", roles[user.role], badge(user.enabled ? "enabled" : "disabled"), actions]);
  }
}
function renderPassword() {
  heading("账户设置", "维护你的登录密码。修改后需要重新登录。");
  const panel = el("div", undefined, "panel form-panel");
  panel.innerHTML = `<form><label>原密码<input name="old_password" type="password" required maxlength="128" autocomplete="current-password"></label><label>新密码<input name="new_password" type="password" required minlength="8" maxlength="128" autocomplete="new-password"></label><p class="hint">密码长度为 8—128 位。</p><div class="form-actions"><button type="submit" class="primary">修改密码</button></div></form>`;
  $("#main").append(panel);
  bindForm($("form", panel), async data => { await api("/auth/password", {method: "POST", body: Object.fromEntries(data)}); showLogin(); notify("密码已修改，请重新登录"); });
}
$("#login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget, submit = $("button", form);
  $("#login-error").textContent = ""; submit.disabled = true; submit.textContent = "登录中…";
  try {
    const result = await api("/auth/login", {method: "POST", body: Object.fromEntries(new FormData(form))});
    state.user = result.user; state.csrf = result.csrf_token; form.reset();
    if (!allowedTabs().includes(location.hash.slice(1))) history.replaceState(null, "", "#overview");
    await enterWorkspace();
  } catch (error) { $("#login-error").textContent = error.message || "连接失败，请稍后重试"; }
  finally { submit.disabled = false; submit.textContent = "登录 →"; }
});
$("#logout").addEventListener("click", event => run(async () => { await api("/auth/logout", {method: "POST"}); showLogin(); }, event.currentTarget));
run(async () => {
  try { const result = await api("/auth/me"); state.user = result.user; state.csrf = result.csrf_token; }
  catch { showLogin(); return; }
  await enterWorkspace();
});
