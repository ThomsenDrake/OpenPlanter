from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.runtime import _seed_wiki


class WikiSeedTests(unittest.TestCase):
    """Tests for the _seed_wiki() baseline → runtime wiki seeding."""

    def _make_baseline(self, root: Path, files: dict[str, str]) -> None:
        """Create wiki/ baseline tree under *root*."""
        for rel, content in files.items():
            p = root / "wiki" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

    def test_initial_seed_copies_all_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_baseline(root, {
                "index.md": "# Index",
                "template.md": "# Template",
                "campaign-finance/ocpf.md": "OCPF data",
            })
            _seed_wiki(root, ".openplanter")

            runtime_wiki = root / ".openplanter" / "wiki"
            self.assertTrue(runtime_wiki.exists())
            self.assertEqual(
                (runtime_wiki / "index.md").read_text(), "# Index",
            )
            self.assertEqual(
                (runtime_wiki / "template.md").read_text(), "# Template",
            )
            self.assertEqual(
                (runtime_wiki / "campaign-finance" / "ocpf.md").read_text(),
                "OCPF data",
            )

    def test_no_overwrite_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_baseline(root, {"index.md": "baseline content"})

            # First seed
            _seed_wiki(root, ".openplanter")

            # Agent modifies runtime copy
            runtime_index = root / ".openplanter" / "wiki" / "index.md"
            runtime_index.write_text("agent modified", encoding="utf-8")

            # Update baseline
            (root / "wiki" / "index.md").write_text(
                "updated baseline", encoding="utf-8",
            )

            # Re-seed — should NOT overwrite agent's version
            _seed_wiki(root, ".openplanter")
            self.assertEqual(runtime_index.read_text(), "agent modified")

    def test_incremental_new_files_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_baseline(root, {"index.md": "# Index"})
            _seed_wiki(root, ".openplanter")

            # Modify the runtime copy so we can verify it's preserved
            runtime_index = root / ".openplanter" / "wiki" / "index.md"
            runtime_index.write_text("agent version", encoding="utf-8")

            # Add a new baseline file
            self._make_baseline(root, {
                "index.md": "# Index",
                "contracts/new-source.md": "new source data",
            })

            _seed_wiki(root, ".openplanter")

            # Existing file preserved
            self.assertEqual(runtime_index.read_text(), "agent version")
            # New file copied
            new_file = root / ".openplanter" / "wiki" / "contracts" / "new-source.md"
            self.assertTrue(new_file.exists())
            self.assertEqual(new_file.read_text(), "new source data")

    def test_no_baseline_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # No wiki/ directory at all
            _seed_wiki(root, ".openplanter")
            self.assertFalse((root / ".openplanter" / "wiki").exists())

    def test_hidden_dirs_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_baseline(root, {"index.md": "# Index"})
            # Add hidden dir and __pycache__ to baseline
            hidden = root / "wiki" / ".pytest_cache" / "README.md"
            hidden.parent.mkdir(parents=True, exist_ok=True)
            hidden.write_text("cache readme", encoding="utf-8")

            pycache = root / "wiki" / "__pycache__" / "mod.pyc"
            pycache.parent.mkdir(parents=True, exist_ok=True)
            pycache.write_text("bytecode", encoding="utf-8")

            _seed_wiki(root, ".openplanter")

            runtime_wiki = root / ".openplanter" / "wiki"
            self.assertTrue((runtime_wiki / "index.md").exists())
            self.assertFalse((runtime_wiki / ".pytest_cache").exists())
            self.assertFalse((runtime_wiki / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
