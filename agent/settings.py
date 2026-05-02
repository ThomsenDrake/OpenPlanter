from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


VALID_REASONING_EFFORTS: set[str] = {"low", "medium", "high"}
VALID_CHROME_MCP_CHANNELS: set[str] = {"stable", "beta", "dev", "canary"}
VALID_EMBEDDINGS_PROVIDERS: set[str] = {"voyage", "mistral"}
VALID_OBSIDIAN_EXPORT_MODES: set[str] = {"fresh_vault", "existing_vault_folder"}
DEFAULT_OBSIDIAN_EXPORT_SUBDIR = "OpenPlanter"


def normalize_reasoning_effort(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned not in VALID_REASONING_EFFORTS:
        raise ValueError(
            f"Invalid reasoning effort '{value}'. Expected one of: "
            f"{', '.join(sorted(VALID_REASONING_EFFORTS))}"
        )
    return cleaned


def normalize_bool(value: bool | str | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned in {"1", "true", "yes", "on"}:
        return True
    if cleaned in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value '{value}'.")


def normalize_chrome_mcp_channel(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned not in VALID_CHROME_MCP_CHANNELS:
        raise ValueError(
            f"Invalid Chrome MCP channel '{value}'. Expected one of: "
            f"{', '.join(sorted(VALID_CHROME_MCP_CHANNELS))}"
        )
    return cleaned


def normalize_embeddings_provider(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned not in VALID_EMBEDDINGS_PROVIDERS:
        raise ValueError(
            f"Invalid embeddings provider '{value}'. Expected one of: "
            f"{', '.join(sorted(VALID_EMBEDDINGS_PROVIDERS))}"
        )
    return cleaned


def normalize_obsidian_export_mode(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower().replace("-", "_")
    if not cleaned:
        return None
    aliases = {
        "fresh": "fresh_vault",
        "vault": "fresh_vault",
        "existing": "existing_vault_folder",
        "folder": "existing_vault_folder",
        "subfolder": "existing_vault_folder",
    }
    cleaned = aliases.get(cleaned, cleaned)
    if cleaned not in VALID_OBSIDIAN_EXPORT_MODES:
        raise ValueError(
            f"Invalid Obsidian export mode '{value}'. Expected one of: "
            f"{', '.join(sorted(VALID_OBSIDIAN_EXPORT_MODES))}"
        )
    return cleaned


@dataclass(slots=True)
class PersistentSettings:
    default_model: str | None = None
    default_reasoning_effort: str | None = None
    default_model_openai: str | None = None
    default_model_anthropic: str | None = None
    default_model_openrouter: str | None = None
    default_model_cerebras: str | None = None
    default_model_zai: str | None = None
    default_model_ollama: str | None = None
    embeddings_provider: str | None = None
    chrome_mcp_enabled: bool | None = None
    chrome_mcp_auto_connect: bool | None = None
    chrome_mcp_browser_url: str | None = None
    chrome_mcp_channel: str | None = None
    chrome_mcp_connect_timeout_sec: int | None = None
    chrome_mcp_rpc_timeout_sec: int | None = None
    default_investigation_id: str | None = None
    obsidian_export_enabled: bool | None = None
    obsidian_export_root: str | None = None
    obsidian_export_mode: str | None = None
    obsidian_export_subdir: str | None = None
    obsidian_generate_canvas: bool | None = None

    def default_model_for_provider(self, provider: str) -> str | None:
        per_provider = {
            "openai": self.default_model_openai,
            "anthropic": self.default_model_anthropic,
            "openrouter": self.default_model_openrouter,
            "cerebras": self.default_model_cerebras,
            "zai": self.default_model_zai,
            "ollama": self.default_model_ollama,
        }
        specific = per_provider.get(provider)
        if specific:
            return specific
        return self.default_model or None

    def normalized(self) -> "PersistentSettings":
        model = (self.default_model or "").strip() or None
        effort = normalize_reasoning_effort(self.default_reasoning_effort)
        return PersistentSettings(
            default_model=model,
            default_reasoning_effort=effort,
            default_model_openai=(self.default_model_openai or "").strip() or None,
            default_model_anthropic=(self.default_model_anthropic or "").strip() or None,
            default_model_openrouter=(self.default_model_openrouter or "").strip() or None,
            default_model_cerebras=(self.default_model_cerebras or "").strip() or None,
            default_model_zai=(self.default_model_zai or "").strip() or None,
            default_model_ollama=(self.default_model_ollama or "").strip() or None,
            embeddings_provider=normalize_embeddings_provider(self.embeddings_provider),
            chrome_mcp_enabled=normalize_bool(self.chrome_mcp_enabled),
            chrome_mcp_auto_connect=normalize_bool(self.chrome_mcp_auto_connect),
            chrome_mcp_browser_url=(self.chrome_mcp_browser_url or "").strip() or None,
            chrome_mcp_channel=normalize_chrome_mcp_channel(self.chrome_mcp_channel),
            chrome_mcp_connect_timeout_sec=(
                max(1, int(self.chrome_mcp_connect_timeout_sec))
                if self.chrome_mcp_connect_timeout_sec is not None
                else None
            ),
            chrome_mcp_rpc_timeout_sec=(
                max(1, int(self.chrome_mcp_rpc_timeout_sec))
                if self.chrome_mcp_rpc_timeout_sec is not None
                else None
            ),
            default_investigation_id=(self.default_investigation_id or "").strip() or None,
            obsidian_export_enabled=normalize_bool(self.obsidian_export_enabled),
            obsidian_export_root=(self.obsidian_export_root or "").strip() or None,
            obsidian_export_mode=normalize_obsidian_export_mode(self.obsidian_export_mode),
            obsidian_export_subdir=(
                ((self.obsidian_export_subdir or "").strip() or DEFAULT_OBSIDIAN_EXPORT_SUBDIR)
                if self.obsidian_export_subdir is not None
                else None
            ),
            obsidian_generate_canvas=normalize_bool(self.obsidian_generate_canvas),
        )

    def to_json(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.default_model:
            payload["default_model"] = self.default_model
        if self.default_reasoning_effort:
            payload["default_reasoning_effort"] = self.default_reasoning_effort
        if self.default_model_openai:
            payload["default_model_openai"] = self.default_model_openai
        if self.default_model_anthropic:
            payload["default_model_anthropic"] = self.default_model_anthropic
        if self.default_model_openrouter:
            payload["default_model_openrouter"] = self.default_model_openrouter
        if self.default_model_cerebras:
            payload["default_model_cerebras"] = self.default_model_cerebras
        if self.default_model_zai:
            payload["default_model_zai"] = self.default_model_zai
        if self.default_model_ollama:
            payload["default_model_ollama"] = self.default_model_ollama
        if self.embeddings_provider:
            payload["embeddings_provider"] = self.embeddings_provider
        if self.chrome_mcp_enabled is not None:
            payload["chrome_mcp_enabled"] = self.chrome_mcp_enabled
        if self.chrome_mcp_auto_connect is not None:
            payload["chrome_mcp_auto_connect"] = self.chrome_mcp_auto_connect
        if self.chrome_mcp_browser_url:
            payload["chrome_mcp_browser_url"] = self.chrome_mcp_browser_url
        if self.chrome_mcp_channel:
            payload["chrome_mcp_channel"] = self.chrome_mcp_channel
        if self.chrome_mcp_connect_timeout_sec is not None:
            payload["chrome_mcp_connect_timeout_sec"] = self.chrome_mcp_connect_timeout_sec
        if self.chrome_mcp_rpc_timeout_sec is not None:
            payload["chrome_mcp_rpc_timeout_sec"] = self.chrome_mcp_rpc_timeout_sec
        if self.default_investigation_id:
            payload["default_investigation_id"] = self.default_investigation_id
        if self.obsidian_export_enabled is not None:
            payload["obsidian_export_enabled"] = self.obsidian_export_enabled
        if self.obsidian_export_root:
            payload["obsidian_export_root"] = self.obsidian_export_root
        if self.obsidian_export_mode:
            payload["obsidian_export_mode"] = self.obsidian_export_mode
        if self.obsidian_export_subdir:
            payload["obsidian_export_subdir"] = self.obsidian_export_subdir
        if self.obsidian_generate_canvas is not None:
            payload["obsidian_generate_canvas"] = self.obsidian_generate_canvas
        return payload

    @classmethod
    def from_json(cls, payload: dict | None) -> "PersistentSettings":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            default_model=(str(payload.get("default_model", "")).strip() or None),
            default_reasoning_effort=(
                str(payload.get("default_reasoning_effort", "")).strip() or None
            ),
            default_model_openai=(str(payload.get("default_model_openai", "")).strip() or None),
            default_model_anthropic=(str(payload.get("default_model_anthropic", "")).strip() or None),
            default_model_openrouter=(str(payload.get("default_model_openrouter", "")).strip() or None),
            default_model_cerebras=(str(payload.get("default_model_cerebras", "")).strip() or None),
            default_model_zai=(str(payload.get("default_model_zai", "")).strip() or None),
            default_model_ollama=(str(payload.get("default_model_ollama", "")).strip() or None),
            embeddings_provider=(str(payload.get("embeddings_provider", "")).strip() or None),
            chrome_mcp_enabled=payload.get("chrome_mcp_enabled"),
            chrome_mcp_auto_connect=payload.get("chrome_mcp_auto_connect"),
            chrome_mcp_browser_url=(str(payload.get("chrome_mcp_browser_url", "")).strip() or None),
            chrome_mcp_channel=(str(payload.get("chrome_mcp_channel", "")).strip() or None),
            chrome_mcp_connect_timeout_sec=(
                int(payload["chrome_mcp_connect_timeout_sec"])
                if payload.get("chrome_mcp_connect_timeout_sec") is not None
                else None
            ),
            chrome_mcp_rpc_timeout_sec=(
                int(payload["chrome_mcp_rpc_timeout_sec"])
                if payload.get("chrome_mcp_rpc_timeout_sec") is not None
                else None
            ),
            default_investigation_id=(str(payload.get("default_investigation_id", "")).strip() or None),
            obsidian_export_enabled=payload.get("obsidian_export_enabled"),
            obsidian_export_root=(str(payload.get("obsidian_export_root", "")).strip() or None),
            obsidian_export_mode=(str(payload.get("obsidian_export_mode", "")).strip() or None),
            obsidian_export_subdir=(str(payload.get("obsidian_export_subdir", "")).strip() or None),
            obsidian_generate_canvas=payload.get("obsidian_generate_canvas"),
        ).normalized()


@dataclass(slots=True)
class SettingsStore:
    workspace: Path
    session_root_dir: str = ".openplanter"
    settings_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        root = self.workspace / self.session_root_dir
        root.mkdir(parents=True, exist_ok=True)
        self.settings_path = root / "settings.json"

    def load(self) -> PersistentSettings:
        if not self.settings_path.exists():
            return PersistentSettings()
        try:
            parsed = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return PersistentSettings()
        return PersistentSettings.from_json(parsed)

    def save(self, settings: PersistentSettings) -> None:
        normalized = settings.normalized()
        self.settings_path.write_text(
            json.dumps(normalized.to_json(), indent=2),
            encoding="utf-8",
        )
