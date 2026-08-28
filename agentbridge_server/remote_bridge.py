from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from agentbridge_server.bridge import make_completion_marker

class ConnectorSocket(Protocol):
    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


class ConnectorOfflineError(RuntimeError):
    pass


class ConnectorResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConnectorInfo:
    device_id: str
    connected_at: str


@dataclass(frozen=True)
class PendingRequest:
    device_id: str
    future: asyncio.Future[str]
    require_completion_marker: bool


class RemoteAgentBridge:
    """Routes server-side MCP calls to one outbound local connector per device."""

    def __init__(self) -> None:
        self._connectors: dict[str, ConnectorSocket] = {}
        self._connector_info: dict[str, ConnectorInfo] = {}
        self._pending: dict[str, PendingRequest] = {}
        self._connection_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._request_locks: dict[str, asyncio.Lock] = {}

    async def register(self, socket: ConnectorSocket, *, device_id: str) -> None:
        old_socket: ConnectorSocket | None
        async with self._connection_lock:
            old_socket = self._connectors.get(device_id)
            self._connectors[device_id] = socket
            self._connector_info[device_id] = ConnectorInfo(
                device_id=device_id,
                connected_at=datetime.now(timezone.utc).isoformat(),
            )

        if old_socket is not None and old_socket is not socket:
            await old_socket.close(code=4001, reason="replaced by a newer connector")

    async def unregister(self, socket: ConnectorSocket) -> None:
        offline_devices: list[str] = []
        async with self._connection_lock:
            for device_id, registered_socket in tuple(self._connectors.items()):
                if registered_socket is socket:
                    del self._connectors[device_id]
                    self._connector_info.pop(device_id, None)
                    offline_devices.append(device_id)

        if not offline_devices:
            return

        for request_id, pending in tuple(self._pending.items()):
            if pending.device_id in offline_devices:
                if not pending.future.done():
                    pending.future.set_exception(
                        ConnectorOfflineError(
                            f"Connector for device {pending.device_id!r} disconnected"
                        )
                    )
                self._pending.pop(request_id, None)

    async def status(self) -> dict[str, Any]:
        async with self._connection_lock:
            connectors = [
                {
                    "device_id": info.device_id,
                    "connected_at": info.connected_at,
                }
                for info in self._connector_info.values()
            ]
        return {
            "connector_count": len(connectors),
            "connectors": sorted(connectors, key=lambda item: item["device_id"]),
        }

    async def ask_chatgpt(
        self,
        prompt: str,
        *,
        device_id: str,
        timeout_seconds: float,
        require_completion_marker: bool = False,
    ) -> str:
        prompt = prompt.strip()
        device_id = device_id.strip()
        if not prompt:
            raise ValueError("prompt cannot be empty")
        if len(prompt) > 50_000:
            raise ValueError("prompt is too long; maximum is 50,000 characters")
        if not device_id:
            raise ValueError("device_id cannot be empty")

        request_lock = await self._request_lock_for(device_id)
        async with request_lock:
            async with self._connection_lock:
                socket = self._connectors.get(device_id)
            if socket is None:
                raise ConnectorOfflineError(
                    f"No connector is online for device {device_id!r}. "
                    "Start AgentBridge Connector on the computer that owns the "
                    "signed-in ChatGPT tab."
                )

            request_id = str(uuid4())
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self._pending[request_id] = PendingRequest(
                device_id, future, require_completion_marker
            )
            try:
                completion_marker = (
                    make_completion_marker() if require_completion_marker else None
                )
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
                    f"ChatGPT on device {device_id!r} did not finish within "
                    f"{timeout_seconds:.0f} seconds"
                ) from exc
            finally:
                self._pending.pop(request_id, None)

    async def handle_connector_message(
        self, socket: ConnectorSocket, *, device_id: str, message: dict[str, Any]
    ) -> None:
        async with self._connection_lock:
            if self._connectors.get(device_id) is not socket:
                return

        message_type = message.get("type")
        if message_type == "connector.ping":
            async with self._send_lock:
                await socket.send_json({"type": "connector.pong"})
            return

        request_id = message.get("id")
        if not isinstance(request_id, str):
            return
        pending = self._pending.get(request_id)
        if pending is None or pending.device_id != device_id or pending.future.done():
            return

        if message_type == "ask.response":
            answer = message.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                pending.future.set_exception(
                    ConnectorResponseError("ChatGPT returned an empty response")
                )
            else:
                if (
                    pending.require_completion_marker
                    and message.get("completion_verified") is not True
                ):
                    pending.future.set_exception(
                        ConnectorResponseError(
                            "Connector did not verify the completion marker"
                        )
                    )
                else:
                    pending.future.set_result(answer.strip())
        elif message_type == "ask.error":
            detail = message.get("error")
            pending.future.set_exception(
                ConnectorResponseError(str(detail or "unknown connector error"))
            )

    async def _request_lock_for(self, device_id: str) -> asyncio.Lock:
        async with self._connection_lock:
            return self._request_locks.setdefault(device_id, asyncio.Lock())
