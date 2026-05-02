use std::env;

use crate::config::{
    AgentConfig, FOUNDRY_OPENAI_API_KEY_PLACEHOLDER, normalize_continuity_mode,
    normalize_embeddings_provider, normalize_recursion_policy, normalize_web_search_provider,
    normalize_zai_plan, resolve_openai_api_key, resolve_zai_base_url,
};
use crate::credentials::CredentialBundle;
use crate::obsidian::{normalize_obsidian_export_mode, normalize_obsidian_export_subdir};
use crate::settings::PersistentSettings;

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

pub fn apply_settings_to_config(cfg: &mut AgentConfig, settings: &PersistentSettings) {
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

    if !has_env_value(&["OPENPLANTER_EMBEDDINGS_PROVIDER"]) {
        if let Some(provider) = settings.embeddings_provider.as_deref() {
            cfg.embeddings_provider = normalize_embeddings_provider(Some(provider));
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

    if !has_env_value(&["OPENPLANTER_MODEL"]) {
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
    use std::env;

    #[test]
    fn apply_settings_to_config_sets_continuity_when_env_missing() {
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
        let saved_mode = env::var("OPENPLANTER_OBSIDIAN_EXPORT_MODE").ok();
        let saved_subdir = env::var("OPENPLANTER_OBSIDIAN_EXPORT_SUBDIR").ok();
        unsafe {
            env::remove_var("OPENPLANTER_OBSIDIAN_EXPORT_MODE");
            env::remove_var("OPENPLANTER_OBSIDIAN_EXPORT_SUBDIR");
        }

        let mut cfg = AgentConfig::default();
        let settings = PersistentSettings {
            obsidian_export_mode: Some("fresh-vault".into()),
            obsidian_export_subdir: Some("/Research/OpenPlanter/".into()),
            ..Default::default()
        };

        apply_settings_to_config(&mut cfg, &settings);

        assert_eq!(cfg.obsidian_export_mode, "fresh_vault");
        assert_eq!(cfg.obsidian_export_subdir, "Research/OpenPlanter");

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
}
