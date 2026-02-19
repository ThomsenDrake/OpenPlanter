from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.tools import WorkspaceTools


class PatchToolTests(unittest.TestCase):
    def test_apply_patch_multi_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            (root / "to_delete.txt").write_text("bye\n", encoding="utf-8")
            tools = WorkspaceTools(root=root)

            patch = """*** Begin Patch
*** Update File: a.txt
@@
 one
-two
+TWO
 three
*** Add File: b.txt
+hello
+world
*** Delete File: to_delete.txt
*** End Patch"""
            msg = tools.apply_patch(patch)

            self.assertIn("Patch applied successfully", msg)
            self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "one\nTWO\nthree\n")
            self.assertEqual((root / "b.txt").read_text(encoding="utf-8"), "hello\nworld\n")
            self.assertFalse((root / "to_delete.txt").exists())

    def test_apply_patch_move_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "old.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            tools = WorkspaceTools(root=root)

            patch = """*** Begin Patch
*** Update File: old.txt
*** Move to: moved/new.txt
@@
 alpha
-beta
+BETA
*** End Patch"""
            msg = tools.apply_patch(patch)

            self.assertIn("Moved:", msg)
            self.assertFalse((root / "old.txt").exists())
            self.assertEqual((root / "moved/new.txt").read_text(encoding="utf-8"), "alpha\nBETA\n")

    def test_apply_patch_bad_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tools = WorkspaceTools(root=root)
            msg = tools.apply_patch("invalid patch")
            self.assertIn("Patch failed", msg)


if __name__ == "__main__":
    unittest.main()
