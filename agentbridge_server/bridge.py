from __future__ import annotations

import asyncio
import re
import secrets
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4


class ExtensionSocket(Protocol):
    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


class ExtensionOfflineError(RuntimeError):
    pass


class ExtensionResponseError(RuntimeError):
    pass


COMPLETION_MARKER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")


def validate_completion_marker(marker: str | None) -> str | None:
    if marker is None:
        return None
    if not isinstance(marker, str) or not COMPLETION_MARKER_PATTERN.fullmatch(marker):
        raise ValueError("completion_marker must be 8-128 safe marker characters")
    return marker


def make_completion_marker() -> str:
    return f"AGENTBRIDGE_DONE_{secrets.token_hex(16)}"


def make_completion_marker() -> str:
    return f"AGENTBRIDGE_DONE_{secrets.token_hex(16)}"


@dataclass(frozen=True)
class ExtensionInfo:
    client_id: str
    origin: str
    connected_at: str


class AgentBridge:
    """Owns one Edge extension connection and one in-flight ChatGPT request."""

    def __init__(self) -> None:
        self._socket: ExtensionSocket | None = None
        self._extension_info: ExtensionInfo | None = None
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._connection_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

    async def register(
        self, socket: ExtensionSocket, *, client_id: str, origin: str
    ) -> None:
        old_socket: ExtensionSocket | None = None
        async with self._connection_lock:
            if self._socket is not socket:
                old_socket = self._socket
            self._socket = socket
            self._extension_info = ExtensionInfo(
                client_id=client_id,
                origin=origin,
                connected_at=datetime.now(timezone.utc).isoformat(),
            )

        if old_socket is not None:
            await old_socket.close(code=4001, reason="replaced by a newer extension")

    async def unregister(self, socket: ExtensionSocket) -> None:
        went_offline = False
        async with self._connection_lock:
            if self._socket is socket:
                self._socket = None
                self._extension_info = None
                went_offline = True

        if went_offline:
            error = ExtensionOfflineError("Edge extension disconnected")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    async def status(self) -> dict[str, Any]:
        async with self._connection_lock:
            info = self._extension_info
        return {
            "extension_online": info is not None,
            "busy": self._request_lock.locked(),
            "extension": (
                {
                    "client_id": info.client_id,
                    "origin": info.origin,
                    "connected_at": info.connected_at,
                }
                if info
                else None
            ),
        }

    async def ask_chatgpt(
        self,
        prompt: str,
        *,
        timeout_seconds: float,
        completion_marker: str | None = None,
    ) -> str:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt cannot be empty")
        if len(prompt) > 50_000:
            raise ValueError("prompt is too long; maximum is 50,000 characters")
        completion_marker = validate_completion_marker(completion_marker)

        async with self._request_lock:
            async with self._connection_lock:
                socket = self._socket
            if socket is None:
                raise ExtensionOfflineError(
                    "Edge extension is offline. Open Edge with the AgentBridge "
                    "extension enabled and keep one signed-in chatgpt.com tab open."
                )

            request_id = str(uuid4())
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
            try:
                async with self._send_lock:
                    request = {
                        "type": "ask.request",
                        "id": request_id,
                        "prompt": prompt,
                        "timeout_ms": int(timeout_seconds * 1000),
                    }
                    if completion_marker is not None:
                        request["completion_marker"] = completion_marker
                    await socket.send_json(request)
                return await asyncio.wait_for(future, timeout=timeout_seconds + 5)
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"ChatGPT webpage did not finish within {timeout_seconds:.0f} seconds"
                ) from exc
            finally:
                self._pending.pop(request_id, None)

    async def handle_extension_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "ping":
            async with self._connection_lock:
                socket = self._socket
            if socket is not None:
                async with self._send_lock:
                    await socket.send_json({"type": "pong"})
            return

        request_id = message.get("id")
        if not isinstance(request_id, str):
            return
        future = self._pending.get(request_id)
        if future is None or future.done():
            return

        if message_type == "ask.response":
            answer = message.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                future.set_exception(
                    ExtensionResponseError("ChatGPT returned an empty response")
                )
            else:
                future.set_result(answer.strip())
        elif message_type == "ask.error":
            detail = message.get("error")
            future.set_exception(
                ExtensionResponseError(str(detail or "unknown extension error"))
            )
