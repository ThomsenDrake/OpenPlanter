use std::env;

use crate::config::{
    AgentConfig, normalize_chrome_mcp_browser_url, normalize_chrome_mcp_channel,
};
use crate::credentials::CredentialBundle;
use crate::settings::PersistentSettings;

/// Merge credentials into an AgentConfig.
/// Priority: existing config value > env_creds > file_creds.
pub fn merge_credentials_into_config(
    cfg: &mut AgentConfig,
    env_creds: &CredentialBundle,
    file_creds: &CredentialBundle,
) {
    if cfg.openai_api_key.is_none() {
        cfg.openai_api_key = env_creds
            .openai_api_key
            .clone()
            .or_else(|| env_creds.openai_oauth_token.clone())
            .or_else(|| file_creds.openai_api_key.clone());
        if cfg.openai_api_key.is_none() {
            cfg.openai_api_key = file_creds.openai_oauth_token.clone();
        }
    }
    if cfg.api_key.is_none() {
        cfg.api_key = cfg.openai_api_key.clone();
    }

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
    merge!(exa_api_key);
    merge!(voyage_api_key);
    merge!(mistral_transcription_api_key);
}

pub fn apply_settings_to_config(cfg: &mut AgentConfig, settings: &PersistentSettings) {
    if !has_env_value(&["OPENPLANTER_REASONING_EFFORT"]) {
        if let Some(reasoning_effort) = settings.default_reasoning_effort.clone() {
            cfg.reasoning_effort = Some(reasoning_effort);
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
        cfg.chrome_mcp_browser_url =
            normalize_chrome_mcp_browser_url(settings.chrome_mcp_browser_url.as_deref());
    }

    if !has_env_value(&["OPENPLANTER_CHROME_MCP_CHANNEL"]) {
        if let Some(channel) = settings.chrome_mcp_channel.as_deref() {
            cfg.chrome_mcp_channel = normalize_chrome_mcp_channel(Some(channel));
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
