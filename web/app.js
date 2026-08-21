const PROTOCOL_VERSION = 1;

const elements = {
  relayUrl: document.querySelector("#relay-url"),
  deviceId: document.querySelector("#device-id"),
  token: document.querySelector("#token"),
  cwd: document.querySelector("#cwd"),
  connect: document.querySelector("#connect-button"),
  relayStatus: document.querySelector("#relay-status"),
  agentStatus: document.querySelector("#agent-status"),
  messages: document.querySelector("#messages"),
  approvals: document.querySelector("#approvals"),
  composer: document.querySelector("#composer"),
  prompt: document.querySelector("#prompt"),
  send: document.querySelector("#send-button"),
  interrupt: document.querySelector("#interrupt-button"),
  approvalTemplate: document.querySelector("#approval-template"),
};

const state = {
  socket: null,
  relayConnected: false,
  agentOnline: false,
  turnActive: false,
  streamingBody: null,
};

const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
elements.relayUrl.value = `${wsScheme}://${window.location.host}/ws`;

function message(type, payload = {}, replyTo = null) {
  const result = {
    id: crypto.randomUUID(),
    type,
    protocol_version: PROTOCOL_VERSION,
    timestamp: new Date().toISOString(),
    payload,
  };
  if (replyTo !== null) result.reply_to = replyTo;
  return result;
}

function setStatus(element, text, online) {
  element.textContent = text;
  element.classList.toggle("online", online);
  element.classList.toggle("offline", !online);
}

function updateControls() {
  const ready = state.relayConnected && state.agentOnline;
  elements.send.disabled = !ready;
  elements.interrupt.disabled = !ready || !state.turnActive;
  elements.connect.textContent = state.relayConnected ? "断开" : "连接";
}

function addMessage(role, text, label = null) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const heading = document.createElement("div");
  heading.className = "message-label";
  heading.textContent = label ?? ({ user: "你", agent: "本地 Agent", error: "错误" }[role] || "系统");

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;

  article.append(heading, body);
  elements.messages.append(article);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return body;
}

function appendAgentDelta(delta) {
  if (!state.streamingBody) {
    state.streamingBody = addMessage("agent", "");
  }
  state.streamingBody.textContent += delta;
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function socketSend(data) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    addMessage("error", "WebSocket 尚未连接。");
    return false;
  }
  state.socket.send(JSON.stringify(data));
  return true;
}

function connect() {
  if (state.socket && state.socket.readyState <= WebSocket.OPEN) {
    state.socket.close(1000, "user disconnected");
    return;
  }

  const url = elements.relayUrl.value.trim();
  const deviceId = elements.deviceId.value.trim();
  if (!url || !deviceId) {
    addMessage("error", "请填写 WebSocket 地址和设备 ID。");
    return;
  }

  setStatus(elements.relayStatus, "正在连接", false);
  const socket = new WebSocket(url);
  state.socket = socket;

  socket.addEventListener("open", () => {
    socket.send(
      JSON.stringify(
        message("hello", {
          role: "browser",
          device_id: deviceId,
          token: elements.token.value,
        }),
      ),
    );
  });

  socket.addEventListener("message", (event) => {
    try {
      handleMessage(JSON.parse(event.data));
    } catch (error) {
      addMessage("error", `无法解析服务端消息：${error.message}`);
    }
  });

  socket.addEventListener("close", (event) => {
    state.relayConnected = false;
    state.agentOnline = false;
    state.turnActive = false;
    state.streamingBody = null;
    setStatus(elements.relayStatus, `中转未连接 (${event.code})`, false);
    setStatus(elements.agentStatus, "Agent 离线", false);
    updateControls();
  });

  socket.addEventListener("error", () => {
    addMessage("error", "WebSocket 连接失败，请检查中转地址和 HTTPS/WSS 配置。");
  });
}

function handleMessage(data) {
  const payload = data.payload || {};
  switch (data.type) {
    case "hello.ack":
      state.relayConnected = true;
      state.agentOnline = Boolean(payload.agent_online);
      setStatus(elements.relayStatus, "中转已连接", true);
      setStatus(elements.agentStatus, state.agentOnline ? "Agent 在线" : "Agent 离线", state.agentOnline);
      addMessage("system", `已连接设备：${payload.device_id}`);
      updateControls();
      break;
    case "agent.status":
      state.agentOnline = Boolean(payload.online);
      setStatus(
        elements.agentStatus,
        state.agentOnline ? `Agent 在线 · ${payload.state || "ready"}` : "Agent 离线",
        state.agentOnline,
      );
      if (payload.default_cwd && !elements.cwd.value) {
        elements.cwd.placeholder = payload.default_cwd;
      }
      updateControls();
      break;
    case "task.accepted":
      state.turnActive = true;
      state.streamingBody = null;
      addMessage("system", `任务已开始 · ${payload.cwd}`);
      updateControls();
      break;
    case "task.error":
    case "relay.error":
      addMessage("error", payload.message || "未知错误");
      break;
    case "codex.event":
      renderCodexEvent(payload.message || {});
      break;
    case "approval.required":
      renderApproval(payload);
      break;
    case "approval.resolved":
      addMessage("system", payload.approved ? "操作已允许。" : "操作已拒绝。");
      break;
    case "interaction.required":
      addMessage("error", `当前界面尚未支持此交互：${payload.method}`);
      break;
    case "turn.interrupted":
      addMessage("system", "已发送中断请求。");
      break;
    case "turn.steered":
      addMessage("system", "补充要求已发送给当前任务。");
      break;
  }
}

function renderCodexEvent(event) {
  const method = event.method;
  const params = event.params || {};

  if (method === "item/agentMessage/delta") {
    appendAgentDelta(params.delta || "");
    return;
  }

  if (method === "turn/started") {
    state.turnActive = true;
    state.streamingBody = null;
    updateControls();
    return;
  }

  if (method === "turn/completed") {
    state.turnActive = false;
    state.streamingBody = null;
    const status = params.turn?.status || "completed";
    addMessage("system", `任务结束：${status}`);
    updateControls();
    return;
  }

  if (method === "error") {
    addMessage("error", params.error?.message || params.message || JSON.stringify(params));
    return;
  }

  if (method === "item/started" && params.item?.type === "commandExecution") {
    const command = params.item.command || params.item.parsedCommand || "准备执行命令";
    addMessage("system", typeof command === "string" ? command : JSON.stringify(command), "命令");
  }
}

function renderApproval(payload) {
  const fragment = elements.approvalTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".approval-card");
  const title = fragment.querySelector(".approval-title");
  const reason = fragment.querySelector(".approval-reason");
  const detail = fragment.querySelector(".approval-detail");
  const approve = fragment.querySelector(".approve");
  const deny = fragment.querySelector(".deny");
  const params = payload.params || {};

  title.textContent = payload.method.includes("fileChange") || payload.method.includes("Patch")
    ? "Agent 请求修改文件"
    : "Agent 请求执行命令";
  reason.textContent = params.reason || params.cwd || "请检查下面的操作，再决定是否允许。";
  detail.textContent = params.command || JSON.stringify(params, null, 2);

  const resolve = (approved) => {
    socketSend(
      message("approval.resolve", {
        request_id: payload.request_id,
        approved,
      }),
    );
    card.remove();
  };
  approve.addEventListener("click", () => resolve(true));
  deny.addEventListener("click", () => resolve(false));
  elements.approvals.append(fragment);
}

elements.connect.addEventListener("click", connect);

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = elements.prompt.value.trim();
  if (!text) return;
  if (
    socketSend(
      message("task.start", {
        text,
        cwd: elements.cwd.value.trim() || null,
      }),
    )
  ) {
    addMessage("user", text);
    elements.prompt.value = "";
  }
});

elements.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});

elements.interrupt.addEventListener("click", () => {
  socketSend(message("turn.interrupt"));
});

updateControls();

function applyLauncherBootstrap() {
  if (!window.location.hash) return;
  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get("token");
  const deviceId = params.get("device");
  const shouldConnect = params.get("autoconnect") === "1";

  if (token) elements.token.value = token;
  if (deviceId) elements.deviceId.value = deviceId;

  // Remove the pairing token from the visible URL and browser history immediately.
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  if (shouldConnect && token) {
    window.setTimeout(connect, 150);
  }
}

applyLauncherBootstrap();
