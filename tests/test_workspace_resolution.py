from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.workspace_resolution import (
    WorkspaceResolutionError,
    resolve_startup_workspace,
)


class WorkspaceResolutionTests(unittest.TestCase):
    def test_explicit_non_root_workspace_overrides_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            explicit = repo / "custom-workspace"
            default = repo / "workspace"
            repo.mkdir()
            explicit.mkdir()
            default.mkdir()
            (repo / ".git").mkdir()
            (repo / ".env").write_text("OPENPLANTER_WORKSPACE=workspace\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                resolved = resolve_startup_workspace(str(explicit), True, repo)

            self.assertEqual(resolved.workspace, explicit.resolve())
            self.assertEqual(resolved.source, "cli_arg")
            self.assertEqual(resolved.guardrail_action, "none")

    def test_explicit_repo_root_workspace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / "workspace").mkdir()

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(WorkspaceResolutionError):
                    resolve_startup_workspace(str(repo), True, repo)

    def test_explicit_file_workspace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            bogus_target = repo / "workspace.txt"
            bogus_target.write_text("not a directory\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(WorkspaceResolutionError):
                    resolve_startup_workspace(str(bogus_target), True, repo)

    def test_nearest_ancestor_dotenv_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outer = root / "outer"
            repo = outer / "repo"
            nested = repo / "subdir" / "deeper"
            outer_workspace = outer / "outer-ws"
            repo_workspace = repo / "inner-ws"
            nested.mkdir(parents=True)
            outer_workspace.mkdir()
            repo_workspace.mkdir()
            (outer / ".env").write_text("OPENPLANTER_WORKSPACE=outer-ws\n", encoding="utf-8")
            (repo / ".env").write_text("OPENPLANTER_WORKSPACE=inner-ws\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                resolved = resolve_startup_workspace(".", False, nested)

            self.assertEqual(resolved.workspace, repo_workspace.resolve())
            self.assertEqual(resolved.source, "dotenv")
            self.assertEqual(resolved.env_path, (repo / ".env").resolve())

    def test_dotenv_relative_workspace_is_resolved_from_env_file_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            nested = repo / "agent" / "inner"
            workspace = repo / "workspace"
            nested.mkdir(parents=True)
            workspace.mkdir()
            (repo / ".env").write_text("OPENPLANTER_WORKSPACE=workspace\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                resolved = resolve_startup_workspace(".", False, nested)

            self.assertEqual(resolved.workspace, workspace.resolve())
            self.assertEqual(resolved.source, "dotenv")

    def test_missing_workspace_key_redirects_repo_root_to_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            workspace = repo / "workspace"
            workspace.mkdir()
            (repo / ".env").write_text("OPENPLANTER_PROVIDER=openai\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                resolved = resolve_startup_workspace(".", False, repo)

            self.assertEqual(resolved.workspace, workspace.resolve())
            self.assertEqual(resolved.source, "cwd")
            self.assertEqual(resolved.guardrail_action, "redirected_to_workspace")

    def test_missing_workspace_key_fails_when_repo_root_has_no_workspace_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / ".env").write_text("OPENPLANTER_PROVIDER=openai\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(WorkspaceResolutionError):
                    resolve_startup_workspace(".", False, repo)

    def test_invalid_process_env_override_falls_back_to_guardrail_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            workspace = repo / "workspace"
            workspace.mkdir()

            with patch.dict(os.environ, {"OPENPLANTER_WORKSPACE": str(repo / "missing")}, clear=True):
                resolved = resolve_startup_workspace(".", False, repo)

            self.assertEqual(resolved.workspace, workspace.resolve())
            self.assertEqual(resolved.source, "cwd")
            self.assertEqual(resolved.invalid_env_override, str(repo / "missing"))
            self.assertEqual(resolved.guardrail_action, "redirected_to_workspace")

    def test_file_path_workspace_override_is_treated_as_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            workspace = repo / "workspace"
            workspace.mkdir()
            bogus_target = repo / "workspace.txt"
            bogus_target.write_text("not a directory\n", encoding="utf-8")

            with patch.dict(os.environ, {"OPENPLANTER_WORKSPACE": str(bogus_target)}, clear=True):
                resolved = resolve_startup_workspace(".", False, repo)

            self.assertEqual(resolved.workspace, workspace.resolve())
            self.assertEqual(resolved.source, "cwd")
            self.assertEqual(resolved.invalid_env_override, str(bogus_target))
            self.assertEqual(resolved.guardrail_action, "redirected_to_workspace")


if __name__ == "__main__":
    unittest.main()
