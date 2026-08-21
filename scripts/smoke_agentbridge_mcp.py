from __future__ import annotations

import argparse
import asyncio

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(url: str) -> None:
    async with httpx.AsyncClient(trust_env=False) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [tool.name for tool in tools.tools]
                if "ask_chatgpt" not in names:
                    raise RuntimeError(f"ask_chatgpt missing; available tools: {names}")
                print("MCP handshake succeeded; tools:", ", ".join(names))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify AgentBridge MCP endpoint")
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    args = parser.parse_args()
    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()
