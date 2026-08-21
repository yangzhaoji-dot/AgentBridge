from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any


logger = logging.getLogger("local_connector.codex")
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
JsonRpcId = str | int


class CodexAppServerError(RuntimeError):
    pass


class CodexAppServer:
    def __init__(
        self,
        *,
        codex_bin: str,
        process_cwd: Path,
        on_event: EventHandler,
        service_tier_override: str | None = None,
    ) -> None:
        self.codex_bin = codex_bin
        self.process_cwd = process_cwd
        self.on_event = on_event
        if service_tier_override not in {None, "fast", "flex"}:
            raise ValueError("service_tier_override must be fast, flex, or unset")
        self.service_tier_override = service_tier_override
        self.process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[JsonRpcId, asyncio.Future[dict[str, Any]]] = {}
        self._server_requests: dict[JsonRpcId, str] = {}
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.process is not None and self.process.returncode is None:
            return

        executable = shutil.which(self.codex_bin) or self.codex_bin
        codex_args: list[str] = []
        if self.service_tier_override:
            codex_args.extend(
                ["-c", f'service_tier="{self.service_tier_override}"']
            )
        codex_args.extend(["app-server", "--listen", "stdio://"])

        command = [executable, *codex_args]
        if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
            shim_dir = Path(executable).parent
            entrypoint_candidates = [
                shim_dir / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            ]
            if shim_dir.name.lower() == ".bin":
                entrypoint_candidates.insert(
                    0, shim_dir.parent / "@openai" / "codex" / "bin" / "codex.js"
                )
            npm_entrypoint = next(
                (path for path in entrypoint_candidates if path.is_file()), None
            )
            node = shutil.which("node")
            if npm_entrypoint is not None and node:
                command = [node, str(npm_entrypoint), *codex_args]
            else:
                command = [
                    os.environ.get("COMSPEC", "cmd.exe"),
                    "/d",
                    "/c",
                    executable,
                    *codex_args,
                ]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self.process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.process_cwd),
            creationflags=creationflags,
            limit=4_000_000,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "web_local_agent",
                    "title": "Web Local Agent",
                    "version": "0.1.0",
                }
            },
            timeout=30,
        )
        await self.notify("initialized", {})

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

        tasks = [task for task in (self._stdout_task, self._stderr_task) if task]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        error = CodexAppServerError("Codex App Server stopped")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
        self._server_requests.clear()

    async def request(
        self, method: str, params: dict[str, Any], *, timeout: float = 30
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send({"method": method, "id": request_id, "params": params})
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"method": method, "params": params})

    async def respond_to_server(
        self, request_id: JsonRpcId, result: dict[str, Any]
    ) -> None:
        if request_id not in self._server_requests:
            raise KeyError(f"unknown server request id: {request_id}")
        await self._send({"id": request_id, "result": result})
        self._server_requests.pop(request_id, None)

    def server_request_method(self, request_id: JsonRpcId) -> str | None:
        return self._server_requests.get(request_id)

    async def start_thread(self, cwd: Path) -> str:
        response = await self.request(
            "thread/start",
            {
                "cwd": str(cwd),
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "sandbox": "workspace-write",
            },
        )
        try:
            return str(response["thread"]["id"])
        except (KeyError, TypeError) as exc:
            raise CodexAppServerError("thread/start returned no thread id") from exc

    async def start_turn(self, thread_id: str, text: str, cwd: Path) -> dict[str, Any]:
        return await self.request(
            "turn/start",
            {
                "threadId": thread_id,
                "cwd": str(cwd),
                "input": [{"type": "text", "text": text}],
            },
        )

    async def steer_turn(self, thread_id: str, text: str) -> dict[str, Any]:
        return await self.request(
            "turn/steer",
            {"threadId": thread_id, "input": [{"type": "text", "text": text}]},
        )

    async def interrupt_turn(self, thread_id: str, turn_id: str) -> dict[str, Any]:
        return await self.request(
            "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}
        )

    async def _send(self, message: dict[str, Any]) -> None:
        process = self.process
        if process is None or process.returncode is not None or process.stdin is None:
            raise CodexAppServerError("Codex App Server is not running")
        encoded = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        async with self._write_lock:
            process.stdin.write(encoded)
            await process.stdin.drain()

    async def _read_stdout(self) -> None:
        process = self.process
        assert process is not None and process.stdout is not None
        stdout = process.stdout
        while True:
            line = await stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("ignored non-JSON output from Codex App Server")
                continue

            request_id = message.get("id")
            if request_id is not None and ("result" in message or "error" in message):
                future = self._pending.get(request_id)
                if future is not None and not future.done():
                    if "error" in message:
                        future.set_exception(
                            CodexAppServerError(str(message.get("error")))
                        )
                    else:
                        future.set_result(message.get("result") or {})
                continue

            if request_id is not None and isinstance(message.get("method"), str):
                self._server_requests[request_id] = message["method"]
                await self.on_event({"kind": "server_request", "message": message})
                continue

            await self.on_event({"kind": "notification", "message": message})

        error = CodexAppServerError("Codex App Server stdout closed")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        await self.on_event({"kind": "process_exited"})

    async def _read_stderr(self) -> None:
        process = self.process
        assert process is not None and process.stderr is not None
        stderr = process.stderr
        while True:
            chunk = await stderr.read(4096)
            if not chunk:
                return
            text = chunk.decode("utf-8", errors="replace").strip()
            if text:
                logger.debug("codex stderr: %s", text[:2000])
