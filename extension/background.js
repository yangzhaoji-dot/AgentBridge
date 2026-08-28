const CONFIG_URL = "http://127.0.0.1:8765/api/extension-config";
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const KEEPALIVE_MS = 20000;

let socket = null;
let reconnectDelay = RECONNECT_MIN_MS;
let reconnectTimer = null;
let keepaliveTimer = null;
let connecting = false;
const completedResponses = new Map();

function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

function rememberResponse(id, response) {
  completedResponses.set(id, response);
  while (completedResponses.size > 50) {
    completedResponses.delete(completedResponses.keys().next().value);
  }
}

function send(message) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error("AgentBridge WebSocket is not connected");
  }
  socket.send(JSON.stringify(message));
}

function clearSocketTimers() {
  if (keepaliveTimer) clearInterval(keepaliveTimer);
  keepaliveTimer = null;
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  setBadge("…", "#8a6d1d");
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
}

async function loadBridgeConfig() {
  const response = await fetch(CONFIG_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`AgentBridge config returned HTTP ${response.status}`);
  }
  return response.json();
}

async function connect() {
  if (
    connecting ||
    socket?.readyState === WebSocket.CONNECTING ||
    socket?.readyState === WebSocket.OPEN
  ) {
    return;
  }
  connecting = true;
  try {
    const config = await loadBridgeConfig();
    const ws = new WebSocket(config.websocket_url);
    socket = ws;

    ws.addEventListener("open", () => {
      reconnectDelay = RECONNECT_MIN_MS;
      send({
        type: "hello",
        token: config.token,
        client_id: chrome.runtime.id,
        protocol_version: 1,
      });
    });

    ws.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      handleBridgeMessage(message);
    });

    ws.addEventListener("close", () => {
      clearSocketTimers();
      socket = null;
      setBadge("OFF", "#8b2f39");
      scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      ws.close();
    });
  } catch (error) {
    console.warn("AgentBridge connect failed", error);
    scheduleReconnect();
  } finally {
    connecting = false;
  }
}

async function getDedicatedChatGPTTab() {
  const tabs = await getChatGPTTabs();
  if (!tabs.length) {
    throw new Error("Open one signed-in chatgpt.com tab in Edge first");
  }

  const configured = await chrome.storage.local.get("chatgptTabId");
  const configuredTab = tabs.find((tab) => tab.id === configured.chatgptTabId);
  if (configuredTab) return configuredTab;

  const activeTab = tabs.find((tab) => tab.active) || tabs[0];
  await chrome.storage.local.set({ chatgptTabId: activeTab.id });
  return activeTab;
}

async function getChatGPTTabs() {
  return chrome.tabs.query({ url: "https://chatgpt.com/*" });
}

async function listChatGPTTabs() {
  const [tabs, configured] = await Promise.all([
    getChatGPTTabs(),
    chrome.storage.local.get("chatgptTabId"),
  ]);
  return {
    bridgeConnected: socket?.readyState === WebSocket.OPEN,
    selectedTabId: configured.chatgptTabId ?? null,
    tabs: tabs.map((tab) => ({
      id: tab.id,
      title: tab.title || "未命名 ChatGPT 对话",
      active: Boolean(tab.active),
      selected: tab.id === configured.chatgptTabId,
    })),
  };
}

async function selectChatGPTTab(tabId) {
  if (!Number.isInteger(tabId)) {
    throw new Error("Invalid ChatGPT tab id");
  }
  const tabs = await getChatGPTTabs();
  const target = tabs.find((tab) => tab.id === tabId);
  if (!target) {
    throw new Error("The selected ChatGPT tab is no longer open");
  }
  await chrome.storage.local.set({ chatgptTabId: tabId });
  return { id: tabId, title: target.title || "未命名 ChatGPT 对话" };
}

async function sendToChatGPTContentScript(tabId, message) {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    if (!detail.includes("Receiving end does not exist")) {
      throw error;
    }

    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["chatgpt_adapter.js", "content.js"],
    });
    return chrome.tabs.sendMessage(tabId, message);
  }
}

async function askChatGPT(message) {
  const cached = completedResponses.get(message.id);
  if (cached) {
    send(cached);
    return;
  }

  let response;
  try {
    const tab = await getDedicatedChatGPTTab();
    const result = await sendToChatGPTContentScript(tab.id, {
      type: "agentbridge.ask",
      id: message.id,
      prompt: message.prompt,
      timeoutMs: message.timeout_ms,
    });
    if (!result?.ok) {
      throw new Error(result?.error || "ChatGPT content script returned no result");
    }
    response = { type: "ask.response", id: message.id, answer: result.answer };
  } catch (error) {
    response = {
      type: "ask.error",
      id: message.id,
      error: error instanceof Error ? error.message : String(error),
    };
  }

  rememberResponse(message.id, response);
  send(response);
}

function handleBridgeMessage(message) {
  if (message.type === "hello.ack") {
    setBadge("ON", "#1c7c54");
    clearSocketTimers();
    keepaliveTimer = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        send({ type: "ping", timestamp: Date.now() });
      }
    }, KEEPALIVE_MS);
  } else if (message.type === "ask.request") {
    askChatGPT(message);
  }
}

chrome.runtime.onInstalled.addListener(() => connect());
chrome.runtime.onStartup.addListener(() => connect());
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "agentbridge.content.ready") {
    connect();
    return;
  }
  if (message?.type === "agentbridge.tabs.list") {
    listChatGPTTabs()
      .then((result) => sendResponse({ ok: true, ...result }))
      .catch((error) =>
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        }),
      );
    return true;
  }
  if (message?.type === "agentbridge.tabs.select") {
    selectChatGPTTab(message.tabId)
      .then((tab) => sendResponse({ ok: true, tab }))
      .catch((error) =>
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        }),
      );
    return true;
  }
});
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const configured = await chrome.storage.local.get("chatgptTabId");
  if (configured.chatgptTabId === tabId) {
    await chrome.storage.local.remove("chatgptTabId");
  }
});

connect();
