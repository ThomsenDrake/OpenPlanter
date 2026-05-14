from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import AgentConfig
from .engine import RLMEngine, _MODEL_CONTEXT_WINDOWS, _DEFAULT_CONTEXT_WINDOW
from .model import EchoFallbackModel, ModelError
from .retrieval import build_embeddings_status
from .runtime import SessionRuntime
from .settings import ProviderProfile, SettingsStore, _slugify_profile_id


SLASH_COMMANDS: list[str] = [
    "/quit",
    "/exit",
    "/help",
    "/status",
    "/clear",
    "/model",
    "/reasoning",
    "/embeddings",
    "/stt",
    "/chrome",
]


def _queue_prompt_style():
    """Return a prompt_toolkit Style for the queued-input prompt."""
    from prompt_toolkit.styles import Style
    return Style.from_dict({"dim": "ansigray"})




def _make_left_markdown():
    """Create a Markdown subclass that left-aligns headings instead of centering."""
    from rich import box as _box
    from rich.markdown import Markdown as _RichMarkdown, Heading as _RichHeading
    from rich.panel import Panel as _Panel
    from rich.text import Text as _Text

    class _LeftHeading(_RichHeading):
        def __rich_console__(self, console, options):
            text = self.text
            text.justify = "left"
            if self.tag == "h1":
                yield _Panel(text, box=_box.HEAVY, style="markdown.h1.border")
            else:
                if self.tag == "h2":
                    yield _Text("")
                yield text

    class _LeftMarkdown(_RichMarkdown):
        elements = {**_RichMarkdown.elements, "heading_open": _LeftHeading}

    return _LeftMarkdown


_LeftMarkdown = _make_left_markdown()

SPLASH_ART = r"""      \\     //       ____ _____ ____ _____ _   _ ____       \\     //
   \\  \\   //  //   / ___| ____/ ___|_   _| | | / ___|   \\  \\   //  //
    \\  .---.  //   | |   |  _| \___ \ | | | | | \___ \    \\  .---.  //
        ( o )       | |___| |___ ___) || | | |_| |___) |       ( o )
        `-+-'        \____|_____|____/ |_|  \___/|____/        `-+-'
         / \                                                    / \
        /___\                                                  /___\
""".rstrip("\n")

# Short aliases for common models.  Keys are lowered before lookup.
HELP_LINES: list[str] = [
    "Commands:",
    "  /model              Show current model, provider, aliases",
    "  /model <name>       Switch model (e.g. /model opus, /model gpt5)",
    "  /model <name> --save  Switch and persist as default",
    "  /model list [all]   List available models",
    "  /model profiles | /model profile <id>  List or switch saved LLM profiles",
    "  /reasoning [low|medium|high|xhigh|off]  Change reasoning effort",
    "  /embeddings [voyage|mistral] [--save]  Change retrieval embeddings provider",
    "  /embeddings profiles | /embeddings profile <id>  List or switch saved embedding profiles",
    "  /stt [model] [--save]  Change audio/STT transcription model",
    "  /stt profiles | /stt profile <id>  List or switch saved STT profiles",
    "  /chrome status|on|off|auto|url <endpoint>|channel <stable|beta|dev|canary> [--save]",
    "  /status  /clear  /quit  /exit  /help",
]

MODEL_ALIASES: dict[str, str] = {
    "opus": "anthropic-foundry/claude-opus-4-6",
    "opus4.6": "anthropic-foundry/claude-opus-4-6",
    "sonnet": "anthropic-foundry/claude-sonnet-4-6",
    "sonnet4.6": "anthropic-foundry/claude-sonnet-4-6",
    "haiku": "anthropic-foundry/claude-haiku-4-5",
    "haiku4.5": "anthropic-foundry/claude-haiku-4-5",
    "gpt5": "azure-foundry/gpt-5.5",
    "gpt-5": "azure-foundry/gpt-5.5",
    "gpt5.3": "azure-foundry/gpt-5.3-codex",
    "gpt-5.3": "azure-foundry/gpt-5.3-codex",
    "gpt5.4": "azure-foundry/gpt-5.4",
    "gpt-5.4": "azure-foundry/gpt-5.4",
    "gpt5.5": "azure-foundry/gpt-5.5",
    "gpt-5.5": "azure-foundry/gpt-5.5",
    "kimi": "azure-foundry/Kimi-K2.5",
    "gpt4": "gpt-4.1",
    "gpt4.1": "gpt-4.1",
    "gpt4o": "gpt-4o",
    "o4": "o4-mini",
    "o4-mini": "o4-mini",
    "o3": "o3-mini",
    "o3-mini": "o3-mini",
    "cerebras": "qwen-3-235b-a22b-instruct-2507",
    "qwen235b": "qwen-3-235b-a22b-instruct-2507",
    "oss120b": "gpt-oss-120b",
    "glm5": "glm-5",
    "zai": "glm-5",
    "llama": "llama3.2",
    "llama3": "llama3.2",
    "mistral": "mistral",
}


@dataclass
class ChatContext:
    runtime: SessionRuntime
    cfg: AgentConfig
    settings_store: SettingsStore


def _format_token_count(n: int) -> str:
    """Format a token count for display: 1234 -> '1.2k', 15678 -> '15.7k'."""
    if n < 1000:
        return str(n)
    if n < 10000:
        return f"{n / 1000:.1f}k"
    if n < 1000000:
        return f"{n / 1000:.0f}k"
    return f"{n / 1000000:.1f}M"


def _format_session_tokens(session_tokens: dict[str, dict[str, int]]) -> str:
    """Build a compact token summary string from engine.session_tokens."""
    total_in = sum(v["input"] for v in session_tokens.values())
    total_out = sum(v["output"] for v in session_tokens.values())
    if total_in == 0 and total_out == 0:
        return ""
    return f"{_format_token_count(total_in)} in / {_format_token_count(total_out)} out"


def _get_model_display_name(engine: RLMEngine) -> str:
    """Extract a human-readable model name from the engine's model object."""
    model = engine.model
    if isinstance(model, EchoFallbackModel):
        return "(no model)"
    return getattr(model, "model", "(unknown)")


def _api_key_for_provider(cfg: AgentConfig, provider: str) -> str | None:
    """Return the configured API key for *provider*, or ``None``."""
    return {
        "openai": cfg.openai_api_key,
        "anthropic": cfg.anthropic_api_key,
        "openrouter": cfg.openrouter_api_key,
        "cerebras": cfg.cerebras_api_key,
        "zai": cfg.zai_api_key,
        "ollama": "ollama",
    }.get(provider)


def _available_providers(cfg: AgentConfig) -> list[str]:
    """Return provider names that have an API key configured."""
    providers: list[str] = []
    if cfg.openai_api_key:
        providers.append("openai")
    if cfg.anthropic_api_key:
        providers.append("anthropic")
    if cfg.openrouter_api_key:
        providers.append("openrouter")
    if cfg.cerebras_api_key:
        providers.append("cerebras")
    if cfg.zai_api_key:
        providers.append("zai")
    providers.append("ollama")
    return providers


def _base_url_for_provider(cfg: AgentConfig, provider: str) -> str | None:
    return {
        "openai": cfg.openai_base_url,
        "anthropic": cfg.anthropic_base_url,
        "openrouter": cfg.openrouter_base_url,
        "cerebras": cfg.cerebras_base_url,
        "zai": cfg.zai_base_url,
        "ollama": cfg.ollama_base_url,
    }.get(provider)


def _set_base_url_for_provider(cfg: AgentConfig, provider: str, base_url: str | None) -> None:
    if not base_url:
        return
    if provider == "openai":
        cfg.openai_base_url = base_url
        cfg.base_url = base_url
    elif provider == "anthropic":
        cfg.anthropic_base_url = base_url
    elif provider == "openrouter":
        cfg.openrouter_base_url = base_url
    elif provider == "cerebras":
        cfg.cerebras_base_url = base_url
    elif provider == "zai":
        cfg.zai_base_url = base_url
    elif provider == "ollama":
        cfg.ollama_base_url = base_url


def _format_profile_pool(
    settings: Any,
    modality: str,
    label: str,
) -> list[str]:
    pool = settings.profiles.get(modality, {})
    if not pool:
        return [f"No saved {label} profiles."]
    active = settings.active_profiles.get(modality)
    lines = [f"{label.title()} profiles:"]
    for profile_id in sorted(pool):
        profile = pool[profile_id]
        marker = "*" if profile_id == active else " "
        name = f"{profile.name}: " if profile.name else ""
        lines.append(f"{marker} {profile_id} - {name}{profile.provider}/{profile.model}")
    return lines


def _apply_llm_profile(ctx: ChatContext, profile_id: str, profile: ProviderProfile) -> None:
    ctx.cfg.llm_profile_id = profile_id
    ctx.cfg.llm_profile_name = profile.name
    ctx.cfg.provider = profile.provider
    ctx.cfg.model = profile.model
    _set_base_url_for_provider(ctx.cfg, profile.provider, profile.base_url)
    effort = str(profile.options.get("reasoning_effort", "") or "").strip().lower()
    if effort:
        ctx.cfg.reasoning_effort = None if effort in {"off", "none"} else effort


def _clear_llm_profile(ctx: ChatContext) -> None:
    ctx.cfg.llm_profile_id = None
    ctx.cfg.llm_profile_name = None
    ctx.runtime.engine.config.llm_profile_id = None
    ctx.runtime.engine.config.llm_profile_name = None


def _apply_embedding_profile(ctx: ChatContext, profile_id: str, profile: ProviderProfile) -> None:
    ctx.cfg.embedding_profile_id = profile_id
    ctx.cfg.embedding_profile_name = profile.name
    ctx.cfg.embeddings_provider = profile.provider
    ctx.cfg.embeddings_model = profile.model or (
        "voyage-4" if profile.provider == "voyage" else "mistral-embed"
    )
    ctx.cfg.embeddings_base_url = profile.base_url or (
        "https://api.voyageai.com"
        if profile.provider == "voyage"
        else "https://api.mistral.ai"
    )
    ctx.runtime.engine.config.embeddings_provider = ctx.cfg.embeddings_provider
    ctx.runtime.engine.config.embeddings_model = ctx.cfg.embeddings_model
    ctx.runtime.engine.config.embeddings_base_url = ctx.cfg.embeddings_base_url


def _clear_embedding_profile(ctx: ChatContext) -> None:
    ctx.cfg.embedding_profile_id = None
    ctx.cfg.embedding_profile_name = None
    ctx.runtime.engine.config.embedding_profile_id = None
    ctx.runtime.engine.config.embedding_profile_name = None


def _profile_option_int(profile: ProviderProfile, key: str, fallback: int) -> int:
    value = profile.options.get(key)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return fallback


def _profile_option_float(profile: ProviderProfile, key: str, fallback: float) -> float:
    value = profile.options.get(key)
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return fallback


def _apply_stt_profile(ctx: ChatContext, profile_id: str, profile: ProviderProfile) -> None:
    ctx.cfg.stt_profile_id = profile_id
    ctx.cfg.stt_profile_name = profile.name
    if profile.provider != "mistral":
        return
    ctx.cfg.mistral_transcription_model = profile.model or ctx.cfg.mistral_transcription_model
    ctx.cfg.mistral_transcription_base_url = (
        profile.base_url or ctx.cfg.mistral_transcription_base_url
    )
    ctx.cfg.mistral_transcription_max_bytes = _profile_option_int(
        profile,
        "max_bytes",
        ctx.cfg.mistral_transcription_max_bytes,
    )
    ctx.cfg.mistral_transcription_chunk_max_seconds = _profile_option_int(
        profile,
        "chunk_max_seconds",
        ctx.cfg.mistral_transcription_chunk_max_seconds,
    )
    ctx.cfg.mistral_transcription_chunk_overlap_seconds = _profile_option_float(
        profile,
        "chunk_overlap_seconds",
        ctx.cfg.mistral_transcription_chunk_overlap_seconds,
    )
    ctx.cfg.mistral_transcription_max_chunks = _profile_option_int(
        profile,
        "max_chunks",
        ctx.cfg.mistral_transcription_max_chunks,
    )
    ctx.cfg.mistral_transcription_request_timeout_sec = _profile_option_int(
        profile,
        "request_timeout_sec",
        ctx.cfg.mistral_transcription_request_timeout_sec,
    )
    ctx.runtime.engine.config.mistral_transcription_model = ctx.cfg.mistral_transcription_model
    ctx.runtime.engine.config.mistral_transcription_base_url = (
        ctx.cfg.mistral_transcription_base_url
    )
    ctx.runtime.engine.config.mistral_transcription_max_bytes = (
        ctx.cfg.mistral_transcription_max_bytes
    )
    ctx.runtime.engine.config.mistral_transcription_chunk_max_seconds = (
        ctx.cfg.mistral_transcription_chunk_max_seconds
    )
    ctx.runtime.engine.config.mistral_transcription_chunk_overlap_seconds = (
        ctx.cfg.mistral_transcription_chunk_overlap_seconds
    )
    ctx.runtime.engine.config.mistral_transcription_max_chunks = (
        ctx.cfg.mistral_transcription_max_chunks
    )
    ctx.runtime.engine.config.mistral_transcription_request_timeout_sec = (
        ctx.cfg.mistral_transcription_request_timeout_sec
    )


def _clear_stt_profile(ctx: ChatContext) -> None:
    ctx.cfg.stt_profile_id = None
    ctx.cfg.stt_profile_name = None
    ctx.runtime.engine.config.stt_profile_id = None
    ctx.runtime.engine.config.stt_profile_name = None


def handle_model_command(args: str, ctx: ChatContext) -> list[str]:
    """Handle /model sub-commands. Returns display lines."""
    from .builder import (
        _fetch_models_for_provider,
        build_engine,
        infer_provider_for_model,
    )

    parts = args.strip().split()

    if not parts:
        model_name = _get_model_display_name(ctx.runtime.engine)
        effort = ctx.cfg.reasoning_effort or "(off)"
        avail = ", ".join(_available_providers(ctx.cfg)) or "none"
        profile = ctx.cfg.llm_profile_name or ctx.cfg.llm_profile_id or "(none)"
        return [
            f"Provider: {ctx.cfg.provider} | Model: {model_name} | Reasoning: {effort}",
            f"Active LLM profile: {profile}",
            f"Configured providers: {avail}",
            f"Aliases: {', '.join(sorted(MODEL_ALIASES.keys()))}",
        ]

    if parts[0] in {"profiles", "profile"}:
        settings = ctx.settings_store.load()
        if parts[0] == "profiles" or len(parts) < 2:
            return _format_profile_pool(settings, "llm", "LLM")
        profile_id = parts[1].strip()
        profile = settings.profiles.get("llm", {}).get(profile_id)
        if profile is None:
            return [f"Unknown LLM profile '{profile_id}'."] + _format_profile_pool(
                settings,
                "llm",
                "LLM",
            )
        _apply_llm_profile(ctx, profile_id, profile)
        try:
            new_engine = build_engine(ctx.cfg)
        except ModelError as exc:
            return [f"Failed to switch LLM profile: {exc}"]
        ctx.runtime.engine = new_engine
        settings.active_profiles["llm"] = profile_id
        ctx.settings_store.save(settings)
        return [f"Switched to LLM profile: {profile_id}"]

    # /model list [all|<provider>]
    if parts[0] == "list":
        list_target = parts[1] if len(parts) > 1 else None
        if list_target == "all":
            providers = _available_providers(ctx.cfg)
        elif list_target in {"openai", "anthropic", "openrouter", "cerebras", "zai", "ollama"}:
            providers = [list_target]
        else:
            providers = [ctx.cfg.provider]

        lines: list[str] = []
        for provider in providers:
            try:
                models = _fetch_models_for_provider(ctx.cfg, provider)
            except ModelError as exc:
                lines.append(f"{provider}: skipped ({exc})")
                continue
            lines.append(f"{provider}: {len(models)} models")
            for row in models[:15]:
                lines.append(f"  {row['id']}")
            if len(models) > 15:
                lines.append(f"  ...and {len(models) - 15} more")
        return lines

    # Switch model — resolve aliases first.
    raw_model = parts[0]
    new_model = MODEL_ALIASES.get(raw_model.lower(), raw_model)
    save = "--save" in parts

    # Auto-switch provider when the model name implies a different one.
    inferred = infer_provider_for_model(new_model)
    provider_switched = False
    if inferred and inferred != ctx.cfg.provider and ctx.cfg.provider != "openrouter":
        key = _api_key_for_provider(ctx.cfg, inferred)
        if not key:
            return [
                f"Model '{new_model}' requires provider '{inferred}', "
                f"but no API key is configured for it."
            ]
        ctx.cfg.provider = inferred
        provider_switched = True

    ctx.cfg.model = new_model
    try:
        new_engine = build_engine(ctx.cfg)
    except ModelError as exc:
        return [f"Failed to switch model: {exc}"]
    ctx.runtime.engine = new_engine
    if not save:
        _clear_llm_profile(ctx)

    alias_note = f" (alias: {raw_model})" if raw_model.lower() in MODEL_ALIASES else ""
    lines = [f"Switched to model: {new_model}{alias_note}"]
    if provider_switched:
        lines.append(f"Provider auto-switched to: {ctx.cfg.provider}")

    if save:
        settings = ctx.settings_store.load()
        provider = ctx.cfg.provider
        profile_id = _slugify_profile_id(provider, new_model)
        settings.profiles.setdefault("llm", {})[profile_id] = ProviderProfile(
            name=f"{provider} {new_model}",
            provider=provider,
            model=new_model,
            base_url=_base_url_for_provider(ctx.cfg, provider),
            auth_ref=provider,
            options={"reasoning_effort": ctx.cfg.reasoning_effort},
        )
        settings.active_profiles["llm"] = profile_id
        ctx.cfg.llm_profile_id = profile_id
        ctx.cfg.llm_profile_name = f"{provider} {new_model}"
        if provider == "openai":
            settings.default_model_openai = new_model
        elif provider == "anthropic":
            settings.default_model_anthropic = new_model
        elif provider == "openrouter":
            settings.default_model_openrouter = new_model
        elif provider == "cerebras":
            settings.default_model_cerebras = new_model
        elif provider == "zai":
            settings.default_model_zai = new_model
        elif provider == "ollama":
            settings.default_model_ollama = new_model
        else:
            settings.default_model = new_model
        ctx.settings_store.save(settings)
        lines.append(f"Saved as workspace LLM profile: {profile_id}")

    return lines


def handle_reasoning_command(args: str, ctx: ChatContext) -> list[str]:
    """Handle /reasoning sub-commands. Returns display lines."""
    from .builder import build_engine

    parts = args.strip().split()
    if not parts:
        effort = ctx.cfg.reasoning_effort or "(off)"
        return [
            f"Current reasoning effort: {effort}",
            "Usage: /reasoning <low|medium|high|xhigh|off> [--save]",
        ]

    value = parts[0].lower()
    save = "--save" in parts

    if value in {"off", "none", "disable", "disabled"}:
        ctx.cfg.reasoning_effort = None
    elif value in {"low", "medium", "high", "xhigh"}:
        ctx.cfg.reasoning_effort = value
    else:
        return [f"Invalid effort '{value}'. Use: low, medium, high, xhigh, off"]

    # Rebuild engine with new reasoning effort.
    try:
        new_engine = build_engine(ctx.cfg)
    except ModelError as exc:
        return [f"Failed to apply reasoning change: {exc}"]
    ctx.runtime.engine = new_engine

    display = ctx.cfg.reasoning_effort or "off"
    lines = [f"Reasoning effort set to: {display}"]

    if save:
        settings = ctx.settings_store.load()
        settings.default_reasoning_effort = ctx.cfg.reasoning_effort
        ctx.settings_store.save(settings)
        lines.append("Saved as workspace default.")

    return lines


def _compute_suggestions(buf: str) -> tuple[list[str], int]:
    """Return (matching_commands, selected_index) for the current input buffer.

    Activates only when *buf* starts with ``/`` and contains no spaces.
    ``selected_index`` starts at -1 (nothing highlighted).
    """
    if not buf.startswith("/") or " " in buf:
        return [], -1
    matches = [cmd for cmd in SLASH_COMMANDS if cmd.startswith(buf)]
    return matches, -1


def _get_mode_label(cfg: AgentConfig) -> str:
    """Return a short mode label for the current config."""
    if cfg.recursive:
        return "recursive"
    return "flat"


def _format_chrome_status(ctx: ChatContext) -> list[str]:
    status = ctx.runtime.engine.tools.chrome_mcp_status()
    attach_mode = (
        f"BU_CDP_URL={ctx.cfg.chrome_mcp_browser_url}"
        if ctx.cfg.chrome_mcp_browser_url
        else ("auto-discovery" if ctx.cfg.chrome_mcp_auto_connect else "manual-disabled")
    )
    lines = [
        (
            "Browser Harness: "
            f"enabled={ctx.cfg.chrome_mcp_enabled} | attach={attach_mode} | "
            f"legacy_channel={ctx.cfg.chrome_mcp_channel}"
        ),
        f"Runtime status: {status.status} | {status.detail}",
    ]
    if status.tool_count:
        lines.append(f"Discovered Browser Harness tools: {status.tool_count}")
    return lines


def _format_embeddings_status(ctx: ChatContext) -> list[str]:
    status = build_embeddings_status(
        provider=ctx.cfg.embeddings_provider,
        embeddings_model=ctx.cfg.embeddings_model,
        voyage_api_key=ctx.cfg.voyage_api_key,
        mistral_api_key=ctx.cfg.mistral_api_key,
    )
    return [
        (
            "Embeddings: "
            f"provider={status.provider} | model={status.model} | status={status.status}"
        ),
        f"Active embedding profile: {ctx.cfg.embedding_profile_name or ctx.cfg.embedding_profile_id or '(none)'}",
        f"Retrieval status: {status.detail}",
    ]


def handle_embeddings_command(args: str, ctx: ChatContext) -> list[str]:
    parts = [part for part in args.strip().split() if part]
    if not parts:
        return _format_embeddings_status(ctx) + [
            "Usage: /embeddings [voyage|mistral] [--save]",
        ]

    save = "--save" in parts
    parts = [part for part in parts if part != "--save"]
    if not parts:
        return ["Usage: /embeddings [voyage|mistral] [--save]"]

    if parts[0] in {"profiles", "profile"}:
        settings = ctx.settings_store.load()
        if parts[0] == "profiles" or len(parts) < 2:
            return _format_profile_pool(settings, "embedding", "embedding")
        profile_id = parts[1].strip()
        profile = settings.profiles.get("embedding", {}).get(profile_id)
        if profile is None:
            return [
                f"Unknown embedding profile '{profile_id}'.",
            ] + _format_profile_pool(settings, "embedding", "embedding")
        _apply_embedding_profile(ctx, profile_id, profile)
        settings.active_profiles["embedding"] = profile_id
        ctx.settings_store.save(settings)
        return _format_embeddings_status(ctx) + [
            f"Switched to embedding profile: {profile_id}"
        ]

    provider = parts[0].strip().lower()
    if provider not in {"voyage", "mistral"}:
        return [f"Invalid embeddings provider '{provider}'. Use: voyage, mistral"]

    ctx.cfg.embeddings_provider = provider
    ctx.cfg.embeddings_model = "voyage-4" if provider == "voyage" else "mistral-embed"
    ctx.cfg.embeddings_base_url = (
        "https://api.voyageai.com" if provider == "voyage" else "https://api.mistral.ai"
    )
    ctx.runtime.engine.config.embeddings_provider = provider
    ctx.runtime.engine.config.embeddings_model = ctx.cfg.embeddings_model
    ctx.runtime.engine.config.embeddings_base_url = ctx.cfg.embeddings_base_url
    if not save:
        _clear_embedding_profile(ctx)
    if save:
        settings = ctx.settings_store.load()
        profile_id = _slugify_profile_id(provider, ctx.cfg.embeddings_model)
        settings.profiles.setdefault("embedding", {})[profile_id] = ProviderProfile(
            name=f"{provider.title()} embeddings",
            provider=provider,
            adapter="embedding",
            model=ctx.cfg.embeddings_model,
            base_url=ctx.cfg.embeddings_base_url,
            auth_ref=provider,
        )
        settings.active_profiles["embedding"] = profile_id
        settings.embeddings_provider = provider
        ctx.settings_store.save(settings)
        ctx.cfg.embedding_profile_id = profile_id
        ctx.cfg.embedding_profile_name = f"{provider.title()} embeddings"
        ctx.runtime.engine.config.embedding_profile_id = profile_id
        ctx.runtime.engine.config.embedding_profile_name = f"{provider.title()} embeddings"
    lines = _format_embeddings_status(ctx)
    if save:
        lines.append(f"Saved as workspace embedding profile: {profile_id}")
    return lines


def handle_stt_command(args: str, ctx: ChatContext) -> list[str]:
    parts = [part for part in args.strip().split() if part]
    if not parts:
        return [
            (
                "Audio/STT: "
                f"provider=mistral | model={ctx.cfg.mistral_transcription_model} | "
                f"profile={ctx.cfg.stt_profile_name or ctx.cfg.stt_profile_id or '(none)'}"
            ),
            "Usage: /stt [model] [--save]",
        ]

    save = "--save" in parts
    parts = [part for part in parts if part != "--save"]
    if not parts:
        return ["Usage: /stt [model] [--save]"]

    if parts[0] in {"profiles", "profile"}:
        settings = ctx.settings_store.load()
        if parts[0] == "profiles" or len(parts) < 2:
            return _format_profile_pool(settings, "stt", "STT")
        profile_id = parts[1].strip()
        profile = settings.profiles.get("stt", {}).get(profile_id)
        if profile is None:
            return [f"Unknown STT profile '{profile_id}'."] + _format_profile_pool(
                settings,
                "stt",
                "STT",
            )
        _apply_stt_profile(ctx, profile_id, profile)
        settings.active_profiles["stt"] = profile_id
        ctx.settings_store.save(settings)
        return [f"Switched to STT profile: {profile_id}"]

    model = parts[0].strip()
    if not model:
        return ["Usage: /stt [model] [--save]"]

    ctx.cfg.mistral_transcription_model = model
    ctx.runtime.engine.config.mistral_transcription_model = model
    if not save:
        _clear_stt_profile(ctx)
    lines = [f"Audio/STT model set to: {model}"]
    if save:
        settings = ctx.settings_store.load()
        profile_id = _slugify_profile_id("mistral", model)
        profile_name = f"Mistral {model} STT"
        settings.profiles.setdefault("stt", {})[profile_id] = ProviderProfile(
            name=profile_name,
            provider="mistral",
            adapter="speech-to-text",
            model=model,
            base_url=ctx.cfg.mistral_transcription_base_url,
            auth_ref="mistral",
            options={
                "max_bytes": ctx.cfg.mistral_transcription_max_bytes,
                "chunk_max_seconds": ctx.cfg.mistral_transcription_chunk_max_seconds,
                "chunk_overlap_seconds": ctx.cfg.mistral_transcription_chunk_overlap_seconds,
                "max_chunks": ctx.cfg.mistral_transcription_max_chunks,
                "request_timeout_sec": ctx.cfg.mistral_transcription_request_timeout_sec,
            },
        )
        settings.active_profiles["stt"] = profile_id
        settings.mistral_transcription_model = model
        ctx.settings_store.save(settings)
        ctx.cfg.stt_profile_id = profile_id
        ctx.cfg.stt_profile_name = profile_name
        ctx.runtime.engine.config.stt_profile_id = profile_id
        ctx.runtime.engine.config.stt_profile_name = profile_name
        lines.append(f"Saved as workspace STT profile: {profile_id}")
    return lines


def handle_chrome_command(args: str, ctx: ChatContext) -> list[str]:
    from .builder import build_engine

    parts = [part for part in args.strip().split() if part]
    save = False
    if "--save" in parts:
        save = True
        parts = [part for part in parts if part != "--save"]

    if not parts or parts[0] == "status":
        lines = _format_chrome_status(ctx)
        if not parts:
            lines.append(
                "Usage: /chrome status|on|off|auto|url <endpoint>|channel <stable|beta|dev|canary> [--save]"
            )
        return lines

    action = parts[0].lower()
    if action == "on":
        ctx.cfg.chrome_mcp_enabled = True
    elif action == "off":
        ctx.cfg.chrome_mcp_enabled = False
    elif action == "auto":
        ctx.cfg.chrome_mcp_enabled = True
        ctx.cfg.chrome_mcp_auto_connect = True
        ctx.cfg.chrome_mcp_browser_url = None
    elif action == "url":
        if len(parts) < 2:
            return ["Usage: /chrome url <endpoint> [--save]"]
        ctx.cfg.chrome_mcp_enabled = True
        ctx.cfg.chrome_mcp_auto_connect = False
        ctx.cfg.chrome_mcp_browser_url = parts[1].strip() or None
    elif action == "channel":
        if len(parts) < 2:
            return ["Usage: /chrome channel <stable|beta|dev|canary> [--save]"]
        channel = parts[1].strip().lower()
        if channel not in {"stable", "beta", "dev", "canary"}:
            return [f"Invalid legacy Chrome channel '{channel}'. Use: stable, beta, dev, canary"]
        ctx.cfg.chrome_mcp_channel = channel
    else:
        return [
            f"Unknown /chrome action '{action}'.",
            "Usage: /chrome status|on|off|auto|url <endpoint>|channel <stable|beta|dev|canary> [--save]",
        ]

    try:
        ctx.runtime.engine = build_engine(ctx.cfg)
    except ModelError as exc:
        return [f"Failed to apply Browser Harness change: {exc}"]

    lines = _format_chrome_status(ctx)
    if save:
        settings = ctx.settings_store.load()
        settings.chrome_mcp_enabled = ctx.cfg.chrome_mcp_enabled
        settings.chrome_mcp_auto_connect = ctx.cfg.chrome_mcp_auto_connect
        settings.chrome_mcp_browser_url = ctx.cfg.chrome_mcp_browser_url
        settings.chrome_mcp_channel = ctx.cfg.chrome_mcp_channel
        settings.chrome_mcp_connect_timeout_sec = ctx.cfg.chrome_mcp_connect_timeout_sec
        settings.chrome_mcp_rpc_timeout_sec = ctx.cfg.chrome_mcp_rpc_timeout_sec
        ctx.settings_store.save(settings)
        lines.append("Saved as workspace default.")
    return lines


def dispatch_slash_command(
    command: str,
    ctx: ChatContext,
    emit: Callable[[str], None],
) -> str | None:
    """Dispatch a slash command. Returns "quit", "clear", "handled", or None (not a command)."""
    if command in {"/quit", "/exit"}:
        return "quit"
    if command == "/help":
        for ln in HELP_LINES:
            emit(ln)
        return "handled"
    if command == "/status":
        model_name = _get_model_display_name(ctx.runtime.engine)
        effort = ctx.cfg.reasoning_effort or "(off)"
        mode = _get_mode_label(ctx.cfg)
        emit(
            "Provider: "
            f"{ctx.cfg.provider} | Model: {model_name} | Reasoning: {effort} | "
            f"Embeddings: {ctx.cfg.embeddings_provider}:{ctx.cfg.embeddings_model} | "
            f"STT: mistral:{ctx.cfg.mistral_transcription_model} | Mode: {mode}"
        )
        tokens = ctx.runtime.engine.session_tokens
        if tokens:
            for mname, counts in tokens.items():
                emit(
                    f"  {mname}: "
                    f"{_format_token_count(counts['input'])} in / "
                    f"{_format_token_count(counts['output'])} out"
                )
        else:
            emit("  Tokens: (none yet)")
        for line in _format_chrome_status(ctx):
            emit(f"  {line}")
        for line in _format_embeddings_status(ctx):
            emit(f"  {line}")
        return "handled"
    if command == "/clear":
        return "clear"
    if command.startswith("/model"):
        cmd_args = command[len("/model"):].strip()
        lines = handle_model_command(cmd_args, ctx)
        for line in lines:
            emit(line)
        return "handled"
    if command.startswith("/reasoning"):
        cmd_args = command[len("/reasoning"):].strip()
        lines = handle_reasoning_command(cmd_args, ctx)
        for line in lines:
            emit(line)
        return "handled"
    if command.startswith("/embeddings"):
        cmd_args = command[len("/embeddings"):].strip()
        lines = handle_embeddings_command(cmd_args, ctx)
        for line in lines:
            emit(line)
        return "handled"
    if command.startswith("/stt"):
        cmd_args = command[len("/stt"):].strip()
        lines = handle_stt_command(cmd_args, ctx)
        for line in lines:
            emit(line)
        return "handled"
    if command.startswith("/chrome"):
        cmd_args = command[len("/chrome"):].strip()
        lines = handle_chrome_command(cmd_args, ctx)
        for line in lines:
            emit(line)
        return "handled"
    return None


# -- Event parsing for trace output --

# Patterns for event messages from the engine/runtime.
_RE_PREFIX = re.compile(r"^\[d(\d+)(?:/s(\d+))?\]\s*")
_RE_CALLING = re.compile(r"calling model")
_RE_SUBTASK = re.compile(r">> entering subtask")
_RE_EXECUTE = re.compile(r">> executing leaf")
_RE_ERROR = re.compile(r"model error:", re.IGNORECASE)
_RE_TOOL_START = re.compile(r"(\w+)\((.*)?\)$")
_RE_RETRIEVAL_PROGRESS = re.compile(r"^\[retrieval:progress\]\s+(\{.*\})\s*$")

# Max characters to display per trace event line (first line only for multi-line).
_EVENT_MAX_CHARS = 300


def _clip_event(text: str) -> str:
    """Clip a trace event body to a reasonable display length."""
    retrieval = _parse_retrieval_progress(text)
    if retrieval is not None:
        return _format_retrieval_progress_text(retrieval)
    first_line, _, rest = text.partition("\n")
    if len(first_line) > _EVENT_MAX_CHARS:
        return first_line[:_EVENT_MAX_CHARS] + "..."
    if rest:
        extra_lines = rest.count("\n") + 1
        return first_line + f"  (+{extra_lines} lines)"
    return first_line


def _parse_retrieval_progress(text: str) -> dict[str, Any] | None:
    match = _RE_RETRIEVAL_PROGRESS.match(text.strip())
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _format_retrieval_progress_text(payload: dict[str, Any]) -> str:
    corpus = str(payload.get("corpus") or "all")
    phase = str(payload.get("phase") or "scan")
    documents_done = int(payload.get("documents_done") or 0)
    documents_total = int(payload.get("documents_total") or 0)
    percent = int(payload.get("percent") or 0)
    message = str(payload.get("message") or "").strip()
    corpus_label = "all corpora" if corpus == "all" else corpus
    detail = f"{phase} {percent}% ({documents_done}/{documents_total} docs)"
    if documents_total <= 0:
        detail = phase
    if message:
        return f"vectorizing {corpus_label}: {detail} - {message}"
    return f"vectorizing {corpus_label}: {detail}"


# Map tool names to their most informative argument for compact display.
_KEY_ARGS: dict[str, str] = {
    "read_file": "path",
    "read_image": "path",
    "audio_transcribe": "path",
    "document_ocr": "path",
    "document_annotations": "path",
    "document_qa": "question",
    "write_file": "path",
    "edit_file": "path",
    "hashline_edit": "path",
    "apply_patch": "patch",
    "run_shell": "command",
    "run_shell_bg": "command",
    "web_search": "query",
    "fetch_url": "urls",
    "search_files": "query",
    "list_files": "glob",
    "repo_map": "glob",
    "subtask": "objective",
    "execute": "objective",
    "think": "note",
    "check_shell_bg": "job_id",
    "kill_shell_bg": "job_id",
}

# How many lines of thinking text to show during the spinner.
_THINKING_TAIL_LINES = 6
_THINKING_MAX_LINE_WIDTH = 80


@dataclass
class _ToolCallRecord:
    name: str
    key_arg: str
    elapsed_sec: float
    is_error: bool = False


@dataclass
class _StepState:
    depth: int = 0
    step: int = 0
    max_steps: int = 0
    model_text: str = ""
    model_elapsed_sec: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[_ToolCallRecord] = field(default_factory=list)


def _extract_key_arg(name: str, arguments: dict[str, Any]) -> str:
    """Extract the most informative argument value for compact display."""
    key = _KEY_ARGS.get(name)
    if not key:
        # Fallback: first string-valued argument
        for v in arguments.values():
            if isinstance(v, str) and v.strip():
                s = v.strip()
                if len(s) > 60:
                    s = s[:57] + "..."
                return s
        return ""
    val = arguments.get(key, "")
    if isinstance(val, list):
        val = ", ".join(str(x) for x in val[:3])
    s = str(val).strip()
    if len(s) > 60:
        s = s[:57] + "..."
    return s


class _ActivityDisplay:
    """Unified live display for thinking, streaming response, and tool execution.

    Modes:
      - ``thinking``   — cyan header with streaming thinking text
      - ``streaming``  — green header with streaming response text
      - ``tool``       — yellow header with tool name and key argument
      - ``tool_args``  — yellow header with live preview of tool call arguments
    """

    def __init__(self, console: Any, censor_fn: Callable[[str], str] | None = None) -> None:
        self._console = console
        self._censor_fn = censor_fn
        self._lock = threading.Lock()
        self._text_buf: str = ""
        self._mode: str = "thinking"  # thinking | streaming | tool | tool_args | retrieval
        self._step_label: str = ""
        self._tool_name: str = ""
        self._tool_key_arg: str = ""
        self._tool_arg_buf: str = ""
        self._tool_arg_name: str = ""
        self._start_time: float = 0.0
        self._live: Any | None = None
        self._active = False

    # -- Rich renderable protocol --------------------------------------------

    def __rich__(self) -> "Any":
        """Let Rich's Live auto-refresh poll current state instead of pushing updates."""
        return self._build_renderable()

    # -- lifecycle -----------------------------------------------------------

    def start(self, mode: str = "thinking", step_label: str = "") -> None:
        from rich.live import Live

        with self._lock:
            self._mode = mode
            self._step_label = step_label
            self._text_buf = ""
            self._tool_name = ""
            self._tool_key_arg = ""
            self._tool_arg_buf = ""
            self._tool_arg_name = ""
            self._start_time = time.monotonic()

        if self._active and self._live is not None:
            # Reuse existing Live — state updated above, auto-refresh picks it up.
            return

        self._active = True
        self._live = Live(
            self,
            console=self._console,
            transient=True,
            refresh_per_second=8,
        )
        self._live.__enter__()

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._live is not None:
            try:
                self._live.__exit__(None, None, None)
            except Exception:
                pass
            self._live = None
        with self._lock:
            self._text_buf = ""
            self._tool_name = ""
            self._tool_key_arg = ""
            self._tool_arg_buf = ""
            self._tool_arg_name = ""

    # -- data feeds ----------------------------------------------------------

    def feed(self, delta_type: str, text: str) -> None:
        """Handle thinking, text, or tool argument content deltas.

        Only updates internal state — the Live auto-refresh renders at 8fps.
        """
        if not self._active:
            return
        with self._lock:
            if delta_type == "tool_call_start":
                self._mode = "tool_args"
                self._tool_arg_name = text
                self._tool_arg_buf = ""
                return
            if delta_type == "tool_call_args":
                self._tool_arg_buf += text
                return
            if delta_type == "text" and self._mode in ("thinking", "tool_args"):
                # Auto-transition to streaming on first text delta
                self._mode = "streaming"
                self._text_buf = ""
            if delta_type in ("thinking", "text"):
                self._text_buf += text

    def set_tool(self, tool_name: str, key_arg: str = "", step_label: str = "") -> None:
        """Switch to tool mode.

        Only updates internal state — the Live auto-refresh renders at 8fps.
        """
        with self._lock:
            self._mode = "tool"
            self._tool_name = tool_name
            self._tool_key_arg = key_arg
            self._text_buf = ""
            self._tool_arg_buf = ""
            self._tool_arg_name = ""
            if step_label:
                self._step_label = step_label
            self._start_time = time.monotonic()
        if not self._active:
            self.start(mode="tool", step_label=step_label)
            return

    def set_retrieval_progress(self, text: str) -> None:
        if not self._active:
            self.start(mode="retrieval", step_label="")
        with self._lock:
            self._mode = "retrieval"
            self._step_label = ""
            self._text_buf = text
            if not self._start_time:
                self._start_time = time.monotonic()

    def set_step_label(self, label: str) -> None:
        with self._lock:
            self._step_label = label

    # -- rendering -----------------------------------------------------------

    @staticmethod
    def _extract_preview(buf: str) -> str:
        """Extract a human-readable preview from accumulated partial JSON.

        Looks for ``"content": "`` or ``"patch": "`` keys and extracts the
        string value.  Falls back to the raw buffer tail.
        """
        for key in ('"content": "', '"content":"', '"patch": "', '"patch":"'):
            idx = buf.find(key)
            if idx < 0:
                continue
            value_start = idx + len(key)
            raw_value = buf[value_start:]
            # Unescape common JSON escapes for display
            raw_value = (
                raw_value
                .replace("\\n", "\n")
                .replace("\\t", "\t")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
            # Strip trailing incomplete escape or quote
            if raw_value.endswith("\\"):
                raw_value = raw_value[:-1]
            return raw_value

        # Fallback: show last 3 lines of raw buffer
        lines = buf.splitlines()
        return "\n".join(lines[-3:]) if lines else buf

    def _build_renderable(self) -> Any:
        from rich.text import Text

        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0

        with self._lock:
            mode = self._mode
            buf = self._text_buf
            step_label = self._step_label
            tool_name = self._tool_name
            tool_key_arg = self._tool_key_arg
            tool_arg_buf = self._tool_arg_buf
            tool_arg_name = self._tool_arg_name

        if self._censor_fn:
            buf = self._censor_fn(buf)

        step_part = f"  [dim]{step_label}[/dim]" if step_label else ""

        if mode == "thinking":
            header = f"[bold cyan]Thinking...[/bold cyan]  [dim]({elapsed:.1f}s)[/dim]{step_part}"
        elif mode == "retrieval":
            header = f"[bold blue]Vectorizing...[/bold blue]  [dim]({elapsed:.1f}s)[/dim]"
        elif mode == "streaming":
            header = f"[bold green]Responding...[/bold green]  [dim]({elapsed:.1f}s)[/dim]{step_part}"
        elif mode == "tool_args":
            header = f"[bold yellow]Generating {tool_arg_name}...[/bold yellow]  [dim]({elapsed:.1f}s)[/dim]{step_part}"
        else:  # tool
            header = f"[bold yellow]Running {tool_name}...[/bold yellow]  [dim]({elapsed:.1f}s)[/dim]{step_part}"

        if mode == "tool":
            if tool_key_arg:
                arg_display = tool_key_arg
                if len(arg_display) > _THINKING_MAX_LINE_WIDTH:
                    arg_display = arg_display[:_THINKING_MAX_LINE_WIDTH - 3] + "..."
                return Text.from_markup(f"\u2800 {header}\n  [dim italic]{arg_display}[/dim italic]")
            return Text.from_markup(f"\u2800 {header}")

        if mode == "tool_args":
            if not tool_arg_buf:
                return Text.from_markup(f"\u2800 {header}")
            preview = self._extract_preview(tool_arg_buf)
            lines = preview.splitlines()
            tail = lines[-_THINKING_TAIL_LINES:]
            clipped = []
            for ln in tail:
                if len(ln) > _THINKING_MAX_LINE_WIDTH:
                    ln = ln[:_THINKING_MAX_LINE_WIDTH - 3] + "..."
                clipped.append(ln)
            snippet = "\n".join(f"  [dim italic]{ln}[/dim italic]" for ln in clipped)
            return Text.from_markup(f"\u2800 {header}\n{snippet}")

        if not buf:
            return Text.from_markup(f"\u2800 {header}")

        # Take last N lines, truncate width
        lines = buf.splitlines()
        tail = lines[-_THINKING_TAIL_LINES:]
        clipped = []
        for ln in tail:
            if len(ln) > _THINKING_MAX_LINE_WIDTH:
                ln = ln[:_THINKING_MAX_LINE_WIDTH - 3] + "..."
            clipped.append(ln)
        snippet = "\n".join(f"  [dim italic]{ln}[/dim italic]" for ln in clipped)
        return Text.from_markup(f"\u2800 {header}\n{snippet}")

    @property
    def active(self) -> bool:
        return self._active

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode


class RichREPL:
    def __init__(self, ctx: ChatContext, startup_info: dict[str, str] | None = None) -> None:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings
        from rich.console import Console

        self.ctx = ctx
        self.console = Console()
        self._startup_info = startup_info or {}
        self._current_step: _StepState | None = None

        # Background agent thread state
        self._agent_thread: threading.Thread | None = None
        self._agent_result: str | None = None

        # Queued input lines (e.g. from slash-command follow-ups)
        self._queued_input: list[str] = []

        # Demo mode: prepare render hook (installed in run() after splash art).
        censor_fn = None
        self._demo_hook = None
        if ctx.cfg.demo:
            from .demo import DemoCensor, DemoRenderHook
            censor = DemoCensor(ctx.cfg.workspace)
            censor_fn = censor.censor_text
            self._demo_hook = DemoRenderHook(censor)

        self._activity = _ActivityDisplay(self.console, censor_fn=censor_fn)

        history_dir = Path.home() / ".openplanter"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = history_dir / "repl_history"

        completer = WordCompleter(SLASH_COMMANDS, sentence=True)

        kb = KeyBindings()

        @kb.add("escape", "enter")
        def _multiline(event: object) -> None:
            # Alt+Enter inserts a newline
            buf = getattr(event, "current_buffer", None) or getattr(event, "app", None)
            if buf is not None and hasattr(buf, "insert_text"):
                buf.insert_text("\n")
            elif hasattr(event, "current_buffer"):
                event.current_buffer.insert_text("\n")  # type: ignore[union-attr]

        @kb.add("escape")
        def _cancel_agent(event: object) -> None:
            if self._agent_thread is not None and self._agent_thread.is_alive():
                self.ctx.runtime.engine.cancel()
                self.console.print("[dim]Cancelling...[/dim]")

        self.session: PromptSession[str] = PromptSession(
            history=FileHistory(str(history_path)),
            completer=completer,
            key_bindings=kb,
            multiline=False,
        )

    # ------------------------------------------------------------------
    # on_event — simplified, only handles calling model / subtask / error
    # ------------------------------------------------------------------

    def _on_event(self, msg: str) -> None:
        """Callback for runtime.solve() trace events."""
        retrieval = _parse_retrieval_progress(msg)
        if retrieval is not None:
            self._activity.set_retrieval_progress(_format_retrieval_progress_text(retrieval))
            if str(retrieval.get("phase") or "") == "done":
                self._activity.stop()
            return

        m = _RE_PREFIX.match(msg)
        body = msg[m.end():] if m else msg

        # Extract step label from prefix (e.g. "[d0/s3]" → "Step 3/20")
        step_label = ""
        if m:
            _s = m.group(2)
            if _s:
                step_label = f"Step {_s}/{self.ctx.cfg.max_steps_per_call}"

        # Calling model → flush previous step, start thinking display
        if _RE_CALLING.search(body):
            self._flush_step()
            self._activity.start(mode="thinking", step_label=step_label)
            return

        # Subtask/execute entry → flush step, render rule
        if _RE_SUBTASK.search(body) or _RE_EXECUTE.search(body):
            self._flush_step()
            self._activity.stop()
            label = re.sub(r">> (entering subtask|executing leaf):\s*", "", body).strip()
            self.console.rule(f"[dim]{label}[/dim]", style="dim")
            return

        # Error
        if _RE_ERROR.search(body):
            self._activity.stop()
            from rich.text import Text
            first_line = msg.split("\n", 1)[0]
            if len(first_line) > _EVENT_MAX_CHARS:
                first_line = first_line[:_EVENT_MAX_CHARS] + "..."
            self.console.print(Text(first_line, style="bold red"))
            return

        # Tool start (e.g. "read_file(path=foo.py)") → switch to tool mode
        tm = _RE_TOOL_START.search(body)
        if tm:
            tool_name = tm.group(1)
            tool_arg = tm.group(2) or ""
            self._activity.set_tool(tool_name, key_arg=tool_arg, step_label=step_label)
            return

    # ------------------------------------------------------------------
    # on_step — receives structured step events from engine
    # ------------------------------------------------------------------

    def _on_step(self, step_event: dict[str, Any]) -> None:
        action = step_event.get("action")
        if not isinstance(action, dict):
            return
        name = action.get("name", "")

        if name == "_model_turn":
            # Model turn completed → stop activity display, create new step state
            self._activity.stop()
            self._current_step = _StepState(
                depth=step_event.get("depth", 0),
                step=step_event.get("step", 0),
                max_steps=self.ctx.cfg.max_steps_per_call,
                model_text=step_event.get("model_text", ""),
                model_elapsed_sec=step_event.get("elapsed_sec", 0.0),
                input_tokens=step_event.get("input_tokens", 0),
                output_tokens=step_event.get("output_tokens", 0),
            )
            return

        if name == "final":
            # Final answer — flush whatever we have
            self._flush_step()
            return

        # Tool call — append to current step
        if self._current_step is not None:
            key_arg = _extract_key_arg(name, action.get("arguments", {}))
            elapsed = step_event.get("elapsed_sec", 0.0)
            is_error = bool(step_event.get("observation", "").startswith("Tool ") and "crashed" in step_event.get("observation", ""))
            self._current_step.tool_calls.append(
                _ToolCallRecord(
                    name=name,
                    key_arg=key_arg,
                    elapsed_sec=elapsed,
                    is_error=is_error,
                )
            )

    # ------------------------------------------------------------------
    # on_content_delta — forward to thinking display
    # ------------------------------------------------------------------

    def _on_content_delta(self, delta_type: str, text: str) -> None:
        self._activity.feed(delta_type, text)

    # ------------------------------------------------------------------
    # _flush_step — render a completed step
    # ------------------------------------------------------------------

    def _flush_step(self) -> None:
        step = self._current_step
        if step is None:
            return
        self._current_step = None

        from rich.text import Text

        # Timestamp
        ts = datetime.now().strftime("%H:%M:%S")

        # Context usage: input_tokens is how many tokens were in context this turn
        model_name = getattr(self.ctx.runtime.engine.model, "model", "(unknown)")
        context_window = _MODEL_CONTEXT_WINDOWS.get(model_name, _DEFAULT_CONTEXT_WINDOW)
        ctx_str = f"{_format_token_count(step.input_tokens)}/{_format_token_count(context_window)}"

        # Step header rule
        left = f" {ts}  Step {step.step} "
        right_parts = []
        if step.depth > 0:
            right_parts.append(f"depth {step.depth}")
        if step.max_steps:
            right_parts.append(f"{step.step}/{step.max_steps}")
        if step.input_tokens or step.output_tokens:
            right_parts.append(
                f"{_format_token_count(step.input_tokens)}in/{_format_token_count(step.output_tokens)}out"
            )
        right_parts.append(f"[{ctx_str}]")
        right = " | ".join(right_parts) if right_parts else ""
        self.console.rule(f"[bold]{left}[/bold][dim]{right}[/dim]", style="cyan")

        # Model text (dim, truncated)
        if step.model_text:
            preview = step.model_text.strip()
            if len(preview) > 200:
                preview = preview[:197] + "..."
            self.console.print(
                Text(f"  ({step.model_elapsed_sec:.1f}s) {preview}", style="dim"),
            )

        # Tool call tree
        n = len(step.tool_calls)
        for i, tc in enumerate(step.tool_calls):
            is_last = i == n - 1
            connector = "\u2514\u2500" if is_last else "\u251c\u2500"
            name_style = "bold red" if tc.is_error else ""

            # Build line: connector + name + key_arg + elapsed
            parts = Text()
            parts.append(f"  {connector} ", style="dim")
            parts.append(f"{tc.name}", style=name_style)
            if tc.key_arg:
                parts.append(f"  \"{tc.key_arg}\"", style="dim")
            parts.append(f"  {tc.elapsed_sec:.1f}s", style="dim")
            self.console.print(parts)

    # ------------------------------------------------------------------
    # run — main REPL loop
    # ------------------------------------------------------------------

    def _run_agent(self, objective: str) -> None:
        """Run the agent in a background thread. Stores result in _agent_result."""
        try:
            self._agent_result = self.ctx.runtime.solve(
                objective,
                on_event=self._on_event,
                on_step=self._on_step,
                on_content_delta=self._on_content_delta,
            )
        except Exception as exc:
            self._agent_result = f"Agent error: {type(exc).__name__}: {exc}"
        finally:
            # Unblock secondary prompt so result is shown immediately.
            try:
                app = self.session.app
                if app is not None:
                    app.exit("")
            except Exception:
                pass

    def _present_result(self, answer: str) -> None:
        """Render an agent answer to the console."""
        from rich.text import Text

        self._activity.stop()
        self._flush_step()

        self.console.print()
        self.console.print(_LeftMarkdown(answer), justify="left")

        token_str = _format_session_tokens(self.ctx.runtime.engine.session_tokens)
        if token_str:
            self.console.print(Text(f"  tokens: {token_str}", style="dim"))
        self.console.print()

    def run(self) -> None:
        from prompt_toolkit.patch_stdout import patch_stdout
        from rich.text import Text

        self.console.clear()
        self.console.print(Text(SPLASH_ART, style="bold cyan"))

        # Install demo render hook AFTER splash art so the header is uncensored.
        if self._demo_hook is not None:
            self.console.push_render_hook(self._demo_hook)

        if self._startup_info:
            for key, val in self._startup_info.items():
                self.console.print(Text(f"  {key:>10}  {val}", style="dim"))
            self.console.print()
        self.console.print(
            "Type /help for commands, Ctrl+D to exit.  ESC or Ctrl+C to cancel a running task.",
            style="dim",
        )
        self.console.print()

        # raw=True preserves ANSI escape sequences so Rich's Live
        # display isn't corrupted by StdoutProxy's write() escaping.
        with patch_stdout(raw=True):
            while True:
                # Dequeue input queued during a previous agent run.
                if self._queued_input:
                    user_input = self._queued_input.pop(0)
                    self.console.print(Text(f"you> {user_input}", style="bold"))
                else:
                    try:
                        user_input = self.session.prompt("you> ").strip()
                    except KeyboardInterrupt:
                        continue
                    except EOFError:
                        break

                if not user_input:
                    continue

                result = dispatch_slash_command(
                    user_input,
                    self.ctx,
                    emit=lambda line: self.console.print(Text(line, style="cyan")),
                )
                if result == "quit":
                    break
                if result == "clear":
                    self.console.clear()
                    continue
                if result == "handled":
                    continue

                # Regular objective — run in background thread
                self.console.print()
                self._agent_result = None
                self._agent_thread = threading.Thread(
                    target=self._run_agent,
                    args=(user_input,),
                    daemon=True,
                )
                self._agent_thread.start()

                # Secondary input loop: accept input while agent works.
                # Slash commands are dispatched immediately; other input is queued.
                _quit_requested = False
                while self._agent_thread.is_alive():
                    try:
                        queued = self.session.prompt(
                            [("class:dim", "... ")],
                            style=_queue_prompt_style(),
                        ).strip()
                        if not queued:
                            continue
                        # Slash commands: handle immediately.
                        if queued.startswith("/"):
                            result = dispatch_slash_command(
                                queued, self.ctx,
                                emit=lambda line: self.console.print(Text(line, style="cyan")),
                            )
                            if result == "quit":
                                self.ctx.runtime.engine.cancel()
                                _quit_requested = True
                                break
                            if result == "clear":
                                self.console.clear()
                            # "handled" or None — either way, don't queue it.
                            continue
                        self._queued_input.append(queued)
                        self.console.print(
                            Text(f"  (queued: {queued[:60]}{'...' if len(queued) > 60 else ''})", style="dim"),
                        )
                    except KeyboardInterrupt:
                        self.ctx.runtime.engine.cancel()
                        self.console.print("[dim]Cancelling...[/dim]")
                        break
                    except EOFError:
                        break

                self._agent_thread.join()
                self._agent_thread = None

                if self._agent_result is not None:
                    self._present_result(self._agent_result)

                if _quit_requested:
                    break


def run_rich_repl(ctx: ChatContext, startup_info: dict[str, str] | None = None) -> None:
    """Entry point for the Rich REPL."""
    repl = RichREPL(ctx, startup_info=startup_info)
    repl.run()
