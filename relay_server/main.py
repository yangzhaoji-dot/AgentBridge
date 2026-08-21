from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from common.protocol import ProtocolError, make_message, parse_message
from relay_server.hub import RelayHub
from relay_server.settings import Settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("relay")

settings = Settings.from_env()
hub = RelayHub()
web_dir = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Web Local Agent Relay", version="0.1.0")
app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(web_dir / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status/{device_id}")
async def device_status(device_id: str) -> dict[str, object]:
    return {
        "device_id": device_id,
        "agent_online": await hub.agent_is_online(device_id),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    role: Literal["browser", "agent"] | None = None
    device_id: str | None = None

    try:
        raw_hello = await asyncio.wait_for(
            websocket.receive_text(), timeout=settings.hello_timeout_seconds
        )
        hello = parse_message(raw_hello)
        if hello["type"] != "hello":
            raise ProtocolError("the first message must be hello")

        payload = hello["payload"]
        candidate_role = payload.get("role")
        candidate_device_id = payload.get("device_id")
        token = payload.get("token")

        if candidate_role not in {"browser", "agent"}:
            raise ProtocolError("hello.payload.role must be browser or agent")
        if not isinstance(candidate_device_id, str) or not candidate_device_id.strip():
            raise ProtocolError("hello.payload.device_id is required")
        if not isinstance(token, str) or not secrets.compare_digest(
            token, settings.shared_token
        ):
            await websocket.close(code=4401, reason="invalid token")
            return

        role = candidate_role
        device_id = candidate_device_id.strip()
        await hub.register(role, device_id, websocket)
        await websocket.send_json(
            make_message(
                "hello.ack",
                {
                    "role": role,
                    "device_id": device_id,
                    "agent_online": await hub.agent_is_online(device_id),
                },
                reply_to=hello.get("id"),
            )
        )

        while True:
            raw = await websocket.receive_text()
            message = parse_message(raw)
            try:
                await hub.route(role, device_id, message)
            except (LookupError, ValueError) as exc:
                await websocket.send_json(
                    make_message(
                        "relay.error",
                        {"message": str(exc)},
                        reply_to=message.get("id"),
                    )
                )
    except asyncio.TimeoutError:
        await websocket.close(code=4408, reason="hello timeout")
    except ProtocolError as exc:
        await websocket.send_json(make_message("relay.error", {"message": str(exc)}))
        await websocket.close(code=4400, reason="protocol error")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("websocket session failed")
    finally:
        if role is not None and device_id is not None:
            await hub.unregister(role, device_id, websocket)
