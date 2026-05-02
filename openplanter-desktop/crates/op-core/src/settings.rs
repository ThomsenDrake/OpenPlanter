use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::config::{
    normalize_chrome_mcp_browser_url, normalize_chrome_mcp_channel, normalize_continuity_mode,
    normalize_embeddings_provider, normalize_model_alias, normalize_recursion_policy,
    normalize_web_search_provider, normalize_zai_plan,
};
use crate::obsidian::{
    DEFAULT_OBSIDIAN_EXPORT_SUBDIR, normalize_obsidian_export_mode,
    normalize_obsidian_export_subdir,
};

const VALID_REASONING_EFFORTS: &[&str] = &["low", "medium", "high"];

/// Normalize and validate a reasoning effort value.
pub fn normalize_reasoning_effort(value: Option<&str>) -> Result<Option<String>, String> {
    match value {
        None => Ok(None),
        Some(v) => {
            let cleaned = v.trim().to_lowercase();
            if cleaned.is_empty() {
                return Ok(None);
            }
            if !VALID_REASONING_EFFORTS.contains(&cleaned.as_str()) {
                return Err(format!(
                    "Invalid reasoning effort '{}'. Expected one of: {}",
                    v,
                    VALID_REASONING_EFFORTS.join(", ")
                ));
            }
            Ok(Some(cleaned))
        }
    }
}

pub fn normalize_bool(value: Option<&serde_json::Value>) -> Result<Option<bool>, String> {
    match value {
        None | Some(serde_json::Value::Null) => Ok(None),
        Some(serde_json::Value::Bool(value)) => Ok(Some(*value)),
        Some(serde_json::Value::String(value)) => match value.trim().to_lowercase().as_str() {
            "" => Ok(None),
            "1" | "true" | "yes" | "on" => Ok(Some(true)),
            "0" | "false" | "no" | "off" => Ok(Some(false)),
            _ => Err(format!("Invalid boolean value '{}'.", value)),
        },
        Some(other) => Err(format!("Invalid boolean value '{}'.", other)),
    }
}

/// Persistent settings stored per workspace.
///
/// Mirrors the Python `PersistentSettings` dataclass.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct PersistentSettings {
    pub default_model: Option<String>,
    pub default_reasoning_effort: Option<String>,
    pub default_model_openai: Option<String>,
    pub default_model_anthropic: Option<String>,
    pub default_model_openrouter: Option<String>,
    pub default_model_cerebras: Option<String>,
    pub default_model_zai: Option<String>,
    pub default_model_ollama: Option<String>,
    pub zai_plan: Option<String>,
    pub web_search_provider: Option<String>,
    pub embeddings_provider: Option<String>,
    pub continuity_mode: Option<String>,
    pub recursive: Option<bool>,
    pub recursion_policy: Option<String>,
    pub min_subtask_depth: Option<i64>,
    pub max_depth: Option<i64>,
    pub mistral_document_ai_use_shared_key: Option<bool>,
    pub chrome_mcp_enabled: Option<bool>,
    pub chrome_mcp_auto_connect: Option<bool>,
    pub chrome_mcp_browser_url: Option<String>,
    pub chrome_mcp_channel: Option<String>,
    pub chrome_mcp_connect_timeout_sec: Option<i64>,
    pub chrome_mcp_rpc_timeout_sec: Option<i64>,
    pub default_investigation_id: Option<String>,
    pub obsidian_export_enabled: Option<bool>,
    pub obsidian_export_root: Option<String>,
    pub obsidian_export_mode: Option<String>,
    pub obsidian_export_subdir: Option<String>,
    pub obsidian_generate_canvas: Option<bool>,
}

impl PersistentSettings {
    /// Get the default model for a specific provider.
    pub fn default_model_for_provider(&self, provider: &str) -> Option<&str> {
        let specific = match provider {
            "openai" => self.default_model_openai.as_deref(),
            "anthropic" => self.default_model_anthropic.as_deref(),
            "openrouter" => self.default_model_openrouter.as_deref(),
            "cerebras" => self.default_model_cerebras.as_deref(),
            "zai" => self.default_model_zai.as_deref(),
            "ollama" => self.default_model_ollama.as_deref(),
            _ => None,
        };
        if specific.is_some() {
            return specific;
        }
        self.default_model.as_deref()
    }

    /// Return a normalized copy with trimmed/validated values.
    pub fn normalized(&self) -> Result<Self, String> {
        let model = self
            .default_model
            .as_deref()
            .map(|s| s.trim())
            .filter(|s| !s.is_empty())
            .map(normalize_model_alias);

        let effort = normalize_reasoning_effort(self.default_reasoning_effort.as_deref())?;

        let web_search_provider = self
            .web_search_provider
            .as_deref()
            .map(|value| normalize_web_search_provider(Some(value)));
        let embeddings_provider = self
            .embeddings_provider
            .as_deref()
            .map(|value| normalize_embeddings_provider(Some(value)));
        let continuity_mode = self
            .continuity_mode
            .as_deref()
            .map(|value| normalize_continuity_mode(Some(value)));
        let recursion_policy = self
            .recursion_policy
            .as_deref()
            .map(|value| normalize_recursion_policy(Some(value)));
        let max_depth = self.max_depth.map(|value| value.max(0));
        let min_subtask_depth = self
            .min_subtask_depth
            .map(|value| value.max(0))
            .map(|value| value.min(max_depth.unwrap_or(value)));
        let zai_plan = self
            .zai_plan
            .as_deref()
            .map(|value| normalize_zai_plan(Some(value)));

        fn trim_opt(v: &Option<String>) -> Option<String> {
            v.as_deref()
                .map(|s| s.trim())
                .filter(|s| !s.is_empty())
                .map(normalize_model_alias)
        }

        Ok(Self {
            default_model: model,
            default_reasoning_effort: effort,
            default_model_openai: trim_opt(&self.default_model_openai),
            default_model_anthropic: trim_opt(&self.default_model_anthropic),
            default_model_openrouter: trim_opt(&self.default_model_openrouter),
            default_model_cerebras: trim_opt(&self.default_model_cerebras),
            default_model_zai: trim_opt(&self.default_model_zai),
            default_model_ollama: trim_opt(&self.default_model_ollama),
            zai_plan,
            web_search_provider,
            embeddings_provider,
            continuity_mode,
            recursive: self.recursive,
            recursion_policy,
            min_subtask_depth,
            max_depth,
            mistral_document_ai_use_shared_key: self.mistral_document_ai_use_shared_key,
            chrome_mcp_enabled: self.chrome_mcp_enabled,
            chrome_mcp_auto_connect: self.chrome_mcp_auto_connect,
            chrome_mcp_browser_url: normalize_chrome_mcp_browser_url(
                self.chrome_mcp_browser_url.as_deref(),
            ),
            chrome_mcp_channel: self
                .chrome_mcp_channel
                .as_deref()
                .map(|value| normalize_chrome_mcp_channel(Some(value))),
            chrome_mcp_connect_timeout_sec: self
                .chrome_mcp_connect_timeout_sec
                .map(|value| value.max(1)),
            chrome_mcp_rpc_timeout_sec: self.chrome_mcp_rpc_timeout_sec.map(|value| value.max(1)),
            default_investigation_id: trim_opt(&self.default_investigation_id),
            obsidian_export_enabled: self.obsidian_export_enabled,
            obsidian_export_root: self
                .obsidian_export_root
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(ToString::to_string),
            obsidian_export_mode: self
                .obsidian_export_mode
                .as_deref()
                .map(|value| normalize_obsidian_export_mode(Some(value))),
            obsidian_export_subdir: self.obsidian_export_subdir.as_deref().map(|value| {
                let normalized = normalize_obsidian_export_subdir(Some(value));
                if normalized.is_empty() {
                    DEFAULT_OBSIDIAN_EXPORT_SUBDIR.to_string()
                } else {
                    normalized
                }
            }),
            obsidian_generate_canvas: self.obsidian_generate_canvas,
        })
    }

    /// Serialize to JSON map, omitting `None` values.
    pub fn to_json(&self) -> serde_json::Map<String, serde_json::Value> {
        let mut payload = serde_json::Map::new();
        macro_rules! add {
            ($field:ident, $key:expr) => {
                if let Some(ref v) = self.$field {
                    payload.insert($key.to_string(), serde_json::json!(v));
                }
            };
        }
        add!(default_model, "default_model");
        add!(default_reasoning_effort, "default_reasoning_effort");
        add!(default_model_openai, "default_model_openai");
        add!(default_model_anthropic, "default_model_anthropic");
        add!(default_model_openrouter, "default_model_openrouter");
        add!(default_model_cerebras, "default_model_cerebras");
        add!(default_model_zai, "default_model_zai");
        add!(default_model_ollama, "default_model_ollama");
        add!(zai_plan, "zai_plan");
        add!(web_search_provider, "web_search_provider");
        add!(embeddings_provider, "embeddings_provider");
        add!(continuity_mode, "continuity_mode");
        add!(recursive, "recursive");
        add!(recursion_policy, "recursion_policy");
        add!(min_subtask_depth, "min_subtask_depth");
        add!(max_depth, "max_depth");
        add!(
            mistral_document_ai_use_shared_key,
            "mistral_document_ai_use_shared_key"
        );
        add!(chrome_mcp_enabled, "chrome_mcp_enabled");
        add!(chrome_mcp_auto_connect, "chrome_mcp_auto_connect");
        add!(chrome_mcp_browser_url, "chrome_mcp_browser_url");
        add!(chrome_mcp_channel, "chrome_mcp_channel");
        add!(
            chrome_mcp_connect_timeout_sec,
            "chrome_mcp_connect_timeout_sec"
        );
        add!(chrome_mcp_rpc_timeout_sec, "chrome_mcp_rpc_timeout_sec");
        add!(default_investigation_id, "default_investigation_id");
        add!(obsidian_export_enabled, "obsidian_export_enabled");
        add!(obsidian_export_root, "obsidian_export_root");
        add!(obsidian_export_mode, "obsidian_export_mode");
        add!(obsidian_export_subdir, "obsidian_export_subdir");
        add!(obsidian_generate_canvas, "obsidian_generate_canvas");
        payload
    }

    /// Deserialize from a JSON map.
    pub fn from_json(payload: &serde_json::Value) -> Result<Self, String> {
        let obj = match payload.as_object() {
            Some(o) => o,
            None => return Ok(Self::default()),
        };

        fn get_str(map: &serde_json::Map<String, serde_json::Value>, key: &str) -> Option<String> {
            map.get(key)
                .and_then(|v| v.as_str())
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
        }

        let settings = Self {
            default_model: get_str(obj, "default_model"),
            default_reasoning_effort: get_str(obj, "default_reasoning_effort"),
            default_model_openai: get_str(obj, "default_model_openai"),
            default_model_anthropic: get_str(obj, "default_model_anthropic"),
            default_model_openrouter: get_str(obj, "default_model_openrouter"),
            default_model_cerebras: get_str(obj, "default_model_cerebras"),
            default_model_zai: get_str(obj, "default_model_zai"),
            default_model_ollama: get_str(obj, "default_model_ollama"),
            zai_plan: get_str(obj, "zai_plan"),
            web_search_provider: get_str(obj, "web_search_provider"),
            embeddings_provider: get_str(obj, "embeddings_provider"),
            continuity_mode: get_str(obj, "continuity_mode"),
            recursive: normalize_bool(obj.get("recursive"))?,
            recursion_policy: get_str(obj, "recursion_policy"),
            min_subtask_depth: obj
                .get("min_subtask_depth")
                .and_then(|value| value.as_i64()),
            max_depth: obj.get("max_depth").and_then(|value| value.as_i64()),
            mistral_document_ai_use_shared_key: normalize_bool(
                obj.get("mistral_document_ai_use_shared_key"),
            )?,
            chrome_mcp_enabled: normalize_bool(obj.get("chrome_mcp_enabled"))?,
            chrome_mcp_auto_connect: normalize_bool(obj.get("chrome_mcp_auto_connect"))?,
            chrome_mcp_browser_url: normalize_chrome_mcp_browser_url(
                get_str(obj, "chrome_mcp_browser_url").as_deref(),
            ),
            chrome_mcp_channel: get_str(obj, "chrome_mcp_channel")
                .map(|value| normalize_chrome_mcp_channel(Some(&value))),
            chrome_mcp_connect_timeout_sec: obj
                .get("chrome_mcp_connect_timeout_sec")
                .and_then(|value| value.as_i64()),
            chrome_mcp_rpc_timeout_sec: obj
                .get("chrome_mcp_rpc_timeout_sec")
                .and_then(|value| value.as_i64()),
            default_investigation_id: get_str(obj, "default_investigation_id"),
            obsidian_export_enabled: normalize_bool(obj.get("obsidian_export_enabled"))?,
            obsidian_export_root: get_str(obj, "obsidian_export_root"),
            obsidian_export_mode: get_str(obj, "obsidian_export_mode"),
            obsidian_export_subdir: get_str(obj, "obsidian_export_subdir"),
            obsidian_generate_canvas: normalize_bool(obj.get("obsidian_generate_canvas"))?,
        };
        settings.normalized()
    }
}

/// Persistent settings store at `{workspace}/.openplanter/settings.json`.
pub struct SettingsStore {
    pub settings_path: PathBuf,
}

impl SettingsStore {
    pub fn new(workspace: &Path, session_root_dir: &str) -> Self {
        let ws = workspace
            .canonicalize()
            .unwrap_or_else(|_| workspace.to_path_buf());
        let root = ws.join(session_root_dir);
        let _ = fs::create_dir_all(&root);
        Self {
            settings_path: root.join("settings.json"),
        }
    }

    pub fn load(&self) -> PersistentSettings {
        let content = match fs::read_to_string(&self.settings_path) {
            Ok(c) => c,
            Err(_) => return PersistentSettings::default(),
        };
        let parsed: serde_json::Value = match serde_json::from_str(&content) {
            Ok(v) => v,
            Err(_) => return PersistentSettings::default(),
        };
        PersistentSettings::from_json(&parsed).unwrap_or_default()
    }

    pub fn save(&self, settings: &PersistentSettings) -> std::io::Result<()> {
        let normalized = settings
            .normalized()
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidInput, e))?;
        let json = serde_json::to_string_pretty(&normalized.to_json())
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        fs::write(&self.settings_path, json)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_reasoning_effort_valid() {
        assert_eq!(
            normalize_reasoning_effort(Some("high")),
            Ok(Some("high".into()))
        );
        assert_eq!(
            normalize_reasoning_effort(Some(" LOW ")),
            Ok(Some("low".into()))
        );
        assert_eq!(
            normalize_reasoning_effort(Some("Medium")),
            Ok(Some("medium".into()))
        );
    }

    #[test]
    fn test_normalize_reasoning_effort_none() {
        assert_eq!(normalize_reasoning_effort(None), Ok(None));
        assert_eq!(normalize_reasoning_effort(Some("")), Ok(None));
        assert_eq!(normalize_reasoning_effort(Some("  ")), Ok(None));
    }

    #[test]
    fn test_normalize_reasoning_effort_invalid() {
        let result = normalize_reasoning_effort(Some("turbo"));
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("turbo"));
    }

    #[test]
    fn test_default_model_for_provider() {
        let settings = PersistentSettings {
            default_model: Some("global-model".into()),
            default_model_openai: Some("gpt-5.2".into()),
            default_model_zai: Some("glm-5".into()),
            ..Default::default()
        };
        assert_eq!(
            settings.default_model_for_provider("openai"),
            Some("gpt-5.2")
        );
        assert_eq!(
            settings.default_model_for_provider("anthropic"),
            Some("global-model")
        );
        assert_eq!(settings.default_model_for_provider("zai"), Some("glm-5"));
        assert_eq!(
            settings.default_model_for_provider("unknown"),
            Some("global-model")
        );
    }

    #[test]
    fn test_settings_store_save_load() {
        let dir = tempfile::tempdir().unwrap();
        let store = SettingsStore::new(dir.path(), ".openplanter");
        let settings = PersistentSettings {
            default_model: Some("gpt-5.2".into()),
            default_reasoning_effort: Some("high".into()),
            default_model_zai: Some("glm-5".into()),
            zai_plan: Some("coding".into()),
            web_search_provider: Some("firecrawl".into()),
            continuity_mode: Some("continue".into()),
            mistral_document_ai_use_shared_key: Some(false),
            ..Default::default()
        };
        store.save(&settings).unwrap();
        let loaded = store.load();
        assert_eq!(loaded.default_model, Some("gpt-5.2".into()));
        assert_eq!(loaded.default_reasoning_effort, Some("high".into()));
        assert_eq!(loaded.default_model_zai, Some("glm-5".into()));
        assert_eq!(loaded.zai_plan, Some("coding".into()));
        assert_eq!(loaded.web_search_provider, Some("firecrawl".into()));
        assert_eq!(loaded.continuity_mode, Some("continue".into()));
        assert_eq!(loaded.mistral_document_ai_use_shared_key, Some(false));
    }

    #[test]
    fn test_obsidian_settings_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let store = SettingsStore::new(dir.path(), ".openplanter");
        let settings = PersistentSettings {
            obsidian_export_enabled: Some(true),
            obsidian_export_root: Some("/Users/example/Vault".into()),
            obsidian_export_mode: Some("fresh-vault".into()),
            obsidian_export_subdir: Some("Research/OpenPlanter".into()),
            obsidian_generate_canvas: Some(false),
            ..Default::default()
        };
        store.save(&settings).unwrap();
        let loaded = store.load();
        assert_eq!(loaded.obsidian_export_enabled, Some(true));
        assert_eq!(
            loaded.obsidian_export_root,
            Some("/Users/example/Vault".into())
        );
        assert_eq!(loaded.obsidian_export_mode, Some("fresh_vault".into()));
        assert_eq!(
            loaded.obsidian_export_subdir,
            Some("Research/OpenPlanter".into())
        );
        assert_eq!(loaded.obsidian_generate_canvas, Some(false));
    }

    #[test]
    fn test_settings_store_load_missing() {
        let dir = tempfile::tempdir().unwrap();
        let store = SettingsStore::new(dir.path(), ".openplanter");
        let loaded = store.load();
        assert_eq!(loaded, PersistentSettings::default());
    }

    #[test]
    fn test_to_json_omits_none() {
        let settings = PersistentSettings {
            default_model: Some("test".into()),
            default_reasoning_effort: None,
            ..Default::default()
        };
        let json = settings.to_json();
        assert!(json.contains_key("default_model"));
        assert!(!json.contains_key("default_reasoning_effort"));
    }

    #[test]
    fn test_from_json_round_trip() {
        let settings = PersistentSettings {
            default_model: Some("gpt-5.2".into()),
            default_reasoning_effort: Some("high".into()),
            default_model_openai: Some("gpt-5.2".into()),
            default_model_zai: Some("glm-5".into()),
            zai_plan: Some("coding".into()),
            web_search_provider: Some("firecrawl".into()),
            continuity_mode: Some("fresh".into()),
            mistral_document_ai_use_shared_key: Some(false),
            ..Default::default()
        };
        let json_val = serde_json::to_value(settings.to_json()).unwrap();
        let loaded = PersistentSettings::from_json(&json_val).unwrap();
        assert_eq!(loaded.default_model, Some("gpt-5.2".into()));
        assert_eq!(loaded.default_reasoning_effort, Some("high".into()));
        assert_eq!(loaded.default_model_openai, Some("gpt-5.2".into()));
        assert_eq!(loaded.default_model_zai, Some("glm-5".into()));
        assert_eq!(loaded.zai_plan, Some("coding".into()));
        assert_eq!(loaded.web_search_provider, Some("firecrawl".into()));
        assert_eq!(loaded.continuity_mode, Some("fresh".into()));
        assert_eq!(loaded.mistral_document_ai_use_shared_key, Some(false));
    }

    #[test]
    fn test_web_search_provider_normalized() {
        let settings = PersistentSettings {
            web_search_provider: Some("unexpected".into()),
            ..Default::default()
        };
        let normalized = settings.normalized().unwrap();
        assert_eq!(normalized.web_search_provider, Some("exa".into()));
    }

    #[test]
    fn test_zai_plan_normalized() {
        let settings = PersistentSettings {
            zai_plan: Some("unexpected".into()),
            ..Default::default()
        };
        let normalized = settings.normalized().unwrap();
        assert_eq!(normalized.zai_plan, Some("paygo".into()));
    }

    #[test]
    fn test_continuity_mode_normalized() {
        let settings = PersistentSettings {
            continuity_mode: Some("unexpected".into()),
            ..Default::default()
        };
        let normalized = settings.normalized().unwrap();
        assert_eq!(normalized.continuity_mode, Some("auto".into()));
    }

    #[test]
    fn test_model_aliases_normalized() {
        let settings = PersistentSettings {
            default_model: Some("sonnet".into()),
            default_model_anthropic: Some("haiku".into()),
            default_model_openai: Some("gpt5".into()),
            ..Default::default()
        };

        let normalized = settings.normalized().unwrap();
        assert_eq!(
            normalized.default_model,
            Some("anthropic-foundry/claude-sonnet-4-6".into())
        );
        assert_eq!(
            normalized.default_model_anthropic,
            Some("anthropic-foundry/claude-haiku-4-5".into())
        );
        assert_eq!(
            normalized.default_model_openai,
            Some("azure-foundry/gpt-5.4".into())
        );
    }
}
