const $ = (selector) => document.querySelector(selector);
let threadId = null;
let busy = false;
let apiToken = ""; // Deliberately kept in memory, never localStorage.

async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers: {
    "Content-Type": "application/json",
    ...(apiToken ? {Authorization: `Bearer ${apiToken}`} : {}),
  }});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !$("#auth-dialog").open) $("#auth-dialog").showModal();
    const error = new Error(typeof data.detail === "string" ? data.detail : "请求格式错误，请检查输入。");
    error.status = response.status;
    throw error;
  }
  return data;
}

function addMessage(role, text, tools = []) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const label = document.createElement("div");
  label.className = "role";
  label.textContent = role === "user" ? "你" : "TRAVEL ASSISTANT";
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = text; // Model/tool output is untrusted. Never inject HTML.
  article.append(label, body);
  if (tools.length) {
    const trace = document.createElement("div");
    trace.className = "trace";
    for (const tool of tools) {
      const chip = document.createElement("span");
      chip.textContent = `${tool.status === "error" ? "!" : "✓"} ${tool.name}`;
      trace.append(chip);
    }
    article.append(trace);
  }
  $("#messages").append(article);
  article.scrollIntoView({behavior: "smooth", block: "start"});
  return body;
}

function setBusy(value) {
  busy = value;
  $("#send").disabled = value;
  $("#new-chat").disabled = value;
  $("#send").textContent = value ? "处理中…" : "发送 ↗";
}

async function connect() {
  try {
    const health = await request("/health");
    $("#mode").textContent = health.mode === "demo" ? "DEMO · 离线演示" : "LIVE · 实时服务";
    $("#connection").textContent = "服务已连接";
    $("#notice").textContent = [
      health.mode === "demo" ? "当前为固定北京样例演示，不调用大模型或实时天气、地图服务。" : "", ...health.warnings,
    ].filter(Boolean).join("\n");
  } catch (error) {
    $("#connection").textContent = "连接未完成";
    $("#notice").textContent = error.message;
  }
}

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("#message").value.trim();
  if (!message || busy) return;
  setBusy(true);
  $("#welcome").hidden = true;
  addMessage("user", message);
  const pending = addMessage("assistant", "正在理解你的需求并调用工具…");
  const allowSave = $("#allow-save").checked;
  $("#allow-save").checked = false;
  $("#message").value = "";
  try {
    if (!threadId) threadId = (await request("/sessions", {method: "POST"})).thread_id;
    const data = await request("/chat", {method: "POST", body: JSON.stringify({
      message, thread_id: threadId, allow_save: allowSave,
    })});
    pending.parentElement.remove();
    addMessage("assistant", data.content, data.tools);
  } catch (error) {
    pending.textContent = error.message;
    if ([404, 502, 504].includes(error.status)) threadId = null;
    $("#message").value = message;
  } finally { setBusy(false); $("#message").focus(); }
});

$("#message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("#chat-form").requestSubmit();
  }
});
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
  $("#message").value = button.dataset.prompt;
  $("#message").focus();
}));
$("#new-chat").addEventListener("click", async () => {
  if (busy) return;
  setBusy(true);
  try {
    if (threadId) await request(`/sessions/${threadId}`, {method: "DELETE"});
    threadId = null;
    $("#messages").replaceChildren();
    $("#welcome").hidden = false;
    $("#message").value = "";
  } catch (error) { $("#notice").textContent = error.message; }
  finally { setBusy(false); }
});
$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  apiToken = $("#token").value;
  $("#token").value = "";
  $("#auth-dialog").close();
  await connect();
});
connect();
