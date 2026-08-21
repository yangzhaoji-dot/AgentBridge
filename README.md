# AgentBridge

AgentBridge lets a local coding agent ask a user-authorized web AI through a
browser extension. Version 0.1 connects Codex to the signed-in ChatGPT webpage
running in Microsoft Edge.

```text
Codex --MCP ask_chatgpt(prompt)--> AgentBridge --WebSocket--> Edge extension
      <-- final answer ------------------------------------ ChatGPT webpage
```

## Current status

The v0.1 end-to-end path has been verified with a real ChatGPT webpage:

```text
Codex → ask_chatgpt("1+1等于多少？") → ChatGPT → "2" → Codex
```

Current boundaries:

- One local Edge extension connection.
- One dedicated signed-in ChatGPT tab.
- One text-only request at a time.
- User confirmation remains enabled for MCP calls.
- ChatGPT DOM changes can require adapter updates.

## Quick start on Windows

Create the project environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
```

If your network needs a local proxy, append its temporary proxy option to `pip`
and `npm`; do not commit proxy credentials or environment files.

Start the local bridge:

```powershell
.\Start-AgentBridge.ps1
```

Load the unpacked Edge extension from:

```text
extension
```

Then open a signed-in `https://chatgpt.com/` tab. See [EDGE_MVP.md](EDGE_MVP.md)
for the detailed installation and test flow.

## Use from Codex

The project includes a project-scoped MCP configuration at
`.codex/config.toml`. To use AgentBridge from any local Codex task, register the
same Streamable HTTP endpoint globally:

```powershell
codex mcp add agentbridge --url http://127.0.0.1:8765/mcp
```

Start a new Codex task after changing MCP configuration. Ask it to use the tool
explicitly, for example:

```text
请调用 ask_chatgpt 工具，独立审查这个方案。不要发送密钥、私有文件全文或个人信息。
```

## Repository layout

```text
agentbridge_server/  MCP server and authenticated WebSocket bridge
extension/           Edge Manifest V3 extension and ChatGPT DOM adapter
.codex/              Project-scoped MCP configuration
scripts/             Smoke tests for MCP and bridge round trips
tests/               Python tests and browser-adapter fixture
```

`relay_server/`, `local_connector/`, and `web/` are the earlier local-control
prototype retained during the transition. AgentBridge is the active path.

## Safety model

- Bind AgentBridge to `127.0.0.1` in v0.1.
- Authenticate the extension with a locally generated token.
- Accept extension WebSockets only from a `chrome-extension://` origin.
- Treat all web-AI output as untrusted advisory text.
- Never send API keys, passwords, tokens, private file contents, or personal
  data through `ask_chatgpt`.
- Never let web-AI output directly authorize shell commands, file writes, or
  permission changes.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.smoke_agentbridge_mcp
.\.venv\Scripts\python.exe -m scripts.smoke_agentbridge_roundtrip
node --check .\extension\background.js
node --check .\extension\chatgpt_adapter.js
node --check .\extension\content.js
```

## Roadmap

1. Stabilize the ChatGPT adapter with diagnostics and streaming.
2. Add a second web-AI provider through the same adapter contract.
3. Add a second local-agent adapter.
4. Introduce bounded planning and review workflows across agents.
5. Publish a public release after security review, documentation, and license
   selection.

## Security reporting

Do not report credentials, browser sessions, local logs, or security details in
public issues. See [SECURITY.md](SECURITY.md).
