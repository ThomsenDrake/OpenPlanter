use super::session::{
    AppendSessionEventOptions, SESSION_FORMAT, TRACE_SCHEMA_VERSION, append_session_event,
    create_session, is_safe_session_id, session_capabilities_value, session_durability_value,
    sessions_dir,
};
use crate::state::AppState;
use op_core::engine::context::{load_or_migrate_investigation_state, turn_history_from_state};
use op_core::engine::investigation_state::build_question_reasoning_packet;
use op_core::session::replay::{ReplayEntry, ReplayLogger};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::State;

const HANDOFF_FORMAT: &str = "openplanter.session_handoff.v1";
const HANDOFF_SCHEMA_VERSION: u32 = 1;
const MAX_OPEN_QUESTIONS: usize = 8;
const MAX_EVIDENCE_PER_ITEM: usize = 6;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct HandoffSeqSpan {
    pub start_seq: u64,
    pub end_seq: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SessionHandoffSource {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub turn_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub turn_index: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub turn_line: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub started_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ended_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub event_span: Option<HandoffSeqSpan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub continuity_mode: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_status: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SessionHandoffProvenance {
    #[serde(default)]
    pub source_refs: Vec<Value>,
    #[serde(default)]
    pub evidence_refs: Vec<Value>,
    #[serde(default)]
    pub ontology_refs: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SessionHandoffCompat {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub trace_schema_version: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_format: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_origin: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionHandoffPackage {
    pub schema_version: u32,
    pub package_format: String,
    pub handoff_id: String,
    pub exported_at: String,
    pub objective: String,
    #[serde(default)]
    pub open_questions: Vec<Value>,
    #[serde(default)]
    pub candidate_actions: Vec<Value>,
    #[serde(default)]
    pub evidence_index: Map<String, Value>,
    #[serde(default)]
    pub replay_span: Option<HandoffSeqSpan>,
    pub source: SessionHandoffSource,
    #[serde(default)]
    pub provenance: SessionHandoffProvenance,
    #[serde(default)]
    pub compat: SessionHandoffCompat,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportSessionHandoffResult {
    pub path: String,
    pub handoff: SessionHandoffPackage,
}

fn default_activate_session() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImportSessionHandoffRequest {
    pub package_path: String,
    #[serde(default)]
    pub target_session_id: Option<String>,
    #[serde(default = "default_activate_session")]
    pub activate_session: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImportSessionHandoffResult {
    pub path: String,
    pub session_id: String,
    pub created_session: bool,
    pub activated_session: bool,
    pub handoff: SessionHandoffPackage,
}

#[derive(Debug, Clone)]
struct IndexedJsonLine {
    line_number: u32,
    value: Value,
}

#[tauri::command]
pub async fn export_session_handoff(
    session_id: String,
    turn_id: Option<String>,
    state: State<'_, AppState>,
) -> Result<ExportSessionHandoffResult, String> {
    validate_session_id(session_id.as_str(), "Session handoff export")?;
    let session_dir = sessions_dir(&state).await.join(&session_id);
    if !session_dir.is_dir() {
        return Err(format!("Session '{session_id}' not found"));
    }

    let handoff = build_handoff_package(&session_dir, turn_id.as_deref())
        .await
        .map_err(|err| format!("Failed to build session handoff: {err}"))?;
    let output_path = handoff_output_path(&session_dir, &handoff.handoff_id);
    persist_handoff_package(&output_path, &handoff)
        .map_err(|err| format!("Failed to write session handoff: {err}"))?;

    let _ = append_session_event(
        &session_dir,
        "artifact.created",
        serde_json::json!({
            "artifact_id": handoff.handoff_id,
            "artifact_kind": "session_handoff",
            "label": output_path.file_name().and_then(|value| value.to_str()),
            "locator": {
                "path": relative_session_path(&session_dir, &output_path),
            },
        }),
        AppendSessionEventOptions {
            turn_id: handoff.source.turn_id.clone(),
            status: Some("completed".to_string()),
            actor_kind: Some("runtime".to_string()),
            ..AppendSessionEventOptions::default()
        },
    );
    let _ = append_session_event(
        &session_dir,
        "session.handoff.exported",
        serde_json::json!({
            "handoff_id": handoff.handoff_id,
            "turn_id": handoff.source.turn_id,
            "stored_path": relative_session_path(&session_dir, &output_path),
            "replay_span": handoff.replay_span,
        }),
        AppendSessionEventOptions {
            turn_id: handoff.source.turn_id.clone(),
            status: Some("completed".to_string()),
            actor_kind: Some("runtime".to_string()),
            ..AppendSessionEventOptions::default()
        },
    );

    Ok(ExportSessionHandoffResult {
        path: output_path.display().to_string(),
        handoff,
    })
}

#[tauri::command]
pub async fn import_session_handoff(
    request: ImportSessionHandoffRequest,
    state: State<'_, AppState>,
) -> Result<ImportSessionHandoffResult, String> {
    let handoff = read_handoff_package(Path::new(&request.package_path))
        .map_err(|err| format!("Failed to read session handoff: {err}"))?;

    let active_session_id = state.session_id.lock().await.clone();
    let targets_active_session = request
        .target_session_id
        .as_deref()
        .zip(active_session_id.as_deref())
        .is_some_and(|(target, active)| target == active);

    if request.activate_session || targets_active_session {
        // Hold the run gate while importing so a solve cannot start against the same
        // session between validation and activation/import writes.
        let running = state.agent_running.lock().await;
        if *running {
            if request.activate_session {
                return Err(
                    "Cannot activate an imported handoff while an agent task is running.".into(),
                );
            }
            return Err(
                "Cannot import a handoff into the active session while an agent task is running."
                    .into(),
            );
        }

        let sessions_root = sessions_dir(&state).await;
        let (session_id, session_dir, created_session) =
            resolve_import_target(&sessions_root, request.target_session_id.as_deref())?;
        let stored_path = import_handoff_into_session(
            &session_dir,
            &handoff,
            Path::new(&request.package_path),
            true,
        )
        .await
        .map_err(|err| format!("Failed to import session handoff: {err}"))?;

        if request.activate_session {
            let mut session_lock = state.session_id.lock().await;
            *session_lock = Some(session_id.clone());
        }

        drop(running);
        return Ok(ImportSessionHandoffResult {
            path: stored_path.display().to_string(),
            session_id,
            created_session,
            activated_session: request.activate_session,
            handoff,
        });
    }

    let sessions_root = sessions_dir(&state).await;
    let (session_id, session_dir, created_session) =
        resolve_import_target(&sessions_root, request.target_session_id.as_deref())?;
    let stored_path = import_handoff_into_session(
        &session_dir,
        &handoff,
        Path::new(&request.package_path),
        true,
    )
    .await
    .map_err(|err| format!("Failed to import session handoff: {err}"))?;

    Ok(ImportSessionHandoffResult {
        path: stored_path.display().to_string(),
        session_id,
        created_session,
        activated_session: request.activate_session,
        handoff,
    })
}

async fn build_handoff_package(
    session_dir: &Path,
    requested_turn_id: Option<&str>,
) -> std::io::Result<SessionHandoffPackage> {
    let session_id = session_dir_name(session_dir);
    let metadata = read_metadata_map(session_dir)?;
    let turns = read_jsonl_lines(&session_dir.join("turns.jsonl"))?;
    let selected_turn = select_turn(&turns, requested_turn_id, &metadata)
        .map_err(|err| std::io::Error::new(std::io::ErrorKind::NotFound, err))?;
    let state = load_or_migrate_investigation_state(session_dir).await?;
    let packet = build_question_reasoning_packet(&state, MAX_OPEN_QUESTIONS, MAX_EVIDENCE_PER_ITEM);
    let open_questions = packet
        .get("unresolved_questions")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let candidate_actions = packet
        .get("candidate_actions")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let evidence_index = packet
        .get("evidence_index")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let replay_entries = ReplayLogger::read_all(session_dir).await?;
    let replay_span = selected_turn
        .and_then(|turn| extract_span(turn.value.pointer("/provenance/replay_span")))
        .or_else(|| replay_span_from_replay_entries(&replay_entries));
    let source = build_source(session_id.clone(), selected_turn, &metadata);
    let provenance = build_handoff_provenance(
        session_dir,
        selected_turn,
        replay_span.as_ref(),
        &open_questions,
        &candidate_actions,
        &evidence_index,
    );
    let compat = SessionHandoffCompat {
        trace_schema_version: metadata
            .get("schema_version")
            .and_then(Value::as_u64)
            .and_then(|value| u32::try_from(value).ok()),
        session_format: string_field(&metadata, "session_format"),
        session_origin: string_field(&metadata, "session_origin"),
    };

    Ok(SessionHandoffPackage {
        schema_version: HANDOFF_SCHEMA_VERSION,
        package_format: HANDOFF_FORMAT.to_string(),
        handoff_id: new_handoff_id(
            chrono::Utc::now(),
            source
                .turn_id
                .as_deref()
                .or_else(|| requested_turn_id)
                .unwrap_or("snapshot"),
        ),
        exported_at: chrono::Utc::now().to_rfc3339(),
        objective: resolve_objective(selected_turn, &metadata, &state),
        open_questions,
        candidate_actions,
        evidence_index,
        replay_span,
        source,
        provenance,
        compat,
    })
}

async fn import_handoff_into_session(
    session_dir: &Path,
    handoff: &SessionHandoffPackage,
    source_path: &Path,
    append_replay_note: bool,
) -> Result<PathBuf, String> {
    let stored_path = handoff_output_path(session_dir, &handoff.handoff_id);
    persist_handoff_package(&stored_path, handoff)
        .map_err(|err| format!("Failed to store imported handoff: {err}"))?;
    let _ = append_session_event(
        session_dir,
        "session.handoff.imported",
        serde_json::json!({
            "handoff_id": handoff.handoff_id,
            "source_session_id": handoff.source.session_id,
            "source_turn_id": handoff.source.turn_id,
            "source_path": source_path.display().to_string(),
            "stored_path": relative_session_path(session_dir, &stored_path),
            "replay_span": handoff.replay_span,
        }),
        AppendSessionEventOptions {
            status: Some("completed".to_string()),
            actor_kind: Some("runtime".to_string()),
            ..AppendSessionEventOptions::default()
        },
    );

    if append_replay_note {
        append_import_replay_note(session_dir, handoff, &stored_path)
            .await
            .map_err(|err| format!("Failed to append import replay note: {err}"))?;
    }
    refresh_metadata_for_import(session_dir, handoff)?;

    Ok(stored_path)
}

fn resolve_import_target(
    sessions_root: &Path,
    target_session_id: Option<&str>,
) -> Result<(String, PathBuf, bool), String> {
    if let Some(session_id) = target_session_id {
        validate_session_id(session_id, "Session handoff import target")?;
        let session_dir = sessions_root.join(session_id);
        if !session_dir.is_dir() {
            return Err(format!("Target session '{session_id}' not found"));
        }
        return Ok((session_id.to_string(), session_dir, false));
    }

    let session = create_session(sessions_root).map_err(|err| err.to_string())?;
    let session_dir = sessions_root.join(&session.id);
    Ok((session.id, session_dir, true))
}

fn read_handoff_package(path: &Path) -> Result<SessionHandoffPackage, String> {
    let content = fs::read_to_string(path).map_err(|err| err.to_string())?;
    let handoff: SessionHandoffPackage =
        serde_json::from_str(&content).map_err(|err| err.to_string())?;
    validate_handoff_package(&handoff)?;
    Ok(handoff)
}

fn validate_handoff_package(handoff: &SessionHandoffPackage) -> Result<(), String> {
    if handoff.schema_version != HANDOFF_SCHEMA_VERSION {
        return Err(format!(
            "Unsupported handoff schema {}; expected {}",
            handoff.schema_version, HANDOFF_SCHEMA_VERSION
        ));
    }
    if handoff.package_format != HANDOFF_FORMAT {
        return Err(format!(
            "Unsupported handoff package format '{}'; expected '{}'",
            handoff.package_format, HANDOFF_FORMAT
        ));
    }
    if handoff.handoff_id.trim().is_empty() {
        return Err("Handoff package is missing handoff_id".to_string());
    }
    if !is_safe_handoff_id(&handoff.handoff_id) {
        return Err("Handoff package contains an unsafe handoff_id".to_string());
    }
    if handoff
        .replay_span
        .as_ref()
        .is_some_and(|span| span.start_seq == 0 || span.end_seq < span.start_seq)
    {
        return Err("Invalid replay span in handoff package".to_string());
    }
    Ok(())
}

fn persist_handoff_package(path: &Path, handoff: &SessionHandoffPackage) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut payload = serde_json::to_string_pretty(handoff).map_err(std::io::Error::other)?;
    payload.push('\n');
    fs::write(path, payload)
}

fn refresh_metadata_for_import(
    session_dir: &Path,
    handoff: &SessionHandoffPackage,
) -> Result<(), String> {
    let session_id = session_dir_name(session_dir);
    let now = chrono::Utc::now().to_rfc3339();
    let mut metadata = read_metadata_map(session_dir).map_err(|err| err.to_string())?;
    if !metadata.contains_key("created_at") {
        metadata.insert("created_at".to_string(), Value::String(now.clone()));
    }
    metadata.insert("id".to_string(), Value::String(session_id.clone()));
    metadata.insert("session_id".to_string(), Value::String(session_id));
    metadata.insert("updated_at".to_string(), Value::String(now));
    metadata.insert(
        "schema_version".to_string(),
        Value::Number(TRACE_SCHEMA_VERSION.into()),
    );
    metadata
        .entry("session_format".to_string())
        .or_insert_with(|| Value::String(SESSION_FORMAT.to_string()));
    metadata
        .entry("session_origin".to_string())
        .or_insert_with(|| Value::String("desktop".to_string()));
    metadata
        .entry("session_kind".to_string())
        .or_insert_with(|| Value::String("investigation".to_string()));
    metadata
        .entry("turn_count".to_string())
        .or_insert_with(|| Value::Number(0.into()));
    metadata.insert(
        "last_objective".to_string(),
        Value::String(truncate_text(&handoff.objective, 100)),
    );
    metadata.insert(
        "continuity_mode".to_string(),
        Value::String("imported".to_string()),
    );
    metadata.insert("status".to_string(), Value::String("active".to_string()));
    metadata.insert("capabilities".to_string(), session_capabilities_value());
    metadata.insert(
        "durability".to_string(),
        session_durability_value(session_dir),
    );

    let payload =
        serde_json::to_string_pretty(&Value::Object(metadata)).map_err(|err| err.to_string())?;
    fs::write(session_dir.join("metadata.json"), payload).map_err(|err| err.to_string())
}

async fn append_import_replay_note(
    session_dir: &Path,
    handoff: &SessionHandoffPackage,
    stored_path: &Path,
) -> std::io::Result<()> {
    let mut replay = ReplayLogger::new(session_dir);
    replay
        .append(ReplayEntry {
            seq: 0,
            timestamp: String::new(),
            role: "curator".to_string(),
            content: format!(
                "Imported handoff {} from session {} for review or resume. Objective: {}. Snapshot: {}{}",
                handoff.handoff_id,
                handoff.source.session_id,
                default_if_blank(&handoff.objective, "Continue investigation"),
                relative_session_path(session_dir, stored_path),
                handoff
                    .replay_span
                    .as_ref()
                    .map(|span| format!(" (replay {}-{})", span.start_seq, span.end_seq))
                    .unwrap_or_default(),
            ),
            tool_name: None,
            is_rendered: Some(true),
            step_number: None,
            step_depth: None,
            conversation_path: None,
            step_tokens_in: None,
            step_tokens_out: None,
            step_elapsed: None,
            step_model_preview: None,
            step_tool_calls: None,
        })
        .await
}

fn build_source(
    session_id: String,
    selected_turn: Option<&IndexedJsonLine>,
    metadata: &Map<String, Value>,
) -> SessionHandoffSource {
    let turn_value = selected_turn.map(|turn| &turn.value);
    SessionHandoffSource {
        session_id,
        turn_id: turn_value.and_then(|turn| {
            turn.get("turn_id")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        }),
        turn_index: turn_value
            .and_then(|turn| turn.get("turn_index").and_then(Value::as_u64))
            .and_then(|value| u32::try_from(value).ok()),
        turn_line: selected_turn.map(|turn| turn.line_number),
        status: turn_value.and_then(|turn| {
            turn.pointer("/outcome/status")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        }),
        started_at: turn_value.and_then(|turn| {
            turn.get("started_at")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        }),
        ended_at: turn_value.and_then(|turn| {
            turn.get("ended_at")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        }),
        event_span: turn_value
            .and_then(|turn| extract_span(turn.pointer("/provenance/event_span"))),
        continuity_mode: turn_value
            .and_then(|turn| {
                turn.pointer("/continuity/mode")
                    .and_then(Value::as_str)
                    .map(ToString::to_string)
            })
            .or_else(|| string_field(metadata, "continuity_mode")),
        session_status: string_field(metadata, "status"),
    }
}

fn build_handoff_provenance(
    session_dir: &Path,
    selected_turn: Option<&IndexedJsonLine>,
    replay_span: Option<&HandoffSeqSpan>,
    open_questions: &[Value],
    candidate_actions: &[Value],
    evidence_index: &Map<String, Value>,
) -> SessionHandoffProvenance {
    let mut source_refs = Vec::new();
    let mut evidence_refs = Vec::new();
    let mut ontology_refs = Vec::new();
    let mut seen = BTreeSet::new();

    push_unique(
        &mut source_refs,
        &mut seen,
        serde_json::json!({
            "kind": "state_snapshot",
            "file": "metadata.json",
        }),
    );
    if session_dir.join("investigation_state.json").exists() {
        push_unique(
            &mut source_refs,
            &mut seen,
            serde_json::json!({
                "kind": "state_snapshot",
                "file": "investigation_state.json",
            }),
        );
    }
    if let Some(turn) = selected_turn {
        push_unique(
            &mut source_refs,
            &mut seen,
            serde_json::json!({
                "kind": "jsonl_record",
                "file": "turns.jsonl",
                "line": turn.line_number,
                "turn_id": turn.value.get("turn_id").and_then(Value::as_str),
            }),
        );
        if let Some(event_span) = extract_span(turn.value.pointer("/provenance/event_span")) {
            push_unique(
                &mut source_refs,
                &mut seen,
                serde_json::json!({
                    "kind": "event_span",
                    "start_seq": event_span.start_seq,
                    "end_seq": event_span.end_seq,
                }),
            );
        }
        if let Some(outputs) = turn.value.get("outputs").and_then(Value::as_object) {
            if let Some(reference) = outputs.get("assistant_final_ref").and_then(Value::as_str) {
                push_unique(
                    &mut evidence_refs,
                    &mut seen,
                    serde_json::json!({
                        "kind": "message",
                        "id": reference,
                        "label": "assistant_final_ref",
                        "locator": {
                            "file": "events.jsonl",
                            "event_id": reference,
                        }
                    }),
                );
            }
            if let Some(reference) = outputs.get("result_summary_ref").and_then(Value::as_str) {
                push_unique(
                    &mut evidence_refs,
                    &mut seen,
                    serde_json::json!({
                        "kind": "message",
                        "id": reference,
                        "label": "result_summary_ref",
                        "locator": {
                            "file": "events.jsonl",
                            "event_id": reference,
                        }
                    }),
                );
            }
            for artifact in outputs
                .get("artifact_refs")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
            {
                push_unique(
                    &mut evidence_refs,
                    &mut seen,
                    serde_json::json!({
                        "kind": "artifact",
                        "id": artifact,
                        "label": artifact,
                        "locator": {
                            "path": artifact,
                        }
                    }),
                );
            }
        }
    }
    if let Some(span) = replay_span {
        push_unique(
            &mut source_refs,
            &mut seen,
            serde_json::json!({
                "kind": "replay_event",
                "file": "replay.jsonl",
                "start_seq": span.start_seq,
                "end_seq": span.end_seq,
            }),
        );
    }

    for (evidence_id, record) in evidence_index {
        if let Some(source_uri) = record.get("source_uri").and_then(Value::as_str) {
            let kind = if source_uri.starts_with("http://") || source_uri.starts_with("https://") {
                "url"
            } else {
                "file"
            };
            let locator = if kind == "url" {
                serde_json::json!({ "url": source_uri })
            } else {
                serde_json::json!({ "path": source_uri })
            };
            push_unique(
                &mut evidence_refs,
                &mut seen,
                serde_json::json!({
                    "kind": kind,
                    "id": evidence_id,
                    "label": source_uri,
                    "locator": locator,
                }),
            );
        }
        for provenance_id in record
            .get("provenance_ids")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
        {
            push_unique(
                &mut ontology_refs,
                &mut seen,
                serde_json::json!({
                    "object_type": "ProvenanceNode",
                    "object_id": provenance_id,
                    "relation": "evidence_source",
                }),
            );
        }
    }

    for question in open_questions {
        if let Some(question_id) = question.get("id").and_then(Value::as_str) {
            push_unique(
                &mut ontology_refs,
                &mut seen,
                serde_json::json!({
                    "object_type": "Question",
                    "object_id": question_id,
                    "relation": "open_question",
                }),
            );
        }
    }
    for action in candidate_actions {
        if let Some(action_id) = action
            .get("action_id")
            .and_then(Value::as_str)
            .or_else(|| action.get("id").and_then(Value::as_str))
        {
            push_unique(
                &mut ontology_refs,
                &mut seen,
                serde_json::json!({
                    "object_type": "Action",
                    "object_id": action_id,
                    "relation": "candidate_action",
                }),
            );
        }
    }

    SessionHandoffProvenance {
        source_refs,
        evidence_refs,
        ontology_refs,
    }
}

fn select_turn<'a>(
    turns: &'a [IndexedJsonLine],
    requested_turn_id: Option<&str>,
    metadata: &Map<String, Value>,
) -> Result<Option<&'a IndexedJsonLine>, String> {
    if let Some(turn_id) = requested_turn_id {
        return turns
            .iter()
            .find(|turn| {
                turn.value
                    .get("turn_id")
                    .and_then(Value::as_str)
                    .is_some_and(|candidate| candidate == turn_id)
            })
            .map(Some)
            .ok_or_else(|| format!("Turn '{turn_id}' not found"));
    }

    if let Some(turn_id) = metadata.get("last_turn_id").and_then(Value::as_str)
        && let Some(turn) = turns.iter().find(|turn| {
            turn.value
                .get("turn_id")
                .and_then(Value::as_str)
                .is_some_and(|candidate| candidate == turn_id)
        })
    {
        return Ok(Some(turn));
    }

    Ok(turns.last())
}

fn resolve_objective(
    selected_turn: Option<&IndexedJsonLine>,
    metadata: &Map<String, Value>,
    state: &op_core::engine::investigation_state::InvestigationState,
) -> String {
    selected_turn
        .and_then(|turn| turn.value.get("objective").and_then(Value::as_str))
        .map(ToString::to_string)
        .filter(|value| !value.trim().is_empty())
        .or_else(|| string_field(metadata, "last_objective"))
        .or_else(|| (!state.objective.trim().is_empty()).then(|| state.objective.clone()))
        .or_else(|| {
            turn_history_from_state(state)
                .last()
                .map(|turn| turn.objective.clone())
                .filter(|value| !value.trim().is_empty())
        })
        .unwrap_or_else(|| "Continue investigation".to_string())
}

fn read_metadata_map(session_dir: &Path) -> Result<Map<String, Value>, std::io::Error> {
    let path = session_dir.join("metadata.json");
    if !path.exists() {
        return Ok(Map::new());
    }
    let content = fs::read_to_string(path)?;
    let value: Value = serde_json::from_str(&content)
        .map_err(|err| std::io::Error::new(std::io::ErrorKind::InvalidData, err))?;
    Ok(value.as_object().cloned().unwrap_or_default())
}

fn read_jsonl_lines(path: &Path) -> Result<Vec<IndexedJsonLine>, std::io::Error> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let content = fs::read_to_string(path)?;
    let mut rows = Vec::new();
    for (index, line) in content.lines().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let Ok(value) = serde_json::from_str::<Value>(trimmed) else {
            continue;
        };
        rows.push(IndexedJsonLine {
            line_number: (index + 1) as u32,
            value,
        });
    }
    Ok(rows)
}

fn replay_span_from_replay_entries(entries: &[ReplayEntry]) -> Option<HandoffSeqSpan> {
    let start_seq = entries.first()?.seq;
    let end_seq = entries.last()?.seq;
    Some(HandoffSeqSpan { start_seq, end_seq })
}

fn extract_span(value: Option<&Value>) -> Option<HandoffSeqSpan> {
    let obj = value?.as_object()?;
    let start_seq = obj.get("start_seq")?.as_u64()?;
    let end_seq = obj.get("end_seq")?.as_u64()?;
    Some(HandoffSeqSpan { start_seq, end_seq })
}

fn handoff_output_path(session_dir: &Path, handoff_id: &str) -> PathBuf {
    session_dir
        .join("artifacts")
        .join("handoffs")
        .join(format!("{handoff_id}.json"))
}

fn relative_session_path(session_dir: &Path, path: &Path) -> String {
    path.strip_prefix(session_dir)
        .unwrap_or(path)
        .display()
        .to_string()
}

fn session_dir_name(session_dir: &Path) -> String {
    session_dir
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_string()
}

fn string_field(map: &Map<String, Value>, key: &str) -> Option<String> {
    map.get(key)
        .and_then(Value::as_str)
        .map(ToString::to_string)
}

fn push_unique(target: &mut Vec<Value>, seen: &mut BTreeSet<String>, value: Value) {
    let key = serde_json::to_string(&value).unwrap_or_default();
    if seen.insert(key) {
        target.push(value);
    }
}

fn default_if_blank<'a>(value: &'a str, fallback: &'a str) -> &'a str {
    if value.trim().is_empty() {
        fallback
    } else {
        value
    }
}

fn truncate_text(text: &str, max_chars: usize) -> String {
    if text.len() <= max_chars {
        return text.to_string();
    }
    let slice_idx = text.floor_char_boundary(max_chars.saturating_sub(3));
    format!("{}...", &text[..slice_idx])
}

fn validate_session_id(session_id: &str, context: &str) -> Result<(), String> {
    if is_safe_session_id(session_id) {
        Ok(())
    } else {
        Err(format!("{context} contains an unsafe session_id"))
    }
}

fn is_safe_handoff_id(handoff_id: &str) -> bool {
    !handoff_id.is_empty()
        && handoff_id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '-')
}

fn new_handoff_id(now: chrono::DateTime<chrono::Utc>, suffix: &str) -> String {
    let random = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let safe_suffix = suffix
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string();
    format!(
        "handoff-{}-{}-{:08x}",
        now.format("%Y%m%d-%H%M%S"),
        if safe_suffix.is_empty() {
            "snapshot"
        } else {
            safe_suffix.as_str()
        },
        random.subsec_nanos() ^ 0xD0C0_FFEE
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempfile::tempdir;

    fn write_json(path: &Path, value: &Value) {
        fs::write(path, serde_json::to_string_pretty(value).unwrap()).unwrap();
    }

    #[tokio::test]
    async fn build_handoff_package_preserves_reasoning_packet_and_selected_turn() {
        let tmp = tempdir().unwrap();
        let session_dir = tmp.path().join("session-a");
        fs::create_dir_all(session_dir.join("artifacts")).unwrap();
        write_json(
            &session_dir.join("metadata.json"),
            &json!({
                "id": "session-a",
                "session_id": "session-a",
                "created_at": "2026-03-24T10:00:00Z",
                "updated_at": "2026-03-24T10:10:00Z",
                "turn_count": 2,
                "last_turn_id": "turn-000002",
                "last_objective": "Latest objective",
                "continuity_mode": "resume",
                "status": "active",
                "session_format": "openplanter.session.v2",
                "session_origin": "desktop",
                "schema_version": 2
            }),
        );
        fs::write(
            session_dir.join("turns.jsonl"),
            r#"{"turn_id":"turn-000001","turn_index":1,"started_at":"2026-03-24T10:01:00Z","ended_at":"2026-03-24T10:05:00Z","objective":"Map shell entities","continuity":{"mode":"new"},"outputs":{"assistant_final_ref":"evt-00000010","result_summary_ref":"evt-00000011","artifact_refs":["docs/findings.md"]},"outcome":{"status":"completed"},"provenance":{"event_span":{"start_seq":10,"end_seq":18},"replay_span":{"start_seq":2,"end_seq":5}}}
{"turn_id":"turn-000002","turn_index":2,"started_at":"2026-03-24T10:06:00Z","ended_at":"2026-03-24T10:09:00Z","objective":"Latest objective","continuity":{"mode":"resume"},"outputs":{"assistant_final_ref":"evt-00000012","result_summary_ref":"evt-00000013","artifact_refs":[]},"outcome":{"status":"completed"},"provenance":{"event_span":{"start_seq":19,"end_seq":24},"replay_span":{"start_seq":6,"end_seq":8}}}
"#,
        )
        .unwrap();
        write_json(
            &session_dir.join("investigation_state.json"),
            &json!({
                "schema_version": "1.0.0",
                "session_id": "session-a",
                "created_at": "2026-03-24T10:00:00Z",
                "updated_at": "2026-03-24T10:10:00Z",
                "objective": "Map shell entities",
                "ontology": {"namespace": "openplanter.core", "version": "2026-03"},
                "entities": {},
                "links": {},
                "claims": {},
                "evidence": {
                    "ev_1": {
                        "id": "ev_1",
                        "evidence_type": "document",
                        "source_uri": "docs/source.md",
                        "provenance_ids": ["prov_1"]
                    }
                },
                "hypotheses": {},
                "questions": {
                    "q_1": {
                        "id": "q_1",
                        "question_text": "Who controls shell entity A?",
                        "status": "open",
                        "priority": "high",
                        "evidence_ids": ["ev_1"]
                    }
                },
                "tasks": {},
                "actions": {},
                "provenance_nodes": {
                    "prov_1": {"id": "prov_1"}
                },
                "confidence_profiles": {},
                "timeline": [],
                "indexes": {"by_external_ref": {}, "by_tag": {}},
                "legacy": {"external_observations": [], "turn_history": [], "loop_metrics": {}, "extra_fields": {}}
            }),
        );

        let handoff = build_handoff_package(&session_dir, Some("turn-000001"))
            .await
            .unwrap();

        assert_eq!(handoff.source.turn_id.as_deref(), Some("turn-000001"));
        assert_eq!(handoff.objective, "Map shell entities");
        assert_eq!(
            handoff.replay_span,
            Some(HandoffSeqSpan {
                start_seq: 2,
                end_seq: 5
            })
        );
        assert_eq!(handoff.open_questions.len(), 1);
        assert_eq!(handoff.candidate_actions.len(), 1);
        assert!(handoff.evidence_index.contains_key("ev_1"));
        assert!(
            handoff
                .provenance
                .source_refs
                .iter()
                .any(|item| item["file"] == "turns.jsonl")
        );
        assert!(
            handoff
                .provenance
                .evidence_refs
                .iter()
                .any(|item| item["kind"] == "artifact")
        );
        assert!(
            handoff
                .provenance
                .ontology_refs
                .iter()
                .any(|item| item["object_type"] == "Question")
        );
    }

    #[tokio::test]
    async fn build_handoff_package_falls_back_to_replay_when_turns_missing() {
        let tmp = tempdir().unwrap();
        let session_dir = tmp.path().join("session-b");
        fs::create_dir_all(session_dir.join("artifacts")).unwrap();
        write_json(
            &session_dir.join("metadata.json"),
            &json!({
                "id": "session-b",
                "session_id": "session-b",
                "created_at": "2026-03-24T10:00:00Z",
                "updated_at": "2026-03-24T10:10:00Z",
                "turn_count": 0,
                "status": "active"
            }),
        );
        fs::write(
            session_dir.join("replay.jsonl"),
            r#"{"seq":4,"timestamp":"2026-03-24T10:01:00Z","role":"user","content":"Investigate donor overlap"}
{"seq":7,"timestamp":"2026-03-24T10:02:00Z","role":"assistant","content":"Initial sweep complete"}
"#,
        )
        .unwrap();
        write_json(
            &session_dir.join("investigation_state.json"),
            &json!({
                "schema_version": "1.0.0",
                "session_id": "session-b",
                "created_at": "2026-03-24T10:00:00Z",
                "updated_at": "2026-03-24T10:10:00Z",
                "objective": "",
                "ontology": {"namespace": "openplanter.core", "version": "2026-03"},
                "entities": {},
                "links": {},
                "claims": {},
                "evidence": {},
                "hypotheses": {},
                "questions": {},
                "tasks": {},
                "actions": {},
                "provenance_nodes": {},
                "confidence_profiles": {},
                "timeline": [],
                "indexes": {"by_external_ref": {}, "by_tag": {}},
                "legacy": {
                    "external_observations": [],
                    "turn_history": [
                        {"turn_number": 1, "objective": "Fallback objective", "result_preview": "", "timestamp": "2026-03-24T10:00:00Z", "steps_used": 0, "replay_seq_start": 4}
                    ],
                    "loop_metrics": {},
                    "extra_fields": {}
                }
            }),
        );

        let handoff = build_handoff_package(&session_dir, None).await.unwrap();

        assert_eq!(handoff.source.turn_id, None);
        assert_eq!(handoff.objective, "Fallback objective");
        assert_eq!(
            handoff.replay_span,
            Some(HandoffSeqSpan {
                start_seq: 4,
                end_seq: 7
            })
        );
    }

    #[test]
    fn validate_handoff_package_rejects_backwards_span() {
        let err = validate_handoff_package(&SessionHandoffPackage {
            schema_version: HANDOFF_SCHEMA_VERSION,
            package_format: HANDOFF_FORMAT.to_string(),
            handoff_id: "handoff-bad".to_string(),
            exported_at: "2026-03-24T10:00:00Z".to_string(),
            objective: "Investigate".to_string(),
            open_questions: Vec::new(),
            candidate_actions: Vec::new(),
            evidence_index: Map::new(),
            replay_span: Some(HandoffSeqSpan {
                start_seq: 9,
                end_seq: 4,
            }),
            source: SessionHandoffSource::default(),
            provenance: SessionHandoffProvenance::default(),
            compat: SessionHandoffCompat::default(),
        })
        .unwrap_err();

        assert!(err.contains("Invalid replay span"));
    }

    #[test]
    fn validate_handoff_package_rejects_unsafe_handoff_id() {
        let err = validate_handoff_package(&SessionHandoffPackage {
            schema_version: HANDOFF_SCHEMA_VERSION,
            package_format: HANDOFF_FORMAT.to_string(),
            handoff_id: "../../../evil".to_string(),
            exported_at: "2026-03-24T10:00:00Z".to_string(),
            objective: "Investigate".to_string(),
            open_questions: Vec::new(),
            candidate_actions: Vec::new(),
            evidence_index: Map::new(),
            replay_span: Some(HandoffSeqSpan {
                start_seq: 1,
                end_seq: 4,
            }),
            source: SessionHandoffSource::default(),
            provenance: SessionHandoffProvenance::default(),
            compat: SessionHandoffCompat::default(),
        })
        .unwrap_err();

        assert!(err.contains("unsafe handoff_id"));
    }

    #[test]
    fn validate_session_id_rejects_path_traversal() {
        let err = validate_session_id("../../../evil", "Session handoff export").unwrap_err();

        assert!(err.contains("unsafe session_id"));
    }

    #[test]
    fn resolve_import_target_rejects_unsafe_target_session_id() {
        let tmp = tempdir().unwrap();
        let sessions_dir = tmp.path().join("sessions");
        fs::create_dir_all(&sessions_dir).unwrap();

        let err = resolve_import_target(&sessions_dir, Some("../../../evil")).unwrap_err();

        assert!(err.contains("unsafe session_id"));
    }

    #[tokio::test]
    async fn import_handoff_into_session_updates_metadata_and_replay() {
        let tmp = tempdir().unwrap();
        let sessions_dir = tmp.path().join("sessions");
        let session = create_session(&sessions_dir).unwrap();
        let session_dir = sessions_dir.join(&session.id);
        let handoff = SessionHandoffPackage {
            schema_version: HANDOFF_SCHEMA_VERSION,
            package_format: HANDOFF_FORMAT.to_string(),
            handoff_id: "handoff-import".to_string(),
            exported_at: "2026-03-24T10:00:00Z".to_string(),
            objective: "Resume imported investigation".to_string(),
            open_questions: vec![json!({"id":"q_1","question":"What changed?"})],
            candidate_actions: Vec::new(),
            evidence_index: Map::new(),
            replay_span: Some(HandoffSeqSpan {
                start_seq: 2,
                end_seq: 6,
            }),
            source: SessionHandoffSource {
                session_id: "source-session".to_string(),
                turn_id: Some("turn-000005".to_string()),
                ..SessionHandoffSource::default()
            },
            provenance: SessionHandoffProvenance::default(),
            compat: SessionHandoffCompat::default(),
        };

        let stored = import_handoff_into_session(
            &session_dir,
            &handoff,
            Path::new("/tmp/source-handoff.json"),
            true,
        )
        .await
        .unwrap();

        assert!(stored.exists());
        let metadata: Value =
            serde_json::from_str(&fs::read_to_string(session_dir.join("metadata.json")).unwrap())
                .unwrap();
        assert_eq!(metadata["continuity_mode"], "imported");
        assert_eq!(metadata["status"], "active");
        assert_eq!(metadata["last_objective"], "Resume imported investigation");
        assert_eq!(metadata["schema_version"], TRACE_SCHEMA_VERSION);
        assert_eq!(metadata["session_format"], SESSION_FORMAT);
        assert_eq!(metadata["capabilities"]["supports_turns_v2"], true);
        assert_eq!(metadata["durability"]["events_jsonl_present"], true);
        assert_eq!(metadata["durability"]["replay_jsonl_present"], true);

        let events = fs::read_to_string(session_dir.join("events.jsonl")).unwrap();
        assert!(events.contains("\"event_type\":\"session.handoff.imported\""));
        let replay = fs::read_to_string(session_dir.join("replay.jsonl")).unwrap();
        assert!(replay.contains("Imported handoff handoff-import"));
    }
}
