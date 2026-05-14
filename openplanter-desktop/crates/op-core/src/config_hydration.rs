use std::env;

use crate::config::{
    AgentConfig, FOUNDRY_OPENAI_API_KEY_PLACEHOLDER, default_embeddings_base_url,
    default_embeddings_model, normalize_continuity_mode, normalize_embeddings_provider,
    normalize_recursion_policy, normalize_web_search_provider, normalize_zai_plan,
    resolve_openai_api_key, resolve_zai_base_url,
};
use crate::credentials::CredentialBundle;
use crate::obsidian::{normalize_obsidian_export_mode, normalize_obsidian_export_subdir};
use crate::settings::{PersistentSettings, ProviderProfile};

/// Merge credentials into an AgentConfig.
/// Priority: existing config value > env_creds > file_creds.
pub fn merge_credentials_into_config(
    cfg: &mut AgentConfig,
    env_creds: &CredentialBundle,
    file_creds: &CredentialBundle,
) {
    if cfg.openai_oauth_token.is_none() {
        cfg.openai_oauth_token = env_creds
            .openai_oauth_token
            .clone()
            .or_else(|| file_creds.openai_oauth_token.clone());
    }
    cfg.openai_api_key = cfg
        .openai_api_key
        .clone()
        .filter(|value| {
            let trimmed = value.trim();
            !trimmed.is_empty() && trimmed != FOUNDRY_OPENAI_API_KEY_PLACEHOLDER
        })
        .or_else(|| env_creds.openai_api_key.clone())
        .or_else(|| file_creds.openai_api_key.clone())
        .or_else(|| cfg.openai_api_key.clone());
    cfg.openai_api_key = resolve_openai_api_key(
        cfg.openai_api_key.clone(),
        &cfg.openai_base_url,
        cfg.openai_oauth_token.clone(),
    );
    cfg.api_key = resolve_openai_api_key(
        cfg.openai_api_key
            .clone()
            .filter(|value| {
                let trimmed = value.trim();
                !trimmed.is_empty() && trimmed != FOUNDRY_OPENAI_API_KEY_PLACEHOLDER
            })
            .or_else(|| {
                cfg.api_key.clone().filter(|value| {
                    let trimmed = value.trim();
                    !trimmed.is_empty() && trimmed != FOUNDRY_OPENAI_API_KEY_PLACEHOLDER
                })
            })
            .or_else(|| cfg.openai_api_key.clone())
            .or_else(|| cfg.api_key.clone()),
        &cfg.base_url,
        cfg.openai_oauth_token.clone(),
    );

    macro_rules! merge {
        ($field:ident) => {
            if cfg.$field.is_none() {
                cfg.$field = env_creds
                    .$field
                    .clone()
                    .or_else(|| file_creds.$field.clone());
            }
        };
    }
    merge!(anthropic_api_key);
    merge!(openrouter_api_key);
    merge!(cerebras_api_key);
    merge!(zai_api_key);
    merge!(exa_api_key);
    merge!(firecrawl_api_key);
    merge!(brave_api_key);
    merge!(tavily_api_key);
    merge!(voyage_api_key);
    merge!(mistral_api_key);
    merge!(mistral_document_ai_api_key);
    merge!(mistral_transcription_api_key);
}

fn profile_option_i64(profile: &ProviderProfile, key: &str, fallback: i64) -> i64 {
    profile
        .options
        .get(key)
        .and_then(|value| {
            value
                .as_i64()
                .or_else(|| value.as_u64().map(|value| value as i64))
        })
        .unwrap_or(fallback)
        .max(1)
}

fn profile_option_f64(profile: &ProviderProfile, key: &str, fallback: f64) -> f64 {
    profile
        .options
        .get(key)
        .and_then(|value| value.as_f64())
        .unwrap_or(fallback)
        .max(0.0)
}

fn llm_base_url_env_keys(provider: &str) -> &'static [&'static str] {
    match provider {
        "openai" => &["OPENPLANTER_OPENAI_BASE_URL", "OPENPLANTER_BASE_URL"],
        "anthropic" => &["OPENPLANTER_ANTHROPIC_BASE_URL"],
        "openrouter" => &["OPENPLANTER_OPENROUTER_BASE_URL"],
        "cerebras" => &["OPENPLANTER_CEREBRAS_BASE_URL"],
        "zai" => &["OPENPLANTER_ZAI_BASE_URL"],
        "ollama" => &["OPENPLANTER_OLLAMA_BASE_URL"],
        _ => &[],
    }
}

pub fn apply_llm_profile(cfg: &mut AgentConfig, profile_id: &str, profile: &ProviderProfile) {
    cfg.llm_profile_id = Some(profile_id.to_string());
    cfg.llm_profile_name = profile.name.clone();
    if !has_env_value(&["OPENPLANTER_PROVIDER"]) {
        cfg.provider = profile.provider.clone();
    }
    if !has_env_value(&["OPENPLANTER_MODEL"]) {
        cfg.model = profile.model.clone();
    }
    if let Some(base_url) = profile.base_url.as_deref() {
        if !has_env_value(llm_base_url_env_keys(&profile.provider)) {
            match profile.provider.as_str() {
                "openai" => {
                    cfg.openai_base_url = base_url.to_string();
                    cfg.base_url = base_url.to_string();
                }
                "anthropic" => cfg.anthropic_base_url = base_url.to_string(),
                "openrouter" => cfg.openrouter_base_url = base_url.to_string(),
                "cerebras" => cfg.cerebras_base_url = base_url.to_string(),
                "zai" => cfg.zai_base_url = base_url.to_string(),
                "ollama" => cfg.ollama_base_url = base_url.to_string(),
                _ => {}
            }
        }
    }
    if let Some(value) = profile.options.get("reasoning_effort") {
        if !has_env_value(&["OPENPLANTER_REASONING_EFFORT"]) {
            let effort = value
                .as_str()
                .unwrap_or_default()
                .trim()
                .to_ascii_lowercase();
            cfg.reasoning_effort = if effort.is_empty() || effort == "none" || effort == "off" {
                None
            } else {
                Some(effort)
            };
        }
    }
    if let Some(value) = profile
        .options
        .get("zai_plan")
        .and_then(|value| value.as_str())
    {
        if !has_env_value(&["OPENPLANTER_ZAI_PLAN"]) {
            cfg.zai_plan = normalize_zai_plan(Some(value));
        }
        if !has_env_value(&["OPENPLANTER_ZAI_BASE_URL"]) {
            cfg.zai_base_url = resolve_zai_base_url(
                &cfg.zai_plan,
                &cfg.zai_paygo_base_url,
                &cfg.zai_coding_base_url,
            );
        }
    }
}

pub fn apply_embedding_profile(cfg: &mut AgentConfig, profile_id: &str, profile: &ProviderProfile) {
    cfg.embedding_profile_id = Some(profile_id.to_string());
    cfg.embedding_profile_name = profile.name.clone();
    cfg.embeddings_provider = normalize_embeddings_provider(Some(&profile.provider));
    cfg.embeddings_model = if profile.model.trim().is_empty() {
        default_embeddings_model(Some(&cfg.embeddings_provider))
    } else {
        profile.model.clone()
    };
    cfg.embeddings_base_url = profile
        .base_url
        .clone()
        .unwrap_or_else(|| default_embeddings_base_url(Some(&cfg.embeddings_provider)));
}

pub fn apply_stt_profile(cfg: &mut AgentConfig, profile_id: &str, profile: &ProviderProfile) {
    cfg.stt_profile_id = Some(profile_id.to_string());
    cfg.stt_profile_name = profile.name.clone();
    if profile.provider != "mistral" {
        return;
    }
    if !profile.model.trim().is_empty() {
        cfg.mistral_transcription_model = profile.model.clone();
    }
    if let Some(base_url) = profile.base_url.as_deref() {
        cfg.mistral_transcription_base_url = base_url.to_string();
    }
    cfg.mistral_transcription_max_bytes =
        profile_option_i64(profile, "max_bytes", cfg.mistral_transcription_max_bytes);
    cfg.mistral_transcription_chunk_max_seconds = profile_option_i64(
        profile,
        "chunk_max_seconds",
        cfg.mistral_transcription_chunk_max_seconds,
    );
    cfg.mistral_transcription_chunk_overlap_seconds = profile_option_f64(
        profile,
        "chunk_overlap_seconds",
        cfg.mistral_transcription_chunk_overlap_seconds,
    );
    cfg.mistral_transcription_max_chunks =
        profile_option_i64(profile, "max_chunks", cfg.mistral_transcription_max_chunks);
    cfg.mistral_transcription_request_timeout_sec = profile_option_i64(
        profile,
        "request_timeout_sec",
        cfg.mistral_transcription_request_timeout_sec,
    );
}

pub fn apply_settings_to_config(cfg: &mut AgentConfig, settings: &PersistentSettings) {
    if !has_env_value(&["OPENPLANTER_PROVIDER"]) && !has_env_value(&["OPENPLANTER_MODEL"]) {
        if let Some(profile_id) = settings.active_profiles.get("llm") {
            if let Some(profile) = settings.active_profile("llm") {
                apply_llm_profile(cfg, profile_id, profile);
            }
        }
    }

    let embeddings_env_overrides = [
        "OPENPLANTER_EMBEDDINGS_PROVIDER",
        "OPENPLANTER_EMBEDDINGS_MODEL",
        "OPENPLANTER_EMBEDDINGS_BASE_URL",
    ];
    if !has_env_value(&embeddings_env_overrides) {
        if let Some(profile_id) = settings.active_profiles.get("embedding") {
            if let Some(profile) = settings.active_profile("embedding") {
                apply_embedding_profile(cfg, profile_id, profile);
            }
        }
    }

    if !has_env_value(&[
        "OPENPLANTER_MISTRAL_TRANSCRIPTION_MODEL",
        "OPENPLANTER_MISTRAL_TRANSCRIPTION_BASE_URL",
        "OPENPLANTER_MISTRAL_TRANSCRIPTION_MAX_BYTES",
        "OPENPLANTER_MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS",
        "OPENPLANTER_MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS",
        "OPENPLANTER_MISTRAL_TRANSCRIPTION_MAX_CHUNKS",
        "OPENPLANTER_MISTRAL_TRANSCRIPTION_REQUEST_TIMEOUT_SEC",
    ]) {
        if let Some(profile_id) = settings.active_profiles.get("stt") {
            if let Some(profile) = settings.active_profile("stt") {
                apply_stt_profile(cfg, profile_id, profile);
            }
        }
    }

    if !has_env_value(&["OPENPLANTER_REASONING_EFFORT"]) {
        if let Some(reasoning_effort) = settings.default_reasoning_effort.clone() {
            cfg.reasoning_effort = Some(reasoning_effort);
        }
    }

    if !has_env_value(&["OPENPLANTER_ZAI_PLAN"]) {
        if let Some(plan) = settings.zai_plan.as_deref() {
            cfg.zai_plan = normalize_zai_plan(Some(plan));
        }
    }

    if !has_env_value(&["OPENPLANTER_ZAI_BASE_URL"]) {
        cfg.zai_base_url = resolve_zai_base_url(
            &cfg.zai_plan,
            &cfg.zai_paygo_base_url,
            &cfg.zai_coding_base_url,
        );
    }

    if !has_env_value(&["OPENPLANTER_WEB_SEARCH_PROVIDER"]) {
        if let Some(provider) = settings.web_search_provider.as_deref() {
            cfg.web_search_provider = normalize_web_search_provider(Some(provider));
        }
    }

    if !has_env_value(&embeddings_env_overrides) && cfg.embedding_profile_id.is_none() {
        if let Some(provider) = settings.embeddings_provider.as_deref() {
            cfg.embeddings_provider = normalize_embeddings_provider(Some(provider));
            cfg.embeddings_model = default_embeddings_model(Some(&cfg.embeddings_provider));
            cfg.embeddings_base_url = default_embeddings_base_url(Some(&cfg.embeddings_provider));
        }
    }

    if !has_env_value(&["OPENPLANTER_CONTINUITY_MODE"]) {
        if let Some(mode) = settings.continuity_mode.as_deref() {
            cfg.continuity_mode = normalize_continuity_mode(Some(mode));
        }
    }

    if !has_env_value(&["OPENPLANTER_RECURSIVE"]) {
        if let Some(recursive) = settings.recursive {
            cfg.recursive = recursive;
        }
    }

    if !has_env_value(&["OPENPLANTER_RECURSION_POLICY"]) {
        if let Some(policy) = settings.recursion_policy.as_deref() {
            cfg.recursion_policy = normalize_recursion_policy(Some(policy));
        }
    }

    if !has_env_value(&["OPENPLANTER_MAX_DEPTH"]) {
        if let Some(max_depth) = settings.max_depth {
            cfg.max_depth = max_depth.max(0);
        }
    }

    if !has_env_value(&["OPENPLANTER_MIN_SUBTASK_DEPTH"]) {
        if let Some(min_depth) = settings.min_subtask_depth {
            cfg.min_subtask_depth = min_depth.clamp(0, cfg.max_depth);
        }
    } else {
        cfg.min_subtask_depth = cfg.min_subtask_depth.clamp(0, cfg.max_depth);
    }
    if !has_env_value(&["OPENPLANTER_MISTRAL_DOCUMENT_AI_USE_SHARED_KEY"]) {
        if let Some(value) = settings.mistral_document_ai_use_shared_key {
            cfg.mistral_document_ai_use_shared_key = value;
        }
    }
    if !has_env_value(&["OPENPLANTER_CHROME_MCP_ENABLED"]) {
        if let Some(enabled) = settings.chrome_mcp_enabled {
            cfg.chrome_mcp_enabled = enabled;
        }
    }

    if !has_env_value(&["OPENPLANTER_CHROME_MCP_AUTO_CONNECT"]) {
        if let Some(auto_connect) = settings.chrome_mcp_auto_connect {
            cfg.chrome_mcp_auto_connect = auto_connect;
        }
    }

    if !has_env_value(&["OPENPLANTER_CHROME_MCP_BROWSER_URL"]) {
        if let Some(browser_url) = settings.chrome_mcp_browser_url.as_deref() {
            cfg.chrome_mcp_browser_url = Some(browser_url.to_string());
        }
    }

    if !has_env_value(&["OPENPLANTER_CHROME_MCP_CHANNEL"]) {
        if let Some(channel) = settings.chrome_mcp_channel.as_deref() {
            cfg.chrome_mcp_channel = channel.to_string();
        }
    }

    if !has_env_value(&["OPENPLANTER_CHROME_MCP_CONNECT_TIMEOUT_SEC"]) {
        if let Some(timeout) = settings.chrome_mcp_connect_timeout_sec {
            cfg.chrome_mcp_connect_timeout_sec = timeout.max(1);
        }
    }

    if !has_env_value(&["OPENPLANTER_CHROME_MCP_RPC_TIMEOUT_SEC"]) {
        if let Some(timeout) = settings.chrome_mcp_rpc_timeout_sec {
            cfg.chrome_mcp_rpc_timeout_sec = timeout.max(1);
        }
    }

    if !has_env_value(&["OPENPLANTER_OBSIDIAN_EXPORT_ENABLED"]) {
        if let Some(enabled) = settings.obsidian_export_enabled {
            cfg.obsidian_export_enabled = enabled;
        }
    }

    if !has_env_value(&["OPENPLANTER_OBSIDIAN_EXPORT_ROOT"]) {
        if let Some(root) = settings.obsidian_export_root.as_deref() {
            cfg.obsidian_export_root = Some(root.into());
        }
    }

    if !has_env_value(&["OPENPLANTER_OBSIDIAN_EXPORT_MODE"]) {
        if let Some(mode) = settings.obsidian_export_mode.as_deref() {
            cfg.obsidian_export_mode = normalize_obsidian_export_mode(Some(mode));
        }
    }

    if !has_env_value(&["OPENPLANTER_OBSIDIAN_EXPORT_SUBDIR"]) {
        if let Some(subdir) = settings.obsidian_export_subdir.as_deref() {
            cfg.obsidian_export_subdir = normalize_obsidian_export_subdir(Some(subdir));
        }
    }

    if !has_env_value(&["OPENPLANTER_OBSIDIAN_GENERATE_CANVAS"]) {
        if let Some(generate_canvas) = settings.obsidian_generate_canvas {
            cfg.obsidian_generate_canvas = generate_canvas;
        }
    }

    if !has_env_value(&["OPENPLANTER_MODEL"]) && cfg.llm_profile_id.is_none() {
        let saved_model = if cfg.provider == "auto" {
            settings.default_model.as_deref()
        } else {
            settings
                .default_model_for_provider(cfg.provider.as_str())
                .or(settings.default_model.as_deref())
        };
        if let Some(model) = saved_model {
            cfg.model = model.to_string();
        }
    }
}

fn has_env_value(keys: &[&str]) -> bool {
    keys.iter().any(|key| {
        env::var(key)
            .ok()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::BTreeMap, env};

    #[test]
    fn apply_settings_to_config_sets_continuity_when_env_missing() {
        let _env_guard = crate::config::ENV_TEST_LOCK.lock().unwrap();
        let saved = env::var("OPENPLANTER_CONTINUITY_MODE").ok();
        unsafe {
            env::remove_var("OPENPLANTER_CONTINUITY_MODE");
        }

        let mut cfg = AgentConfig::default();
        let settings = PersistentSettings {
            continuity_mode: Some("continue".into()),
            ..Default::default()
        };

        apply_settings_to_config(&mut cfg, &settings);

        assert_eq!(cfg.continuity_mode, "continue");

        unsafe {
            match saved {
                Some(value) => env::set_var("OPENPLANTER_CONTINUITY_MODE", value),
                None => env::remove_var("OPENPLANTER_CONTINUITY_MODE"),
            }
        }
    }

    #[test]
    fn apply_settings_to_config_normalizes_obsidian_settings_when_env_missing() {
        let _env_guard = crate::config::ENV_TEST_LOCK.lock().unwrap();
        let saved_mode = env::var("OPENPLANTER_OBSIDIAN_EXPORT_MODE").ok();
        let saved_subdir = env::var("OPENPLANTER_OBSIDIAN_EXPORT_SUBDIR").ok();
        unsafe {
            env::remove_var("OPENPLANTER_OBSIDIAN_EXPORT_MODE");
            env::remove_var("OPENPLANTER_OBSIDIAN_EXPORT_SUBDIR");
        }

        let mut cfg = AgentConfig::default();
        let settings = PersistentSettings {
            obsidian_export_mode: Some("fresh-vault".into()),
            obsidian_export_subdir: Some("/Research/Cestus/".into()),
            ..Default::default()
        };

        apply_settings_to_config(&mut cfg, &settings);

        assert_eq!(cfg.obsidian_export_mode, "fresh_vault");
        assert_eq!(cfg.obsidian_export_subdir, "Research/Cestus");

        unsafe {
            match saved_mode {
                Some(value) => env::set_var("OPENPLANTER_OBSIDIAN_EXPORT_MODE", value),
                None => env::remove_var("OPENPLANTER_OBSIDIAN_EXPORT_MODE"),
            }
            match saved_subdir {
                Some(value) => env::set_var("OPENPLANTER_OBSIDIAN_EXPORT_SUBDIR", value),
                None => env::remove_var("OPENPLANTER_OBSIDIAN_EXPORT_SUBDIR"),
            }
        }
    }

    #[test]
    fn apply_settings_to_config_preserves_embeddings_env_overrides() {
        let _env_guard = crate::config::ENV_TEST_LOCK.lock().unwrap();
        let saved_provider = env::var("OPENPLANTER_EMBEDDINGS_PROVIDER").ok();
        let saved_model = env::var("OPENPLANTER_EMBEDDINGS_MODEL").ok();
        let saved_base_url = env::var("OPENPLANTER_EMBEDDINGS_BASE_URL").ok();
        unsafe {
            env::remove_var("OPENPLANTER_EMBEDDINGS_PROVIDER");
            env::set_var("OPENPLANTER_EMBEDDINGS_MODEL", "env-embed");
            env::remove_var("OPENPLANTER_EMBEDDINGS_BASE_URL");
        }

        let mut embedding_pool = BTreeMap::new();
        embedding_pool.insert(
            "mistral-default".to_string(),
            ProviderProfile {
                provider: "mistral".into(),
                model: "mistral-embed".into(),
                base_url: Some("https://api.mistral.ai/v1".into()),
                ..Default::default()
            },
        );
        let settings = PersistentSettings {
            active_profiles: BTreeMap::from([(
                "embedding".to_string(),
                "mistral-default".to_string(),
            )]),
            profiles: BTreeMap::from([("embedding".to_string(), embedding_pool)]),
            embeddings_provider: Some("mistral".into()),
            ..Default::default()
        };
        let mut cfg = AgentConfig {
            embeddings_provider: "voyage".into(),
            embeddings_model: "env-embed".into(),
            embeddings_base_url: "https://env.example/v1".into(),
            ..Default::default()
        };

        apply_settings_to_config(&mut cfg, &settings);

        assert_eq!(cfg.embeddings_provider, "voyage");
        assert_eq!(cfg.embeddings_model, "env-embed");
        assert_eq!(cfg.embeddings_base_url, "https://env.example/v1");
        assert!(cfg.embedding_profile_id.is_none());

        unsafe {
            match saved_provider {
                Some(value) => env::set_var("OPENPLANTER_EMBEDDINGS_PROVIDER", value),
                None => env::remove_var("OPENPLANTER_EMBEDDINGS_PROVIDER"),
            }
            match saved_model {
                Some(value) => env::set_var("OPENPLANTER_EMBEDDINGS_MODEL", value),
                None => env::remove_var("OPENPLANTER_EMBEDDINGS_MODEL"),
            }
            match saved_base_url {
                Some(value) => env::set_var("OPENPLANTER_EMBEDDINGS_BASE_URL", value),
                None => env::remove_var("OPENPLANTER_EMBEDDINGS_BASE_URL"),
            }
        }
    }

    #[test]
    fn apply_settings_to_config_preserves_llm_env_side_overrides() {
        let _env_guard = crate::config::ENV_TEST_LOCK.lock().unwrap();
        let saved_provider = env::var("OPENPLANTER_PROVIDER").ok();
        let saved_model = env::var("OPENPLANTER_MODEL").ok();
        let saved_reasoning = env::var("OPENPLANTER_REASONING_EFFORT").ok();
        let saved_zai_plan = env::var("OPENPLANTER_ZAI_PLAN").ok();
        let saved_zai_base_url = env::var("OPENPLANTER_ZAI_BASE_URL").ok();
        unsafe {
            env::remove_var("OPENPLANTER_PROVIDER");
            env::remove_var("OPENPLANTER_MODEL");
            env::set_var("OPENPLANTER_REASONING_EFFORT", "low");
            env::set_var("OPENPLANTER_ZAI_PLAN", "paygo");
            env::set_var("OPENPLANTER_ZAI_BASE_URL", "https://env-zai.example/v4");
        }

        let mut llm_pool = BTreeMap::new();
        llm_pool.insert(
            "zai-coding".to_string(),
            ProviderProfile {
                provider: "zai".into(),
                model: "glm-4.6".into(),
                base_url: Some("https://profile-zai.example/v4".into()),
                options: BTreeMap::from([
                    ("reasoning_effort".to_string(), serde_json::json!("high")),
                    ("zai_plan".to_string(), serde_json::json!("coding")),
                ]),
                ..Default::default()
            },
        );
        let settings = PersistentSettings {
            active_profiles: BTreeMap::from([("llm".to_string(), "zai-coding".to_string())]),
            profiles: BTreeMap::from([("llm".to_string(), llm_pool)]),
            ..Default::default()
        };
        let mut cfg = AgentConfig {
            provider: "auto".into(),
            model: "default-model".into(),
            reasoning_effort: Some("low".into()),
            zai_plan: "paygo".into(),
            zai_base_url: "https://env-zai.example/v4".into(),
            ..Default::default()
        };

        apply_settings_to_config(&mut cfg, &settings);

        assert_eq!(cfg.llm_profile_id.as_deref(), Some("zai-coding"));
        assert_eq!(cfg.provider, "zai");
        assert_eq!(cfg.model, "glm-4.6");
        assert_eq!(cfg.reasoning_effort.as_deref(), Some("low"));
        assert_eq!(cfg.zai_plan, "paygo");
        assert_eq!(cfg.zai_base_url, "https://env-zai.example/v4");

        unsafe {
            match saved_provider {
                Some(value) => env::set_var("OPENPLANTER_PROVIDER", value),
                None => env::remove_var("OPENPLANTER_PROVIDER"),
            }
            match saved_model {
                Some(value) => env::set_var("OPENPLANTER_MODEL", value),
                None => env::remove_var("OPENPLANTER_MODEL"),
            }
            match saved_reasoning {
                Some(value) => env::set_var("OPENPLANTER_REASONING_EFFORT", value),
                None => env::remove_var("OPENPLANTER_REASONING_EFFORT"),
            }
            match saved_zai_plan {
                Some(value) => env::set_var("OPENPLANTER_ZAI_PLAN", value),
                None => env::remove_var("OPENPLANTER_ZAI_PLAN"),
            }
            match saved_zai_base_url {
                Some(value) => env::set_var("OPENPLANTER_ZAI_BASE_URL", value),
                None => env::remove_var("OPENPLANTER_ZAI_BASE_URL"),
            }
        }
    }
}
