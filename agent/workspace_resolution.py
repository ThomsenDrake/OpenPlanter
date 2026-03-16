from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .credentials import discover_env_candidates, parse_env_assignments

WORKSPACE_ENV_KEY = "OPENPLANTER_WORKSPACE"

WorkspaceSource = Literal["cli_arg", "env", "dotenv", "cwd"]
GuardrailAction = Literal["none", "redirected_to_workspace"]


class WorkspaceResolutionError(RuntimeError):
    """Raised when startup would use an unsafe workspace path."""


@dataclass(slots=True)
class WorkspaceResolution:
    workspace: Path
    source: WorkspaceSource
    env_path: Path | None = None
    invalid_env_override: str | None = None
    invalid_dotenv_value: str | None = None
    guardrail_action: GuardrailAction = "none"
    warnings: list[str] = field(default_factory=list)


def resolve_startup_workspace(
    cli_workspace: str,
    cli_workspace_explicit: bool,
    cwd: Path,
) -> WorkspaceResolution:
    cwd = _normalize_path(cwd)
    warnings: list[str] = []
    invalid_env_override: str | None = None
    invalid_dotenv_value: str | None = None

    if cli_workspace_explicit:
        candidate = _resolve_candidate(cli_workspace, cwd)
        if candidate.exists() and not candidate.is_dir():
            raise WorkspaceResolutionError(
                f"Refusing to use a file as the workspace: {candidate}. "
                "Pass --workspace to a directory path instead."
            )
        workspace, guardrail_action = _apply_repo_root_guardrail(candidate, allow_redirect=False)
        return WorkspaceResolution(
            workspace=workspace,
            source="cli_arg",
            guardrail_action=guardrail_action,
        )

    env_override = (os.getenv(WORKSPACE_ENV_KEY) or "").strip()
    if env_override:
        candidate = _resolve_candidate(env_override, cwd)
        if candidate.is_dir():
            workspace, guardrail_action = _apply_repo_root_guardrail(candidate, allow_redirect=True)
            return WorkspaceResolution(
                workspace=workspace,
                source="env",
                guardrail_action=guardrail_action,
            )
        invalid_env_override = env_override
        warnings.append(
            f"Ignoring {WORKSPACE_ENV_KEY} from process environment because it does not resolve to an existing directory: {env_override}"
        )

    env_path = next(iter(discover_env_candidates(cwd)), None)
    if env_path is not None:
        raw_value = (parse_env_assignments(env_path).get(WORKSPACE_ENV_KEY) or "").strip()
        if raw_value:
            candidate = _resolve_candidate(raw_value, env_path.parent)
            if candidate.is_dir():
                workspace, guardrail_action = _apply_repo_root_guardrail(candidate, allow_redirect=True)
                return WorkspaceResolution(
                    workspace=workspace,
                    source="dotenv",
                    env_path=env_path,
                    invalid_env_override=invalid_env_override,
                    guardrail_action=guardrail_action,
                    warnings=warnings,
                )
            invalid_dotenv_value = raw_value
            warnings.append(
                f"Ignoring {WORKSPACE_ENV_KEY} from {env_path} because it does not resolve to an existing directory: {raw_value}"
            )

    workspace, guardrail_action = _apply_repo_root_guardrail(cwd, allow_redirect=True)
    return WorkspaceResolution(
        workspace=workspace,
        source="cwd",
        env_path=env_path,
        invalid_env_override=invalid_env_override,
        invalid_dotenv_value=invalid_dotenv_value,
        guardrail_action=guardrail_action,
        warnings=warnings,
    )


def _resolve_candidate(raw_value: str, base_dir: Path) -> Path:
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return _normalize_path(candidate)


def _normalize_path(path: Path) -> Path:
    return Path(os.path.realpath(os.fspath(path.expanduser())))


def _find_repo_root(start: Path) -> Path | None:
    current = _normalize_path(start)
    while True:
        if current.joinpath(".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _apply_repo_root_guardrail(candidate: Path, allow_redirect: bool) -> tuple[Path, GuardrailAction]:
    candidate = _normalize_path(candidate)
    repo_root = _find_repo_root(candidate)
    if repo_root is not None and repo_root == candidate:
        workspace_dir = repo_root / "workspace"
        if allow_redirect and workspace_dir.is_dir():
            return (_normalize_path(workspace_dir), "redirected_to_workspace")
        raise WorkspaceResolutionError(
            f"Refusing to use repository root as the workspace: {repo_root}. "
            f"Set {WORKSPACE_ENV_KEY} in the nearest .env or pass --workspace to a non-root directory."
        )
    return (candidate, "none")
