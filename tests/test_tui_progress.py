"""Tests for TUI progress display, engine cancellation, and input queuing."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from agent.engine import RLMEngine
from agent.tui import _ActivityDisplay


# ---------------------------------------------------------------------------
# _ActivityDisplay mode transitions
# ---------------------------------------------------------------------------

class TestActivityDisplay:
    def _make_display(self):
        console = MagicMock()
        return _ActivityDisplay(console=console)

    def test_initial_mode_is_thinking(self):
        d = self._make_display()
        assert d.mode == "thinking"
        assert d.active is False

    @patch("agent.tui._ActivityDisplay._build_renderable", return_value="")
    def test_start_activates(self, _mock_render):
        d = self._make_display()
        with patch("rich.live.Live") as MockLive:
            instance = MockLive.return_value
            instance.__enter__ = MagicMock(return_value=instance)
            instance.__exit__ = MagicMock(return_value=False)
            d.start(mode="thinking", step_label="Step 1/20")
            assert d.active is True
            assert d.mode == "thinking"
            d.stop()
            assert d.active is False

    def test_feed_text_transitions_to_streaming(self):
        d = self._make_display()
        # Simulate active state without actually creating Live
        d._active = True
        d._mode = "thinking"
        d._start_time = time.monotonic()
        d._live = MagicMock()

        assert d.mode == "thinking"
        d.feed("text", "Hello world")
        assert d.mode == "streaming"

    def test_feed_thinking_stays_in_thinking(self):
        d = self._make_display()
        d._active = True
        d._mode = "thinking"
        d._start_time = time.monotonic()
        d._live = MagicMock()

        d.feed("thinking", "pondering...")
        assert d.mode == "thinking"
        assert d._text_buf == "pondering..."

    def test_set_tool_updates_display(self):
        d = self._make_display()
        d._active = True
        d._mode = "thinking"
        d._start_time = time.monotonic()
        d._live = MagicMock()

        d.set_tool("run_shell", key_arg="ls -la", step_label="Step 3/20")
        assert d.mode == "tool"
        assert d._tool_name == "run_shell"
        assert d._tool_key_arg == "ls -la"
        assert d._step_label == "Step 3/20"

    def test_mode_transitions_thinking_streaming_tool(self):
        d = self._make_display()
        d._active = True
        d._start_time = time.monotonic()
        d._live = MagicMock()

        # Start in thinking
        d._mode = "thinking"
        assert d.mode == "thinking"

        # Feed text → streaming
        d.feed("text", "Here is the answer")
        assert d.mode == "streaming"

        # Set tool → tool
        d.set_tool("read_file", key_arg="foo.py")
        assert d.mode == "tool"

    def test_step_label_displayed(self):
        d = self._make_display()
        d._active = True
        d._start_time = time.monotonic()
        d._mode = "thinking"
        d._step_label = "Step 2/15"
        d._live = MagicMock()

        renderable = d._build_renderable()
        # The renderable should be a Text object containing the step label
        rendered_str = str(renderable)
        assert "Step 2/15" in rendered_str

    def test_stop_clears_state(self):
        d = self._make_display()
        d._active = True
        d._mode = "streaming"
        d._text_buf = "some text"
        d._tool_name = "run_shell"
        d._tool_key_arg = "echo hi"
        d._live = MagicMock()
        d._live.__exit__ = MagicMock(return_value=False)

        d.stop()
        assert d.active is False
        assert d._text_buf == ""
        assert d._tool_name == ""
        assert d._tool_key_arg == ""


# ---------------------------------------------------------------------------
# Engine cancellation
# ---------------------------------------------------------------------------

class TestEngineCancellation:
    def _make_engine(self):
        model = MagicMock()
        model.model = "test-model"
        tools = MagicMock()
        config = MagicMock()
        config.workspace = "/tmp"
        config.max_steps_per_call = 10
        config.max_depth = 2
        config.max_solve_seconds = 0
        config.max_observation_chars = 5000
        config.max_plan_chars = 5000
        config.recursive = False
        config.acceptance_criteria = False
        config.demo = False

        engine = RLMEngine(
            model=model,
            tools=tools,
            config=config,
            system_prompt="test",
        )
        return engine

    def test_cancel_flag_set(self):
        engine = self._make_engine()
        assert not engine._cancel.is_set()
        engine.cancel()
        assert engine._cancel.is_set()

    def test_cancel_resets_between_solves(self):
        engine = self._make_engine()
        engine.cancel()
        assert engine._cancel.is_set()

        # solve_with_context resets the flag
        engine.model.create_conversation = MagicMock()
        # Make model.complete return a turn with text (final answer, no tool calls)
        mock_turn = MagicMock()
        mock_turn.text = "done"
        mock_turn.tool_calls = []
        mock_turn.input_tokens = 10
        mock_turn.output_tokens = 5
        mock_turn.raw_response = {}
        engine.model.complete = MagicMock(return_value=mock_turn)

        result, _ = engine.solve_with_context(objective="test")
        # The cancel flag should have been cleared at the start
        assert not engine._cancel.is_set()

    def test_engine_cancel_exits_early(self):
        engine = self._make_engine()

        # We need cancel to be set AFTER solve_with_context clears it but
        # BEFORE the step loop checks it. Use create_conversation as the hook
        # to set the cancel flag just in time.
        original_create = MagicMock(return_value="conv")

        def create_and_cancel(*args, **kwargs):
            result = original_create(*args, **kwargs)
            engine.cancel()  # Set cancel after clear but before step loop
            return result

        engine.model.create_conversation = create_and_cancel

        result, _ = engine.solve_with_context(objective="do stuff")
        assert result == "Task cancelled."
        # model.complete should never be called since we cancelled before step 1
        engine.model.complete.assert_not_called()

    def test_cancel_before_tool_returns_cancelled(self):
        """When cancel is set, _run_one_tool returns early."""
        engine = self._make_engine()
        engine.cancel()

        tc = MagicMock()
        tc.id = "call_1"
        tc.name = "read_file"
        tc.arguments = {"path": "foo.py"}

        result, is_final = engine._run_one_tool(
            tc=tc, depth=0, step=1, objective="test",
            context=MagicMock(), on_event=None, on_step=None,
            deadline=0, current_model=engine.model,
            replay_logger=None,
        )
        assert result.content == "Task cancelled."


# ---------------------------------------------------------------------------
# Input queuing (lightweight, no full TUI)
# ---------------------------------------------------------------------------

class TestInputQueuing:
    def test_queued_input_consumed(self):
        """Verify queued input list acts as FIFO."""
        queue: list[str] = ["second question", "third question"]

        # Simulate: pop first item
        first = queue.pop(0)
        assert first == "second question"
        assert queue == ["third question"]

        second = queue.pop(0)
        assert second == "third question"
        assert queue == []
