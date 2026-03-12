use std::path::PathBuf;

use crate::state::AppState;
use op_core::events::{
    InitStatusView, MigrationInitRequest, MigrationInitResultView, MigrationSourceInspection,
    StandardInitReportView,
};
use op_core::workspace_init;
use tauri::{AppHandle, Emitter, State};

async fn current_workspace_config(state: &State<'_, AppState>) -> op_core::config::AgentConfig {
    state.config.lock().await.clone()
}

async fn ensure_idle(state: &State<'_, AppState>) -> Result<(), String> {
    if *state.agent_running.lock().await {
        return Err("Cannot run init while the agent is active".to_string());
    }
    Ok(())
}

#[tauri::command]
pub async fn get_init_status(state: State<'_, AppState>) -> Result<InitStatusView, String> {
    let cfg = current_workspace_config(&state).await;
    workspace_init::get_init_status(&cfg.workspace, &cfg.session_root_dir)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn run_standard_init(
    state: State<'_, AppState>,
) -> Result<StandardInitReportView, String> {
    ensure_idle(&state).await?;
    let _guard = state.init_lock.lock().await;
    let cfg = current_workspace_config(&state).await;
    tokio::task::spawn_blocking(move || {
        workspace_init::run_standard_init(&cfg.workspace, &cfg.session_root_dir, true)
    })
    .await
    .map_err(|e| e.to_string())?
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn complete_first_run_gate(state: State<'_, AppState>) -> Result<InitStatusView, String> {
    ensure_idle(&state).await?;
    let _guard = state.init_lock.lock().await;
    let cfg = current_workspace_config(&state).await;
    tokio::task::spawn_blocking(move || {
        workspace_init::complete_first_run_gate(&cfg.workspace, &cfg.session_root_dir)
    })
    .await
    .map_err(|e| e.to_string())?
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn inspect_migration_source(path: String) -> Result<MigrationSourceInspection, String> {
    let path = PathBuf::from(path);
    tokio::task::spawn_blocking(move || workspace_init::inspect_migration_source(&path))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn run_migration_init(
    request: MigrationInitRequest,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<MigrationInitResultView, String> {
    ensure_idle(&state).await?;
    let _guard = state.init_lock.lock().await;
    let cfg = current_workspace_config(&state).await;
    tokio::task::spawn_blocking(move || {
        workspace_init::run_migration_init(&request, &cfg, |event| {
            let _ = app.emit("init:migration-progress", event);
        })
    })
    .await
    .map_err(|e| e.to_string())?
    .map_err(|e| e.to_string())
}
