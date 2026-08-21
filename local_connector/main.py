from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from common.protocol import make_message, parse_message
from local_connector.codex_client import CodexAppServer
from local_connector.policy import (
    LEGACY_APPROVAL_METHODS,
    V2_APPROVAL_METHODS,
    approval_result,
    resolve_allowed_cwd,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("local_connector")


@dataclass(frozen=True)
class ConnectorSettings:
    relay_url: str
    shared_token: str
    device_id: str
    codex_bin: str
    codex_service_tier_override: str | None
    default_cwd: Path
    allowed_roots: list[Path]

    @classmethod
    def from_env(cls) -> "ConnectorSettings":
        shared_token = os.getenv("RELAY_SHARED_TOKEN")
        if not shared_token:
            raise RuntimeError("RELAY_SHARED_TOKEN must be set")
        default_cwd = Path(
            os.getenv("LOCAL_AGENT_DEFAULT_CWD", str(Path.cwd()))
        ).expanduser().resolve()
        roots_raw = os.getenv("LOCAL_AGENT_ALLOWED_ROOTS", str(default_cwd))
        allowed_roots = [
            Path(part).expanduser().resolve()
            for part in roots_raw.split(os.pathsep)
            if part.strip()
        ]
        return cls(
            relay_url=os.getenv("RELAY_URL", "ws://127.0.0.1:8000/ws"),
            shared_token=shared_token,
            device_id=os.getenv("LOCAL_AGENT_DEVICE_ID", socket.gethostname()),
            codex_bin=os.getenv("CODEX_BIN", "codex"),
            codex_service_tier_override=(
                os.getenv("CODEX_SERVICE_TIER_OVERRIDE") or None
            ),
            default_cwd=default_cwd,
            allowed_roots=allowed_roots,
        )


class LocalConnector:
    def __init__(self, settings: ConnectorSettings) -> None:
        self.settings = settings
        self.socket: ClientConnection | None = None
        self.codex = CodexAppServer(
            codex_bin=settings.codex_bin,
            process_cwd=settings.default_cwd,
            on_event=self._on_codex_event,
            service_tier_override=settings.codex_service_tier_override,
        )
        self.threads_by_cwd: dict[str, str] = {}
        self.active_thread_id: str | None = None
        self.active_turn_id: str | None = None
        self._operation_lock = asyncio.Lock()

    async def run_forever(self) -> None:
        await self.codex.start()
        delay = 1.0
        try:
            while True:
                try:
                    await self._run_relay_session()
                    delay = 1.0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("relay connection failed: %s", exc)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
        finally:
            await self.codex.close()

    async def _run_relay_session(self) -> None:
        logger.info("connecting to %s as %s", self.settings.relay_url, self.settings.device_id)
        async with websockets.connect(
            self.settings.relay_url,
            ping_interval=20,
            ping_timeout=20,
            max_size=1_000_000,
        ) as websocket:
            self.socket = websocket
            await self._send(
                make_message(
                    "hello",
                    {
                        "role": "agent",
                        "device_id": self.settings.device_id,
                        "token": self.settings.shared_token,
                    },
                )
            )
            hello = parse_message(await websocket.recv())
            if hello["type"] != "hello.ack":
                raise RuntimeError(f"relay rejected hello: {hello}")
            await self._send_status("ready")
            logger.info("connected; waiting for browser tasks")

            try:
                async for raw in websocket:
                    if not isinstance(raw, str):
                        continue
                    await self._handle_relay_message(parse_message(raw))
            finally:
                self.socket = None

    async def _handle_relay_message(self, message: dict[str, Any]) -> None:
        message_type = message["type"]
        payload = message["payload"]
        try:
            if message_type == "task.start":
                await self._start_task(payload, message.get("id"))
            elif message_type == "turn.steer":
                await self._steer_turn(payload, message.get("id"))
            elif message_type == "turn.interrupt":
                await self._interrupt_turn(message.get("id"))
            elif message_type == "approval.resolve":
                await self._resolve_approval(payload, message.get("id"))
            elif message_type == "connector.ping":
                await self._send_status("ready", reply_to=message.get("id"))
        except Exception as exc:
            logger.exception("failed to handle %s", message_type)
            await self._send(
                make_message(
                    "task.error",
                    {"message": str(exc), "source_type": message_type},
                    reply_to=message.get("id"),
                )
            )

    async def _start_task(self, payload: dict[str, Any], reply_to: str | None) -> None:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("task text is required")

        requested_cwd = payload.get("cwd") or str(self.settings.default_cwd)
        if not isinstance(requested_cwd, str):
            raise ValueError("cwd must be a string")
        cwd = resolve_allowed_cwd(requested_cwd, self.settings.allowed_roots)

        async with self._operation_lock:
            if self.active_turn_id is not None:
                raise RuntimeError("a Codex turn is already running; steer or interrupt it")

            cwd_key = os.path.normcase(str(cwd))
            thread_id = self.threads_by_cwd.get(cwd_key)
            if thread_id is None:
                thread_id = await self.codex.start_thread(cwd)
                self.threads_by_cwd[cwd_key] = thread_id

            response = await self.codex.start_turn(thread_id, text.strip(), cwd)
            self.active_thread_id = thread_id
            turn = response.get("turn", {})
            self.active_turn_id = turn.get("id") if isinstance(turn, dict) else None
            await self._send(
                make_message(
                    "task.accepted",
                    {
                        "thread_id": thread_id,
                        "turn_id": self.active_turn_id,
                        "cwd": str(cwd),
                    },
                    reply_to=reply_to,
                )
            )

    async def _steer_turn(self, payload: dict[str, Any], reply_to: str | None) -> None:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("steer text is required")
        if self.active_thread_id is None or self.active_turn_id is None:
            raise RuntimeError("there is no active turn")
        result = await self.codex.steer_turn(self.active_thread_id, text.strip())
        await self._send(make_message("turn.steered", result, reply_to=reply_to))

    async def _interrupt_turn(self, reply_to: str | None) -> None:
        if self.active_thread_id is None or self.active_turn_id is None:
            raise RuntimeError("there is no active turn")
        result = await self.codex.interrupt_turn(
            self.active_thread_id, self.active_turn_id
        )
        await self._send(make_message("turn.interrupted", result, reply_to=reply_to))

    async def _resolve_approval(
        self, payload: dict[str, Any], reply_to: str | None
    ) -> None:
        request_id = payload.get("request_id")
        approved = payload.get("approved")
        if not isinstance(approved, bool):
            raise ValueError("approved must be true or false")
        method = self.codex.server_request_method(request_id)
        if method is None:
            raise KeyError(f"approval request is no longer pending: {request_id}")
        result = approval_result(method, approved)
        await self.codex.respond_to_server(request_id, result)
        await self._send(
            make_message(
                "approval.resolved",
                {"request_id": request_id, "approved": approved},
                reply_to=reply_to,
            )
        )

    async def _on_codex_event(self, event: dict[str, Any]) -> None:
        kind = event["kind"]
        message = event.get("message", {})
        if kind == "server_request":
            method = message.get("method")
            event_type = (
                "approval.required"
                if method in V2_APPROVAL_METHODS | LEGACY_APPROVAL_METHODS
                else "interaction.required"
            )
            await self._send(
                make_message(
                    event_type,
                    {
                        "request_id": message.get("id"),
                        "method": method,
                        "params": message.get("params", {}),
                    },
                )
            )
            return

        if kind == "process_exited":
            self.active_thread_id = None
            self.active_turn_id = None
            await self._send_status("codex_stopped")
            return

        method = message.get("method")
        params = message.get("params", {})
        if method == "turn/started" and isinstance(params, dict):
            turn = params.get("turn", {})
            if isinstance(turn, dict):
                self.active_turn_id = turn.get("id")
            self.active_thread_id = params.get("threadId", self.active_thread_id)
        elif method == "turn/completed":
            self.active_turn_id = None

        await self._send(make_message("codex.event", {"message": message}))

    async def _send_status(self, state: str, reply_to: str | None = None) -> None:
        await self._send(
            make_message(
                "agent.status",
                {
                    "online": True,
                    "state": state,
                    "device_id": self.settings.device_id,
                    "default_cwd": str(self.settings.default_cwd),
                    "allowed_roots": [str(path) for path in self.settings.allowed_roots],
                },
                reply_to=reply_to,
            )
        )

    async def _send(self, message: dict[str, Any]) -> None:
        websocket = self.socket
        if websocket is None:
            logger.debug("dropped outbound message while relay is disconnected: %s", message["type"])
            return
        await websocket.send(json.dumps(message, ensure_ascii=False))


async def async_main() -> None:
    settings = ConnectorSettings.from_env()
    connector = LocalConnector(settings)
    await connector.run_forever()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
