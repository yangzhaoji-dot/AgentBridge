import asyncio
import json
import socket
from collections.abc import Callable
from typing import Any

import pytest
import uvicorn
import websockets
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agentbridge_connector.app import create_app as create_connector_app
from agentbridge_connector.service import EdgeConnectorService
from agentbridge_connector.settings import EdgeConnectorSettings
from agentbridge_server.remote_app import create_app as create_remote_app
from agentbridge_server.remote_bridge import RemoteAgentBridge
from agentbridge_server.remote_settings import RemoteRelaySettings
from agentbridge_server.settings import AgentBridgeSettings


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def start_server(app: Any, port: int) -> tuple[uvicorn.Server, asyncio.Task[None]]:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            return server, task
        await asyncio.sleep(0.02)
    server.should_exit = True
    await task
    raise RuntimeError(f"Uvicorn did not start on port {port}")


async def stop_server(server: uvicorn.Server, task: asyncio.Task[None]) -> None:
    server.should_exit = True
    try:
        await asyncio.wait_for(task, timeout=5)
    except asyncio.TimeoutError:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def wait_for(predicate: Callable[[], bool], *, timeout_seconds: float = 3) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("condition did not become true")


async def call_remote_mcp_tool(url: str, device_id: str) -> str:
    async with httpx.AsyncClient(trust_env=False) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert "ask_chatgpt" in [tool.name for tool in tools.tools]
                result = await session.call_tool(
                    "ask_chatgpt",
                    {"prompt": "What is 1+1?", "device_id": device_id},
                )
                texts = [
                    item.text for item in result.content if getattr(item, "text", None)
                ]
                assert texts == ["2"]
                return texts[0]


@pytest.mark.asyncio
async def test_remote_relay_connector_and_extension_complete_a_two_websocket_round_trip() -> None:
    pairing_token = "P" * 32
    local_token = "L" * 32
    remote_port = available_port()
    connector_port = available_port()

    remote_bridge = RemoteAgentBridge()
    remote_app = create_remote_app(
        RemoteRelaySettings(
            pairing_tokens={"integration-desktop": pairing_token},
            request_timeout_seconds=20,
        ),
        remote_bridge,
    )
    remote_server, remote_task = await start_server(remote_app, remote_port)
    connector_server: uvicorn.Server | None = None
    connector_task: asyncio.Task[None] | None = None

    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{remote_port}/ws/connector"
        ) as unapproved_connector:
            await unapproved_connector.send(
                json.dumps(
                    {
                        "type": "connector.hello",
                        "device_id": "unapproved-device",
                        "token": pairing_token,
                    }
                )
            )
            with pytest.raises(websockets.exceptions.ConnectionClosedError) as closed:
                await unapproved_connector.recv()
            assert closed.value.rcvd is not None
            assert closed.value.rcvd.code == 4401

        connector_settings = EdgeConnectorSettings(
            local=AgentBridgeSettings(
                token=local_token,
                request_timeout_seconds=20,
                allow_non_extension_origin=False,
            ),
            remote_ws_url=f"ws://127.0.0.1:{remote_port}/ws/connector",
            pairing_token=pairing_token,
            device_id="integration-desktop",
        )
        connector_service = EdgeConnectorService(connector_settings)
        connector_app = create_connector_app(connector_settings, connector_service)
        connector_server, connector_task = await start_server(connector_app, connector_port)

        await wait_for(lambda: connector_service.remote_connected)
        async with websockets.connect(
            f"ws://127.0.0.1:{connector_port}/ws",
            origin="chrome-extension://integration-test",
        ) as extension_socket:
            await extension_socket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "token": local_token,
                        "client_id": "integration-edge",
                    }
                )
            )
            hello_ack = json.loads(await extension_socket.recv())
            assert hello_ack["type"] == "hello.ack"

            answer_task = asyncio.create_task(
                call_remote_mcp_tool(
                    f"http://127.0.0.1:{remote_port}/mcp", "integration-desktop"
                )
            )
            extension_request = json.loads(await extension_socket.recv())
            assert extension_request["type"] == "ask.request"
            assert extension_request["prompt"] == "What is 1+1?"

            await extension_socket.send(
                json.dumps(
                    {
                        "type": "ask.response",
                        "id": extension_request["id"],
                        "answer": "2",
                    }
                )
            )
            assert await answer_task == "2"
    finally:
        if connector_server is not None and connector_task is not None:
            await stop_server(connector_server, connector_task)
        await stop_server(remote_server, remote_task)
