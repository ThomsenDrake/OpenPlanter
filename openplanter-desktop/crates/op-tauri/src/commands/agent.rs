use std::collections::HashSet;
use std::path::Path;
use std::sync::Arc;

use tauri::{AppHandle, Emitter, State};
use tokio_util::sync::CancellationToken;

use crate::bridge::{LoggingEmitter, TauriEmitter};
use crate::commands::session::sessions_dir;
use crate::state::AppState;
use op_core::engine::context::{
    TurnSummary, append_turn_summary, load_or_migrate_investigation_state, turn_history_from_state,
};
use op_core::engine::investigation_state::{
    build_question_reasoning_packet, has_reasoning_content,
};
use op_core::engine::{SolveEmitter, SolveInitialContext};
use op_core::session::replay::{ReplayEntry, ReplayLogger};
use op_core::workspace_init;

const FOLLOW_UP_TOKEN_CUES: &[&str] = &[
    "it", "this", "that", "these", "those", "also", "why", "how", "continue", "clarify", "expand",
];
const FOLLOW_UP_PHRASE_CUES: &[&str] = &["what about", "follow up", "tell me more"];
const TOKEN_OVERLAP_THRESHOLD: f64 = 0.20;
const STOPWORDS: &[&str] = &[
    "a", "an", "and", "are", "but", "does", "for", "from", "had", "has", "have", "into", "its",
    "not", "our", "the", "their", "them", "then", "there", "they", "was", "were", "what", "when",
    "where", "which", "with", "would",
];

fn normalize_words(text: &str) -> Vec<String> {
    text.to_lowercase()
        .split(|ch: char| !ch.is_alphanumeric())
        .filter(|token| !token.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn normalized_tokens(text: &str) -> HashSet<String> {
    normalize_words(text)
        .into_iter()
        .filter(|token| token.len() >= 3 && !STOPWORDS.contains(&token.as_str()))
        .collect()
}

fn has_follow_up_cue(objective: &str) -> bool {
    let normalized = normalize_words(objective).join(" ");
    let token_set = normalize_words(objective)
        .into_iter()
        .collect::<HashSet<_>>();
    FOLLOW_UP_TOKEN_CUES
        .iter()
        .any(|cue| token_set.contains(*cue))
        || FOLLOW_UP_PHRASE_CUES
            .iter()
            .any(|cue| normalized.contains(cue))
}

fn token_overlap_ratio(objective: &str, turn_history: &[TurnSummary]) -> f64 {
    let current_tokens = normalized_tokens(objective);
    if current_tokens.is_empty() || turn_history.is_empty() {
        return 0.0;
    }

    let recent_tokens = turn_history
        .iter()
        .rev()
        .take(2)
        .flat_map(|entry| {
            normalized_tokens(&entry.objective)
                .into_iter()
                .chain(normalized_tokens(&entry.result_preview))
        })
        .collect::<HashSet<_>>();
    if recent_tokens.is_empty() {
        return 0.0;
    }

    let shared = current_tokens.intersection(&recent_tokens).count();
    shared as f64 / current_tokens.len() as f64
}

fn bounded_turn_history(
    turn_history: &[TurnSummary],
    max_turn_summaries: usize,
) -> Vec<TurnSummary> {
    let keep = std::cmp::min(6, max_turn_summaries.max(1));
    turn_history
        .iter()
        .rev()
        .take(keep)
        .cloned()
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect()
}

fn resolve_continuity(
    objective: &str,
    configured_mode: &str,
    turn_history: &[TurnSummary],
    max_turn_summaries: usize,
) -> (Option<Vec<TurnSummary>>, Option<String>, Option<String>) {
    match configured_mode {
        "fresh" => (None, None, None),
        "continue" => (
            Some(bounded_turn_history(turn_history, max_turn_summaries)),
            Some("continue".to_string()),
            Some("explicit_continue".to_string()),
        ),
        _ => {
            if turn_history.is_empty() {
                return (None, None, None);
            }
            if has_follow_up_cue(objective) {
                return (
                    Some(bounded_turn_history(turn_history, max_turn_summaries)),
                    Some("continue".to_string()),
                    Some("follow_up_cue".to_string()),
                );
            }
            let overlap = token_overlap_ratio(objective, turn_history);
            if overlap >= TOKEN_OVERLAP_THRESHOLD {
                (
                    Some(bounded_turn_history(turn_history, max_turn_summaries)),
                    Some("continue".to_string()),
                    Some(format!("token_overlap:{overlap:.2}")),
                )
            } else {
                (None, None, None)
            }
        }
    }
}

async fn build_solve_initial_context(
    session_dir: &Path,
    session_id: &str,
    objective: &str,
    configured_mode: &str,
    max_turn_summaries: usize,
) -> (SolveInitialContext, Option<String>) {
    let mut initial_context = SolveInitialContext {
        session_id: Some(session_id.to_string()),
        session_dir: Some(session_dir.display().to_string()),
        turn_history: None,
        continuity_mode: None,
        continuity_reason: None,
        question_reasoning_packet: None,
    };

    match load_or_migrate_investigation_state(session_dir).await {
        Ok(state) => {
            let turn_history = turn_history_from_state(&state);
            let (bounded_history, continuity_mode, continuity_reason) = resolve_continuity(
                objective,
                configured_mode,
                &turn_history,
                max_turn_summaries,
            );
            initial_context.turn_history = bounded_history;
            initial_context.continuity_mode = continuity_mode;
            initial_context.continuity_reason = continuity_reason;
            let packet = build_question_reasoning_packet(&state, 8, 6);
            if has_reasoning_content(&packet) {
                initial_context.question_reasoning_packet = Some(packet);
            }
            (initial_context, None)
        }
        Err(err) => (
            initial_context,
            Some(format!(
                "[solve] failed to load investigation state for continuity and reasoning packet; continuing without session memory: {err}"
            )),
        ),
    }
}

/// Start solving an objective. Result streamed via events.
#[tauri::command]
pub async fn solve(
    objective: String,
    session_id: String,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let cfg = state.config.lock().await.clone();
    let chrome_mcp = state.chrome_mcp_manager(&cfg).await;
    let init_status = workspace_init::get_init_status(&cfg.workspace, &cfg.session_root_dir)
        .map_err(|e| e.to_string())?;
    if init_status.gate_state != "ready" {
        return Err("Workspace initialization is not complete. Run /init first.".to_string());
    }

    {
        let mut running = state.agent_running.lock().await;
        if *running {
            return Err("An agent task is already running.".to_string());
        }
        *running = true;
    }

    // Create a fresh cancellation token for this solve run
    let token = CancellationToken::new();
    {
        let mut current = state.cancel_token.lock().await;
        *current = token.clone();
    }
    let error_handle = app.clone();
    let running_flag = state.agent_running.clone();

    // Set up replay logging for this session
    let session_dir = sessions_dir(&state).await.join(&session_id);
    let mut replay = ReplayLogger::new(&session_dir);
    let replay_seq_start = ReplayLogger::max_seq(&session_dir).await.unwrap_or(0) + 1;

    // Log the user message
    let user_entry = ReplayEntry {
        seq: 0,
        timestamp: String::new(),
        role: "user".into(),
        content: objective.clone(),
        tool_name: None,
        is_rendered: None,
        step_number: None,
        step_tokens_in: None,
        step_tokens_out: None,
        step_elapsed: None,
        step_model_preview: None,
        step_tool_calls: None,
    };
    if let Err(e) = replay.append(user_entry).await {
        eprintln!("[agent] failed to log user message: {e}");
    }

    // Update metadata: increment turn_count, set last_objective
    if let Err(e) =
        crate::commands::session::update_session_metadata(&session_dir, &objective).await
    {
        eprintln!("[agent] failed to update metadata: {e}");
    }

    let emitter = Arc::new(LoggingEmitter::new(TauriEmitter::new(app), replay));
    let cwd = std::env::current_dir()
        .map(|dir| dir.display().to_string())
        .unwrap_or_else(|_| "<unavailable>".to_string());
    emitter.emit_trace(&format!(
        "[solve] pid={} cwd={} workspace={} session={}",
        std::process::id(),
        cwd,
        cfg.workspace.display(),
        session_id
    ));
    emitter.emit_trace(&format!("[startup:info] {}", state.startup_trace()));
    let (initial_context, initial_context_warning) = build_solve_initial_context(
        &session_dir,
        &session_id,
        &objective,
        &cfg.continuity_mode,
        cfg.max_turn_summaries.max(1) as usize,
    )
    .await;
    if let Some(warning) = initial_context_warning.as_deref() {
        emitter.emit_trace(warning);
    }

    tokio::spawn(async move {
        let emitter_for_inner = emitter.clone();
        let cfg_for_inner = cfg.clone();
        let objective_for_inner = objective.clone();
        let initial_context_for_inner = initial_context.clone();
        let chrome_mcp_for_inner = chrome_mcp.clone();
        let token_for_inner = token.clone();
        let result = tokio::spawn(async move {
            op_core::engine::solve_with_initial_context_and_chrome_mcp(
                &objective_for_inner,
                &cfg_for_inner,
                emitter_for_inner.as_ref(),
                token_for_inner,
                Some(initial_context_for_inner),
                chrome_mcp_for_inner,
            )
            .await;
        })
        .await;

        if result.is_ok() {
            if let Some(completion) = emitter.take_completion() {
                if let Err(err) = append_turn_summary(
                    &session_dir,
                    &objective,
                    &completion.result,
                    completion
                        .loop_metrics
                        .as_ref()
                        .map(|metrics| metrics.steps)
                        .unwrap_or(0),
                    replay_seq_start,
                    cfg.max_turn_summaries.max(1) as usize,
                )
                .await
                {
                    emitter.emit_trace(&format!(
                        "[solve] failed to persist turn summary; continuing without continuity update: {err}"
                    ));
                }
            }
        }

        {
            let mut running = running_flag.lock().await;
            *running = false;
        }

        // If the inner task panicked, emit an error so the frontend
        // doesn't get stuck in "running" state forever.
        if let Err(e) = result {
            let msg = format!("Internal error: {e}");
            eprintln!("[bridge] panic: {msg}");
            let _ = error_handle.emit("agent:error", op_core::events::ErrorEvent { message: msg });
        }
    });

    Ok(())
}

/// Cancel a running solve.
#[tauri::command]
pub async fn cancel(state: State<'_, AppState>) -> Result<(), String> {
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

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;
    use tokio::fs;

    #[tokio::test]
    async fn test_build_solve_initial_context_includes_packet_when_state_has_reasoning() {
        let tmp = tempdir().unwrap();
        fs::write(
            tmp.path().join("investigation_state.json"),
            r#"{
                "schema_version":"1.0.0",
                "session_id":"sid",
                "questions":{"q_1":{"id":"q_1","question_text":"Open question","status":"open","priority":"high","claim_ids":["cl_1"]}},
                "claims":{"cl_1":{"id":"cl_1","claim_text":"Needs support","status":"unresolved","evidence_ids":["ev_1"]}},
                "evidence":{"ev_1":{"id":"ev_1","evidence_type":"web_fetch","source_uri":"https://example.test","provenance_ids":["pv_1"]}}
            }"#,
        )
        .await
        .unwrap();

        let (context, warning) =
            build_solve_initial_context(tmp.path(), "sid", "Investigate this", "auto", 50).await;
        assert!(warning.is_none());
        let packet = context
            .question_reasoning_packet
            .expect("packet should be present");
        assert_eq!(packet["focus_question_ids"], serde_json::json!(["q_1"]));
        assert_eq!(
            packet["candidate_actions"][0]["id"],
            serde_json::json!("ca_q_q_1")
        );
        assert_eq!(context.session_id, Some("sid".to_string()));
        assert_eq!(context.session_dir, Some(tmp.path().display().to_string()));
    }

    #[tokio::test]
    async fn test_build_solve_initial_context_ignores_invalid_typed_state_without_warning() {
        let tmp = tempdir().unwrap();
        fs::write(tmp.path().join("investigation_state.json"), "{not-json")
            .await
            .unwrap();

        let (context, warning) =
            build_solve_initial_context(tmp.path(), "sid", "Investigate this", "auto", 50).await;
        assert!(warning.is_none());
        assert!(context.question_reasoning_packet.is_none());
        assert_eq!(context.session_id, Some("sid".to_string()));
        assert_eq!(context.session_dir, Some(tmp.path().display().to_string()));
    }

    #[tokio::test]
    async fn test_build_solve_initial_context_continues_on_follow_up_cue() {
        let tmp = tempdir().unwrap();
        fs::write(
            tmp.path().join("investigation_state.json"),
            r#"{
                "schema_version":"1.0.0",
                "session_id":"sid",
                "legacy":{"turn_history":[{"turn_number":1,"objective":"Investigate Acme donor network","result_preview":"Found linked shell companies","timestamp":"2026-01-01T00:00:00Z","steps_used":3,"replay_seq_start":1}]}
            }"#,
        )
        .await
        .unwrap();

        let (context, warning) =
            build_solve_initial_context(tmp.path(), "sid", "Why does that matter?", "auto", 50)
                .await;
        assert!(warning.is_none());
        assert_eq!(context.continuity_mode.as_deref(), Some("continue"));
        assert_eq!(context.continuity_reason.as_deref(), Some("follow_up_cue"));
        assert_eq!(context.turn_history.as_ref().map(Vec::len), Some(1));
    }

    #[tokio::test]
    async fn test_build_solve_initial_context_continues_on_token_overlap() {
        let tmp = tempdir().unwrap();
        fs::write(
            tmp.path().join("investigation_state.json"),
            r#"{
                "schema_version":"1.0.0",
                "session_id":"sid",
                "legacy":{"turn_history":[{"turn_number":1,"objective":"Investigate donor network shell companies","result_preview":"Matched donor network address records","timestamp":"2026-01-01T00:00:00Z","steps_used":3,"replay_seq_start":1}]}
            }"#,
        )
        .await
        .unwrap();

        let (context, warning) = build_solve_initial_context(
            tmp.path(),
            "sid",
            "Compare donor network addresses",
            "auto",
            50,
        )
        .await;
        assert!(warning.is_none());
        assert_eq!(context.continuity_mode.as_deref(), Some("continue"));
        assert!(
            context
                .continuity_reason
                .as_deref()
                .is_some_and(|value| value.starts_with("token_overlap:"))
        );
    }

    #[tokio::test]
    async fn test_build_solve_initial_context_keeps_unrelated_turns_fresh() {
        let tmp = tempdir().unwrap();
        fs::write(
            tmp.path().join("investigation_state.json"),
            r#"{
                "schema_version":"1.0.0",
                "session_id":"sid",
                "legacy":{"turn_history":[{"turn_number":1,"objective":"Investigate donor network shell companies","result_preview":"Matched donor network address records","timestamp":"2026-01-01T00:00:00Z","steps_used":3,"replay_seq_start":1}]}
            }"#,
        )
        .await
        .unwrap();

        let (context, warning) = build_solve_initial_context(
            tmp.path(),
            "sid",
            "Summarize zoning permits in Boston",
            "auto",
            50,
        )
        .await;
        assert!(warning.is_none());
        assert!(context.turn_history.is_none());
        assert!(context.continuity_mode.is_none());
        assert!(context.continuity_reason.is_none());
    }
}
