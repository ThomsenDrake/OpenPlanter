from __future__ import annotations

import atexit
import json
import os
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

from .config import (
    CHROME_MCP_DEFAULT_CHANNEL,
    normalize_chrome_mcp_browser_url,
    normalize_chrome_mcp_channel,
)


class ChromeMcpError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChromeMcpToolDef:
    name: str
    description: str
    parameters: dict[str, Any]

    def as_tool_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass(frozen=True)
class ChromeMcpImage:
    base64_data: str
    media_type: str


@dataclass(frozen=True)
class ChromeMcpCallResult:
    content: str
    is_error: bool = False
    image: ChromeMcpImage | None = None


@dataclass(frozen=True)
class ChromeMcpStatus:
    status: str
    detail: str
    tool_count: int = 0
    last_refresh_at: float | None = None


@dataclass
class _PendingRequest:
    event: threading.Event
    result: dict[str, Any] | None = None
    error: Exception | None = None


def _env_text(name: str, default: str) -> str:
    value = (os.getenv(name) or "").strip()
    return value or default


def _format_protocol_error(error: object) -> str:
    if isinstance(error, dict):
        message = str(error.get("message") or "Unknown MCP error").strip()
        code = error.get("code")
        if code is None:
            return message
        return f"{message} (code {code})"
    return str(error or "Unknown MCP error")


def _status_detail_from_exception(
    exc: Exception,
    *,
    browser_url: str | None,
    stderr_tail: list[str],
) -> str:
    detail = str(exc).strip() or type(exc).__name__
    stderr_text = " ".join(line.strip() for line in stderr_tail[-4:] if line.strip())
    lower = f"{detail} {stderr_text}".lower()
    hints: list[str] = []
    if "npx" in lower and ("not found" in lower or "no such file" in lower):
        hints.append("Install Node.js/npm so `npx` is available locally.")
    if "timed out" in lower or "timeout" in lower:
        if browser_url:
            hints.append("Confirm the remote debugging endpoint is reachable.")
        else:
            hints.append(
                "Enable Chrome remote debugging at chrome://inspect/#remote-debugging "
                "and allow the Chrome DevTools MCP connection prompt."
            )
    if "inspect/#remote-debugging" not in lower and browser_url is None:
        hints.append(
            "Chrome 144+ must have remote debugging enabled at chrome://inspect/#remote-debugging."
        )
    if stderr_text:
        detail = f"{detail} stderr: {stderr_text}"
    if hints:
        detail = f"{detail} {' '.join(hints)}"
    return detail.strip()


class ChromeMcpManager:
    def __init__(
        self,
        *,
        enabled: bool,
        auto_connect: bool,
        browser_url: str | None,
        channel: str,
        connect_timeout_sec: int,
        rpc_timeout_sec: int,
    ) -> None:
        self.enabled = bool(enabled)
        self.auto_connect = bool(auto_connect)
        self.browser_url = normalize_chrome_mcp_browser_url(browser_url)
        self.channel = normalize_chrome_mcp_channel(channel or CHROME_MCP_DEFAULT_CHANNEL)
        self.connect_timeout_sec = max(1, int(connect_timeout_sec))
        self.rpc_timeout_sec = max(1, int(rpc_timeout_sec))
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._pending: dict[int, _PendingRequest] = {}
        self._next_id = 1
        self._tools: list[ChromeMcpToolDef] = []
        self._last_refresh_at: float | None = None
        self._status = ChromeMcpStatus(
            status="disabled" if not self.enabled else "ready",
            detail=(
                "Chrome DevTools MCP is disabled."
                if not self.enabled
                else "Chrome DevTools MCP will initialize on the next solve."
            ),
            tool_count=0,
        )
        self._stderr_tail: list[str] = []

    def status_snapshot(self) -> ChromeMcpStatus:
        with self._lock:
            return ChromeMcpStatus(
                status=self._status.status,
                detail=self._status.detail,
                tool_count=self._status.tool_count,
                last_refresh_at=self._status.last_refresh_at,
            )

    def ensure_connected(self) -> None:
        if not self.enabled:
            with self._lock:
                self._status = ChromeMcpStatus(
                    status="disabled",
                    detail="Chrome DevTools MCP is disabled.",
                    tool_count=len(self._tools),
                    last_refresh_at=self._last_refresh_at,
                )
            return
        with self._lock:
            if self._proc is not None and self._proc.poll() is None and self._reader_thread is not None:
                return
            if not self.browser_url and not self.auto_connect:
                detail = (
                    "Chrome DevTools MCP is enabled but cannot attach: set "
                    "`chrome_mcp_browser_url` or enable `chrome_mcp_auto_connect`."
                )
                self._status = ChromeMcpStatus(
                    status="unavailable",
                    detail=detail,
                    tool_count=len(self._tools),
                    last_refresh_at=self._last_refresh_at,
                )
                raise ChromeMcpError(detail)
            self._start_process_locked()
        try:
            self._initialize_handshake()
        except Exception as exc:
            detail = _status_detail_from_exception(
                exc,
                browser_url=self.browser_url,
                stderr_tail=self._stderr_tail,
            )
            with self._lock:
                self._status = ChromeMcpStatus(
                    status="unavailable",
                    detail=detail,
                    tool_count=len(self._tools),
                    last_refresh_at=self._last_refresh_at,
                )
            self.shutdown()
            raise ChromeMcpError(detail) from exc

    def list_tools(self, *, force_refresh: bool = False) -> list[ChromeMcpToolDef]:
        if not self.enabled:
            return []
        self.ensure_connected()
        with self._lock:
            if self._tools and not force_refresh:
                return list(self._tools)
        tools: list[ChromeMcpToolDef] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            result = self._request_with_reconnect(
                "tools/list",
                params=params,
                timeout_sec=self.rpc_timeout_sec,
            )
            raw_tools = result.get("tools")
            if isinstance(raw_tools, list):
                for item in raw_tools:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "").strip()
                    if not name:
                        continue
                    description = str(item.get("description") or "").strip()
                    parameters = item.get("inputSchema")
                    if not isinstance(parameters, dict):
                        parameters = {"type": "object", "properties": {}, "required": []}
                    tools.append(
                        ChromeMcpToolDef(
                            name=name,
                            description=description,
                            parameters=parameters,
                        )
                    )
            raw_cursor = result.get("nextCursor")
            cursor = str(raw_cursor).strip() if raw_cursor else None
            if not cursor:
                break
        now = time.time()
        with self._lock:
            self._tools = tools
            self._last_refresh_at = now
            self._status = ChromeMcpStatus(
                status="ready",
                detail=(
                    f"Chrome DevTools MCP ready with {len(tools)} tool(s) "
                    f"via {'browser_url' if self.browser_url else 'auto-connect'}."
                ),
                tool_count=len(tools),
                last_refresh_at=now,
            )
            return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ChromeMcpCallResult:
        if not self.enabled:
            raise ChromeMcpError("Chrome DevTools MCP is disabled.")
        self.ensure_connected()
        result = self._request_with_reconnect(
            "tools/call",
            params={"name": name, "arguments": arguments},
            timeout_sec=self.rpc_timeout_sec,
        )
        return self._parse_call_result(result)

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown_locked()

    def _request_with_reconnect(
        self,
        method: str,
        *,
        params: dict[str, Any],
        timeout_sec: int,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._request(method, params=params, timeout_sec=timeout_sec)
            except Exception as exc:
                last_error = exc
                with self._lock:
                    self._shutdown_locked()
                    self._status = ChromeMcpStatus(
                        status="unavailable",
                        detail=_status_detail_from_exception(
                            exc,
                            browser_url=self.browser_url,
                            stderr_tail=self._stderr_tail,
                        ),
                        tool_count=len(self._tools),
                        last_refresh_at=self._last_refresh_at,
                    )
                if attempt == 0:
                    self.ensure_connected()
                    continue
                break
        raise ChromeMcpError(str(last_error or "Chrome DevTools MCP request failed"))

    def _initialize_handshake(self) -> None:
        init_params = {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "openplanter-agent", "version": "1.0"},
        }
        self._request("initialize", params=init_params, timeout_sec=self.connect_timeout_sec)
        self._notify("notifications/initialized", {})

    def _request(
        self,
        method: str,
        *,
        params: dict[str, Any],
        timeout_sec: int,
    ) -> dict[str, Any]:
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None or proc.stdin is None:
                raise ChromeMcpError("Chrome DevTools MCP process is not running.")
            request_id = self._next_id
            self._next_id += 1
            pending = _PendingRequest(event=threading.Event())
            self._pending[request_id] = pending
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            try:
                proc.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                self._pending.pop(request_id, None)
                raise ChromeMcpError(f"Failed to send MCP request {method}: {exc}") from exc
        if not pending.event.wait(timeout_sec):
            with self._lock:
                self._pending.pop(request_id, None)
            raise ChromeMcpError(f"Timed out waiting for Chrome DevTools MCP {method} response.")
        if pending.error is not None:
            raise ChromeMcpError(str(pending.error))
        return pending.result or {}

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None or proc.stdin is None:
                raise ChromeMcpError("Chrome DevTools MCP process is not running.")
            payload = {"jsonrpc": "2.0", "method": method, "params": params}
            proc.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
            proc.stdin.flush()

    def _start_process_locked(self) -> None:
        self._shutdown_locked()
        command = _env_text("OPENPLANTER_CHROME_MCP_COMMAND", "npx")
        if shutil.which(command) is None:
            raise ChromeMcpError(f"`{command}` is not installed or not on PATH.")
        package = _env_text("OPENPLANTER_CHROME_MCP_PACKAGE", "chrome-devtools-mcp@latest")
        args = [command, "-y", package]
        if self.browser_url:
            args.append(f"--browserUrl={self.browser_url}")
        else:
            args.append("--autoConnect")
            args.append(f"--channel={self.channel}")
        extra_args = (os.getenv("OPENPLANTER_CHROME_MCP_EXTRA_ARGS") or "").strip()
        if extra_args:
            args.extend(shlex.split(extra_args))
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            start_new_session=True,
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="openplanter-chrome-mcp-reader",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop,
            name="openplanter-chrome-mcp-stderr",
            daemon=True,
        )
        self._reader_thread.start()
        self._stderr_thread.start()

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                request_id = payload.get("id")
                if not isinstance(request_id, int):
                    continue
                with self._lock:
                    pending = self._pending.pop(request_id, None)
                if pending is None:
                    continue
                if "error" in payload:
                    pending.error = ChromeMcpError(_format_protocol_error(payload.get("error")))
                else:
                    result = payload.get("result")
                    pending.result = result if isinstance(result, dict) else {}
                pending.event.set()
        finally:
            exit_code = proc.poll()
            error = ChromeMcpError(
                f"Chrome DevTools MCP process exited unexpectedly"
                + (f" with code {exit_code}." if exit_code is not None else ".")
            )
            with self._lock:
                pending = list(self._pending.values())
                self._pending.clear()
            for item in pending:
                item.error = error
                item.event.set()

    def _stderr_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw_line in proc.stderr:
            line = raw_line.strip()
            if not line:
                continue
            with self._lock:
                self._stderr_tail.append(line)
                self._stderr_tail = self._stderr_tail[-20:]

    def _shutdown_locked(self) -> None:
        proc = self._proc
        self._proc = None
        self._reader_thread = None
        self._stderr_thread = None
        pending = list(self._pending.values())
        self._pending.clear()
        for item in pending:
            item.error = ChromeMcpError("Chrome DevTools MCP shut down before responding.")
            item.event.set()
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _parse_call_result(self, result: dict[str, Any]) -> ChromeMcpCallResult:
        content_parts: list[str] = []
        image: ChromeMcpImage | None = None
        raw_content = result.get("content")
        if isinstance(raw_content, list):
            for item in raw_content:
                if isinstance(item, str):
                    if item.strip():
                        content_parts.append(item.strip())
                    continue
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip().lower()
                if item_type == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        content_parts.append(text.strip())
                    continue
                if item_type == "image":
                    data = item.get("data")
                    media_type = item.get("mimeType") or item.get("mediaType")
                    if (
                        image is None
                        and isinstance(data, str)
                        and data.strip()
                        and isinstance(media_type, str)
                        and media_type.strip()
                    ):
                        image = ChromeMcpImage(
                            base64_data=data.strip(),
                            media_type=media_type.strip(),
                        )
                    media_text = media_type.strip() if isinstance(media_type, str) else "image"
                    content_parts.append(f"[{media_text} attached]")
                    continue
                uri = item.get("uri") or item.get("url")
                if isinstance(uri, str) and uri.strip():
                    label = str(item.get("name") or item_type or "resource").strip()
                    content_parts.append(f"{label}: {uri.strip()}")
        structured = result.get("structuredContent")
        if not content_parts and structured is not None:
            try:
                content_parts.append(json.dumps(structured, indent=2, ensure_ascii=True))
            except TypeError:
                content_parts.append(str(structured))
        content = "\n".join(part for part in content_parts if part).strip()
        if not content:
            content = "Chrome DevTools MCP tool completed with no textual output."
        is_error = bool(result.get("isError"))
        if is_error:
            content = f"Chrome DevTools MCP tool error: {content}"
        return ChromeMcpCallResult(content=content, is_error=is_error, image=image)


_SHARED_MANAGERS: dict[tuple[Any, ...], ChromeMcpManager] = {}
_SHARED_LOCK = threading.Lock()


def acquire_shared_manager(
    *,
    enabled: bool,
    auto_connect: bool,
    browser_url: str | None,
    channel: str,
    connect_timeout_sec: int,
    rpc_timeout_sec: int,
) -> ChromeMcpManager | None:
    if not enabled:
        return None
    key = (
        bool(enabled),
        bool(auto_connect),
        normalize_chrome_mcp_browser_url(browser_url),
        normalize_chrome_mcp_channel(channel),
        max(1, int(connect_timeout_sec)),
        max(1, int(rpc_timeout_sec)),
        _env_text("OPENPLANTER_CHROME_MCP_COMMAND", "npx"),
        _env_text("OPENPLANTER_CHROME_MCP_PACKAGE", "chrome-devtools-mcp@latest"),
        (os.getenv("OPENPLANTER_CHROME_MCP_EXTRA_ARGS") or "").strip(),
    )
    with _SHARED_LOCK:
        manager = _SHARED_MANAGERS.get(key)
        if manager is None:
            manager = ChromeMcpManager(
                enabled=enabled,
                auto_connect=auto_connect,
                browser_url=browser_url,
                channel=channel,
                connect_timeout_sec=connect_timeout_sec,
                rpc_timeout_sec=rpc_timeout_sec,
            )
            _SHARED_MANAGERS[key] = manager
        return manager


def shutdown_all_shared_managers() -> None:
    with _SHARED_LOCK:
        managers = list(_SHARED_MANAGERS.values())
        _SHARED_MANAGERS.clear()
    for manager in managers:
        manager.shutdown()


atexit.register(shutdown_all_shared_managers)
