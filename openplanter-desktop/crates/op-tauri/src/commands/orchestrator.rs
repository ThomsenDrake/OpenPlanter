use crate::bridge::TauriOrchestratorEmitter;
use crate::state::AppState;
use op_core::events::OrchestratorSnapshotEvent;
use op_core::orchestrator::{OrchestratorConfig, OrchestratorRuntime};
use op_core::workflow_spec::WorkflowSpec;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tauri::{AppHandle, State};

fn resolve_workflow_path(
    configured_workspace: &Path,
    workflow_path: Option<String>,
) -> Result<PathBuf, String> {
    if let Some(value) = workflow_path.map(|value| value.trim().to_string()) {
        if value.is_empty() {
            return Err("workflow path cannot be empty".to_string());
        }
        let candidate = PathBuf::from(&value);
        return Ok(if candidate.is_absolute() {
            candidate
        } else {
            configured_workspace.join(candidate)
        });
    }

    let candidates = [
        configured_workspace
            .join(".openplanter")
            .join("WORKFLOW.md"),
        configured_workspace.join("WORKFLOW.md"),
    ];

    candidates
        .into_iter()
        .find(|candidate| candidate.is_file())
        .ok_or_else(|| {
            format!(
                "no workflow spec found in {} or {}",
                configured_workspace
                    .join(".openplanter")
                    .join("WORKFLOW.md")
                    .display(),
                configured_workspace.join("WORKFLOW.md").display()
            )
        })
}

#[tauri::command]
pub async fn orchestrator_start(
    app: AppHandle,
    workflow_path: Option<String>,
    state: State<'_, AppState>,
) -> Result<OrchestratorSnapshotEvent, String> {
    let workspace = state.config.lock().await.workspace.clone();
    let workflow_path = resolve_workflow_path(&workspace, workflow_path)?;
    let mut slot = state.orchestrator.lock().await;
    let initial_spec = WorkflowSpec::load_from_path_async(&workflow_path)
        .await
        .map_err(|err| err.to_string())?;

    let existing = slot.take();
    if let Some(existing) = existing {
        let _ = existing.stop().await;
    }

    let emitter = Arc::new(TauriOrchestratorEmitter::new(app));
    let runtime = OrchestratorRuntime::start_with_spec(
        OrchestratorConfig::new(workflow_path),
        initial_spec,
        emitter,
    );
    let snapshot = runtime.snapshot().await;
    *slot = Some(runtime);

    Ok(snapshot)
}

#[tauri::command]
pub async fn orchestrator_stop(
    state: State<'_, AppState>,
) -> Result<OrchestratorSnapshotEvent, String> {
    let runtime = {
        let mut slot = state.orchestrator.lock().await;
        slot.take()
    };

    match runtime {
        Some(runtime) => Ok(runtime.stop().await),
        None => Err("orchestrator is not running".to_string()),
    }
}

#[tauri::command]
pub async fn orchestrator_snapshot(
    state: State<'_, AppState>,
) -> Result<OrchestratorSnapshotEvent, String> {
    let snapshot_handle = {
        let slot = state.orchestrator.lock().await;
        match slot.as_ref() {
            Some(runtime) => runtime.snapshot_handle(),
            None => return Err("orchestrator is not running".to_string()),
        }
    };
    Ok(snapshot_handle.lock().await.clone())
}
