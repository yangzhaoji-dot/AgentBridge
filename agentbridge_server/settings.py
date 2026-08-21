from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentBridgeSettings:
    token: str
    request_timeout_seconds: float
    allow_non_extension_origin: bool

    @classmethod
    def load(cls) -> "AgentBridgeSettings":
        project_root = Path(__file__).resolve().parent.parent
        runtime_dir = project_root / ".runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        token_path = runtime_dir / "agentbridge-token.txt"

        token = os.getenv("AGENTBRIDGE_TOKEN", "").strip()
        if not token:
            if token_path.is_file():
                token = token_path.read_text(encoding="utf-8-sig").strip()
            else:
                token = secrets.token_hex(32).upper()
                token_path.write_text(token, encoding="utf-8")

        if len(token) < 32:
            raise RuntimeError("AGENTBRIDGE_TOKEN must contain at least 32 characters")

        timeout = float(os.getenv("AGENTBRIDGE_REQUEST_TIMEOUT", "180"))
        if timeout < 10 or timeout > 900:
            raise RuntimeError("AGENTBRIDGE_REQUEST_TIMEOUT must be between 10 and 900")

        allow_non_extension = os.getenv(
            "AGENTBRIDGE_ALLOW_NON_EXTENSION_ORIGIN", ""
        ).lower() in {"1", "true", "yes"}

        return cls(
            token=token,
            request_timeout_seconds=timeout,
            allow_non_extension_origin=allow_non_extension,
        )
