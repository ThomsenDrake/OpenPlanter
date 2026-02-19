"""Integration tests that hit real model APIs.

These tests make actual HTTP calls and consume API credits.
They are skipped automatically when the corresponding API key is
not found in .openplanter/credentials.json.

Run explicitly:
    PYTHONPATH=src python3 -m unittest tests.test_live_models -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.config import AgentConfig
from agent.credentials import CredentialStore
from agent.engine import SYSTEM_PROMPT, RLMEngine
from agent.model import AnthropicModel, OpenAICompatibleModel
from agent.tools import WorkspaceTools

# ---------------------------------------------------------------------------
# Load credentials once for the module
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_cred_store = CredentialStore(workspace=_PROJECT_ROOT, session_root_dir=".openplanter")
_creds = _cred_store.load()

_OPENAI_KEY = _creds.openai_api_key or ""
_ANTHROPIC_KEY = _creds.anthropic_api_key or ""
_OPENROUTER_KEY = _creds.openrouter_api_key or ""

# Cheap/fast models to keep costs and latency minimal
_OPENAI_MODEL = "gpt-4.1-mini"
_ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
_OPENROUTER_MODEL = "openai/gpt-4.1-mini"


class OpenAILiveTests(unittest.TestCase):
    @unittest.skipUnless(_OPENAI_KEY, "No OpenAI API key configured")
    def test_openai_returns_valid_model_turn(self) -> None:
        model = OpenAICompatibleModel(
            model=_OPENAI_MODEL,
            api_key=_OPENAI_KEY,
            timeout_sec=30,
        )
        conv = model.create_conversation(
            SYSTEM_PROMPT,
            json.dumps({
                "objective": "Return immediately with a final answer saying 'hello'.",
                "depth": 0,
                "max_depth": 1,
                "max_steps_per_call": 1,
                "workspace": "/tmp/test",
                "external_context_summary": "(empty)",
            }),
        )
        turn = model.complete(conv)
        # Should have either tool calls or text
        self.assertTrue(turn.tool_calls or turn.text)

    @unittest.skipUnless(_OPENAI_KEY, "No OpenAI API key configured")
    def test_openai_tool_call_round_trip(self) -> None:
        """Verify we can append tool results and continue the conversation."""
        model = OpenAICompatibleModel(
            model=_OPENAI_MODEL,
            api_key=_OPENAI_KEY,
            timeout_sec=30,
        )
        conv = model.create_conversation(
            SYSTEM_PROMPT,
            json.dumps({
                "objective": "List files then say 'done'.",
                "depth": 0,
                "max_depth": 1,
                "max_steps_per_call": 3,
                "workspace": "/tmp/test",
                "external_context_summary": "(empty)",
            }),
        )
        turn = model.complete(conv)
        if turn.tool_calls:
            model.append_assistant_turn(conv, turn)
            from agent.model import ToolResult
            results = [
                ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content="file1.py\nfile2.py",
                )
                for tc in turn.tool_calls
            ]
            model.append_tool_results(conv, results)
            turn2 = model.complete(conv)
            self.assertTrue(turn2.tool_calls or turn2.text)


class AnthropicLiveTests(unittest.TestCase):
    @unittest.skipUnless(_ANTHROPIC_KEY, "No Anthropic API key configured")
    def test_anthropic_returns_valid_model_turn(self) -> None:
        model = AnthropicModel(
            model=_ANTHROPIC_MODEL,
            api_key=_ANTHROPIC_KEY,
            timeout_sec=30,
        )
        conv = model.create_conversation(
            SYSTEM_PROMPT,
            json.dumps({
                "objective": "Return immediately with a final answer saying 'hello'.",
                "depth": 0,
                "max_depth": 1,
                "max_steps_per_call": 1,
                "workspace": "/tmp/test",
                "external_context_summary": "(empty)",
            }),
        )
        turn = model.complete(conv)
        self.assertTrue(turn.tool_calls or turn.text)

    @unittest.skipUnless(_ANTHROPIC_KEY, "No Anthropic API key configured")
    def test_anthropic_with_thinking_budget(self) -> None:
        model = AnthropicModel(
            model=_ANTHROPIC_MODEL,
            api_key=_ANTHROPIC_KEY,
            reasoning_effort="low",
            timeout_sec=30,
        )
        conv = model.create_conversation(
            SYSTEM_PROMPT,
            json.dumps({
                "objective": "Return immediately with a final answer saying 'hello'.",
                "depth": 0,
                "max_depth": 1,
                "max_steps_per_call": 1,
                "workspace": "/tmp/test",
                "external_context_summary": "(empty)",
            }),
        )
        turn = model.complete(conv)
        self.assertTrue(turn.tool_calls or turn.text)


class OpenRouterLiveTests(unittest.TestCase):
    @unittest.skipUnless(_OPENROUTER_KEY, "No OpenRouter API key configured")
    def test_openrouter_returns_valid_model_turn(self) -> None:
        model = OpenAICompatibleModel(
            model=_OPENROUTER_MODEL,
            api_key=_OPENROUTER_KEY,
            base_url="https://openrouter.ai/api/v1",
            timeout_sec=30,
            strict_tools=False,
            extra_headers={
                "HTTP-Referer": "https://github.com/openplanter",
                "X-Title": "OpenPlanter",
            },
        )
        conv = model.create_conversation(
            SYSTEM_PROMPT,
            json.dumps({
                "objective": "Return immediately with a final answer saying 'hello'.",
                "depth": 0,
                "max_depth": 1,
                "max_steps_per_call": 1,
                "workspace": "/tmp/test",
                "external_context_summary": "(empty)",
            }),
        )
        turn = model.complete(conv)
        self.assertTrue(turn.tool_calls or turn.text)


class EndToEndLiveTests(unittest.TestCase):
    """Full engine solve against a real model."""

    @unittest.skipUnless(_OPENAI_KEY, "No OpenAI API key configured")
    def test_engine_solve_writes_and_reads_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg = AgentConfig(
                workspace=root,
                max_depth=1,
                max_steps_per_call=6,
                openai_api_key=_OPENAI_KEY,
            )
            model = OpenAICompatibleModel(
                model=_OPENAI_MODEL,
                api_key=_OPENAI_KEY,
                timeout_sec=60,
            )
            tools = WorkspaceTools(root=root)
            engine = RLMEngine(model=model, tools=tools, config=cfg)

            result = engine.solve(
                "Create a file called hello.txt containing exactly 'hello world', "
                "then read it to confirm, then return the file contents as your final answer."
            )
            # The model should have created the file
            hello_path = root / "hello.txt"
            self.assertTrue(hello_path.exists(), "Model did not create hello.txt")
            self.assertIn("hello world", hello_path.read_text())
            # Result should contain the content or at least not be an error
            self.assertNotIn("Model error", result)
            self.assertNotIn("Step budget exhausted", result)

    @unittest.skipUnless(_ANTHROPIC_KEY, "No Anthropic API key configured")
    def test_engine_solve_anthropic_simple_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg = AgentConfig(
                workspace=root,
                max_depth=1,
                max_steps_per_call=8,
                anthropic_api_key=_ANTHROPIC_KEY,
            )
            model = AnthropicModel(
                model=_ANTHROPIC_MODEL,
                api_key=_ANTHROPIC_KEY,
                timeout_sec=90,
            )
            tools = WorkspaceTools(root=root)
            engine = RLMEngine(model=model, tools=tools, config=cfg)

            result = engine.solve(
                "Write a file called test.txt with content 'anthropic works', "
                "then return 'done' as your final answer."
            )
            test_path = root / "test.txt"
            self.assertTrue(test_path.exists(), "Model did not create test.txt")
            self.assertIn("anthropic works", test_path.read_text())
            self.assertNotIn("Model error", result)


if __name__ == "__main__":
    unittest.main()
