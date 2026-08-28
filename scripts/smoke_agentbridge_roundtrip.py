from __future__ import annotations

import asyncio
import json

import httpx
import websockets
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


CONFIG_URL = "http://127.0.0.1:8765/api/extension-config"
MCP_URL = "http://127.0.0.1:8765/mcp"


async def fake_edge_extension(ready: asyncio.Event) -> None:
    async with httpx.AsyncClient(trust_env=False) as client:
        config = (await client.get(CONFIG_URL)).json()

    async with websockets.connect(
        config["websocket_url"], origin="chrome-extension://agentbridge-smoke"
    ) as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "hello",
                    "token": config["token"],
                    "client_id": "agentbridge-smoke",
                    "protocol_version": 1,
                }
            )
        )
        hello = json.loads(await socket.recv())
        if hello.get("type") != "hello.ack":
            raise RuntimeError(f"extension hello failed: {hello}")
        ready.set()

        async for raw in socket:
            message = json.loads(raw)
            if message.get("type") == "ask.request":
                await socket.send(
                    json.dumps(
                        {
                            "type": "ask.response",
                            "id": message["id"],
                            "answer": "FAKE_CHATGPT_OK",
                            "completion_verified": bool(message.get("completion_marker")),
                        }
                    )
                )
            elif message.get("type") == "pong":
                continue


async def call_mcp_tool(ready: asyncio.Event) -> None:
    await asyncio.wait_for(ready.wait(), timeout=5)
    async with httpx.AsyncClient(trust_env=False) as http_client:
        async with streamable_http_client(MCP_URL, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "ask_chatgpt", {"prompt": "smoke test"}
                )
                texts = [
                    item.text for item in result.content if getattr(item, "text", None)
                ]
                if "FAKE_CHATGPT_OK" not in texts:
                    raise RuntimeError(f"unexpected MCP tool result: {result}")
                print("Full MCP -> WebSocket -> extension round trip succeeded")


async def run() -> None:
    ready = asyncio.Event()
    extension_task = asyncio.create_task(fake_edge_extension(ready))
    try:
        await call_mcp_tool(ready)
    finally:
        extension_task.cancel()
        try:
            await extension_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(run())
