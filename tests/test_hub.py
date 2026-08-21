from typing import Any

import pytest

from common.protocol import make_message
from relay_server.hub import RelayHub


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.closed = False

    async def send_json(self, data: Any) -> None:
        self.messages.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_browser_and_agent_messages_are_routed_both_ways() -> None:
    hub = RelayHub()
    browser = FakeSocket()
    agent = FakeSocket()
    await hub.register("browser", "device-a", browser)
    await hub.register("agent", "device-a", agent)

    request = make_message("task.start", {"text": "hello"})
    await hub.route("browser", "device-a", request)
    assert agent.messages[-1] == request

    event = make_message("codex.event", {"message": {"method": "turn/started"}})
    await hub.route("agent", "device-a", event)
    assert browser.messages[-1] == event


@pytest.mark.asyncio
async def test_browser_gets_clear_error_when_agent_is_offline() -> None:
    hub = RelayHub()
    with pytest.raises(LookupError, match="offline"):
        await hub.route("browser", "missing", make_message("task.start", {}))
