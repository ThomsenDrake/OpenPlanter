use tauri::{AppHandle, Emitter, State};
use tokio_util::sync::CancellationToken;

use crate::bridge::TauriEmitter;
use crate::state::AppState;

/// Start solving an objective. Result streamed via events.
#[tauri::command]
pub async fn solve(
    objective: String,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<(), String> {
    // Create a fresh cancellation token for this solve run
    let token = CancellationToken::new();
    {
        let mut current = state.cancel_token.lock().await;
        *current = token.clone();
    }

    let cfg = state.config.lock().await.clone();
    let emitter = TauriEmitter::new(app.clone());
    let error_handle = app;

    tokio::spawn(async move {
        let result = tokio::spawn(async move {
            op_core::engine::solve(&objective, &cfg, &emitter, token).await;
        })
        .await;

        // If the inner task panicked, emit an error so the frontend
        // doesn't get stuck in "running" state forever.
        if let Err(e) = result {
            let msg = format!("Internal error: {e}");
            eprintln!("[bridge] panic: {msg}");
            let _ = error_handle.emit(
                "agent:error",
                op_core::events::ErrorEvent {
                    message: msg,
                },
            );
        }
    });

    Ok(())
}

/// Cancel a running solve.
#[tauri::command]
pub async fn cancel(
    state: State<'_, AppState>,
) -> Result<(), String> {
    let token = state.cancel_token.lock().await;
    token.cancel();
    Ok(())
}

/// Debug logging from frontend (temporary).
#[tauri::command]
pub async fn debug_log(msg: String) -> Result<(), String> {
    eprintln!("[frontend] {msg}");
    Ok(())
}
