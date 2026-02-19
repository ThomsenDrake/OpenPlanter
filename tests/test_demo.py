"""Tests for agent.demo — DemoCensor and DemoRenderHook."""

from __future__ import annotations

import unittest
from pathlib import Path

from agent.demo import DemoCensor, DemoRenderHook


class DemoCensorPathTests(unittest.TestCase):
    """Workspace path censoring: distinguishing parts censored, generic parts
    and the project name preserved."""

    def test_username_censored(self) -> None:
        ws = Path("/Users/johndoe/Documents/MyProject")
        c = DemoCensor(ws)
        text = "Workspace: /Users/johndoe/Documents/MyProject"
        result = c.censor_text(text)
        self.assertNotIn("johndoe", result)
        # Generic parts and project name survive
        self.assertIn("Users", result)
        self.assertIn("Documents", result)
        self.assertIn("MyProject", result)

    def test_multiple_custom_segments_censored(self) -> None:
        ws = Path("/home/alice/secret_org/repos/CoolApp")
        c = DemoCensor(ws)
        text = "/home/alice/secret_org/repos/CoolApp"
        result = c.censor_text(text)
        self.assertNotIn("alice", result)
        self.assertNotIn("secret_org", result)
        self.assertIn("home", result)
        self.assertIn("repos", result)
        self.assertIn("CoolApp", result)

    def test_same_length_path_replacement(self) -> None:
        ws = Path("/Users/bob/Documents/Proj")
        c = DemoCensor(ws)
        text = "path is /Users/bob/Documents/Proj end"
        result = c.censor_text(text)
        # "bob" → 3 block chars
        self.assertIn("\u2588" * 3, result)
        self.assertEqual(len(text), len(result))


class DemoCensorEdgeCases(unittest.TestCase):
    """Empty and plain text edge cases."""

    def test_empty_string(self) -> None:
        ws = Path("/tmp/Proj")
        c = DemoCensor(ws)
        self.assertEqual(c.censor_text(""), "")

    def test_no_match_passes_through(self) -> None:
        ws = Path("/tmp/Proj")
        c = DemoCensor(ws)
        text = "this is all lowercase and has no path segments"
        self.assertEqual(c.censor_text(text), text)

    def test_entity_names_not_censored_by_censor_text(self) -> None:
        """Entity censoring is handled by the prompt, not DemoCensor."""
        ws = Path("/tmp/Proj")
        c = DemoCensor(ws)
        text = "Contact John Smith at Boston Medical Center."
        result = c.censor_text(text)
        # Entity names pass through — the model is instructed to censor them
        self.assertIn("John Smith", result)
        self.assertIn("Boston Medical Center", result)

    def test_splash_art_preserved(self) -> None:
        from agent.tui import SPLASH_ART
        ws = Path("/Users/testuser/Documents/TestProject")
        c = DemoCensor(ws)
        result = c.censor_text(SPLASH_ART)
        # Structure (newlines) must be intact
        self.assertEqual(SPLASH_ART.count("\n"), result.count("\n"))


class DemoCensorRichTextTests(unittest.TestCase):
    """Rich Text style spans survive same-length censoring."""

    def test_rich_text_style_preserved(self) -> None:
        from rich.text import Text

        ws = Path("/Users/alice/Documents/Proj")
        c = DemoCensor(ws)

        t = Text("Path: /Users/alice/Documents/Proj")
        t.stylize("bold", 0, 5)  # "Path:" is bold
        c.censor_rich_text(t)

        self.assertNotIn("alice", t.plain)
        self.assertIn("Users", t.plain)
        # Style span should still exist
        self.assertTrue(any("bold" in str(span) for span in t._spans))

    def test_rich_text_unchanged_when_no_match(self) -> None:
        from rich.text import Text

        ws = Path("/tmp/Proj")
        c = DemoCensor(ws)
        t = Text("nothing to censor here")
        original_plain = t.plain
        c.censor_rich_text(t)
        self.assertEqual(t.plain, original_plain)


class DemoRenderHookTests(unittest.TestCase):
    """DemoRenderHook processes Text, Markdown, and Rule correctly."""

    def _make_hook(self) -> DemoRenderHook:
        ws = Path("/Users/jdoe/Documents/Proj")
        censor = DemoCensor(ws)
        return DemoRenderHook(censor)

    def test_text_censored(self) -> None:
        from rich.text import Text

        hook = self._make_hook()
        t = Text("/Users/jdoe/Documents/Proj")
        results = hook.process_renderables([t])
        self.assertEqual(len(results), 1)
        self.assertNotIn("jdoe", results[0].plain)
        self.assertIn("Users", results[0].plain)

    def test_markdown_censored(self) -> None:
        from rich.markdown import Markdown

        hook = self._make_hook()
        md = Markdown("Hello from /Users/jdoe/Documents/Proj")
        results = hook.process_renderables([md])
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], Markdown)
        self.assertNotIn("jdoe", results[0].markup)

    def test_rule_censored(self) -> None:
        from rich.rule import Rule

        hook = self._make_hook()
        r = Rule(title="Step 1 /Users/jdoe/Documents/Proj")
        results = hook.process_renderables([r])
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], Rule)
        self.assertNotIn("jdoe", results[0].title)

    def test_other_renderable_passes_through(self) -> None:
        hook = self._make_hook()
        obj = {"arbitrary": "object"}
        results = hook.process_renderables([obj])
        self.assertEqual(results, [obj])


class DemoPromptTests(unittest.TestCase):
    """Demo mode adds entity-censoring instruction to the system prompt."""

    def test_demo_section_included_when_enabled(self) -> None:
        from agent.prompts import build_system_prompt
        prompt = build_system_prompt(recursive=False, demo=True)
        self.assertIn("Demo Mode", prompt)
        self.assertIn("censor", prompt.lower())

    def test_demo_section_absent_when_disabled(self) -> None:
        from agent.prompts import build_system_prompt
        prompt = build_system_prompt(recursive=False, demo=False)
        self.assertNotIn("Demo Mode", prompt)


if __name__ == "__main__":
    unittest.main()
