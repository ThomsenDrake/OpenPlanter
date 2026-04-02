from __future__ import annotations

import unittest

from agent.__main__ import _parse_cli_args


class MainCliParsingTests(unittest.TestCase):
    def test_resume_preserves_positional_session_id(self) -> None:
        _parser, args = _parse_cli_args(["session-123", "--resume"])
        self.assertTrue(args.resume)
        self.assertEqual(args.session_id_positional, "session-123")
        self.assertIsNone(getattr(args, "command", None))

    def test_defrag_subcommand_still_parses(self) -> None:
        _parser, args = _parse_cli_args(["defrag", "--mode", "cleanup", "/tmp/workspace"])
        self.assertEqual(args.command, "defrag")
        self.assertEqual(args.mode, "cleanup")
        self.assertEqual(args.workspace_path, "/tmp/workspace")

    def test_resume_with_literal_defrag_session_id_uses_main_parser(self) -> None:
        _parser, args = _parse_cli_args(["defrag", "--resume"])
        self.assertTrue(args.resume)
        self.assertEqual(args.session_id_positional, "defrag")
        self.assertIsNone(getattr(args, "command", None))


if __name__ == "__main__":
    unittest.main()
