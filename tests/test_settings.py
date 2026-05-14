from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from agent.__main__ import _apply_active_profiles_to_config, _resolve_provider
from agent.builder import _validate_model_provider, infer_provider_for_model
from agent.config import AgentConfig
from agent.credentials import CredentialBundle
from agent.model import ModelError
from agent.settings import (
    PersistentSettings,
    ProviderProfile,
    SettingsStore,
    normalize_chrome_mcp_channel,
    normalize_embeddings_provider,
    normalize_reasoning_effort,
)
from agent.tui import SLASH_COMMANDS, _compute_suggestions


class SettingsTests(unittest.TestCase):
    def test_settings_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            settings = PersistentSettings(
                default_model="gpt-5.2",
                default_reasoning_effort="high",
            )
            store.save(settings)
            loaded = store.load()
            self.assertEqual(loaded.default_model, "gpt-5.2")
            self.assertEqual(loaded.default_reasoning_effort, "high")

    def test_chrome_mcp_settings_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            settings = PersistentSettings(
                chrome_mcp_enabled=True,
                chrome_mcp_auto_connect=False,
                chrome_mcp_browser_url="http://127.0.0.1:9222",
                chrome_mcp_channel="beta",
                chrome_mcp_connect_timeout_sec=21,
                chrome_mcp_rpc_timeout_sec=61,
            )
            store.save(settings)
            loaded = store.load()
            self.assertTrue(loaded.chrome_mcp_enabled)
            self.assertFalse(loaded.chrome_mcp_auto_connect)
            self.assertEqual(loaded.chrome_mcp_browser_url, "http://127.0.0.1:9222")
            self.assertEqual(loaded.chrome_mcp_channel, "beta")
            self.assertEqual(loaded.chrome_mcp_connect_timeout_sec, 21)
            self.assertEqual(loaded.chrome_mcp_rpc_timeout_sec, 61)

    def test_obsidian_settings_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            settings = PersistentSettings(
                obsidian_export_enabled=True,
                obsidian_export_root="/Users/example/Vault",
                obsidian_export_mode="fresh-vault",
                obsidian_export_subdir="Research/Cestus",
                obsidian_generate_canvas=False,
            )
            store.save(settings)
            loaded = store.load()
            self.assertTrue(loaded.obsidian_export_enabled)
            self.assertEqual(loaded.obsidian_export_root, "/Users/example/Vault")
            self.assertEqual(loaded.obsidian_export_mode, "fresh_vault")
            self.assertEqual(loaded.obsidian_export_subdir, "Research/Cestus")
            self.assertFalse(loaded.obsidian_generate_canvas)

    def test_embeddings_provider_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            settings = PersistentSettings(embeddings_provider="mistral")
            store.save(settings)
            loaded = store.load()
            self.assertEqual(loaded.embeddings_provider, "mistral")

    def test_provider_profiles_roundtrip_separate_pools(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            settings = PersistentSettings(
                active_profiles={
                    "llm": "azure-foundry",
                    "embedding": "mistral-embed",
                    "stt": "mistral-voxtral",
                },
                profiles={
                    "llm": {
                        "azure-foundry": ProviderProfile(
                            name="Azure Foundry GPT",
                            provider="openai",
                            adapter="openai-compatible",
                            model="azure-foundry/gpt-5.5",
                            base_url="https://example.test/openai/v1",
                            auth_ref="openai",
                        )
                    },
                    "embedding": {
                        "mistral-embed": ProviderProfile(
                            name="Mistral embeddings",
                            provider="mistral",
                            adapter="embedding",
                            model="mistral-embed",
                            base_url="https://api.mistral.ai",
                            auth_ref="mistral",
                        )
                    },
                    "stt": {
                        "mistral-voxtral": ProviderProfile(
                            name="Mistral Voxtral STT",
                            provider="mistral",
                            adapter="speech-to-text",
                            model="voxtral-mini-latest",
                            base_url="https://api.mistral.ai",
                            auth_ref="mistral",
                            options={"chunk_max_seconds": 600},
                        )
                    },
                },
            )
            store.save(settings)
            loaded = store.load()
            self.assertEqual(loaded.active_profiles["llm"], "azure-foundry")
            self.assertEqual(loaded.active_profiles["embedding"], "mistral-embed")
            self.assertEqual(loaded.active_profiles["stt"], "mistral-voxtral")
            self.assertEqual(
                loaded.profiles["llm"]["azure-foundry"].model,
                "azure-foundry/gpt-5.5",
            )
            self.assertEqual(
                loaded.profiles["embedding"]["mistral-embed"].model,
                "mistral-embed",
            )
            self.assertEqual(
                loaded.profiles["stt"]["mistral-voxtral"].options["chunk_max_seconds"],
                600,
            )

    def test_legacy_settings_migrate_to_provider_profiles(self) -> None:
        settings = PersistentSettings(
            default_model_openai="azure-foundry/gpt-5.5",
            embeddings_provider="mistral",
            mistral_transcription_model="voxtral-mini-latest",
            mistral_transcription_chunk_max_seconds=600,
        ).normalized()

        self.assertEqual(settings.active_profiles["llm"], "openai-default")
        self.assertEqual(settings.active_profiles["embedding"], "mistral-default")
        self.assertEqual(settings.active_profiles["stt"], "mistral-voxtral")
        self.assertEqual(
            settings.profiles["llm"]["openai-default"].model,
            "azure-foundry/gpt-5.5",
        )
        self.assertEqual(
            settings.profiles["embedding"]["mistral-default"].model,
            "mistral-embed",
        )
        self.assertEqual(
            settings.profiles["stt"]["mistral-voxtral"].options["chunk_max_seconds"],
            600,
        )

    def test_option_only_stt_settings_migrate_to_profile(self) -> None:
        settings = PersistentSettings(
            mistral_transcription_max_chunks=12,
            mistral_transcription_request_timeout_sec=240,
        ).normalized()

        self.assertEqual(settings.active_profiles["stt"], "mistral-voxtral")
        profile = settings.profiles["stt"]["mistral-voxtral"]
        self.assertEqual(profile.model, "voxtral-mini-latest")
        self.assertEqual(profile.options["max_chunks"], 12)
        self.assertEqual(profile.options["request_timeout_sec"], 240)

    def test_profile_id_collisions_get_unique_ids(self) -> None:
        settings = PersistentSettings(
            active_profiles={"llm": "OpenAI_GPT_4"},
            profiles={
                "llm": {
                    "OpenAI GPT 4": ProviderProfile(
                        provider="openai",
                        model="gpt-4o",
                    ),
                    "OpenAI_GPT_4": ProviderProfile(
                        provider="openai",
                        model="gpt-4.1-mini",
                    ),
                }
            },
        ).normalized()

        self.assertIn("openai-gpt-4", settings.profiles["llm"])
        self.assertIn("openai-gpt-4-2", settings.profiles["llm"])
        self.assertEqual(settings.active_profiles["llm"], "openai-gpt-4-2")
        self.assertEqual(
            settings.profiles["llm"]["openai-gpt-4-2"].model,
            "gpt-4.1-mini",
        )

    def test_invalid_llm_profile_provider_is_inferred_from_model(self) -> None:
        profile = ProviderProfile(
            provider="not-a-provider",
            model="azure-foundry/gpt-5.5",
        ).normalized("llm")

        self.assertEqual(profile.provider, "openai")

    def test_embedding_env_overrides_skip_active_profile(self) -> None:
        settings = PersistentSettings(
            active_profiles={"embedding": "mistral-embed"},
            profiles={
                "embedding": {
                    "mistral-embed": ProviderProfile(
                        provider="mistral",
                        model="mistral-embed",
                        base_url="https://api.mistral.ai",
                    )
                }
            },
        ).normalized()
        args = Namespace(provider=None, model=None, embeddings_provider=None)

        for env_key in ("OPENPLANTER_EMBEDDINGS_MODEL", "OPENPLANTER_EMBEDDINGS_BASE_URL"):
            with self.subTest(env_key=env_key):
                cfg = AgentConfig(
                    workspace=Path("/tmp/workspace"),
                    embeddings_provider="voyage",
                    embeddings_model="env-embed",
                    embeddings_base_url="https://embeddings.example.test",
                )
                with patch.dict("os.environ", {env_key: "1"}, clear=True):
                    _apply_active_profiles_to_config(cfg, settings, args)

                self.assertIsNone(cfg.embedding_profile_id)
                self.assertEqual(cfg.embeddings_provider, "voyage")
                self.assertEqual(cfg.embeddings_model, "env-embed")
                self.assertEqual(cfg.embeddings_base_url, "https://embeddings.example.test")

    def test_llm_env_overrides_preserve_profile_side_fields(self) -> None:
        settings = PersistentSettings(
            active_profiles={"llm": "zai-coding"},
            profiles={
                "llm": {
                    "zai-coding": ProviderProfile(
                        provider="zai",
                        model="glm-4.6",
                        base_url="https://profile-zai.example/v4",
                        options={
                            "reasoning_effort": "high",
                            "zai_plan": "coding",
                        },
                    )
                }
            },
        ).normalized()
        args = Namespace(provider=None, model=None, embeddings_provider=None)
        cfg = AgentConfig(
            workspace=Path("/tmp/workspace"),
            provider="auto",
            model="default-model",
            reasoning_effort="low",
            zai_plan="paygo",
            zai_base_url="https://env-zai.example/v4",
        )

        with patch.dict(
            "os.environ",
            {
                "OPENPLANTER_REASONING_EFFORT": "low",
                "OPENPLANTER_ZAI_PLAN": "paygo",
                "OPENPLANTER_ZAI_BASE_URL": "https://env-zai.example/v4",
            },
            clear=True,
        ):
            _apply_active_profiles_to_config(cfg, settings, args)

        self.assertEqual(cfg.llm_profile_id, "zai-coding")
        self.assertEqual(cfg.provider, "zai")
        self.assertEqual(cfg.model, "glm-4.6")
        self.assertEqual(cfg.reasoning_effort, "low")
        self.assertEqual(cfg.zai_plan, "paygo")
        self.assertEqual(cfg.zai_base_url, "https://env-zai.example/v4")

    def test_legacy_profile_migration_refreshes_changed_defaults(self) -> None:
        settings = PersistentSettings(default_model_openai="azure-foundry/gpt-5.5").normalized()
        self.assertEqual(
            settings.profiles["llm"]["openai-default"].model,
            "azure-foundry/gpt-5.5",
        )

        settings.default_model_openai = "azure-foundry/gpt-5.6"
        refreshed = settings.normalized()

        self.assertEqual(
            refreshed.profiles["llm"]["openai-default"].model,
            "azure-foundry/gpt-5.6",
        )
        self.assertEqual(refreshed.default_model_for_provider("openai"), "azure-foundry/gpt-5.6")

    def test_normalize_reasoning_effort(self) -> None:
        self.assertEqual(normalize_reasoning_effort("LOW"), "low")
        self.assertEqual(normalize_reasoning_effort(" medium "), "medium")
        self.assertEqual(normalize_reasoning_effort(" XHIGH "), "xhigh")
        self.assertIsNone(normalize_reasoning_effort(""))
        with self.assertRaises(ValueError):
            normalize_reasoning_effort("extreme")

    def test_normalize_chrome_channel(self) -> None:
        self.assertEqual(normalize_chrome_mcp_channel("BETA"), "beta")
        self.assertIsNone(normalize_chrome_mcp_channel(""))
        with self.assertRaises(ValueError):
            normalize_chrome_mcp_channel("nightly")

    def test_normalize_embeddings_provider(self) -> None:
        self.assertEqual(normalize_embeddings_provider("MISTRAL"), "mistral")
        self.assertIsNone(normalize_embeddings_provider(""))
        with self.assertRaises(ValueError):
            normalize_embeddings_provider("other")

    def test_per_provider_model_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            settings = PersistentSettings(
                default_model="global-model",
                default_model_openai="gpt-4.1-mini",
                default_model_anthropic="claude-opus-4-6",
                default_model_openrouter="anthropic/claude-sonnet-4-5",
                default_model_zai="glm-5",
            )
            store.save(settings)
            loaded = store.load()
            self.assertEqual(loaded.default_model, "global-model")
            self.assertEqual(loaded.default_model_openai, "gpt-4.1-mini")
            self.assertEqual(loaded.default_model_anthropic, "claude-opus-4-6")
            self.assertEqual(loaded.default_model_openrouter, "anthropic/claude-sonnet-4-5")
            self.assertEqual(loaded.default_model_zai, "glm-5")

    def test_default_model_for_provider_specific(self) -> None:
        settings = PersistentSettings(
            default_model="global-model",
            default_model_openai="gpt-4.1-mini",
        )
        self.assertEqual(settings.default_model_for_provider("openai"), "gpt-4.1-mini")

    def test_default_model_for_provider_fallback(self) -> None:
        settings = PersistentSettings(default_model="global-model")
        self.assertEqual(settings.default_model_for_provider("openai"), "global-model")
        self.assertEqual(settings.default_model_for_provider("anthropic"), "global-model")

    def test_default_model_for_provider_none(self) -> None:
        settings = PersistentSettings()
        self.assertIsNone(settings.default_model_for_provider("openai"))
        self.assertIsNone(settings.default_model_for_provider("anthropic"))
        self.assertIsNone(settings.default_model_for_provider("openrouter"))
        self.assertIsNone(settings.default_model_for_provider("cerebras"))
        self.assertIsNone(settings.default_model_for_provider("zai"))

    def test_per_provider_model_ollama(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            settings = PersistentSettings(
                default_model_ollama="mistral",
            )
            store.save(settings)
            loaded = store.load()
            self.assertEqual(loaded.default_model_ollama, "mistral")

    def test_default_model_for_provider_ollama(self) -> None:
        settings = PersistentSettings(
            default_model="global-model",
            default_model_ollama="llama3.2",
        )
        self.assertEqual(settings.default_model_for_provider("ollama"), "llama3.2")

    def test_default_model_for_provider_zai(self) -> None:
        settings = PersistentSettings(
            default_model="global-model",
            default_model_zai="glm-5",
        )
        self.assertEqual(settings.default_model_for_provider("zai"), "glm-5")

    def test_backward_compat_old_settings(self) -> None:
        """Old settings.json without per-provider keys still loads fine."""
        import json
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SettingsStore(workspace=root, session_root_dir=".openplanter")
            # Write old-format JSON (no provider keys).
            old_data = {"default_model": "old-model", "default_reasoning_effort": "high"}
            store.settings_path.write_text(json.dumps(old_data), encoding="utf-8")
            loaded = store.load()
            self.assertEqual(loaded.default_model, "old-model")
            self.assertEqual(loaded.default_reasoning_effort, "high")
            self.assertIsNone(loaded.default_model_openai)
            self.assertIsNone(loaded.default_model_anthropic)
            self.assertIsNone(loaded.default_model_openrouter)
            self.assertIsNone(loaded.default_model_zai)


class ComputeSuggestionsTests(unittest.TestCase):
    def test_slash_shows_all(self) -> None:
        matches, idx = _compute_suggestions("/")
        self.assertEqual(len(matches), len(SLASH_COMMANDS))
        self.assertEqual(idx, -1)

    def test_slash_e_filters(self) -> None:
        matches, idx = _compute_suggestions("/e")
        self.assertEqual(matches, ["/exit", "/embeddings"])
        self.assertEqual(idx, -1)

    def test_slash_q_filters(self) -> None:
        matches, idx = _compute_suggestions("/q")
        self.assertEqual(matches, ["/quit"])

    def test_no_slash_no_suggestions(self) -> None:
        matches, _ = _compute_suggestions("hello")
        self.assertEqual(matches, [])

    def test_space_disables_suggestions(self) -> None:
        matches, _ = _compute_suggestions("/quit ")
        self.assertEqual(matches, [])

    def test_empty_string_no_suggestions(self) -> None:
        matches, _ = _compute_suggestions("")
        self.assertEqual(matches, [])

    def test_no_match(self) -> None:
        matches, _ = _compute_suggestions("/z")
        self.assertEqual(matches, [])

    def test_slash_cl_filters(self) -> None:
        matches, _ = _compute_suggestions("/cl")
        self.assertEqual(matches, ["/clear"])

    def test_exact_match(self) -> None:
        matches, _ = _compute_suggestions("/help")
        self.assertEqual(matches, ["/help"])

    def test_slash_m_matches_model(self) -> None:
        matches, _ = _compute_suggestions("/m")
        self.assertIn("/model", matches)

    def test_slash_r_matches_reasoning(self) -> None:
        matches, _ = _compute_suggestions("/r")
        self.assertIn("/reasoning", matches)

    def test_slash_c_matches_chrome(self) -> None:
        matches, _ = _compute_suggestions("/ch")
        self.assertIn("/chrome", matches)

    def test_slash_em_matches_embeddings(self) -> None:
        matches, _ = _compute_suggestions("/em")
        self.assertIn("/embeddings", matches)


class InferProviderTests(unittest.TestCase):
    def test_claude_is_anthropic(self) -> None:
        self.assertEqual(infer_provider_for_model("claude-opus-4-6"), "anthropic")
        self.assertEqual(infer_provider_for_model("claude-sonnet-4-5-20250929"), "anthropic")
        self.assertEqual(infer_provider_for_model("Claude-3-Haiku"), "anthropic")
        self.assertEqual(
            infer_provider_for_model("anthropic-foundry/claude-opus-4-6"),
            "anthropic",
        )

    def test_gpt_is_openai(self) -> None:
        self.assertEqual(infer_provider_for_model("gpt-5.2"), "openai")
        self.assertEqual(infer_provider_for_model("gpt-4.1-mini"), "openai")
        self.assertEqual(infer_provider_for_model("GPT-4o"), "openai")
        self.assertEqual(
            infer_provider_for_model("azure-foundry/gpt-5.5"),
            "openai",
        )

    def test_o_series_is_openai(self) -> None:
        self.assertEqual(infer_provider_for_model("o1-mini"), "openai")
        self.assertEqual(infer_provider_for_model("o3-mini"), "openai")
        self.assertEqual(infer_provider_for_model("o4-mini"), "openai")
        self.assertEqual(infer_provider_for_model("o1"), "openai")

    def test_slash_is_openrouter(self) -> None:
        self.assertEqual(infer_provider_for_model("anthropic/claude-sonnet-4-5"), "openrouter")
        self.assertEqual(infer_provider_for_model("openai/gpt-5.2"), "openrouter")

    def test_cerebras_models(self) -> None:
        self.assertEqual(infer_provider_for_model("qwen-3-235b-a22b-instruct-2507"), "cerebras")
        self.assertEqual(infer_provider_for_model("gpt-oss-120b"), "cerebras")
        self.assertEqual(infer_provider_for_model("llama-4-scout-cerebras"), "cerebras")

    def test_ollama_models(self) -> None:
        self.assertEqual(infer_provider_for_model("llama3.2"), "ollama")
        self.assertEqual(infer_provider_for_model("llama-3.1"), "ollama")
        self.assertEqual(infer_provider_for_model("mistral"), "ollama")
        self.assertEqual(infer_provider_for_model("gemma2"), "ollama")
        self.assertEqual(infer_provider_for_model("phi3"), "ollama")
        self.assertEqual(infer_provider_for_model("codellama"), "ollama")
        self.assertEqual(infer_provider_for_model("deepseek-v2"), "ollama")
        self.assertEqual(infer_provider_for_model("qwen2.5"), "ollama")

    def test_cerebras_qwen3_not_ollama(self) -> None:
        """qwen-3 models go to Cerebras, not Ollama."""
        self.assertEqual(infer_provider_for_model("qwen-3-235b-a22b-instruct-2507"), "cerebras")

    def test_zai_models(self) -> None:
        self.assertEqual(infer_provider_for_model("glm-5"), "zai")
        self.assertEqual(infer_provider_for_model("GLM-4.5"), "zai")

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(infer_provider_for_model("my-custom-model"))
        self.assertIsNone(infer_provider_for_model("some-random-model"))


class ValidateModelProviderTests(unittest.TestCase):
    def test_matching_provider_passes(self) -> None:
        _validate_model_provider("gpt-5.2", "openai")
        _validate_model_provider("claude-opus-4-6", "anthropic")
        _validate_model_provider("anthropic/claude-sonnet-4-5", "openrouter")
        _validate_model_provider("glm-5", "zai")

    def test_mismatch_raises(self) -> None:
        with self.assertRaises(ModelError):
            _validate_model_provider("claude-opus-4-6", "openai")
        with self.assertRaises(ModelError):
            _validate_model_provider("gpt-5.2", "anthropic")

    def test_openrouter_allows_anything(self) -> None:
        _validate_model_provider("claude-opus-4-6", "openrouter")
        _validate_model_provider("gpt-5.2", "openrouter")

    def test_unknown_model_passes(self) -> None:
        _validate_model_provider("my-custom-model", "openai")
        _validate_model_provider("some-random-model", "anthropic")


class ResolveProviderTests(unittest.TestCase):
    def test_mistral_transcription_key_does_not_change_chat_provider(self) -> None:
        creds = CredentialBundle(mistral_transcription_api_key="mistral-test")
        self.assertEqual(_resolve_provider("auto", creds), "anthropic")


if __name__ == "__main__":
    unittest.main()
