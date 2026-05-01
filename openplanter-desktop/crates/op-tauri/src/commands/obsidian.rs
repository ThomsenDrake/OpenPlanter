use crate::state::AppState;
use op_core::config::AgentConfig;
use op_core::engine::context::load_or_migrate_investigation_state;
use op_core::obsidian::{
    DEFAULT_OBSIDIAN_EXPORT_SUBDIR, ObsidianExportConfig, ObsidianExportResult,
    ObsidianExportStatus, export_investigation_pack, export_status, normalize_obsidian_export_mode,
    normalize_obsidian_export_subdir, obsidian_open_uri_for_path,
};
use op_core::settings::{PersistentSettings, SettingsStore};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, State};
use tauri_plugin_shell::ShellExt;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ConfigureObsidianExportRequest {
    pub enabled: Option<bool>,
    pub root: Option<String>,
    pub mode: Option<String>,
    pub subdir: Option<String>,
    pub generate_canvas: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenObsidianInvestigationResult {
    pub opened: bool,
    pub uri: String,
    pub export: ObsidianExportResult,
}

pub(crate) fn config_from_agent(cfg: &AgentConfig) -> ObsidianExportConfig {
    ObsidianExportConfig {
        enabled: cfg.obsidian_export_enabled,
        root: cfg.obsidian_export_root.clone(),
        mode: cfg.obsidian_export_mode.clone(),
        subdir: cfg.obsidian_export_subdir.clone(),
        generate_canvas: cfg.obsidian_generate_canvas,
    }
}

fn settings_from_config(config: &ObsidianExportConfig) -> PersistentSettings {
    PersistentSettings {
        obsidian_export_enabled: Some(config.enabled),
        obsidian_export_root: config.root.as_ref().map(|path| path.display().to_string()),
        obsidian_export_mode: Some(normalize_obsidian_export_mode(Some(&config.mode))),
        obsidian_export_subdir: Some(normalize_obsidian_export_subdir(Some(&config.subdir))),
        obsidian_generate_canvas: Some(config.generate_canvas),
        ..PersistentSettings::default()
    }
}

fn apply_request_to_config(
    mut config: ObsidianExportConfig,
    request: &ConfigureObsidianExportRequest,
) -> ObsidianExportConfig {
    if let Some(enabled) = request.enabled {
        config.enabled = enabled;
    }
    if let Some(root) = request.root.as_deref() {
        config.root = if root.trim().is_empty() {
            None
        } else {
            Some(PathBuf::from(root.trim()))
        };
    }
    if let Some(mode) = request.mode.as_deref() {
        config.mode = normalize_obsidian_export_mode(Some(mode));
    }
    if let Some(subdir) = request.subdir.as_deref() {
        let normalized = normalize_obsidian_export_subdir(Some(subdir));
        config.subdir = if normalized.is_empty() {
            DEFAULT_OBSIDIAN_EXPORT_SUBDIR.to_string()
        } else {
            normalized
        };
    }
    if let Some(generate_canvas) = request.generate_canvas {
        config.generate_canvas = generate_canvas;
    }
    config
}

fn apply_export_config_to_agent(cfg: &mut AgentConfig, config: &ObsidianExportConfig) {
    cfg.obsidian_export_enabled = config.enabled;
    cfg.obsidian_export_root = config.root.clone();
    cfg.obsidian_export_mode = normalize_obsidian_export_mode(Some(&config.mode));
    cfg.obsidian_export_subdir = normalize_obsidian_export_subdir(Some(&config.subdir));
    cfg.obsidian_generate_canvas = config.generate_canvas;
}

fn metadata_investigation_id(session_dir: &Path) -> Option<String> {
    let content = std::fs::read_to_string(session_dir.join("metadata.json")).ok()?;
    let value = serde_json::from_str::<Value>(&content).ok()?;
    value
        .get("investigation_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

pub(crate) async fn export_session_dir_with_config(
    workspace: &Path,
    session_dir: &Path,
    config: &ObsidianExportConfig,
) -> Result<ObsidianExportResult, String> {
    let mut state = load_or_migrate_investigation_state(session_dir)
        .await
        .map_err(|error| format!("Failed to load investigation state: {error}"))?;
    if state.active_investigation_id.is_none() {
        state.active_investigation_id = metadata_investigation_id(session_dir);
    }
    export_investigation_pack(workspace, session_dir, &state, config)
        .map_err(|error| error.to_string())
}

async fn resolve_session_dir(
    explicit_session_id: Option<String>,
    state: &State<'_, AppState>,
) -> Result<(String, PathBuf, AgentConfig), String> {
    let cfg = state.config.lock().await.clone();
    let session_id = match explicit_session_id {
        Some(id) if !id.trim().is_empty() => id,
        _ => state
            .session_id
            .lock()
            .await
            .clone()
            .ok_or_else(|| "No active session selected".to_string())?,
    };
    if session_id.contains(['/', '\\', '\0']) {
        return Err("Invalid session id".to_string());
    }
    let session_dir = cfg
        .workspace
        .join(&cfg.session_root_dir)
        .join("sessions")
        .join(&session_id);
    if !session_dir.join("metadata.json").exists()
        && !session_dir.join("investigation_state.json").exists()
    {
        return Err(format!("Session not found: {session_id}"));
    }
    Ok((session_id, session_dir, cfg))
}

#[tauri::command]
pub async fn get_obsidian_export_status(
    state: State<'_, AppState>,
) -> Result<ObsidianExportStatus, String> {
    let cfg = state.config.lock().await.clone();
    Ok(export_status(&cfg.workspace, &config_from_agent(&cfg)))
}

#[tauri::command]
pub async fn configure_obsidian_export(
    request: ConfigureObsidianExportRequest,
    state: State<'_, AppState>,
) -> Result<ObsidianExportStatus, String> {
    let mut cfg = state.config.lock().await;
    let config = apply_request_to_config(config_from_agent(&cfg), &request);
    apply_export_config_to_agent(&mut cfg, &config);

    let store = SettingsStore::new(&cfg.workspace, &cfg.session_root_dir);
    let mut merged = store.load();
    let incoming = settings_from_config(&config);
    if request.enabled.is_some() {
        merged.obsidian_export_enabled = incoming.obsidian_export_enabled;
    }
    if request.root.is_some() {
        merged.obsidian_export_root = incoming.obsidian_export_root;
    }
    if request.mode.is_some() {
        merged.obsidian_export_mode = incoming.obsidian_export_mode;
    }
    if request.subdir.is_some() {
        merged.obsidian_export_subdir = incoming.obsidian_export_subdir;
    }
    if request.generate_canvas.is_some() {
        merged.obsidian_generate_canvas = incoming.obsidian_generate_canvas;
    }
    store.save(&merged).map_err(|error| error.to_string())?;
    Ok(export_status(&cfg.workspace, &config))
}

#[tauri::command]
pub async fn export_obsidian_investigation(
    session_id: Option<String>,
    state: State<'_, AppState>,
) -> Result<ObsidianExportResult, String> {
    let (_session_id, session_dir, cfg) = resolve_session_dir(session_id, &state).await?;
    export_session_dir_with_config(&cfg.workspace, &session_dir, &config_from_agent(&cfg)).await
}

#[tauri::command]
#[allow(deprecated)]
pub async fn open_obsidian_investigation(
    session_id: Option<String>,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<OpenObsidianInvestigationResult, String> {
    let export = export_obsidian_investigation(session_id, state).await?;
    let uri = obsidian_open_uri_for_path(Path::new(&export.home_path));
    app.shell()
        .open(uri.clone(), None)
        .map_err(|error| format!("Failed to open Obsidian URI: {error}"))?;
    Ok(OpenObsidianInvestigationResult {
        opened: true,
        uri,
        export,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn obsidian_uri_encodes_absolute_path() {
        let uri = obsidian_open_uri_for_path(Path::new("/tmp/My Vault/OpenPlanter/Home.md"));
        assert_eq!(
            uri,
            "obsidian://open?path=%2Ftmp%2FMy%20Vault%2FOpenPlanter%2FHome.md"
        );
    }

    #[test]
    fn configure_request_preserves_defaults() {
        let config = apply_request_to_config(
            ObsidianExportConfig::default(),
            &ConfigureObsidianExportRequest {
                enabled: Some(true),
                root: Some("/tmp/Vault".into()),
                mode: Some("fresh-vault".into()),
                subdir: None,
                generate_canvas: Some(false),
            },
        );
        assert!(config.enabled);
        assert_eq!(config.root, Some(PathBuf::from("/tmp/Vault")));
        assert_eq!(config.mode, "fresh_vault");
        assert_eq!(config.subdir, "OpenPlanter");
        assert!(!config.generate_canvas);
    }
}
