from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from agentbridge_connector.settings import EdgeConnectorSettings
from agentbridge_server.bridge import AgentBridge, validate_completion_marker


logger = logging.getLogger("agentbridge.connector")
RemoteSender = Callable[[dict[str, Any]], Awaitable[None]]


class EdgeConnectorService:
    """Maintains an outbound relay connection while serving the local extension."""

    def __init__(
        self,
        settings: EdgeConnectorSettings,
        *,
        bridge: AgentBridge | None = None,
    ) -> None:
        self.settings = settings
        self.bridge = bridge or AgentBridge()
        self._remote_socket: ClientConnection | None = None
        self._remote_send_lock = asyncio.Lock()
        self._stopping = asyncio.Event()
        self._request_tasks: set[asyncio.Task[None]] = set()
        self.remote_connected = False

    async def run_forever(self) -> None:
        delay = 1.0
        while not self._stopping.is_set():
            try:
                await self._run_remote_session()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._stopping.is_set():
                    logger.warning("remote relay connection failed: %s", exc)
                    await self._wait_or_stop(delay)
                    delay = min(delay * 2, self.settings.reconnect_max_seconds)

    async def stop(self) -> None:
        self._stopping.set()
        remote_socket = self._remote_socket
        if remote_socket is not None:
            await remote_socket.close(code=1001, reason="connector stopping")
        pending_tasks = tuple(self._request_tasks)
        for task in pending_tasks:
            task.cancel()
        for task in pending_tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def status(self) -> dict[str, Any]:
        return {
            "remote_connected": self.remote_connected,
            "remote_ws_url": self.settings.remote_ws_url,
            "device_id": self.settings.device_id,
            **(await self.bridge.status()),
        }

    async def handle_remote_message(
        self, message: dict[str, Any], *, sender: RemoteSender | None = None
    ) -> None:
        message_type = message.get("type")
        if message_type == "connector.ping":
            await (sender or self._send_remote)({"type": "connector.pong"})
            return
        if message_type != "ask.request":
            return

        request_id = message.get("id")
        prompt = message.get("prompt")
        timeout_ms = message.get("timeout_ms")
        completion_marker = message.get("completion_marker")
        if not isinstance(request_id, str) or not request_id:
            return
        if not isinstance(prompt, str):
            await (sender or self._send_remote)(
                {
                    "type": "ask.error",
                    "id": request_id,
                    "error": "relay supplied a non-text prompt",
                }
            )
            return
        if not isinstance(timeout_ms, int) or not 10_000 <= timeout_ms <= 900_000:
            await (sender or self._send_remote)(
                {
                    "type": "ask.error",
                    "id": request_id,
                    "error": "relay supplied an invalid timeout_ms",
                }
            )
            return
        try:
            completion_marker = validate_completion_marker(completion_marker)
        except ValueError as exc:
            await (sender or self._send_remote)(
                {"type": "ask.error", "id": request_id, "error": str(exc)}
            )
            return

        response_sender = sender or self._send_remote
        try:
            result = await self.bridge.ask_chatgpt_result(
                prompt,
                timeout_seconds=timeout_ms / 1000,
                completion_marker=completion_marker,
            )
            await response_sender(
                {
                    "type": "ask.response",
                    "id": request_id,
                    "answer": result.text,
                    "completion_verified": result.completion_verified,
                }
            )
        except Exception as exc:
            await response_sender(
                {"type": "ask.error", "id": request_id, "error": str(exc)}
            )

    async def _run_remote_session(self) -> None:
        logger.info(
            "connecting to remote relay %s as %s",
            self.settings.remote_ws_url,
            self.settings.device_id,
        )
        async with websockets.connect(
            self.settings.remote_ws_url,
            ping_interval=20,
            ping_timeout=20,
            max_size=1_000_000,
        ) as websocket:
            self._remote_socket = websocket
            try:
                await self._send_remote(
                    {
                        "type": "connector.hello",
                        "protocol_version": 1,
                        "device_id": self.settings.device_id,
                        "token": self.settings.pairing_token,
                    }
                )
                raw_hello = await asyncio.wait_for(websocket.recv(), timeout=10)
                hello = self._decode_message(raw_hello)
                if hello.get("type") != "connector.hello.ack":
                    raise RuntimeError(f"remote relay rejected connector hello: {hello}")
                self.remote_connected = True
                logger.info("remote relay connected")

                async for raw_message in websocket:
                    message = self._decode_message(raw_message)
                    task = asyncio.create_task(self.handle_remote_message(message))
                    self._request_tasks.add(task)
                    task.add_done_callback(self._request_tasks.discard)
            finally:
                self.remote_connected = False
                self._remote_socket = None

    async def _send_remote(self, message: dict[str, Any]) -> None:
        socket = self._remote_socket
        if socket is None:
            raise RuntimeError("remote relay is disconnected")
        async with self._remote_send_lock:
            await socket.send(json.dumps(message, ensure_ascii=False))

    async def _wait_or_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    @staticmethod
    def _decode_message(raw: str | bytes) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise RuntimeError("remote relay sent a non-text WebSocket frame")
        message = json.loads(raw)
        if not isinstance(message, dict):
            raise RuntimeError("remote relay sent a non-object JSON message")
        return message
