from __future__ import annotations

import os
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteRelaySettings:
    """Settings owned by the public-or-private AgentBridge relay."""

    pairing_tokens: dict[str, str]
    request_timeout_seconds: float
    hello_timeout_seconds: float = 10.0

    @classmethod
    def load(cls) -> "RemoteRelaySettings":
        pairings_json = os.getenv("AGENTBRIDGE_PAIRINGS_JSON", "").strip()
        if pairings_json:
            try:
                raw_pairings = json.loads(pairings_json)
            except json.JSONDecodeError as exc:
                raise RuntimeError("AGENTBRIDGE_PAIRINGS_JSON must be valid JSON") from exc
            if not isinstance(raw_pairings, dict):
                raise RuntimeError("AGENTBRIDGE_PAIRINGS_JSON must be a JSON object")
            if any(
                not isinstance(device_id, str) or not isinstance(token, str)
                for device_id, token in raw_pairings.items()
            ):
                raise RuntimeError(
                    "AGENTBRIDGE_PAIRINGS_JSON device IDs and tokens must be strings"
                )
            pairing_tokens = {
                device_id.strip(): token.strip()
                for device_id, token in raw_pairings.items()
            }
        else:
            # A single-device deployment may use the shorter form. It is still
            # bound to one explicit device ID instead of accepting arbitrary IDs.
            pairing_token = os.getenv("AGENTBRIDGE_PAIRING_TOKEN", "").strip()
            device_id = os.getenv("AGENTBRIDGE_DEVICE_ID", "local-dev").strip()
            pairing_tokens = {device_id: pairing_token}

        if not pairing_tokens or any(
            not device_id or len(token) < 32
            for device_id, token in pairing_tokens.items()
        ):
            raise RuntimeError(
                "Each configured AgentBridge device must have a non-empty ID and "
                "a pairing token containing at least 32 characters"
            )

        request_timeout_seconds = float(
            os.getenv("AGENTBRIDGE_REQUEST_TIMEOUT", "180")
        )
        if not 10 <= request_timeout_seconds <= 900:
            raise RuntimeError(
                "AGENTBRIDGE_REQUEST_TIMEOUT must be between 10 and 900 seconds"
            )

        return cls(
            pairing_tokens=pairing_tokens,
            request_timeout_seconds=request_timeout_seconds,
        )

    def pairing_token_for(self, device_id: str) -> str | None:
        return self.pairing_tokens.get(device_id)
