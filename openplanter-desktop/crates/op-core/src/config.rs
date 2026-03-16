use std::collections::HashMap;
use std::env;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use serde::{Deserialize, Serialize};

pub const MISTRAL_TRANSCRIPTION_BASE_URL: &str = "https://api.mistral.ai";
pub const MISTRAL_TRANSCRIPTION_DEFAULT_MODEL: &str = "voxtral-mini-latest";
pub const MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS: i64 = 900;
pub const MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS: f64 = 2.0;
pub const MISTRAL_TRANSCRIPTION_MAX_CHUNKS: i64 = 48;
pub const MISTRAL_TRANSCRIPTION_REQUEST_TIMEOUT_SEC: i64 = 180;
pub const CHROME_MCP_DEFAULT_CHANNEL: &str = "stable";
pub const CHROME_MCP_CONNECT_TIMEOUT_SEC: i64 = 15;
pub const CHROME_MCP_RPC_TIMEOUT_SEC: i64 = 45;

/// Default model for each supported provider.
pub static PROVIDER_DEFAULT_MODELS: LazyLock<HashMap<&'static str, &'static str>> =
    LazyLock::new(|| {
        HashMap::from([
            ("openai", "gpt-5.2"),
            ("anthropic", "claude-opus-4-6"),
            ("openrouter", "anthropic/claude-sonnet-4-5"),
            ("cerebras", "qwen-3-235b-a22b-instruct-2507"),
            ("ollama", "llama3.2"),
        ])
    });

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

fn env_opt(key: &str) -> Option<String> {
    env::var(key).ok().filter(|s| !s.trim().is_empty())
}

fn env_int(key: &str, default: i64) -> i64 {
    env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

fn env_float(key: &str, default: f64) -> f64 {
    env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

fn env_bool(key: &str, default: bool) -> bool {
    match env::var(key) {
        Ok(v) => matches!(v.trim().to_lowercase().as_str(), "1" | "true" | "yes" | "on"),
        Err(_) => default,
    }
}

pub fn normalize_chrome_mcp_channel(value: Option<&str>) -> String {
    match value.unwrap_or_default().trim().to_lowercase().as_str() {
        "beta" => "beta".to_string(),
        "dev" => "dev".to_string(),
        "canary" => "canary".to_string(),
        _ => CHROME_MCP_DEFAULT_CHANNEL.to_string(),
    }
}

pub fn normalize_chrome_mcp_browser_url(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

/// Central configuration for the OpenPlanter agent.
///
/// Mirrors the Python `AgentConfig` dataclass field-for-field.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentConfig {
    pub workspace: PathBuf,
    pub provider: String,
    pub model: String,
    pub reasoning_effort: Option<String>,

    // Base URLs
    pub base_url: String,
    pub openai_base_url: String,
    pub anthropic_base_url: String,
    pub openrouter_base_url: String,
    pub cerebras_base_url: String,
    pub ollama_base_url: String,
    pub exa_base_url: String,
    pub mistral_transcription_base_url: String,

    // API keys
    pub api_key: Option<String>,
    pub openai_api_key: Option<String>,
    pub anthropic_api_key: Option<String>,
    pub openrouter_api_key: Option<String>,
    pub cerebras_api_key: Option<String>,
    pub exa_api_key: Option<String>,
    pub voyage_api_key: Option<String>,
    pub mistral_transcription_api_key: Option<String>,
    pub mistral_transcription_model: String,
    pub mistral_transcription_max_bytes: i64,
    pub mistral_transcription_chunk_max_seconds: i64,
    pub mistral_transcription_chunk_overlap_seconds: f64,
    pub mistral_transcription_max_chunks: i64,
    pub mistral_transcription_request_timeout_sec: i64,
    pub chrome_mcp_enabled: bool,
    pub chrome_mcp_auto_connect: bool,
    pub chrome_mcp_browser_url: Option<String>,
    pub chrome_mcp_channel: String,
    pub chrome_mcp_connect_timeout_sec: i64,
    pub chrome_mcp_rpc_timeout_sec: i64,

    // Limits
    pub max_depth: i64,
    pub max_steps_per_call: i64,
    pub budget_extension_enabled: bool,
    pub budget_extension_block_steps: i64,
    pub budget_extension_max_blocks: i64,
    pub max_observation_chars: i64,
    pub command_timeout_sec: i64,
    pub shell: String,
    pub max_files_listed: i64,
    pub max_file_chars: i64,
    pub max_search_hits: i64,
    pub max_shell_output_chars: i64,
    pub session_root_dir: String,
    pub max_persisted_observations: i64,
    pub max_solve_seconds: i64,
    pub rate_limit_max_retries: i64,
    pub rate_limit_backoff_base_sec: f64,
    pub rate_limit_backoff_max_sec: f64,
    pub rate_limit_retry_after_cap_sec: f64,
    pub recursive: bool,
    pub min_subtask_depth: i64,
    pub acceptance_criteria: bool,
    pub max_plan_chars: i64,
    pub max_turn_summaries: i64,
    pub demo: bool,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            workspace: PathBuf::from("."),
            provider: "auto".into(),
            model: "claude-opus-4-6".into(),
            reasoning_effort: Some("high".into()),
            base_url: "https://api.openai.com/v1".into(),
            openai_base_url: "https://api.openai.com/v1".into(),
            anthropic_base_url: "https://api.anthropic.com/v1".into(),
            openrouter_base_url: "https://openrouter.ai/api/v1".into(),
            cerebras_base_url: "https://api.cerebras.ai/v1".into(),
            ollama_base_url: "http://localhost:11434/v1".into(),
            exa_base_url: "https://api.exa.ai".into(),
            mistral_transcription_base_url: MISTRAL_TRANSCRIPTION_BASE_URL.into(),
            api_key: None,
            openai_api_key: None,
            anthropic_api_key: None,
            openrouter_api_key: None,
            cerebras_api_key: None,
            exa_api_key: None,
            voyage_api_key: None,
            mistral_transcription_api_key: None,
            mistral_transcription_model: MISTRAL_TRANSCRIPTION_DEFAULT_MODEL.into(),
            mistral_transcription_max_bytes: 100 * 1024 * 1024,
            mistral_transcription_chunk_max_seconds: MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS,
            mistral_transcription_chunk_overlap_seconds:
                MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
            mistral_transcription_max_chunks: MISTRAL_TRANSCRIPTION_MAX_CHUNKS,
            mistral_transcription_request_timeout_sec: MISTRAL_TRANSCRIPTION_REQUEST_TIMEOUT_SEC,
            chrome_mcp_enabled: false,
            chrome_mcp_auto_connect: true,
            chrome_mcp_browser_url: None,
            chrome_mcp_channel: CHROME_MCP_DEFAULT_CHANNEL.into(),
            chrome_mcp_connect_timeout_sec: CHROME_MCP_CONNECT_TIMEOUT_SEC,
            chrome_mcp_rpc_timeout_sec: CHROME_MCP_RPC_TIMEOUT_SEC,
            max_depth: 4,
            max_steps_per_call: 100,
            budget_extension_enabled: true,
            budget_extension_block_steps: 20,
            budget_extension_max_blocks: 2,
            max_observation_chars: 6000,
            command_timeout_sec: 45,
            shell: "/bin/sh".into(),
            max_files_listed: 400,
            max_file_chars: 20000,
            max_search_hits: 200,
            max_shell_output_chars: 16000,
            session_root_dir: ".openplanter".into(),
            max_persisted_observations: 400,
            max_solve_seconds: 0,
            rate_limit_max_retries: 12,
            rate_limit_backoff_base_sec: 1.0,
            rate_limit_backoff_max_sec: 60.0,
            rate_limit_retry_after_cap_sec: 120.0,
            recursive: true,
            min_subtask_depth: 0,
            acceptance_criteria: true,
            max_plan_chars: 40_000,
            max_turn_summaries: 50,
            demo: false,
        }
    }
}

impl AgentConfig {
    /// Build configuration from environment variables, mirroring `AgentConfig.from_env()`.
    pub fn from_env(workspace: impl AsRef<Path>) -> Self {
        let ws = dunce_canonicalize(workspace.as_ref());

        let openai_api_key = env_opt("OPENPLANTER_OPENAI_API_KEY")
            .or_else(|| env_opt("OPENAI_API_KEY"))
            .or_else(|| env_opt("OPENPLANTER_OPENAI_OAUTH_TOKEN"))
            .or_else(|| env_opt("OPENAI_OAUTH_TOKEN"));

        let anthropic_api_key = env_opt("OPENPLANTER_ANTHROPIC_API_KEY")
            .or_else(|| env_opt("ANTHROPIC_API_KEY"));

        let openrouter_api_key = env_opt("OPENPLANTER_OPENROUTER_API_KEY")
            .or_else(|| env_opt("OPENROUTER_API_KEY"));

        let cerebras_api_key = env_opt("OPENPLANTER_CEREBRAS_API_KEY")
            .or_else(|| env_opt("CEREBRAS_API_KEY"));

        let exa_api_key = env_opt("OPENPLANTER_EXA_API_KEY")
            .or_else(|| env_opt("EXA_API_KEY"));

        let voyage_api_key = env_opt("OPENPLANTER_VOYAGE_API_KEY")
            .or_else(|| env_opt("VOYAGE_API_KEY"));

        let mistral_transcription_api_key = env_opt("OPENPLANTER_MISTRAL_TRANSCRIPTION_API_KEY")
            .or_else(|| env_opt("MISTRAL_TRANSCRIPTION_API_KEY"))
            .or_else(|| env_opt("MISTRAL_API_KEY"));

        let openai_base_url = env_opt("OPENPLANTER_OPENAI_BASE_URL")
            .or_else(|| env_opt("OPENPLANTER_BASE_URL"))
            .unwrap_or_else(|| "https://api.openai.com/v1".into());

        let reasoning_effort_raw = env_or("OPENPLANTER_REASONING_EFFORT", "high")
            .trim()
            .to_lowercase();
        let reasoning_effort = if reasoning_effort_raw.is_empty() {
            None
        } else {
            Some(reasoning_effort_raw)
        };

        let provider_raw = env_or("OPENPLANTER_PROVIDER", "auto")
            .trim()
            .to_lowercase();
        let provider = if provider_raw.is_empty() {
            "auto".into()
        } else {
            provider_raw
        };

        Self {
            workspace: ws,
            provider,
            model: env_or("OPENPLANTER_MODEL", "claude-opus-4-6"),
            reasoning_effort,
            base_url: openai_base_url.clone(),
            api_key: openai_api_key.clone(),
            openai_base_url,
            anthropic_base_url: env_or(
                "OPENPLANTER_ANTHROPIC_BASE_URL",
                "https://api.anthropic.com/v1",
            ),
            openrouter_base_url: env_or(
                "OPENPLANTER_OPENROUTER_BASE_URL",
                "https://openrouter.ai/api/v1",
            ),
            cerebras_base_url: env_or(
                "OPENPLANTER_CEREBRAS_BASE_URL",
                "https://api.cerebras.ai/v1",
            ),
            ollama_base_url: env_or(
                "OPENPLANTER_OLLAMA_BASE_URL",
                "http://localhost:11434/v1",
            ),
            exa_base_url: env_or("OPENPLANTER_EXA_BASE_URL", "https://api.exa.ai"),
            mistral_transcription_base_url: env_opt("OPENPLANTER_MISTRAL_TRANSCRIPTION_BASE_URL")
                .or_else(|| env_opt("MISTRAL_TRANSCRIPTION_BASE_URL"))
                .or_else(|| env_opt("MISTRAL_BASE_URL"))
                .unwrap_or_else(|| MISTRAL_TRANSCRIPTION_BASE_URL.into()),
            openai_api_key,
            anthropic_api_key,
            openrouter_api_key,
            cerebras_api_key,
            exa_api_key,
            voyage_api_key,
            mistral_transcription_api_key,
            mistral_transcription_model: env_opt("OPENPLANTER_MISTRAL_TRANSCRIPTION_MODEL")
                .or_else(|| env_opt("MISTRAL_TRANSCRIPTION_MODEL"))
                .unwrap_or_else(|| MISTRAL_TRANSCRIPTION_DEFAULT_MODEL.into()),
            mistral_transcription_max_bytes: env_int(
                "OPENPLANTER_MISTRAL_TRANSCRIPTION_MAX_BYTES",
                100 * 1024 * 1024,
            ),
            mistral_transcription_chunk_max_seconds: env_int(
                "OPENPLANTER_MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS",
                MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS,
            ),
            mistral_transcription_chunk_overlap_seconds: env_float(
                "OPENPLANTER_MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS",
                MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
            ),
            mistral_transcription_max_chunks: env_int(
                "OPENPLANTER_MISTRAL_TRANSCRIPTION_MAX_CHUNKS",
                MISTRAL_TRANSCRIPTION_MAX_CHUNKS,
            ),
            mistral_transcription_request_timeout_sec: env_int(
                "OPENPLANTER_MISTRAL_TRANSCRIPTION_REQUEST_TIMEOUT_SEC",
                MISTRAL_TRANSCRIPTION_REQUEST_TIMEOUT_SEC,
            ),
            chrome_mcp_enabled: env_bool("OPENPLANTER_CHROME_MCP_ENABLED", false),
            chrome_mcp_auto_connect: env_bool("OPENPLANTER_CHROME_MCP_AUTO_CONNECT", true),
            chrome_mcp_browser_url: normalize_chrome_mcp_browser_url(
                env_opt("OPENPLANTER_CHROME_MCP_BROWSER_URL").as_deref(),
            ),
            chrome_mcp_channel: normalize_chrome_mcp_channel(
                env_opt("OPENPLANTER_CHROME_MCP_CHANNEL").as_deref(),
            ),
            chrome_mcp_connect_timeout_sec: env_int(
                "OPENPLANTER_CHROME_MCP_CONNECT_TIMEOUT_SEC",
                CHROME_MCP_CONNECT_TIMEOUT_SEC,
            )
            .max(1),
            chrome_mcp_rpc_timeout_sec: env_int(
                "OPENPLANTER_CHROME_MCP_RPC_TIMEOUT_SEC",
                CHROME_MCP_RPC_TIMEOUT_SEC,
            )
            .max(1),
            max_depth: env_int("OPENPLANTER_MAX_DEPTH", 4),
            max_steps_per_call: env_int("OPENPLANTER_MAX_STEPS", 100),
            budget_extension_enabled: env_bool("OPENPLANTER_BUDGET_EXTENSION_ENABLED", true),
            budget_extension_block_steps: env_int("OPENPLANTER_BUDGET_EXTENSION_BLOCK_STEPS", 20)
                .max(1),
            budget_extension_max_blocks: env_int("OPENPLANTER_BUDGET_EXTENSION_MAX_BLOCKS", 2)
                .max(0),
            max_observation_chars: env_int("OPENPLANTER_MAX_OBS_CHARS", 6000),
            command_timeout_sec: env_int("OPENPLANTER_CMD_TIMEOUT", 45),
            shell: env_or("OPENPLANTER_SHELL", "/bin/sh"),
            max_files_listed: env_int("OPENPLANTER_MAX_FILES", 400),
            max_file_chars: env_int("OPENPLANTER_MAX_FILE_CHARS", 20000),
            max_search_hits: env_int("OPENPLANTER_MAX_SEARCH_HITS", 200),
            max_shell_output_chars: env_int("OPENPLANTER_MAX_SHELL_CHARS", 16000),
            session_root_dir: env_or("OPENPLANTER_SESSION_DIR", ".openplanter"),
            max_persisted_observations: env_int("OPENPLANTER_MAX_PERSISTED_OBS", 400),
            max_solve_seconds: env_int("OPENPLANTER_MAX_SOLVE_SECONDS", 0),
            rate_limit_max_retries: env_int("OPENPLANTER_RATE_LIMIT_MAX_RETRIES", 12),
            rate_limit_backoff_base_sec: env_float("OPENPLANTER_RATE_LIMIT_BACKOFF_BASE_SEC", 1.0),
            rate_limit_backoff_max_sec: env_float("OPENPLANTER_RATE_LIMIT_BACKOFF_MAX_SEC", 60.0),
            rate_limit_retry_after_cap_sec: env_float(
                "OPENPLANTER_RATE_LIMIT_RETRY_AFTER_CAP_SEC",
                120.0,
            ),
            recursive: env_bool("OPENPLANTER_RECURSIVE", true),
            min_subtask_depth: env_int("OPENPLANTER_MIN_SUBTASK_DEPTH", 0),
            acceptance_criteria: env_bool("OPENPLANTER_ACCEPTANCE_CRITERIA", true),
            max_plan_chars: env_int("OPENPLANTER_MAX_PLAN_CHARS", 40_000),
            max_turn_summaries: env_int("OPENPLANTER_MAX_TURN_SUMMARIES", 50),
            demo: env_bool("OPENPLANTER_DEMO", false),
        }
    }
}

/// Canonicalize a path, expanding `~` and resolving symlinks.
/// Falls back to the original path on error.
fn dunce_canonicalize(p: &Path) -> PathBuf {
    let expanded = if p.starts_with("~") {
        if let Some(home) = dirs_home() {
            home.join(p.strip_prefix("~").unwrap_or(p))
        } else {
            p.to_path_buf()
        }
    } else {
        p.to_path_buf()
    };
    std::fs::canonicalize(&expanded).unwrap_or(expanded)
}

fn dirs_home() -> Option<PathBuf> {
    env::var("HOME")
        .ok()
        .map(PathBuf::from)
        .or_else(|| env::var("USERPROFILE").ok().map(PathBuf::from))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let cfg = AgentConfig::default();
        assert_eq!(cfg.provider, "auto");
        assert_eq!(cfg.model, "claude-opus-4-6");
        assert_eq!(cfg.reasoning_effort, Some("high".into()));
        assert!(!cfg.chrome_mcp_enabled);
        assert!(cfg.chrome_mcp_auto_connect);
        assert_eq!(cfg.chrome_mcp_browser_url, None);
        assert_eq!(cfg.chrome_mcp_channel, CHROME_MCP_DEFAULT_CHANNEL);
        assert_eq!(cfg.chrome_mcp_connect_timeout_sec, CHROME_MCP_CONNECT_TIMEOUT_SEC);
        assert_eq!(cfg.chrome_mcp_rpc_timeout_sec, CHROME_MCP_RPC_TIMEOUT_SEC);
        assert_eq!(cfg.max_depth, 4);
        assert_eq!(cfg.max_steps_per_call, 100);
        assert!(cfg.budget_extension_enabled);
        assert_eq!(cfg.budget_extension_block_steps, 20);
        assert_eq!(cfg.budget_extension_max_blocks, 2);
        assert_eq!(cfg.rate_limit_max_retries, 12);
        assert_eq!(cfg.rate_limit_backoff_base_sec, 1.0);
        assert_eq!(cfg.rate_limit_backoff_max_sec, 60.0);
        assert_eq!(cfg.rate_limit_retry_after_cap_sec, 120.0);
        assert!(cfg.recursive);
        assert!(cfg.acceptance_criteria);
        assert!(!cfg.demo);
    }

    #[test]
    fn test_provider_default_models() {
        assert_eq!(PROVIDER_DEFAULT_MODELS.get("openai"), Some(&"gpt-5.2"));
        assert_eq!(
            PROVIDER_DEFAULT_MODELS.get("anthropic"),
            Some(&"claude-opus-4-6")
        );
        assert_eq!(
            PROVIDER_DEFAULT_MODELS.get("openrouter"),
            Some(&"anthropic/claude-sonnet-4-5")
        );
        assert_eq!(
            PROVIDER_DEFAULT_MODELS.get("cerebras"),
            Some(&"qwen-3-235b-a22b-instruct-2507")
        );
        assert_eq!(PROVIDER_DEFAULT_MODELS.get("ollama"), Some(&"llama3.2"));
    }

    #[test]
    fn test_normalize_chrome_mcp_helpers() {
        assert_eq!(
            normalize_chrome_mcp_channel(Some("BETA")),
            "beta".to_string()
        );
        assert_eq!(
            normalize_chrome_mcp_channel(Some("unexpected")),
            CHROME_MCP_DEFAULT_CHANNEL.to_string()
        );
        assert_eq!(
            normalize_chrome_mcp_browser_url(Some("  http://127.0.0.1:9222  ")),
            Some("http://127.0.0.1:9222".to_string())
        );
        assert_eq!(normalize_chrome_mcp_browser_url(Some("  ")), None);
    }

    /// Combined env-based test to avoid race conditions from parallel test execution.
    /// Tests both default and custom env var loading in sequence.
    #[test]
    fn test_from_env_defaults_and_custom() {
        let keys = [
            "OPENPLANTER_PROVIDER",
            "OPENPLANTER_MODEL",
            "OPENPLANTER_REASONING_EFFORT",
            "OPENPLANTER_OPENAI_API_KEY",
            "OPENAI_API_KEY",
            "OPENPLANTER_OPENAI_OAUTH_TOKEN",
            "OPENAI_OAUTH_TOKEN",
            "OPENPLANTER_ANTHROPIC_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENPLANTER_MAX_DEPTH",
            "OPENPLANTER_BUDGET_EXTENSION_ENABLED",
            "OPENPLANTER_BUDGET_EXTENSION_BLOCK_STEPS",
            "OPENPLANTER_BUDGET_EXTENSION_MAX_BLOCKS",
            "OPENPLANTER_CHROME_MCP_ENABLED",
            "OPENPLANTER_CHROME_MCP_AUTO_CONNECT",
            "OPENPLANTER_CHROME_MCP_BROWSER_URL",
            "OPENPLANTER_CHROME_MCP_CHANNEL",
            "OPENPLANTER_CHROME_MCP_CONNECT_TIMEOUT_SEC",
            "OPENPLANTER_CHROME_MCP_RPC_TIMEOUT_SEC",
            "OPENPLANTER_RECURSIVE",
            "OPENPLANTER_DEMO",
            "OPENPLANTER_RATE_LIMIT_MAX_RETRIES",
            "OPENPLANTER_RATE_LIMIT_BACKOFF_BASE_SEC",
            "OPENPLANTER_RATE_LIMIT_BACKOFF_MAX_SEC",
            "OPENPLANTER_RATE_LIMIT_RETRY_AFTER_CAP_SEC",
        ];
        // Save original values
        let saved: Vec<_> = keys
            .iter()
            .map(|k| (*k, env::var(k).ok()))
            .collect();

        // SAFETY: test-only; combined into one test to avoid parallel env mutation
        unsafe {
            // --- Phase 1: test defaults (all cleared) ---
            for k in &keys {
                env::remove_var(k);
            }
        }

        let cfg = AgentConfig::from_env("/tmp");
        assert_eq!(cfg.provider, "auto");
        assert_eq!(cfg.model, "claude-opus-4-6");
        assert_eq!(cfg.reasoning_effort, Some("high".into()));
        assert!(!cfg.chrome_mcp_enabled);
        assert!(cfg.chrome_mcp_auto_connect);
        assert_eq!(cfg.chrome_mcp_browser_url, None);
        assert_eq!(cfg.chrome_mcp_channel, CHROME_MCP_DEFAULT_CHANNEL);
        assert_eq!(cfg.chrome_mcp_connect_timeout_sec, CHROME_MCP_CONNECT_TIMEOUT_SEC);
        assert_eq!(cfg.chrome_mcp_rpc_timeout_sec, CHROME_MCP_RPC_TIMEOUT_SEC);
        assert_eq!(cfg.max_depth, 4);
        assert!(cfg.budget_extension_enabled);
        assert_eq!(cfg.budget_extension_block_steps, 20);
        assert_eq!(cfg.budget_extension_max_blocks, 2);
        assert_eq!(cfg.rate_limit_max_retries, 12);
        assert_eq!(cfg.rate_limit_backoff_base_sec, 1.0);
        assert_eq!(cfg.rate_limit_backoff_max_sec, 60.0);
        assert_eq!(cfg.rate_limit_retry_after_cap_sec, 120.0);
        assert!(cfg.recursive);
        assert!(!cfg.demo);
        assert!(cfg.openai_api_key.is_none());
        assert!(cfg.anthropic_api_key.is_none());

        unsafe {
            // --- Phase 2: test custom values ---
            env::set_var("OPENPLANTER_PROVIDER", "openai");
            env::set_var("OPENPLANTER_MODEL", "gpt-5.2");
            env::set_var("OPENPLANTER_REASONING_EFFORT", "low");
            env::set_var("OPENPLANTER_MAX_DEPTH", "8");
            env::set_var("OPENPLANTER_BUDGET_EXTENSION_ENABLED", "false");
            env::set_var("OPENPLANTER_BUDGET_EXTENSION_BLOCK_STEPS", "9");
            env::set_var("OPENPLANTER_BUDGET_EXTENSION_MAX_BLOCKS", "1");
            env::set_var("OPENPLANTER_CHROME_MCP_ENABLED", "true");
            env::set_var("OPENPLANTER_CHROME_MCP_AUTO_CONNECT", "false");
            env::set_var("OPENPLANTER_CHROME_MCP_BROWSER_URL", "http://127.0.0.1:9222");
            env::set_var("OPENPLANTER_CHROME_MCP_CHANNEL", "beta");
            env::set_var("OPENPLANTER_CHROME_MCP_CONNECT_TIMEOUT_SEC", "17");
            env::set_var("OPENPLANTER_CHROME_MCP_RPC_TIMEOUT_SEC", "52");
            env::set_var("OPENPLANTER_RECURSIVE", "false");
            env::set_var("OPENPLANTER_DEMO", "true");
            env::set_var("OPENAI_API_KEY", "sk-test123");
            env::set_var("OPENPLANTER_RATE_LIMIT_MAX_RETRIES", "5");
            env::set_var("OPENPLANTER_RATE_LIMIT_BACKOFF_BASE_SEC", "2.5");
            env::set_var("OPENPLANTER_RATE_LIMIT_BACKOFF_MAX_SEC", "30.0");
            env::set_var("OPENPLANTER_RATE_LIMIT_RETRY_AFTER_CAP_SEC", "90.0");
        }

        let cfg = AgentConfig::from_env("/tmp");
        assert_eq!(cfg.provider, "openai");
        assert_eq!(cfg.model, "gpt-5.2");
        assert_eq!(cfg.reasoning_effort, Some("low".into()));
        assert_eq!(cfg.max_depth, 8);
        assert!(!cfg.budget_extension_enabled);
        assert_eq!(cfg.budget_extension_block_steps, 9);
        assert_eq!(cfg.budget_extension_max_blocks, 1);
        assert!(cfg.chrome_mcp_enabled);
        assert!(!cfg.chrome_mcp_auto_connect);
        assert_eq!(
            cfg.chrome_mcp_browser_url,
            Some("http://127.0.0.1:9222".to_string())
        );
        assert_eq!(cfg.chrome_mcp_channel, "beta");
        assert_eq!(cfg.chrome_mcp_connect_timeout_sec, 17);
        assert_eq!(cfg.chrome_mcp_rpc_timeout_sec, 52);
        assert_eq!(cfg.rate_limit_max_retries, 5);
        assert_eq!(cfg.rate_limit_backoff_base_sec, 2.5);
        assert_eq!(cfg.rate_limit_backoff_max_sec, 30.0);
        assert_eq!(cfg.rate_limit_retry_after_cap_sec, 90.0);
        assert!(!cfg.recursive);
        assert!(cfg.demo);
        assert_eq!(cfg.openai_api_key, Some("sk-test123".into()));

        unsafe {
            // --- Phase 3: OAuth token also counts as OpenAI auth ---
            env::remove_var("OPENPLANTER_OPENAI_API_KEY");
            env::remove_var("OPENAI_API_KEY");
            env::set_var("OPENAI_OAUTH_TOKEN", "oauth-token");
        }

        let cfg = AgentConfig::from_env("/tmp");
        assert_eq!(cfg.openai_api_key, Some("oauth-token".into()));

        // Restore original values
        for (k, v) in saved {
            unsafe {
                match v {
                    Some(val) => env::set_var(k, val),
                    None => env::remove_var(k),
                }
            }
        }
    }
}
