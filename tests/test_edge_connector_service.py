import asyncio
from typing import Any

import pytest

from agentbridge_connector.service import EdgeConnectorService
from agentbridge_connector.settings import EdgeConnectorSettings
from agentbridge_server.settings import AgentBridgeSettings


class FakeExtensionSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, data: Any) -> None:
        self.messages.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        pass


def make_settings() -> EdgeConnectorSettings:
    return EdgeConnectorSettings(
        local=AgentBridgeSettings(
            token="A" * 32,
            request_timeout_seconds=180,
            allow_non_extension_origin=False,
        ),
        remote_ws_url="wss://bridge.example.test/ws/connector",
        pairing_token="B" * 32,
        device_id="desk-a",
    )


def test_connector_settings_rejects_credentials_embedded_in_a_relay_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTBRIDGE_REMOTE_WS_URL", "wss://user:secret@bridge.example.test/ws/connector"
    )

    with pytest.raises(RuntimeError, match="must not contain credentials"):
        EdgeConnectorSettings.load()


@pytest.mark.asyncio
async def test_connector_forwards_remote_request_to_the_local_extension() -> None:
    service = EdgeConnectorService(make_settings())
    extension = FakeExtensionSocket()
    await service.bridge.register(
        extension, client_id="edge-test", origin="chrome-extension://example"
    )
    replies: list[dict[str, Any]] = []

    async def send_reply(message: dict[str, Any]) -> None:
        replies.append(message)

    task = asyncio.create_task(
        service.handle_remote_message(
            {
                "type": "ask.request",
                "id": "remote-request",
                "prompt": "What is 1+1?",
                "timeout_ms": 20_000,
                "completion_marker": "AGENTBRIDGE_DONE_test",
            },
            sender=send_reply,
        )
    )
    await asyncio.sleep(0)
    extension_request = extension.messages[-1]
    assert extension_request["type"] == "ask.request"
    assert extension_request["prompt"] == "What is 1+1?"
    assert extension_request["completion_marker"] == "AGENTBRIDGE_DONE_test"

    await service.bridge.handle_extension_message(
        {
            "type": "ask.response",
            "id": extension_request["id"],
            "answer": "2",
        }
    )
    await task
    assert replies == [{"type": "ask.response", "id": "remote-request", "answer": "2"}]


@pytest.mark.asyncio
async def test_connector_rejects_an_invalid_remote_timeout() -> None:
    service = EdgeConnectorService(make_settings())
    replies: list[dict[str, Any]] = []

    async def send_reply(message: dict[str, Any]) -> None:
        replies.append(message)

    await service.handle_remote_message(
        {
            "type": "ask.request",
            "id": "remote-request",
            "prompt": "hello",
            "timeout_ms": 1,
        },
        sender=send_reply,
    )
    assert replies == [
        {
            "type": "ask.error",
            "id": "remote-request",
            "error": "relay supplied an invalid timeout_ms",
        }
    ]
