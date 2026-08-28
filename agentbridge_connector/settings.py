from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from agentbridge_server.settings import AgentBridgeSettings


@dataclass(frozen=True)
class EdgeConnectorSettings:
    """Settings for the computer that owns the browser extension."""

    local: AgentBridgeSettings
    remote_ws_url: str
    pairing_token: str
    device_id: str
    reconnect_max_seconds: float = 30.0

    @classmethod
    def load(cls) -> "EdgeConnectorSettings":
        remote_ws_url = os.getenv("AGENTBRIDGE_REMOTE_WS_URL", "").strip()
        parsed_url = urlparse(remote_ws_url)
        if parsed_url.scheme not in {"ws", "wss"} or not parsed_url.netloc:
            raise RuntimeError(
                "AGENTBRIDGE_REMOTE_WS_URL must be a ws:// or wss:// connector URL"
            )
        if (
            parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise RuntimeError(
                "AGENTBRIDGE_REMOTE_WS_URL must not contain credentials, query values, "
                "or fragments"
            )
        if not parsed_url.path.rstrip("/").endswith("/ws/connector"):
            raise RuntimeError(
                "AGENTBRIDGE_REMOTE_WS_URL must end with /ws/connector"
            )

        pairing_token = os.getenv("AGENTBRIDGE_PAIRING_TOKEN", "").strip()
        if len(pairing_token) < 32:
            raise RuntimeError(
                "AGENTBRIDGE_PAIRING_TOKEN must contain at least 32 characters"
            )

        device_id = os.getenv("AGENTBRIDGE_DEVICE_ID", socket.gethostname()).strip()
        if not device_id:
            raise RuntimeError("AGENTBRIDGE_DEVICE_ID cannot be empty")

        return cls(
            local=AgentBridgeSettings.load(),
            remote_ws_url=remote_ws_url,
            pairing_token=pairing_token,
            device_id=device_id,
        )
