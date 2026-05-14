use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::config::{
    ANTHROPIC_FOUNDRY_MODEL_PREFIX, AZURE_FOUNDRY_MODEL_PREFIX, FOUNDRY_ANTHROPIC_BASE_URL,
    FOUNDRY_OPENAI_BASE_URL, MISTRAL_EMBEDDING_BASE_URL, MISTRAL_EMBEDDING_MODEL,
    MISTRAL_TRANSCRIPTION_BASE_URL, MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS,
    MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS, MISTRAL_TRANSCRIPTION_DEFAULT_MODEL,
    MISTRAL_TRANSCRIPTION_MAX_CHUNKS, MISTRAL_TRANSCRIPTION_REQUEST_TIMEOUT_SEC,
    VOYAGE_EMBEDDING_BASE_URL, VOYAGE_EMBEDDING_MODEL, ZAI_PAYGO_BASE_URL,
    normalize_chrome_mcp_browser_url, normalize_chrome_mcp_channel, normalize_continuity_mode,
    normalize_embeddings_provider, normalize_model_alias, normalize_recursion_policy,
    normalize_web_search_provider, normalize_zai_plan,
};
use crate::obsidian::{
    DEFAULT_OBSIDIAN_EXPORT_SUBDIR, normalize_obsidian_export_mode,
    normalize_obsidian_export_subdir,
};

const VALID_REASONING_EFFORTS: &[&str] = &["low", "medium", "high", "xhigh"];
const VALID_LLM_PROVIDERS: &[&str] = &[
    "openai",
    "anthropic",
    "openrouter",
    "cerebras",
    "zai",
    "ollama",
];

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

const PROFILE_MODALITIES: [&str; 3] = ["llm", "embedding", "stt"];

fn slugify_profile_id(parts: &[&str]) -> String {
    let raw = parts
        .iter()
        .filter(|part| !part.trim().is_empty())
        .map(|part| part.trim().to_ascii_lowercase())
        .collect::<Vec<_>>()
        .join("-");
    let mut out = String::new();
    let mut last_dash = false;
    for ch in raw.chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch);
            last_dash = false;
        } else if !last_dash {
            out.push('-');
            last_dash = true;
        }
    }
    let trimmed = out.trim_matches('-').to_string();
    if trimmed.is_empty() {
        "default".to_string()
    } else {
        trimmed
    }
}

fn infer_llm_provider(model: &str) -> String {
    let text = model.trim().to_ascii_lowercase();
    if text.starts_with(ANTHROPIC_FOUNDRY_MODEL_PREFIX) || text.starts_with("claude") {
        "anthropic".to_string()
    } else if text.starts_with(AZURE_FOUNDRY_MODEL_PREFIX)
        || text.starts_with("gpt")
        || text.starts_with("o1")
        || text.starts_with("o3")
        || text.starts_with("o4")
    {
        "openai".to_string()
    } else if text.contains('/') {
        "openrouter".to_string()
    } else if text.starts_with("glm") || text.starts_with("zai-glm") {
        "zai".to_string()
    } else if text.starts_with("qwen-3")
        || text.starts_with("gpt-oss")
        || text.starts_with("llama-4")
    {
        "cerebras".to_string()
    } else if text.starts_with("llama")
        || text.starts_with("mistral")
        || text.starts_with("gemma")
        || text.starts_with("phi")
        || text.starts_with("codellama")
        || text.starts_with("deepseek")
    {
        "ollama".to_string()
    } else {
        "anthropic".to_string()
    }
}

fn default_base_url(provider: &str, modality: &str) -> Option<String> {
    match modality {
        "embedding" => Some(if provider == "voyage" {
            VOYAGE_EMBEDDING_BASE_URL.to_string()
        } else {
            MISTRAL_EMBEDDING_BASE_URL.to_string()
        }),
        "stt" => Some(MISTRAL_TRANSCRIPTION_BASE_URL.to_string()),
        _ => match provider {
            "openai" => Some(FOUNDRY_OPENAI_BASE_URL.to_string()),
            "anthropic" => Some(FOUNDRY_ANTHROPIC_BASE_URL.to_string()),
            "openrouter" => Some("https://openrouter.ai/api/v1".to_string()),
            "cerebras" => Some("https://api.cerebras.ai/v1".to_string()),
            "zai" => Some(ZAI_PAYGO_BASE_URL.to_string()),
            "ollama" => Some("http://localhost:11434/v1".to_string()),
            _ => None,
        },
    }
}

fn default_model(provider: &str, modality: &str) -> Option<String> {
    match modality {
        "embedding" => Some(if provider == "voyage" {
            VOYAGE_EMBEDDING_MODEL.to_string()
        } else {
            MISTRAL_EMBEDDING_MODEL.to_string()
        }),
        "stt" => Some(MISTRAL_TRANSCRIPTION_DEFAULT_MODEL.to_string()),
        _ => None,
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct ProviderProfile {
    pub name: Option<String>,
    pub provider: String,
    pub adapter: String,
    pub model: String,
    pub base_url: Option<String>,
    pub auth_ref: Option<String>,
    pub options: BTreeMap<String, Value>,
}

impl ProviderProfile {
    pub fn normalized(&self, modality: &str) -> Self {
        let modality = modality.trim().to_ascii_lowercase();
        let mut provider = self.provider.trim().to_ascii_lowercase();
        if modality == "embedding" {
            provider = normalize_embeddings_provider(Some(&provider));
        } else if modality == "stt" {
            if provider.is_empty() {
                provider = "mistral".to_string();
            }
        } else if provider.is_empty() || !VALID_LLM_PROVIDERS.contains(&provider.as_str()) {
            provider = infer_llm_provider(&self.model);
        }

        let adapter = match self.adapter.trim() {
            "" if modality == "llm" && provider == "anthropic" => "anthropic".to_string(),
            "" if modality == "llm" => "openai-compatible".to_string(),
            "" if modality == "embedding" => "embedding".to_string(),
            "" if modality == "stt" => "speech-to-text".to_string(),
            value => value.trim().to_ascii_lowercase(),
        };
        let model = self
            .model
            .trim()
            .to_string()
            .is_empty()
            .then(|| default_model(&provider, &modality))
            .flatten()
            .unwrap_or_else(|| self.model.trim().to_string());
        let base_url = self
            .base_url
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.trim_end_matches('/').to_string())
            .or_else(|| default_base_url(&provider, &modality));
        let auth_ref = self
            .auth_ref
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.to_ascii_lowercase())
            .or_else(|| {
                if modality == "stt" {
                    Some("mistral".to_string())
                } else {
                    Some(provider.clone())
                }
            });
        let mut options = self.options.clone();
        if modality == "stt" {
            options
                .entry("max_bytes".to_string())
                .or_insert_with(|| Value::from(100 * 1024 * 1024));
            options
                .entry("chunk_max_seconds".to_string())
                .or_insert_with(|| Value::from(MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS));
            options
                .entry("chunk_overlap_seconds".to_string())
                .or_insert_with(|| Value::from(MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS));
            options
                .entry("max_chunks".to_string())
                .or_insert_with(|| Value::from(MISTRAL_TRANSCRIPTION_MAX_CHUNKS));
            options
                .entry("request_timeout_sec".to_string())
                .or_insert_with(|| Value::from(MISTRAL_TRANSCRIPTION_REQUEST_TIMEOUT_SEC));
        }
        Self {
            name: self
                .name
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(ToString::to_string),
            provider,
            adapter,
            model,
            base_url,
            auth_ref,
            options,
        }
    }
}

fn normalize_profile_pools(
    pools: &BTreeMap<String, BTreeMap<String, ProviderProfile>>,
) -> (
    BTreeMap<String, BTreeMap<String, ProviderProfile>>,
    BTreeMap<String, BTreeMap<String, String>>,
) {
    let mut normalized: BTreeMap<String, BTreeMap<String, ProviderProfile>> = BTreeMap::new();
    let mut id_map: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    for modality in PROFILE_MODALITIES {
        let mut pool = BTreeMap::new();
        let mut modality_id_map = BTreeMap::new();
        if let Some(raw_pool) = pools.get(modality) {
            for (raw_id, profile) in raw_pool {
                let normalized_profile = profile.normalized(modality);
                if normalized_profile.model.is_empty() && modality != "embedding" {
                    continue;
                }
                let mut profile_id = slugify_profile_id(&[raw_id]);
                if pool.contains_key(&profile_id) {
                    let base_id = profile_id.clone();
                    let mut counter = 2;
                    loop {
                        let candidate = format!("{base_id}-{counter}");
                        if !pool.contains_key(&candidate) {
                            profile_id = candidate;
                            break;
                        }
                        counter += 1;
                    }
                }
                modality_id_map.insert(raw_id.clone(), profile_id.clone());
                pool.insert(profile_id, normalized_profile);
            }
        }
        normalized.insert(modality.to_string(), pool);
        id_map.insert(modality.to_string(), modality_id_map);
    }
    (normalized, id_map)
}

fn upsert_profile(
    pools: &mut BTreeMap<String, BTreeMap<String, ProviderProfile>>,
    active: &mut BTreeMap<String, String>,
    modality: &str,
    profile: ProviderProfile,
    profile_id: &str,
    make_active: bool,
    replace: bool,
) {
    let normalized = profile.normalized(modality);
    let selected_id = slugify_profile_id(&[profile_id]);
    let pool = pools.entry(modality.to_string()).or_default();
    if replace || !pool.contains_key(&selected_id) {
        pool.insert(selected_id.clone(), normalized);
    }
    if make_active || !active.contains_key(modality) {
        active.insert(modality.to_string(), selected_id);
    }
}

fn migrate_legacy_profiles(settings: &mut PersistentSettings) {
    let provider_models = [
        ("openai", settings.default_model_openai.clone()),
        ("anthropic", settings.default_model_anthropic.clone()),
        ("openrouter", settings.default_model_openrouter.clone()),
        ("cerebras", settings.default_model_cerebras.clone()),
        ("zai", settings.default_model_zai.clone()),
        ("ollama", settings.default_model_ollama.clone()),
    ];
    for (provider, model) in provider_models {
        let Some(model) = model else {
            continue;
        };
        let mut options = BTreeMap::new();
        if provider == "zai" {
            if let Some(plan) = settings.zai_plan.clone() {
                options.insert("zai_plan".to_string(), Value::String(plan));
            }
        }
        upsert_profile(
            &mut settings.profiles,
            &mut settings.active_profiles,
            "llm",
            ProviderProfile {
                name: Some(format!("{provider} default")),
                provider: provider.to_string(),
                adapter: String::new(),
                model,
                base_url: default_base_url(provider, "llm"),
                auth_ref: Some(provider.to_string()),
                options,
            },
            &format!("{provider}-default"),
            false,
            true,
        );
    }

    if let Some(model) = settings.default_model.clone() {
        let provider = infer_llm_provider(&model);
        let make_active = !settings.active_profiles.contains_key("llm");
        upsert_profile(
            &mut settings.profiles,
            &mut settings.active_profiles,
            "llm",
            ProviderProfile {
                name: Some("Workspace default LLM".to_string()),
                provider: provider.clone(),
                adapter: String::new(),
                model,
                base_url: default_base_url(&provider, "llm"),
                auth_ref: Some(provider),
                options: BTreeMap::new(),
            },
            "workspace-default",
            make_active,
            true,
        );
    }

    if let Some(provider) = settings.embeddings_provider.clone() {
        let provider = normalize_embeddings_provider(Some(&provider));
        let make_active = !settings.active_profiles.contains_key("embedding");
        upsert_profile(
            &mut settings.profiles,
            &mut settings.active_profiles,
            "embedding",
            ProviderProfile {
                name: Some(format!("{} embeddings", title_case(&provider))),
                provider: provider.clone(),
                adapter: "embedding".to_string(),
                model: default_model(&provider, "embedding").unwrap_or_default(),
                base_url: default_base_url(&provider, "embedding"),
                auth_ref: Some(provider.clone()),
                options: BTreeMap::new(),
            },
            &format!("{provider}-default"),
            make_active,
            true,
        );
    }

    let mut options = BTreeMap::new();
    if let Some(value) = settings.mistral_transcription_max_bytes {
        options.insert("max_bytes".to_string(), Value::from(value));
    }
    if let Some(value) = settings.mistral_transcription_chunk_max_seconds {
        options.insert("chunk_max_seconds".to_string(), Value::from(value));
    }
    if let Some(value) = settings.mistral_transcription_chunk_overlap_seconds {
        options.insert("chunk_overlap_seconds".to_string(), Value::from(value));
    }
    if let Some(value) = settings.mistral_transcription_max_chunks {
        options.insert("max_chunks".to_string(), Value::from(value));
    }
    if let Some(value) = settings.mistral_transcription_request_timeout_sec {
        options.insert("request_timeout_sec".to_string(), Value::from(value));
    }
    if settings.mistral_transcription_model.is_some()
        || settings.mistral_transcription_base_url.is_some()
        || !options.is_empty()
    {
        let make_active = !settings.active_profiles.contains_key("stt");
        upsert_profile(
            &mut settings.profiles,
            &mut settings.active_profiles,
            "stt",
            ProviderProfile {
                name: Some("Mistral Voxtral STT".to_string()),
                provider: "mistral".to_string(),
                adapter: "speech-to-text".to_string(),
                model: settings
                    .mistral_transcription_model
                    .clone()
                    .unwrap_or_else(|| MISTRAL_TRANSCRIPTION_DEFAULT_MODEL.to_string()),
                base_url: settings
                    .mistral_transcription_base_url
                    .clone()
                    .or_else(|| Some(MISTRAL_TRANSCRIPTION_BASE_URL.to_string())),
                auth_ref: Some("mistral".to_string()),
                options,
            },
            "mistral-voxtral",
            make_active,
            true,
        );
    }

    for modality in PROFILE_MODALITIES {
        let active_id = settings.active_profiles.get(modality).cloned();
        if let Some(active_id) = active_id {
            if !settings
                .profiles
                .get(modality)
                .is_some_and(|pool| pool.contains_key(&active_id))
            {
                settings.active_profiles.remove(modality);
            }
        }
    }
}

fn title_case(value: &str) -> String {
    let mut chars = value.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
}

/// Persistent settings stored per workspace.
///
/// Mirrors the Python `PersistentSettings` dataclass.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct PersistentSettings {
    #[serde(default)]
    pub active_profiles: BTreeMap<String, String>,
    #[serde(default)]
    pub profiles: BTreeMap<String, BTreeMap<String, ProviderProfile>>,
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
    pub mistral_transcription_base_url: Option<String>,
    pub mistral_transcription_model: Option<String>,
    pub mistral_transcription_max_bytes: Option<i64>,
    pub mistral_transcription_chunk_max_seconds: Option<i64>,
    pub mistral_transcription_chunk_overlap_seconds: Option<f64>,
    pub mistral_transcription_max_chunks: Option<i64>,
    pub mistral_transcription_request_timeout_sec: Option<i64>,
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
    pub fn active_profile(&self, modality: &str) -> Option<&ProviderProfile> {
        let profile_id = self.active_profiles.get(modality)?;
        self.profiles.get(modality)?.get(profile_id)
    }

    pub fn first_profile_for_provider(
        &self,
        modality: &str,
        provider: &str,
    ) -> Option<(&str, &ProviderProfile)> {
        let provider = provider.trim().to_ascii_lowercase();
        self.profiles
            .get(modality)?
            .iter()
            .find_map(|(id, profile)| {
                if profile.provider == provider {
                    Some((id.as_str(), profile))
                } else {
                    None
                }
            })
    }

    /// Get the default model for a specific provider.
    pub fn default_model_for_provider(&self, provider: &str) -> Option<&str> {
        if let Some(active) = self.active_profile("llm") {
            if provider == "auto" || active.provider == provider {
                return Some(active.model.as_str());
            }
        }
        if let Some((_, profile)) = self.first_profile_for_provider("llm", provider) {
            return Some(profile.model.as_str());
        }
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
        let (profiles, profile_id_map) = normalize_profile_pools(&self.profiles);
        let active_profiles = self
            .active_profiles
            .iter()
            .filter_map(|(key, value)| {
                let key = key.trim().to_ascii_lowercase();
                let raw_value = value.trim();
                if PROFILE_MODALITIES.contains(&key.as_str()) && !raw_value.is_empty() {
                    let value = profile_id_map
                        .get(&key)
                        .and_then(|pool| pool.get(raw_value))
                        .cloned()
                        .unwrap_or_else(|| slugify_profile_id(&[raw_value]));
                    Some((key, value))
                } else {
                    None
                }
            })
            .collect::<BTreeMap<_, _>>();
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

        let mut normalized = Self {
            active_profiles,
            profiles,
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
            mistral_transcription_base_url: self
                .mistral_transcription_base_url
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(|value| value.trim_end_matches('/').to_string()),
            mistral_transcription_model: self
                .mistral_transcription_model
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(ToString::to_string),
            mistral_transcription_max_bytes: self
                .mistral_transcription_max_bytes
                .map(|value| value.max(1)),
            mistral_transcription_chunk_max_seconds: self
                .mistral_transcription_chunk_max_seconds
                .map(|value| value.max(1)),
            mistral_transcription_chunk_overlap_seconds: self
                .mistral_transcription_chunk_overlap_seconds
                .map(|value| value.max(0.0)),
            mistral_transcription_max_chunks: self
                .mistral_transcription_max_chunks
                .map(|value| value.max(1)),
            mistral_transcription_request_timeout_sec: self
                .mistral_transcription_request_timeout_sec
                .map(|value| value.max(1)),
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
        };
        migrate_legacy_profiles(&mut normalized);
        Ok(normalized)
    }

    /// Serialize to JSON map, omitting `None` values.
    pub fn to_json(&self) -> serde_json::Map<String, serde_json::Value> {
        let mut payload = serde_json::Map::new();
        if !self.active_profiles.is_empty() {
            payload.insert(
                "active_profiles".to_string(),
                serde_json::to_value(&self.active_profiles).unwrap_or(serde_json::Value::Null),
            );
        }
        let nonempty_profiles = self
            .profiles
            .iter()
            .filter(|(_, pool)| !pool.is_empty())
            .map(|(modality, pool)| (modality.clone(), pool.clone()))
            .collect::<BTreeMap<_, _>>();
        if !nonempty_profiles.is_empty() {
            payload.insert(
                "profiles".to_string(),
                serde_json::to_value(&nonempty_profiles).unwrap_or(serde_json::Value::Null),
            );
        }
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
        add!(
            mistral_transcription_base_url,
            "mistral_transcription_base_url"
        );
        add!(mistral_transcription_model, "mistral_transcription_model");
        add!(
            mistral_transcription_max_bytes,
            "mistral_transcription_max_bytes"
        );
        add!(
            mistral_transcription_chunk_max_seconds,
            "mistral_transcription_chunk_max_seconds"
        );
        add!(
            mistral_transcription_chunk_overlap_seconds,
            "mistral_transcription_chunk_overlap_seconds"
        );
        add!(
            mistral_transcription_max_chunks,
            "mistral_transcription_max_chunks"
        );
        add!(
            mistral_transcription_request_timeout_sec,
            "mistral_transcription_request_timeout_sec"
        );
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
            active_profiles: obj
                .get("active_profiles")
                .and_then(|value| serde_json::from_value(value.clone()).ok())
                .unwrap_or_default(),
            profiles: obj
                .get("profiles")
                .and_then(|value| serde_json::from_value(value.clone()).ok())
                .unwrap_or_default(),
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
            mistral_transcription_base_url: get_str(obj, "mistral_transcription_base_url"),
            mistral_transcription_model: get_str(obj, "mistral_transcription_model"),
            mistral_transcription_max_bytes: obj
                .get("mistral_transcription_max_bytes")
                .and_then(|value| value.as_i64()),
            mistral_transcription_chunk_max_seconds: obj
                .get("mistral_transcription_chunk_max_seconds")
                .and_then(|value| value.as_i64()),
            mistral_transcription_chunk_overlap_seconds: obj
                .get("mistral_transcription_chunk_overlap_seconds")
                .and_then(|value| value.as_f64()),
            mistral_transcription_max_chunks: obj
                .get("mistral_transcription_max_chunks")
                .and_then(|value| value.as_i64()),
            mistral_transcription_request_timeout_sec: obj
                .get("mistral_transcription_request_timeout_sec")
                .and_then(|value| value.as_i64()),
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
        assert_eq!(
            normalize_reasoning_effort(Some("XHIGH")),
            Ok(Some("xhigh".into()))
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
            obsidian_export_subdir: Some("Research/Cestus".into()),
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
            Some("Research/Cestus".into())
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
    fn test_provider_profiles_round_trip() {
        let mut profiles = BTreeMap::new();
        let mut llm_pool = BTreeMap::new();
        llm_pool.insert(
            "azure-foundry".to_string(),
            ProviderProfile {
                name: Some("Azure Foundry GPT".into()),
                provider: "openai".into(),
                adapter: "openai-compatible".into(),
                model: "azure-foundry/gpt-5.5".into(),
                base_url: Some("https://example.test/openai/v1".into()),
                auth_ref: Some("openai".into()),
                options: BTreeMap::new(),
            },
        );
        let mut embedding_pool = BTreeMap::new();
        embedding_pool.insert(
            "mistral-embed".to_string(),
            ProviderProfile {
                name: Some("Mistral embeddings".into()),
                provider: "mistral".into(),
                adapter: "embedding".into(),
                model: "mistral-embed".into(),
                base_url: Some(MISTRAL_EMBEDDING_BASE_URL.into()),
                auth_ref: Some("mistral".into()),
                options: BTreeMap::new(),
            },
        );
        let mut stt_options = BTreeMap::new();
        stt_options.insert("chunk_max_seconds".to_string(), Value::from(600));
        let mut stt_pool = BTreeMap::new();
        stt_pool.insert(
            "mistral-voxtral".to_string(),
            ProviderProfile {
                name: Some("Mistral Voxtral STT".into()),
                provider: "mistral".into(),
                adapter: "speech-to-text".into(),
                model: "voxtral-mini-latest".into(),
                base_url: Some(MISTRAL_TRANSCRIPTION_BASE_URL.into()),
                auth_ref: Some("mistral".into()),
                options: stt_options,
            },
        );
        profiles.insert("llm".to_string(), llm_pool);
        profiles.insert("embedding".to_string(), embedding_pool);
        profiles.insert("stt".to_string(), stt_pool);

        let settings = PersistentSettings {
            active_profiles: BTreeMap::from([
                ("llm".to_string(), "azure-foundry".to_string()),
                ("embedding".to_string(), "mistral-embed".to_string()),
                ("stt".to_string(), "mistral-voxtral".to_string()),
            ]),
            profiles,
            ..Default::default()
        };
        let json_val = serde_json::to_value(settings.normalized().unwrap().to_json()).unwrap();
        let loaded = PersistentSettings::from_json(&json_val).unwrap();

        assert_eq!(
            loaded.active_profiles.get("llm"),
            Some(&"azure-foundry".to_string())
        );
        assert_eq!(
            loaded.active_profiles.get("embedding"),
            Some(&"mistral-embed".to_string())
        );
        assert_eq!(
            loaded.active_profiles.get("stt"),
            Some(&"mistral-voxtral".to_string())
        );
        assert_eq!(
            loaded.profiles["llm"]["azure-foundry"].model,
            "azure-foundry/gpt-5.5"
        );
        assert_eq!(
            loaded.profiles["embedding"]["mistral-embed"].model,
            "mistral-embed"
        );
        assert_eq!(
            loaded.profiles["stt"]["mistral-voxtral"]
                .options
                .get("chunk_max_seconds"),
            Some(&Value::from(600))
        );
    }

    #[test]
    fn test_legacy_settings_migrate_to_provider_profiles() {
        let settings = PersistentSettings {
            default_model_openai: Some("azure-foundry/gpt-5.5".into()),
            embeddings_provider: Some("mistral".into()),
            mistral_transcription_model: Some("voxtral-mini-latest".into()),
            mistral_transcription_chunk_max_seconds: Some(600),
            ..Default::default()
        };
        let normalized = settings.normalized().unwrap();

        assert_eq!(
            normalized.active_profiles.get("llm"),
            Some(&"openai-default".to_string())
        );
        assert_eq!(
            normalized.active_profiles.get("embedding"),
            Some(&"mistral-default".to_string())
        );
        assert_eq!(
            normalized.active_profiles.get("stt"),
            Some(&"mistral-voxtral".to_string())
        );
        assert_eq!(
            normalized.profiles["llm"]["openai-default"].model,
            "azure-foundry/gpt-5.5"
        );
        assert_eq!(
            normalized.profiles["embedding"]["mistral-default"].model,
            "mistral-embed"
        );
        assert_eq!(
            normalized.profiles["stt"]["mistral-voxtral"]
                .options
                .get("chunk_max_seconds"),
            Some(&Value::from(600))
        );
    }

    #[test]
    fn test_legacy_profile_migration_refreshes_changed_defaults() {
        let mut llm_pool = BTreeMap::new();
        llm_pool.insert(
            "openai-default".to_string(),
            ProviderProfile {
                name: Some("openai default".into()),
                provider: "openai".into(),
                model: "old-model".into(),
                auth_ref: Some("openai".into()),
                ..Default::default()
            },
        );
        let settings = PersistentSettings {
            active_profiles: BTreeMap::from([("llm".to_string(), "openai-default".to_string())]),
            profiles: BTreeMap::from([("llm".to_string(), llm_pool)]),
            default_model_openai: Some("azure-foundry/gpt-5.5".into()),
            ..Default::default()
        };

        let normalized = settings.normalized().unwrap();

        assert_eq!(
            normalized.profiles["llm"]["openai-default"].model,
            "azure-foundry/gpt-5.5"
        );
        assert_eq!(
            normalized.active_profiles.get("llm"),
            Some(&"openai-default".to_string())
        );
    }

    #[test]
    fn test_option_only_stt_settings_migrate_to_profile() {
        let settings = PersistentSettings {
            mistral_transcription_max_chunks: Some(12),
            mistral_transcription_request_timeout_sec: Some(240),
            ..Default::default()
        };
        let normalized = settings.normalized().unwrap();

        assert_eq!(
            normalized.active_profiles.get("stt"),
            Some(&"mistral-voxtral".to_string())
        );
        let profile = &normalized.profiles["stt"]["mistral-voxtral"];
        assert_eq!(profile.model, "voxtral-mini-latest");
        assert_eq!(profile.options.get("max_chunks"), Some(&Value::from(12)));
        assert_eq!(
            profile.options.get("request_timeout_sec"),
            Some(&Value::from(240))
        );
    }

    #[test]
    fn test_profile_id_collisions_get_unique_ids() {
        let mut llm_pool = BTreeMap::new();
        llm_pool.insert(
            "OpenAI GPT 4".to_string(),
            ProviderProfile {
                provider: "openai".into(),
                model: "gpt-4o".into(),
                ..Default::default()
            },
        );
        llm_pool.insert(
            "OpenAI_GPT_4".to_string(),
            ProviderProfile {
                provider: "openai".into(),
                model: "gpt-4.1-mini".into(),
                ..Default::default()
            },
        );
        let settings = PersistentSettings {
            active_profiles: BTreeMap::from([("llm".to_string(), "OpenAI_GPT_4".to_string())]),
            profiles: BTreeMap::from([("llm".to_string(), llm_pool)]),
            ..Default::default()
        };
        let normalized = settings.normalized().unwrap();

        assert!(normalized.profiles["llm"].contains_key("openai-gpt-4"));
        assert!(normalized.profiles["llm"].contains_key("openai-gpt-4-2"));
        assert_eq!(
            normalized.active_profiles.get("llm"),
            Some(&"openai-gpt-4-2".to_string())
        );
        assert_eq!(
            normalized.profiles["llm"]["openai-gpt-4-2"].model,
            "gpt-4.1-mini"
        );
    }

    #[test]
    fn test_invalid_llm_profile_provider_is_inferred_from_model() {
        let profile = ProviderProfile {
            provider: "not-a-provider".into(),
            model: "azure-foundry/gpt-5.5".into(),
            ..Default::default()
        }
        .normalized("llm");

        assert_eq!(profile.provider, "openai");
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
            Some("azure-foundry/gpt-5.5".into())
        );
    }
}
