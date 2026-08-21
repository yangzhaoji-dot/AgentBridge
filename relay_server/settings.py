from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    shared_token: str
    hello_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("RELAY_SHARED_TOKEN")
        if not token:
            raise RuntimeError("RELAY_SHARED_TOKEN must be set")
        return cls(shared_token=token)
