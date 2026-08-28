from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from agentbridge_connector.service import EdgeConnectorService
from agentbridge_connector.settings import EdgeConnectorSettings


logger = logging.getLogger("agentbridge.connector.app")


def create_app(
    settings: EdgeConnectorSettings | None = None,
    service: EdgeConnectorService | None = None,
) -> FastAPI:
    """Serve the unchanged Edge extension on localhost and relay outward."""

    connector_settings = settings or EdgeConnectorSettings.load()
    connector_service = service or EdgeConnectorService(connector_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        remote_task = asyncio.create_task(connector_service.run_forever())
        try:
            yield
        finally:
            await connector_service.stop()
            remote_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await remote_task

    app = FastAPI(
        title="AgentBridge Local Connector",
        version="0.2.0-dev",
        lifespan=lifespan,
    )
    app.state.connector = connector_service

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {"name": "AgentBridge Local Connector", **(await connector_service.status())}

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return await connector_service.status()

    @app.get("/api/extension-config")
    async def extension_config() -> JSONResponse:
        response = JSONResponse(
            {
                "protocol_version": 1,
                "websocket_url": "ws://127.0.0.1:8765/ws",
                "token": connector_settings.local.token,
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.websocket("/ws")
    async def extension_websocket(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin", "")
        if not connector_settings.local.allow_non_extension_origin and not origin.startswith(
            "chrome-extension://"
        ):
            await websocket.close(code=4403, reason="extension origin required")
            return

        await websocket.accept()
        registered = False
        try:
            hello = await asyncio.wait_for(websocket.receive_json(), timeout=8)
            if not isinstance(hello, dict) or hello.get("type") != "hello":
                await websocket.close(code=4400, reason="hello required")
                return
            token = hello.get("token")
            if not isinstance(token, str) or not secrets.compare_digest(
                token, connector_settings.local.token
            ):
                await websocket.close(code=4401, reason="invalid token")
                return

            client_id = str(hello.get("client_id") or "edge-extension")
            await connector_service.bridge.register(
                websocket, client_id=client_id, origin=origin
            )
            registered = True
            await websocket.send_json({"type": "hello.ack", "protocol_version": 1})

            while True:
                message = await websocket.receive_json()
                if isinstance(message, dict):
                    await connector_service.bridge.handle_extension_message(message)
        except asyncio.TimeoutError:
            await websocket.close(code=4408, reason="hello timeout")
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("local extension websocket failed")
        finally:
            if registered:
                await connector_service.bridge.unregister(websocket)

    return app
