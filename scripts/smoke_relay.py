from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any
from uuid import uuid4

import websockets

from common.protocol import make_message, parse_message


async def receive_message(socket: Any, timeout: float = 15) -> dict[str, Any]:
    raw = await asyncio.wait_for(socket.recv(), timeout=timeout)
    if not isinstance(raw, str):
        raise RuntimeError("relay returned a binary frame")
    return parse_message(raw)


async def run(url: str, token: str, device_id: str, prompt: str | None) -> None:
    async with websockets.connect(url, max_size=1_000_000) as socket:
        await socket.send(
            json.dumps(
                make_message(
                    "hello",
                    {"role": "browser", "device_id": device_id, "token": token},
                ),
                ensure_ascii=False,
            )
        )
        hello = await receive_message(socket)
        if hello["type"] != "hello.ack":
            raise RuntimeError(f"unexpected hello response: {hello}")
        if not hello["payload"].get("agent_online"):
            raise RuntimeError("relay is online but local connector is offline")
        print("Browser -> relay handshake succeeded")

        ping_id = str(uuid4())
        await socket.send(
            json.dumps(
                make_message("connector.ping", message_id=ping_id), ensure_ascii=False
            )
        )
        while True:
            status = await receive_message(socket)
            if status["type"] == "agent.status" and status.get("reply_to") == ping_id:
                break
        print("Relay -> connector -> browser round trip succeeded")

        if not prompt:
            return

        await socket.send(
            json.dumps(
                make_message("task.start", {"text": prompt, "cwd": None}),
                ensure_ascii=False,
            )
        )
        answer: list[str] = []
        while True:
            event = await receive_message(socket, timeout=120)
            if event["type"] == "task.error":
                raise RuntimeError(event["payload"].get("message", "task failed"))
            if event["type"] != "codex.event":
                continue
            codex_message = event["payload"].get("message", {})
            method = codex_message.get("method")
            params = codex_message.get("params", {})
            if method == "item/agentMessage/delta":
                answer.append(params.get("delta", ""))
            elif method == "error":
                detail = params.get("error", params)
                raise RuntimeError(f"Codex error: {detail}")
            elif method == "turn/completed":
                break

        print("Codex turn completed")
        print("Agent answer:", json.dumps("".join(answer).strip(), ensure_ascii=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify relay and connector routing")
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws")
    parser.add_argument("--token", required=True)
    parser.add_argument("--device-id", default="local-dev")
    parser.add_argument("--prompt")
    args = parser.parse_args()
    asyncio.run(run(args.url, args.token, args.device_id, args.prompt))


if __name__ == "__main__":
    main()
