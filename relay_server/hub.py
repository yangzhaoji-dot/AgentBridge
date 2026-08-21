from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Protocol

from common.protocol import make_message


class WebSocketLike(Protocol):
    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


BROWSER_MESSAGE_TYPES = {
    "task.start",
    "turn.interrupt",
    "turn.steer",
    "approval.resolve",
    "interaction.resolve",
    "connector.ping",
}


class RelayHub:
    def __init__(self) -> None:
        self._agents: dict[str, WebSocketLike] = {}
        self._browsers: dict[str, set[WebSocketLike]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def register(self, role: str, device_id: str, socket: WebSocketLike) -> None:
        old_agent: WebSocketLike | None = None
        async with self._lock:
            if role == "agent":
                old_agent = self._agents.get(device_id)
                self._agents[device_id] = socket
            else:
                self._browsers[device_id].add(socket)

        if old_agent is not None and old_agent is not socket:
            await old_agent.close(code=4001, reason="replaced by a newer connector")

        if role == "agent":
            await self.broadcast_to_browsers(
                device_id,
                make_message("agent.status", {"online": True, "state": "connected"}),
            )

    async def unregister(self, role: str, device_id: str, socket: WebSocketLike) -> None:
        agent_went_offline = False
        async with self._lock:
            if role == "agent" and self._agents.get(device_id) is socket:
                del self._agents[device_id]
                agent_went_offline = True
            elif role == "browser":
                browsers = self._browsers.get(device_id)
                if browsers is not None:
                    browsers.discard(socket)
                    if not browsers:
                        self._browsers.pop(device_id, None)

        if agent_went_offline:
            await self.broadcast_to_browsers(
                device_id,
                make_message("agent.status", {"online": False, "state": "disconnected"}),
            )

    async def agent_is_online(self, device_id: str) -> bool:
        async with self._lock:
            return device_id in self._agents

    async def route(
        self,
        sender_role: str,
        device_id: str,
        message: dict[str, Any],
    ) -> None:
        if sender_role == "browser":
            if message["type"] not in BROWSER_MESSAGE_TYPES:
                raise ValueError(f"browser cannot send message type {message['type']!r}")
            async with self._lock:
                agent = self._agents.get(device_id)
            if agent is None:
                raise LookupError("local agent is offline")
            await agent.send_json(message)
            return

        await self.broadcast_to_browsers(device_id, message)

    async def broadcast_to_browsers(
        self, device_id: str, message: dict[str, Any]
    ) -> None:
        async with self._lock:
            browsers = list(self._browsers.get(device_id, set()))

        stale: list[WebSocketLike] = []
        for browser in browsers:
            try:
                await browser.send_json(message)
            except Exception:
                stale.append(browser)

        if stale:
            async with self._lock:
                live = self._browsers.get(device_id)
                if live is not None:
                    for browser in stale:
                        live.discard(browser)
                    if not live:
                        self._browsers.pop(device_id, None)
