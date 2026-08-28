import asyncio
from typing import Any

import pytest

from agentbridge_server.remote_bridge import ConnectorOfflineError, RemoteAgentBridge


class FakeConnectorSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.closed = False

    async def send_json(self, data: Any) -> None:
        self.messages.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_remote_bridge_routes_a_server_request_to_the_selected_device() -> None:
    bridge = RemoteAgentBridge()
    connector = FakeConnectorSocket()
    await bridge.register(connector, device_id="desk-a")

    task = asyncio.create_task(
        bridge.ask_chatgpt("What is 1+1?", device_id="desk-a", timeout_seconds=2)
    )
    await asyncio.sleep(0)
    request = connector.messages[-1]

    assert request["type"] == "ask.request"
    assert request["prompt"] == "What is 1+1?"
    await bridge.handle_connector_message(
        connector,
        device_id="desk-a",
        message={"type": "ask.response", "id": request["id"], "answer": "2"},
    )

    assert await task == "2"


@pytest.mark.asyncio
async def test_remote_bridge_reports_when_the_requested_device_is_offline() -> None:
    bridge = RemoteAgentBridge()

    with pytest.raises(ConnectorOfflineError, match="No connector is online"):
        await bridge.ask_chatgpt("hello", device_id="desk-a", timeout_seconds=1)


@pytest.mark.asyncio
async def test_replaced_connector_cannot_complete_a_new_request() -> None:
    bridge = RemoteAgentBridge()
    old_connector = FakeConnectorSocket()
    current_connector = FakeConnectorSocket()
    await bridge.register(old_connector, device_id="desk-a")
    await bridge.register(current_connector, device_id="desk-a")

    assert old_connector.closed is True
    task = asyncio.create_task(
        bridge.ask_chatgpt("hello", device_id="desk-a", timeout_seconds=2)
    )
    await asyncio.sleep(0)
    request = current_connector.messages[-1]

    await bridge.handle_connector_message(
        old_connector,
        device_id="desk-a",
        message={"type": "ask.response", "id": request["id"], "answer": "wrong"},
    )
    assert task.done() is False

    await bridge.handle_connector_message(
        current_connector,
        device_id="desk-a",
        message={"type": "ask.response", "id": request["id"], "answer": "right"},
    )
    assert await task == "right"
