from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


VALID_REASONING_EFFORTS: set[str] = {"low", "medium", "high", "xhigh"}
VALID_CHROME_MCP_CHANNELS: set[str] = {"stable", "beta", "dev", "canary"}
VALID_EMBEDDINGS_PROVIDERS: set[str] = {"voyage", "mistral"}
VALID_OBSIDIAN_EXPORT_MODES: set[str] = {"fresh_vault", "existing_vault_folder"}
VALID_LLM_PROVIDERS: set[str] = {
    "openai",
    "anthropic",
    "openrouter",
    "cerebras",
    "zai",
    "ollama",
}
DEFAULT_OBSIDIAN_EXPORT_SUBDIR = "Cestus"
PROFILE_MODALITIES: tuple[str, ...] = ("llm", "embedding", "stt")
DEFAULT_LLM_BASE_URLS: dict[str, str] = {
    "openai": "https://foundry-proxy.cheetah-koi.ts.net/openai/v1",
    "anthropic": "https://foundry-proxy.cheetah-koi.ts.net/anthropic/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "zai": "https://api.z.ai/api/paas/v4",
    "ollama": "http://localhost:11434/v1",
}
DEFAULT_EMBEDDING_MODELS: dict[str, str] = {
    "voyage": "voyage-4",
    "mistral": "mistral-embed",
}
DEFAULT_EMBEDDING_BASE_URLS: dict[str, str] = {
    "voyage": "https://api.voyageai.com",
    "mistral": "https://api.mistral.ai",
}
DEFAULT_STT_OPTIONS: dict[str, int | float] = {
    "max_bytes": 100 * 1024 * 1024,
    "chunk_max_seconds": 900,
    "chunk_overlap_seconds": 2.0,
    "max_chunks": 48,
    "request_timeout_sec": 180,
}


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
            f"Invalid legacy Chrome channel '{value}'. Expected one of: "
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


def _slugify_profile_id(*parts: str) -> str:
    raw = "-".join(part for part in parts if part).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "default"


def _infer_llm_provider(model: str | None) -> str:
    text = (model or "").strip().lower()
    if text.startswith("anthropic-foundry/") or text.startswith("claude"):
        return "anthropic"
    if text.startswith("azure-foundry/") or text.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if "/" in text:
        return "openrouter"
    if text.startswith(("glm", "zai-glm")):
        return "zai"
    if text.startswith(("qwen-3", "gpt-oss", "llama-4")):
        return "cerebras"
    if text.startswith(("llama", "mistral", "gemma", "phi", "codellama", "deepseek")):
        return "ollama"
    return "anthropic"


def _default_auth_ref(provider: str, modality: str) -> str:
    if modality == "embedding" and provider in {"voyage", "mistral"}:
        return provider
    if modality == "stt":
        return "mistral"
    return provider


def _default_base_url(provider: str, modality: str) -> str | None:
    if modality == "embedding":
        return DEFAULT_EMBEDDING_BASE_URLS.get(provider)
    if modality == "stt":
        return "https://api.mistral.ai"
    return DEFAULT_LLM_BASE_URLS.get(provider)


def _default_model(provider: str, modality: str) -> str | None:
    if modality == "embedding":
        return DEFAULT_EMBEDDING_MODELS.get(provider)
    if modality == "stt":
        return "voxtral-mini-latest"
    return None


@dataclass(slots=True)
class ProviderProfile:
    name: str | None = None
    provider: str = ""
    adapter: str = ""
    model: str = ""
    base_url: str | None = None
    auth_ref: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def normalized(self, modality: str) -> "ProviderProfile":
        modality = modality.strip().lower()
        provider = (self.provider or "").strip().lower()
        if modality == "embedding":
            provider = normalize_embeddings_provider(provider)
        elif modality == "stt":
            provider = provider or "mistral"
        else:
            provider = provider or _infer_llm_provider(self.model)
            if provider not in VALID_LLM_PROVIDERS:
                provider = _infer_llm_provider(self.model)

        adapter = (self.adapter or "").strip().lower()
        if not adapter:
            adapter = {
                "llm": "anthropic" if provider == "anthropic" else "openai-compatible",
                "embedding": "embedding",
                "stt": "speech-to-text",
            }.get(modality, modality)

        model = (self.model or "").strip() or _default_model(provider, modality) or ""
        base_url = (self.base_url or "").strip().rstrip("/") or _default_base_url(
            provider, modality
        )
        auth_ref = (self.auth_ref or "").strip().lower() or _default_auth_ref(
            provider, modality
        )
        options = dict(self.options or {})
        if modality == "stt":
            options = {**DEFAULT_STT_OPTIONS, **options}
        return ProviderProfile(
            name=(self.name or "").strip() or None,
            provider=provider,
            adapter=adapter,
            model=model,
            base_url=base_url,
            auth_ref=auth_ref,
            options=options,
        )

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "adapter": self.adapter,
            "model": self.model,
        }
        if self.name:
            payload["name"] = self.name
        if self.base_url:
            payload["base_url"] = self.base_url
        if self.auth_ref:
            payload["auth_ref"] = self.auth_ref
        if self.options:
            payload["options"] = self.options
        return payload

    @classmethod
    def from_json(cls, payload: Any) -> "ProviderProfile | None":
        if not isinstance(payload, dict):
            return None
        options = payload.get("options")
        return cls(
            name=(str(payload.get("name", "")).strip() or None),
            provider=str(payload.get("provider", "")).strip(),
            adapter=str(payload.get("adapter", "")).strip(),
            model=str(payload.get("model", "")).strip(),
            base_url=(str(payload.get("base_url", "")).strip() or None),
            auth_ref=(str(payload.get("auth_ref", "")).strip() or None),
            options=dict(options) if isinstance(options, dict) else {},
        )


def _normalize_profile_pools(
    pools: dict[str, dict[str, ProviderProfile | dict[str, Any]]] | None,
) -> tuple[dict[str, dict[str, ProviderProfile]], dict[str, dict[str, str]]]:
    normalized: dict[str, dict[str, ProviderProfile]] = {
        modality: {} for modality in PROFILE_MODALITIES
    }
    id_map: dict[str, dict[str, str]] = {modality: {} for modality in PROFILE_MODALITIES}
    if not isinstance(pools, dict):
        return normalized, id_map
    for modality in PROFILE_MODALITIES:
        raw_pool = pools.get(modality)
        if not isinstance(raw_pool, dict):
            continue
        for raw_id, raw_profile in raw_pool.items():
            profile = (
                raw_profile
                if isinstance(raw_profile, ProviderProfile)
                else ProviderProfile.from_json(raw_profile)
            )
            if profile is None:
                continue
            profile = profile.normalized(modality)
            if not profile.model and modality != "embedding":
                continue
            profile_id = _slugify_profile_id(str(raw_id)) or _slugify_profile_id(
                profile.provider, profile.model
            )
            if profile_id in normalized[modality]:
                base_id = profile_id
                counter = 2
                while f"{base_id}-{counter}" in normalized[modality]:
                    counter += 1
                profile_id = f"{base_id}-{counter}"
            id_map[modality][str(raw_id)] = profile_id
            normalized[modality][profile_id] = profile
    return normalized, id_map


def _upsert_profile(
    pools: dict[str, dict[str, ProviderProfile]],
    active: dict[str, str],
    modality: str,
    profile: ProviderProfile,
    *,
    profile_id: str | None = None,
    make_active: bool = False,
    replace: bool = False,
) -> str:
    normalized = profile.normalized(modality)
    selected_id = _slugify_profile_id(
        profile_id or normalized.provider,
        "" if profile_id else normalized.model,
    )
    pools.setdefault(modality, {})
    if replace or selected_id not in pools[modality]:
        pools[modality][selected_id] = normalized
    if make_active or not active.get(modality):
        active[modality] = selected_id
    return selected_id


def _migrate_legacy_profiles(
    pools: dict[str, dict[str, ProviderProfile]],
    active: dict[str, str],
    settings: "PersistentSettings",
) -> None:
    provider_models = {
        "openai": settings.default_model_openai,
        "anthropic": settings.default_model_anthropic,
        "openrouter": settings.default_model_openrouter,
        "cerebras": settings.default_model_cerebras,
        "zai": settings.default_model_zai,
        "ollama": settings.default_model_ollama,
    }
    for provider, model in provider_models.items():
        if not model:
            continue
        options: dict[str, Any] = {}
        if provider == "zai" and settings.zai_plan:
            options["zai_plan"] = settings.zai_plan
        _upsert_profile(
            pools,
            active,
            "llm",
            ProviderProfile(
                name=f"{provider} default",
                provider=provider,
                model=model,
                base_url=DEFAULT_LLM_BASE_URLS.get(provider),
                auth_ref=provider,
                options=options,
            ),
            profile_id=f"{provider}-default",
            make_active=False,
            replace=True,
        )

    if settings.default_model:
        provider = _infer_llm_provider(settings.default_model)
        _upsert_profile(
            pools,
            active,
            "llm",
            ProviderProfile(
                name="Workspace default LLM",
                provider=provider,
                model=settings.default_model,
                base_url=DEFAULT_LLM_BASE_URLS.get(provider),
                auth_ref=provider,
            ),
            profile_id="workspace-default",
            make_active=not active.get("llm"),
            replace=True,
        )

    if settings.embeddings_provider:
        provider = normalize_embeddings_provider(settings.embeddings_provider)
        _upsert_profile(
            pools,
            active,
            "embedding",
            ProviderProfile(
                name=f"{provider.title()} embeddings",
                provider=provider,
                adapter="embedding",
                model=DEFAULT_EMBEDDING_MODELS[provider],
                base_url=DEFAULT_EMBEDDING_BASE_URLS[provider],
                auth_ref=provider,
            ),
            profile_id=f"{provider}-default",
            make_active=not active.get("embedding"),
            replace=True,
        )

    stt_options = {
        "max_bytes": settings.mistral_transcription_max_bytes,
        "chunk_max_seconds": settings.mistral_transcription_chunk_max_seconds,
        "chunk_overlap_seconds": settings.mistral_transcription_chunk_overlap_seconds,
        "max_chunks": settings.mistral_transcription_max_chunks,
        "request_timeout_sec": settings.mistral_transcription_request_timeout_sec,
    }
    if (
        settings.mistral_transcription_model
        or settings.mistral_transcription_base_url
        or any(value is not None for value in stt_options.values())
    ):
        _upsert_profile(
            pools,
            active,
            "stt",
            ProviderProfile(
                name="Mistral Voxtral STT",
                provider="mistral",
                adapter="speech-to-text",
                model=settings.mistral_transcription_model or "voxtral-mini-latest",
                base_url=settings.mistral_transcription_base_url
                or "https://api.mistral.ai",
                auth_ref="mistral",
                options={
                    key: value
                    for key, value in stt_options.items()
                    if value is not None
                },
            ),
            profile_id="mistral-voxtral",
            make_active=not active.get("stt"),
            replace=True,
        )


@dataclass(slots=True)
class PersistentSettings:
    active_profiles: dict[str, str] = field(default_factory=dict)
    profiles: dict[str, dict[str, ProviderProfile]] = field(default_factory=dict)
    default_model: str | None = None
    default_reasoning_effort: str | None = None
    default_model_openai: str | None = None
    default_model_anthropic: str | None = None
    default_model_openrouter: str | None = None
    default_model_cerebras: str | None = None
    default_model_zai: str | None = None
    default_model_ollama: str | None = None
    zai_plan: str | None = None
    web_search_provider: str | None = None
    embeddings_provider: str | None = None
    mistral_transcription_base_url: str | None = None
    mistral_transcription_model: str | None = None
    mistral_transcription_max_bytes: int | None = None
    mistral_transcription_chunk_max_seconds: int | None = None
    mistral_transcription_chunk_overlap_seconds: float | None = None
    mistral_transcription_max_chunks: int | None = None
    mistral_transcription_request_timeout_sec: int | None = None
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

    def active_profile(self, modality: str) -> ProviderProfile | None:
        modality = modality.strip().lower()
        profile_id = self.active_profiles.get(modality)
        if not profile_id:
            return None
        return self.profiles.get(modality, {}).get(profile_id)

    def first_profile_for_provider(
        self, modality: str, provider: str
    ) -> tuple[str, ProviderProfile] | None:
        provider = provider.strip().lower()
        for profile_id, profile in self.profiles.get(modality, {}).items():
            if profile.provider == provider:
                return profile_id, profile
        return None

    def default_model_for_provider(self, provider: str) -> str | None:
        if active := self.active_profile("llm"):
            if provider == "auto" or active.provider == provider:
                return active.model or None
        if match := self.first_profile_for_provider("llm", provider):
            return match[1].model or None
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
        profiles, profile_id_map = _normalize_profile_pools(self.profiles)
        active_profiles = {
            modality: profile_id_map.get(modality, {}).get(
                (self.active_profiles.get(modality, "") or "").strip(),
                _slugify_profile_id((self.active_profiles.get(modality, "") or "").strip()),
            )
            for modality in PROFILE_MODALITIES
            if (self.active_profiles.get(modality, "") or "").strip()
        }
        normalized_settings = PersistentSettings(
            active_profiles=active_profiles,
            profiles=profiles,
            default_model=model,
            default_reasoning_effort=effort,
            default_model_openai=(self.default_model_openai or "").strip() or None,
            default_model_anthropic=(self.default_model_anthropic or "").strip() or None,
            default_model_openrouter=(self.default_model_openrouter or "").strip() or None,
            default_model_cerebras=(self.default_model_cerebras or "").strip() or None,
            default_model_zai=(self.default_model_zai or "").strip() or None,
            default_model_ollama=(self.default_model_ollama or "").strip() or None,
            zai_plan=(self.zai_plan or "").strip() or None,
            web_search_provider=(self.web_search_provider or "").strip().lower() or None,
            embeddings_provider=normalize_embeddings_provider(self.embeddings_provider),
            mistral_transcription_base_url=(
                (self.mistral_transcription_base_url or "").strip().rstrip("/") or None
            ),
            mistral_transcription_model=(
                (self.mistral_transcription_model or "").strip() or None
            ),
            mistral_transcription_max_bytes=(
                max(1, int(self.mistral_transcription_max_bytes))
                if self.mistral_transcription_max_bytes is not None
                else None
            ),
            mistral_transcription_chunk_max_seconds=(
                max(1, int(self.mistral_transcription_chunk_max_seconds))
                if self.mistral_transcription_chunk_max_seconds is not None
                else None
            ),
            mistral_transcription_chunk_overlap_seconds=(
                max(0.0, float(self.mistral_transcription_chunk_overlap_seconds))
                if self.mistral_transcription_chunk_overlap_seconds is not None
                else None
            ),
            mistral_transcription_max_chunks=(
                max(1, int(self.mistral_transcription_max_chunks))
                if self.mistral_transcription_max_chunks is not None
                else None
            ),
            mistral_transcription_request_timeout_sec=(
                max(1, int(self.mistral_transcription_request_timeout_sec))
                if self.mistral_transcription_request_timeout_sec is not None
                else None
            ),
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
        _migrate_legacy_profiles(
            normalized_settings.profiles,
            normalized_settings.active_profiles,
            normalized_settings,
        )
        for modality in PROFILE_MODALITIES:
            active_id = normalized_settings.active_profiles.get(modality)
            if active_id and active_id not in normalized_settings.profiles.get(modality, {}):
                normalized_settings.active_profiles.pop(modality, None)
        return normalized_settings

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.active_profiles:
            payload["active_profiles"] = dict(self.active_profiles)
        serializable_profiles = {
            modality: {
                profile_id: profile.to_json()
                for profile_id, profile in pool.items()
            }
            for modality, pool in self.profiles.items()
            if pool
        }
        if serializable_profiles:
            payload["profiles"] = serializable_profiles
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
        if self.zai_plan:
            payload["zai_plan"] = self.zai_plan
        if self.web_search_provider:
            payload["web_search_provider"] = self.web_search_provider
        if self.embeddings_provider:
            payload["embeddings_provider"] = self.embeddings_provider
        if self.mistral_transcription_base_url:
            payload["mistral_transcription_base_url"] = self.mistral_transcription_base_url
        if self.mistral_transcription_model:
            payload["mistral_transcription_model"] = self.mistral_transcription_model
        if self.mistral_transcription_max_bytes is not None:
            payload["mistral_transcription_max_bytes"] = self.mistral_transcription_max_bytes
        if self.mistral_transcription_chunk_max_seconds is not None:
            payload["mistral_transcription_chunk_max_seconds"] = (
                self.mistral_transcription_chunk_max_seconds
            )
        if self.mistral_transcription_chunk_overlap_seconds is not None:
            payload["mistral_transcription_chunk_overlap_seconds"] = (
                self.mistral_transcription_chunk_overlap_seconds
            )
        if self.mistral_transcription_max_chunks is not None:
            payload["mistral_transcription_max_chunks"] = self.mistral_transcription_max_chunks
        if self.mistral_transcription_request_timeout_sec is not None:
            payload["mistral_transcription_request_timeout_sec"] = (
                self.mistral_transcription_request_timeout_sec
            )
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
        raw_active = payload.get("active_profiles")
        active_profiles = {
            str(key).strip().lower(): str(value).strip()
            for key, value in (raw_active.items() if isinstance(raw_active, dict) else [])
            if str(key).strip().lower() in PROFILE_MODALITIES and str(value).strip()
        }
        raw_profiles = payload.get("profiles")

        def get_int(key: str) -> int | None:
            value = payload.get(key)
            if value is None or value == "":
                return None
            return int(value)

        def get_float(key: str) -> float | None:
            value = payload.get(key)
            if value is None or value == "":
                return None
            return float(value)

        return cls(
            active_profiles=active_profiles,
            profiles=raw_profiles if isinstance(raw_profiles, dict) else {},
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
            zai_plan=(str(payload.get("zai_plan", "")).strip() or None),
            web_search_provider=(str(payload.get("web_search_provider", "")).strip() or None),
            embeddings_provider=(str(payload.get("embeddings_provider", "")).strip() or None),
            mistral_transcription_base_url=(
                str(payload.get("mistral_transcription_base_url", "")).strip() or None
            ),
            mistral_transcription_model=(
                str(payload.get("mistral_transcription_model", "")).strip() or None
            ),
            mistral_transcription_max_bytes=get_int("mistral_transcription_max_bytes"),
            mistral_transcription_chunk_max_seconds=get_int(
                "mistral_transcription_chunk_max_seconds"
            ),
            mistral_transcription_chunk_overlap_seconds=get_float(
                "mistral_transcription_chunk_overlap_seconds"
            ),
            mistral_transcription_max_chunks=get_int("mistral_transcription_max_chunks"),
            mistral_transcription_request_timeout_sec=get_int(
                "mistral_transcription_request_timeout_sec"
            ),
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
