# AgentBridge remote deployment

This guide makes a server-side Codex call a webpage AI running in a paired
browser on any user-controlled computer. It does **not** expose the user's
browser or Connector to the internet.

```text
Server Codex -> http://127.0.0.1:8765/mcp -> AgentBridge Relay
                                                    ^
                                                    | WSS, outbound from computer
                                                    |
User computer -> AgentBridge Connector -> Edge/Chrome extension -> ChatGPT tab
```

## 1. Clone on the server

On Linux, macOS, or Windows with Python 3.12 installed:

```bash
git clone https://github.com/yangzhaoji-dot/AgentBridge.git
cd AgentBridge
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Windows, use the equivalent `py -3.12 -m venv .venv` and
`.venv\Scripts\python.exe` commands.

The repository-root `AGENTS.md` is automatically read by Codex when a task is
started from this repository or one of its subdirectories. It is project
guidance, not a replacement for a server user's `~/.codex/AGENTS.md`.

## 2. Create a pairing secret

Create one high-entropy secret **per Connector device** and transfer each secret
to its owner through a secure channel. Do not put them in Git, shell history,
issue comments, or chat prompts.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

On the Relay, map device IDs to their own tokens. This prevents one paired
computer from claiming another computer's device ID:

```bash
export AGENTBRIDGE_PAIRINGS_JSON='{"yangzhaoji-desktop":"replace-with-desktop-secret"}'
export AGENTBRIDGE_REQUEST_TIMEOUT=180
```

## 3. Start the Relay on the server

Bind the Relay to loopback. Codex uses this private HTTP endpoint locally on
the server.

```bash
.venv/bin/python -m uvicorn agentbridge_server.remote_app:create_app --factory \
  --host 127.0.0.1 --port 8765
```

Merge [`deploy/server-codex-config.toml.example`](deploy/server-codex-config.toml.example)
into the server user's `~/.codex/config.toml`, then start a new Codex session.

## 4. Expose only the Connector WebSocket

For internet use, place a TLS reverse proxy in front of the Relay and expose
only `/ws/connector`. Keep `/mcp` and `/api/*` private to the server.

Example Caddy site block, after replacing the domain:

```caddyfile
bridge.example.com {
    @connector path /ws/connector
    handle @connector {
        reverse_proxy 127.0.0.1:8765
    }
    respond "Not found" 404
}
```

The resulting Connector URL is:

```text
wss://bridge.example.com/ws/connector
```

For a private LAN test, `ws://server-host:8765/ws/connector` is acceptable only
when the LAN is trusted. Use `wss://` for any network you do not fully control.

## 5. Run the Connector on a user computer

Clone the same repository, create its Python 3.12 environment, install
`requirements.txt`, and set these runtime variables:

```bash
export AGENTBRIDGE_REMOTE_WS_URL='wss://bridge.example.com/ws/connector'
export AGENTBRIDGE_PAIRING_TOKEN='the-token-configured-for-yangzhaoji-desktop'
export AGENTBRIDGE_DEVICE_ID='yangzhaoji-desktop'
python -m agentbridge_connector
```

On Windows PowerShell:

```powershell
$env:AGENTBRIDGE_REMOTE_WS_URL = 'wss://bridge.example.com/ws/connector'
$env:AGENTBRIDGE_PAIRING_TOKEN = 'the-token-configured-for-yangzhaoji-desktop'
$env:AGENTBRIDGE_DEVICE_ID = 'yangzhaoji-desktop'
.\.venv\Scripts\python.exe -m agentbridge_connector
```

The Connector binds only to `127.0.0.1:8765`, so the existing Edge extension
continues to load its configuration locally. Do not start the old local
`Start-AgentBridge.ps1` at the same time because both modes use port 8765.

## 6. Pair the browser and call the tool

Load the `extension/` folder in Edge or Chrome, open a signed-in ChatGPT tab,
and confirm the Connector reports both `remote_connected: true` and
`extension_online: true` at `http://127.0.0.1:8765/api/status`.

On the server, ask Codex to call:

```text
ask_chatgpt(prompt="独立审查这个方案", device_id="yangzhaoji-desktop")
```

The web prompt is transmitted to the paired webpage AI. Do not use this tool
for secrets, credentials, private file contents, or unapproved actions.

## What is verified in this repository

- Unit tests cover Relay routing, device replacement, local Connector forwarding,
  and malformed relay requests.
- A local two-WebSocket integration test should be run before a deployment is
  considered ready.
- A real internet deployment, TLS proxy, server Codex session, and signed-in
  browser must be tested by the owner before calling the whole path operational.
