const elements = {
  connectionStatus: document.querySelector("#connection-status"),
  refresh: document.querySelector("#refresh"),
  tabs: document.querySelector("#tabs"),
  empty: document.querySelector("#empty"),
  message: document.querySelector("#message"),
};

function setMessage(text = "", kind = "") {
  elements.message.textContent = text;
  elements.message.className = `message ${kind}`.trim();
}

function createTabButton(tab) {
  const button = document.createElement("button");
  button.className = `tab${tab.selected ? " selected" : ""}`;
  button.dataset.tabId = String(tab.id);

  const title = document.createElement("span");
  title.className = "tab-title";
  title.textContent = tab.title;

  const meta = document.createElement("span");
  meta.className = "tab-meta";
  const labels = [];
  if (tab.selected) labels.push("当前专用对话");
  if (tab.active) labels.push("浏览器当前页面");
  if (!labels.length) labels.push("点击设为专用对话");
  meta.textContent = labels.join(" · ");

  button.append(title, meta);
  return button;
}

function renderTabs(tabs) {
  elements.tabs.replaceChildren(...tabs.map(createTabButton));
  elements.empty.hidden = tabs.length > 0;
}

async function send(message) {
  return chrome.runtime.sendMessage(message);
}

async function refresh() {
  elements.refresh.disabled = true;
  setMessage();
  try {
    const result = await send({ type: "agentbridge.tabs.list" });
    if (!result?.ok) throw new Error(result?.error || "无法读取 ChatGPT 对话");
    renderTabs(result.tabs || []);
    elements.connectionStatus.textContent = result.bridgeConnected
      ? "本机 AgentBridge 已连接"
      : "本机 AgentBridge 正在连接或未启动";
  } catch (error) {
    setMessage(error instanceof Error ? error.message : String(error), "error");
  } finally {
    elements.refresh.disabled = false;
  }
}

elements.refresh.addEventListener("click", refresh);
elements.tabs.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-tab-id]");
  if (!button) return;
  const tabId = Number(button.dataset.tabId);
  setMessage("正在设置专用对话…");
  try {
    const result = await send({ type: "agentbridge.tabs.select", tabId });
    if (!result?.ok) throw new Error(result?.error || "无法设置专用对话");
    setMessage(`已选择：${result.tab.title}`, "ok");
    await refresh();
  } catch (error) {
    setMessage(error instanceof Error ? error.message : String(error), "error");
  }
});

refresh();
