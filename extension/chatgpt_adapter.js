globalThis.AgentBridgeChatGPT = (() => {
  const PROMPT_SELECTORS = [
    "#prompt-textarea",
    'div[contenteditable="true"][data-lexical-editor="true"]',
    'div[contenteditable="true"][role="textbox"]',
    'textarea[placeholder*="Message"]',
    'textarea[placeholder*="消息"]',
  ];
  const SEND_SELECTORS = [
    '[data-testid="send-button"]',
    'button[aria-label="Send prompt"]',
    'button[aria-label*="Send"]',
    'button[aria-label*="发送"]',
  ];
  const STOP_SELECTORS = [
    '[data-testid="stop-button"]',
    'button[data-testid*="stop"]',
    'button[aria-label*="Stop generating"]',
    'button[aria-label*="停止生成"]',
    'button[aria-label*="Stop"]',
    'button[aria-label*="停止"]',
  ];
  const CONTROL_SETTLE_MS = 1200;
  const FALLBACK_STABLE_MS = 15000;
  const ASSISTANT_SELECTOR = '[data-message-author-role="assistant"]';
  const TRANSIENT_ASSISTANT_TEXT = [
    /^正在思考[.…]*$/u,
    /^思考中[.…]*$/u,
    /^thinking[.…]*$/iu,
    /^working[.…]*$/iu,
  ];

  function firstVisible(selectors) {
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element && element.getClientRects().length > 0) return element;
    }
    return null;
  }

  function assistantMessages() {
    return [...document.querySelectorAll(ASSISTANT_SELECTOR)].filter(
      (element) => element.getClientRects().length > 0,
    );
  }

  function isTransientAssistantText(text) {
    const normalized = text.replace(/\s+/gu, " ").trim();
    return TRANSIENT_ASSISTANT_TEXT.some((pattern) => pattern.test(normalized));
  }

  function setPromptText(input, text) {
    input.focus();
    if (input instanceof HTMLTextAreaElement || input instanceof HTMLInputElement) {
      const prototype =
        input instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      if (!setter) throw new Error("Cannot update the ChatGPT input value");
      setter.call(input, text);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }

    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(input);
    selection.removeAllRanges();
    selection.addRange(range);
    document.execCommand("insertText", false, text);
    input.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertText",
        data: text,
      }),
    );
  }

  function waitForMutation(timeoutMs = 500) {
    return new Promise((resolve) => {
      const observer = new MutationObserver(() => {
        observer.disconnect();
        clearTimeout(timer);
        resolve();
      });
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
      });
      const timer = setTimeout(() => {
        observer.disconnect();
        resolve();
      }, timeoutMs);
    });
  }

  async function waitUntil(predicate, timeoutMs, errorMessage) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const value = predicate();
      if (value) return value;
      await waitForMutation(400);
    }
    throw new Error(errorMessage);
  }

  async function waitForAnswer(beforeCount, timeoutMs) {
    await waitUntil(
      () => {
        const messages = assistantMessages();
        return messages.length > beforeCount ? messages.at(-1) : null;
      },
      Math.min(timeoutMs, 45000),
      "ChatGPT did not create a new assistant message. Check login state and selectors.",
    );

    const deadline = Date.now() + timeoutMs;
    let previousText = "";
    let lastChangeAt = Date.now();
    let responseStartedAt = null;
    let sawBusyControl = false;

    while (Date.now() < deadline) {
      // ChatGPT can replace the whole message element while streaming. Always
      // reacquire the newest assistant node instead of holding a stale element.
      const currentAssistant = assistantMessages().at(-1);
      const text = currentAssistant?.innerText?.trim() || "";
      if (text !== previousText) {
        previousText = text;
        lastChangeAt = Date.now();
        responseStartedAt ??= lastChangeAt;
      }

      const stopButton = firstVisible(STOP_SELECTORS);
      const sendButton = firstVisible(SEND_SELECTORS);
      const sendReady = Boolean(sendButton && !sendButton.disabled);
      if (stopButton || (sendButton && sendButton.disabled)) {
        sawBusyControl = true;
      }
      const stableForMs = Date.now() - lastChangeAt;
      const hasUsableText =
        text &&
        !isTransientAssistantText(text);
      const controlsConfirmCompletion =
        sawBusyControl && !stopButton && sendReady && stableForMs >= CONTROL_SETTLE_MS;
      const fallbackCompletion =
        !sawBusyControl &&
        responseStartedAt !== null &&
        Date.now() - responseStartedAt >= FALLBACK_STABLE_MS &&
        stableForMs >= FALLBACK_STABLE_MS;

      if (hasUsableText && (controlsConfirmCompletion || fallbackCompletion)) {
        console.debug("AgentBridge captured a completed ChatGPT answer", {
          completion: controlsConfirmCompletion ? "composer-ready" : "conservative-fallback",
          stableForMs,
        });
        return text;
      }
      await waitForMutation(350);
    }
    throw new Error(`ChatGPT response timed out after ${Math.round(timeoutMs / 1000)}s`);
  }

  async function ask(prompt, timeoutMs = 180000) {
    const input = await waitUntil(
      () => firstVisible(PROMPT_SELECTORS),
      15000,
      "Cannot find the ChatGPT prompt input. The page may be signed out or changed.",
    );
    const beforeCount = assistantMessages().length;
    setPromptText(input, prompt);

    const sendButton = await waitUntil(
      () => {
        const button = firstVisible(SEND_SELECTORS);
        return button && !button.disabled ? button : null;
      },
      5000,
      "Cannot find an enabled ChatGPT send button.",
    );
    sendButton.click();
    return waitForAnswer(beforeCount, timeoutMs);
  }

  return { ask };
})();
