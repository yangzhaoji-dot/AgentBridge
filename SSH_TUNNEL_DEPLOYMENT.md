# AgentBridge SSH tunnel deployment

Use this first when the Relay already runs on a remote server but you do not
have a domain, Caddy, or public WSS endpoint. It keeps every server port private.

```text
Local Connector -> ws://127.0.0.1:18765/ws/connector
                       | local loopback only
                       v
                  SSH encryption
                       v
Remote Relay -> 127.0.0.1:8765/ws/connector
```

`ws://` is safe in this specific setup because it is confined to local loopback;
the connection between the computer and server is inside SSH encryption. Do not
replace the loopback URL with an unencrypted remote `ws://server:port` address.

## Prerequisites

- The Relay is running on the server at `127.0.0.1:8765`.
- Your browser computer can connect to the server with its configured SSH host,
  for example `ssh cuixing-server`.
- The server pairing configuration contains your device ID. This repository's
  helper reads only that device's token through SSH and never prints it.
- Edge or Chrome has the AgentBridge extension loaded.

## One-time nonsecret configuration

This saves only connection metadata in your Windows user profile. It does not
save or print the pairing token.

```powershell
.\Set-AgentBridgeSshProfile.ps1 `
  -SshHost cuixing-server `
  -DeviceId cuixing-desktop `
  -RemoteEnvPath /home/user1/.config/agentbridge/relay.env `
  -RemoteProjectPath /home/user1/cuixing/AgentBridge
```

## Start on the browser computer

From the AgentBridge project folder in PowerShell:

```powershell
.\Start-AgentBridgeSshConnector.ps1
```

The command starts a hidden SSH tunnel at local port `18765`, reads the
device-specific pairing token through SSH only for the child Connector process,
and starts the Connector at local port `8765`.

Then reload the AgentBridge extension at `edge://extensions` and refresh one
dedicated signed-in `chatgpt.com` tab.

## Verify

On the browser computer:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/status
```

Expected values:

```text
remote_connected: True
extension_online: True
device_id: cuixing-desktop
```

On the server:

```bash
curl http://127.0.0.1:8765/api/status
```

Expected: `connector_count` is at least `1` and lists `cuixing-desktop`.

For a compact local status report:

```powershell
.\Get-AgentBridgeSshStatus.ps1
```

To test a full server MCP call without sending sensitive data:

```powershell
.\Test-AgentBridgeSshBridge.ps1
```

## Stop

```powershell
.\Stop-AgentBridgeSshConnector.ps1
```

This stops only the Connector and the matching locally recorded SSH tunnel. It
does not stop the remote Relay or Codex.

## When to move to WSS

Use a domain plus WSS only when the Connector needs to remain online without an
SSH session, or when multiple independent user computers need a managed public
entry point. Keep the Relay MCP endpoint private in either deployment mode.
