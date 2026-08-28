# AgentBridge

AgentBridge lets a coding agent ask a user-authorized webpage AI without giving
the server direct access to the user's browser session.

```text
Codex / local agent -> AgentBridge Relay (MCP)
                              ^
                              | outbound WSS
                              |
user computer -> Local Connector -> Edge or Chrome extension -> webpage AI
```

The Relay can run on a server or another computer. The browser remains on a
user-controlled computer that is signed in to the selected webpage AI.

## Status

### Verified v0.1 local mode

The original local path was tested with a real ChatGPT webpage:

```text
Codex -> ask_chatgpt("1+1等于多少？") -> ChatGPT -> "2" -> Codex
```

It runs one local MCP server and one Edge extension on the same computer.

### v0.2 development: portable Relay + Connector

The repository now contains the remote topology needed for a browserless
server:

- `agentbridge_server.remote_app` — a server-side MCP Relay.
- `agentbridge_connector` — a cross-platform, outbound-only local Connector.
- The existing Edge/Chrome extension still connects only to localhost.
- A real local test starts a Relay, Connector, and simulated extension using
  two WebSockets and verifies an end-to-end `1+1 -> 2` round trip.

Not yet verified: a real internet Relay behind TLS, a real server-side Codex
session, and a real signed-in browser on a different machine. Follow
[SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md) to perform that owner-controlled
deployment test.

The published `v0.1.0` ZIP contains only the verified local mode. Until a
`v0.2` release is published, use a source clone of `main` for the Relay +
Connector development path.

## Choose a mode

| Goal | Start on the browser computer | Start on the server |
| --- | --- | --- |
| One computer, local Codex | `Start-AgentBridge.ps1` | Not needed |
| Browserless server Codex | `python -m agentbridge_connector` | `uvicorn agentbridge_server.remote_app:create_app --factory` |

Do not start the local bridge and the local Connector at the same time: both
intentionally reserve `127.0.0.1:8765`.

## Install on Windows

Download a release ZIP, extract it to a writable folder, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-AgentBridge.ps1
```

The installer creates a Python environment, installs Node dependencies, and
adds the local-mode desktop shortcuts. Browser extension installation remains a
user-confirmed Edge or Chrome action.

For a source checkout:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
```

## Local mode

Run:

```powershell
.\Start-AgentBridge.ps1
```

Load the unpacked [`extension`](extension) folder in Edge or Chrome, then open
one signed-in `https://chatgpt.com/` tab. See [EDGE_MVP.md](EDGE_MVP.md) for the
detailed local setup flow.

The MCP endpoint is:

```text
http://127.0.0.1:8765/mcp
```

## Remote server mode

The server does not need a browser. A separate user computer runs the Connector
and keeps the signed-in browser tab.

1. Clone this repository on the server and on the browser computer.
2. Configure a unique token for each device on the Relay, then set that
   device's `AGENTBRIDGE_PAIRING_TOKEN` only on its own Connector.
3. Start the server Relay on loopback and expose only its Connector WebSocket
   through a TLS reverse proxy.
4. Start the local Connector with `AGENTBRIDGE_REMOTE_WS_URL` and a unique
   `AGENTBRIDGE_DEVICE_ID`.
5. Register `http://127.0.0.1:8765/mcp` in the **server** Codex configuration.

Use [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md) for exact commands, the Caddy
path restriction, the server MCP configuration sample, and verification steps.

If your server already supports SSH but has no domain or WSS reverse proxy, use
[SSH_TUNNEL_DEPLOYMENT.md](SSH_TUNNEL_DEPLOYMENT.md) first. It keeps the Relay
on server loopback and carries the Connector link inside SSH encryption.

On Windows, after setting the Connector environment variables in the current
PowerShell session, you may use:

```powershell
.\Start-AgentBridgeConnector.ps1
```

## Project instructions

[`AGENTS.md`](AGENTS.md) travels with the repository and provides AgentBridge
project rules to Codex sessions started in this repository or its
subdirectories. Put personal, cross-project rules separately in the server
user's `~/.codex/AGENTS.md`; project rules do not replace global rules.

## Safety model

- The browser and local Connector never accept public inbound traffic.
- The Connector initiates the connection to the Relay.
- Pairing tokens must be high-entropy runtime secrets; never commit or print
  them.
- Keep the Relay MCP endpoint on loopback or a private network.
- Treat all webpage-AI output as untrusted advisory text.
- Never send API keys, passwords, tokens, browser sessions, private file
  contents, or personal data through `ask_chatgpt`.
- Never let webpage-AI output directly authorize shell commands, file writes,
  permission changes, or other external actions.

## Repository layout

```text
agentbridge_server/     Local bridge plus the remote MCP Relay
agentbridge_connector/  Cross-platform local Connector for a paired browser
extension/              Chromium Manifest V3 extension and ChatGPT adapter
deploy/                 Safe server-side Codex configuration example
SERVER_DEPLOYMENT.md    Remote deployment and pairing guide
AGENTS.md               Project-level Codex instructions
```

`relay_server/`, `local_connector/`, and `web/` are an earlier local-control
prototype retained during the transition. They are not the active remote
AgentBridge path.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.smoke_agentbridge_mcp
.\.venv\Scripts\python.exe -m scripts.smoke_agentbridge_roundtrip
node --check .\extension\background.js
node --check .\extension\chatgpt_adapter.js
node --check .\extension\content.js
```

The test suite includes unit tests and a local two-WebSocket remote Relay /
Connector integration test. It does not replace a real TLS, server, and browser
deployment test.

## Roadmap

1. Validate the v0.2 Relay + Connector on a real server and browser computer.
2. Add provider adapters behind a stable `ask_web_ai` contract.
3. Add additional local-agent adapters and bounded multi-agent planning flows.
4. Add observability that records metadata without collecting prompt secrets.

## Security reporting

Do not report credentials, browser sessions, local logs, or security details in
public issues. See [SECURITY.md](SECURITY.md).

## License

AgentBridge is licensed under the [Apache License 2.0](LICENSE).
