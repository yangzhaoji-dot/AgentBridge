let busy = false;

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "agentbridge.ask") return false;

  if (busy) {
    sendResponse({ ok: false, error: "ChatGPT tab is already processing a request" });
    return false;
  }

  busy = true;
  AgentBridgeChatGPT.ask(
    message.prompt,
    message.timeoutMs,
    message.completionMarker,
  )
    .then((answer) => sendResponse({ ok: true, answer }))
    .catch((error) =>
      sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      }),
    )
    .finally(() => {
      busy = false;
    });

  return true;
});

document.documentElement.dataset.agentbridgeReady = "true";
chrome.runtime.sendMessage({ type: "agentbridge.content.ready" }).catch(() => {
  // The background worker reconnects on its next lifecycle event.
});
