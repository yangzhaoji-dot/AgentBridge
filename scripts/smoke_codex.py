from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from local_connector.codex_client import CodexAppServer


async def run(
    cwd: Path, codex_bin: str, service_tier_override: str | None
) -> None:
    async def on_event(event: dict[str, Any]) -> None:
        if event.get("kind") == "process_exited":
            print("Codex App Server exited")

    client = CodexAppServer(
        codex_bin=codex_bin,
        process_cwd=cwd,
        on_event=on_event,
        service_tier_override=service_tier_override,
    )
    await client.start()
    try:
        result = await client.request(
            "thread/start",
            {
                "cwd": str(cwd),
                "approvalPolicy": "on-request",
                "sandbox": "read-only",
                "ephemeral": True,
            },
        )
        thread_id = result.get("thread", {}).get("id")
        if not thread_id:
            raise RuntimeError("thread/start 没有返回 thread id")
        print(f"Handshake succeeded; ephemeral thread id: {thread_id}")
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="验证本机 Codex App Server 握手")
    parser.add_argument("--cwd", default=str(Path.cwd()))
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--service-tier-override", choices=["fast", "flex"])
    args = parser.parse_args()
    asyncio.run(
        run(
            Path(args.cwd).expanduser().resolve(),
            args.codex_bin,
            args.service_tier_override,
        )
    )


if __name__ == "__main__":
    main()
