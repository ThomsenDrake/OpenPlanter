from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.chrome_mcp import (
    ChromeMcpError,
    ChromeMcpManager,
    acquire_shared_manager,
    shutdown_all_shared_managers,
)


FAKE_MCP_SERVER = """#!/usr/bin/env python3
import json
import sys

TOOLS = [
    {
        "name": "navigate_page",
        "description": "Navigate the page",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "take_screenshot",
        "description": "Take a screenshot",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
]

for raw_line in sys.stdin:
    line = raw_line.strip()
    if not line:
        continue
    payload = json.loads(line)
    method = payload.get("method")
    request_id = payload.get("id")
    if method == "initialize" and request_id is not None:
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-11-25",
                "serverInfo": {"name": "fake-chrome-mcp", "version": "1.0"},
            },
        }) + "\\n")
        sys.stdout.flush()
        continue
    if method == "tools/list" and request_id is not None:
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS},
        }) + "\\n")
        sys.stdout.flush()
        continue
    if method == "tools/call" and request_id is not None:
        params = payload.get("params") or {}
        name = params.get("name")
        if name == "take_screenshot":
            result = {
                "content": [
                    {"type": "text", "text": "Screenshot captured."},
                    {"type": "image", "data": "ZmFrZS1pbWFnZQ==", "mimeType": "image/png"},
                ]
            }
        else:
            result = {
                "content": [
                    {"type": "text", "text": f"Called {name}"},
                ]
            }
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }) + "\\n")
        sys.stdout.flush()
"""


def _write_fake_launcher(tmpdir: str) -> Path:
    launcher = Path(tmpdir) / "fake_npx.py"
    launcher.write_text(FAKE_MCP_SERVER, encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


class ChromeMcpManagerTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_all_shared_managers()

    def test_initialize_list_tools_and_call_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = _write_fake_launcher(tmpdir)
            with patch.dict(
                os.environ,
                {
                    "OPENPLANTER_CHROME_MCP_COMMAND": str(launcher),
                    "OPENPLANTER_CHROME_MCP_PACKAGE": "ignored-package",
                },
                clear=False,
            ):
                manager = ChromeMcpManager(
                    enabled=True,
                    auto_connect=True,
                    browser_url=None,
                    channel="stable",
                    connect_timeout_sec=3,
                    rpc_timeout_sec=3,
                )
                tools = manager.list_tools(force_refresh=True)
                self.assertEqual([tool.name for tool in tools], ["navigate_page", "take_screenshot"])

                result = manager.call_tool("navigate_page", {"url": "https://example.com"})
                self.assertIn("Called navigate_page", result.content)
                self.assertFalse(result.is_error)
                manager.shutdown()

    def test_call_tool_parses_image_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = _write_fake_launcher(tmpdir)
            with patch.dict(
                os.environ,
                {
                    "OPENPLANTER_CHROME_MCP_COMMAND": str(launcher),
                    "OPENPLANTER_CHROME_MCP_PACKAGE": "ignored-package",
                },
                clear=False,
            ):
                manager = ChromeMcpManager(
                    enabled=True,
                    auto_connect=True,
                    browser_url=None,
                    channel="stable",
                    connect_timeout_sec=3,
                    rpc_timeout_sec=3,
                )
                result = manager.call_tool("take_screenshot", {})
                self.assertIn("Screenshot captured.", result.content)
                self.assertIsNotNone(result.image)
                assert result.image is not None
                self.assertEqual(result.image.media_type, "image/png")
                self.assertEqual(result.image.base64_data, "ZmFrZS1pbWFnZQ==")
                manager.shutdown()

    def test_missing_attach_mode_reports_unavailable(self) -> None:
        manager = ChromeMcpManager(
            enabled=True,
            auto_connect=False,
            browser_url=None,
            channel="stable",
            connect_timeout_sec=1,
            rpc_timeout_sec=1,
        )
        with self.assertRaises(ChromeMcpError):
            manager.list_tools()
        status = manager.status_snapshot()
        self.assertEqual(status.status, "unavailable")
        self.assertIn("chrome_mcp_browser_url", status.detail)

    def test_shared_manager_registry_reuses_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = _write_fake_launcher(tmpdir)
            with patch.dict(
                os.environ,
                {
                    "OPENPLANTER_CHROME_MCP_COMMAND": str(launcher),
                    "OPENPLANTER_CHROME_MCP_PACKAGE": "ignored-package",
                },
                clear=False,
            ):
                first = acquire_shared_manager(
                    enabled=True,
                    auto_connect=True,
                    browser_url=None,
                    channel="stable",
                    connect_timeout_sec=3,
                    rpc_timeout_sec=3,
                )
                second = acquire_shared_manager(
                    enabled=True,
                    auto_connect=True,
                    browser_url=None,
                    channel="stable",
                    connect_timeout_sec=3,
                    rpc_timeout_sec=3,
                )
                self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
