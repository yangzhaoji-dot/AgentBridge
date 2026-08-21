from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


PROTOCOL_VERSION = 1
MAX_MESSAGE_CHARS = 1_000_000


class ProtocolError(ValueError):
    """Raised when a relay message does not match the small public protocol."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_message(
    message_type: str,
    payload: dict[str, Any] | None = None,
    *,
    message_id: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "id": message_id or str(uuid4()),
        "type": message_type,
        "protocol_version": PROTOCOL_VERSION,
        "timestamp": utc_now(),
        "payload": payload or {},
    }
    if reply_to is not None:
        message["reply_to"] = reply_to
    return message


def parse_message(raw: str) -> dict[str, Any]:
    if len(raw) > MAX_MESSAGE_CHARS:
        raise ProtocolError("message is too large")

    try:
        message = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("message is not valid JSON") from exc

    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")

    message_type = message.get("type")
    if not isinstance(message_type, str) or not message_type.strip():
        raise ProtocolError("message.type must be a non-empty string")

    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        raise ProtocolError("message.payload must be an object")

    version = message.get("protocol_version", PROTOCOL_VERSION)
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {version}")

    message["payload"] = payload
    message["protocol_version"] = version
    return message
