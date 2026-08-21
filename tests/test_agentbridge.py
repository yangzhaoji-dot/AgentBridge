import asyncio
from typing import Any

import pytest

from agentbridge_server.bridge import AgentBridge, ExtensionOfflineError


class FakeExtensionSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.closed = False

    async def send_json(self, data: Any) -> None:
        self.messages.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_ask_chatgpt_round_trip() -> None:
    bridge = AgentBridge()
    socket = FakeExtensionSocket()
    await bridge.register(socket, client_id="edge-test", origin="chrome-extension://abc")

    task = asyncio.create_task(bridge.ask_chatgpt("What is 1+1?", timeout_seconds=2))
    await asyncio.sleep(0)
    request = socket.messages[-1]
    assert request["type"] == "ask.request"
    assert request["prompt"] == "What is 1+1?"

    await bridge.handle_extension_message(
        {"type": "ask.response", "id": request["id"], "answer": "2"}
    )
    assert await task == "2"


@pytest.mark.asyncio
async def test_offline_extension_returns_clear_error() -> None:
    bridge = AgentBridge()
    with pytest.raises(ExtensionOfflineError, match="offline"):
        await bridge.ask_chatgpt("hello", timeout_seconds=1)


@pytest.mark.asyncio
async def test_new_extension_replaces_old_connection() -> None:
    bridge = AgentBridge()
    first = FakeExtensionSocket()
    second = FakeExtensionSocket()
    await bridge.register(first, client_id="first", origin="chrome-extension://one")
    await bridge.register(second, client_id="second", origin="chrome-extension://two")
    assert first.closed is True
    status = await bridge.status()
    assert status["extension"]["client_id"] == "second"
