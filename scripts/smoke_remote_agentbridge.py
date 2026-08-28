from __future__ import annotations

import argparse
import asyncio
import base64

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(url: str, device_id: str, prompt: str, timeout_seconds: float) -> None:
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10.0))
    async with httpx.AsyncClient(trust_env=False, timeout=timeout) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "ask_chatgpt",
                    {"prompt": prompt, "device_id": device_id},
                )
                texts = [
                    item.text for item in result.content if getattr(item, "text", None)
                ]
                if not texts:
                    raise RuntimeError(f"ask_chatgpt returned no text: {result}")
                print("AgentBridge remote web-AI response:")
                print("\n".join(texts))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Call a paired webpage AI through the server-side AgentBridge MCP relay"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--device-id", required=True)
    parser.add_argument(
        "--prompt",
        default="请只回复 AgentBridge remote smoke test OK。",
    )
    parser.add_argument(
        "--prompt-base64",
        help="UTF-8 prompt encoded as base64; takes precedence over --prompt",
    )
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 900:
        raise SystemExit("--timeout must be between 10 and 900 seconds")
    prompt = args.prompt
    if args.prompt_base64:
        try:
            prompt = base64.b64decode(args.prompt_base64, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise SystemExit("--prompt-base64 must be valid UTF-8 base64") from exc
    asyncio.run(run(args.url, args.device_id, prompt, args.timeout))


if __name__ == "__main__":
    main()
