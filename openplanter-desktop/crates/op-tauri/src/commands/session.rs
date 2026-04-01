use crate::state::AppState;
use op_core::events::SessionInfo;
use op_core::session::replay::{ReplayEntry, ReplayLogger};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs;
use std::path::{Component, Path, PathBuf};
use tauri::State;
use tokio::fs as tokio_fs;
use tokio::io::AsyncWriteExt;

/// Write an artifact file to the session directory.
#[tauri::command]
pub async fn write_session_artifact(
    session_dir: String,
    filename: String,
    content: String,
) -> Result<(), String> {
    let path = normalize_session_artifact_path(&session_dir, &filename)?;
    if let Some(parent) = path.parent() {
        tokio_fs::create_dir_all(parent)
            .await
            .map_err(|e| format!("Failed to prepare artifact directory: {e}"))?;
    }

    tokio_fs::write(&path, content)
        .await
        .map_err(|e| format!("Failed to write artifact: {e}"))
}

/// Read an artifact file from the session directory.
/// Returns None if the file doesn't exist.
#[tauri::command]
pub async fn read_session_artifact(
    session_dir: String,
    filename: String,
) -> Result<Option<String>, String> {
    let path = normalize_session_artifact_path(&session_dir, &filename)?;

    if !path.exists() {
        return Ok(None);
    }

    let content = tokio_fs::read_to_string(&path)
        .await
        .map_err(|e| format!("Failed to read artifact: {e}"))?;

    Ok(Some(content))
}

#[tauri::command]
pub async fn read_session_event(
    session_id: String,
    event_id: String,
    state: State<'_, AppState>,
) -> Result<Option<Value>, String> {
    if !is_safe_session_id(&session_id) {
        return Err("Invalid session id".to_string());
    }
    let session_dir = sessions_dir(&state).await.join(&session_id);
    read_session_event_by_path(&session_dir, &event_id)
        .await
        .map_err(|e| format!("Failed to read session event: {e}"))
}

fn looks_like_windows_absolute_path(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() >= 3
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'/' | b'\\')
    {
        return true;
    }
    value.starts_with("\\\\")
}

/// Validate and normalize a session-relative artifact path.
fn normalize_session_artifact_path(
    session_dir: &str,
    relative_path: &str,
) -> Result<PathBuf, String> {
    let session_path = Path::new(session_dir);
    if !session_path.is_absolute() {
        return Err("Session directory must be absolute".to_string());
    }
    let canonical_session = session_path
        .canonicalize()
        .map_err(|_| "Session directory does not exist".to_string())?;

    let trimmed = relative_path.trim();
    if trimmed.is_empty() {
        return Err("Artifact path must not be empty".to_string());
    }
    if trimmed.contains('\0') {
        return Err("Artifact path contains invalid characters".to_string());
    }
    if looks_like_windows_absolute_path(trimmed) {
        return Err("Artifact path must be relative".to_string());
    }

    let relative = Path::new(trimmed);
    if relative.is_absolute() {
        return Err("Artifact path must be relative".to_string());
    }

    let mut normalized = PathBuf::new();
    let mut saw_normal = false;
    for component in relative.components() {
        match component {
            Component::CurDir => {}
            Component::Normal(part) => {
                normalized.push(part);
                saw_normal = true;
            }
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err("Artifact path escapes the session directory".to_string());
            }
        }
    }

    if !saw_normal {
        return Err("Artifact path must point to a file".to_string());
    }

    Ok(canonical_session.join(normalized))
}

async fn read_session_event_by_path(
    session_dir: &Path,
    event_id: &str,
) -> Result<Option<Value>, std::io::Error> {
    let path = session_dir.join("events.jsonl");
    if !path.exists() {
        return Ok(None);
    }
    let content = tokio_fs::read_to_string(path).await?;
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let Ok(value) = serde_json::from_str::<Value>(trimmed) else {
            continue;
        };
        if value
            .get("event_id")
            .and_then(Value::as_str)
            .is_some_and(|candidate| candidate == event_id)
        {
            return Ok(Some(value));
        }
    }
    Ok(None)
}

/// Get the full session directory path for a given session ID.
#[tauri::command]
pub async fn get_session_directory(
    session_id: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let dir = sessions_dir(&state).await.join(&session_id);
    Ok(dir.to_string_lossy().to_string())
}

pub(crate) const TRACE_SCHEMA_VERSION: u32 = 2;
pub(crate) const SESSION_FORMAT: &str = "openplanter.session.v2";
const TRACE_ENVELOPE: &str = "openplanter.trace.event.v2";
const TURN_RECORD_FORMAT: &str = "openplanter.trace.turn.v2";
const MAX_OBJECTIVE_CHARS: usize = 100;

pub(crate) fn is_safe_session_id(session_id: &str) -> bool {
    let mut components = Path::new(session_id).components();
    !session_id.trim().is_empty()
        && !session_id.chars().any(|ch| matches!(ch, '/' | '\\' | '\0'))
        && matches!(
            (components.next(), components.next()),
            (Some(std::path::Component::Normal(_)), None)
        )
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FailureInfo {
    pub code: String,
    pub category: String,
    pub phase: String,
    pub retryable: bool,
    pub message: String,
    #[serde(default)]
    pub details: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resumable: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user_visible: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_code: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub http_status: Option<u16>,
}

impl FailureInfo {
    pub fn cancelled(message: impl Into<String>) -> Self {
        Self {
            code: "cancelled".to_string(),
            category: "user_action".to_string(),
            phase: "session_finalize".to_string(),
            retryable: false,
            message: message.into(),
            details: serde_json::json!({}),
            resumable: Some(true),
            user_visible: Some(true),
            provider: None,
            provider_code: None,
            http_status: None,
        }
    }

    pub fn degraded(message: impl Into<String>) -> Self {
        Self {
            code: "degraded".to_string(),
            category: "runtime".to_string(),
            phase: "session_finalize".to_string(),
            retryable: true,
            message: message.into(),
            details: serde_json::json!({}),
            resumable: Some(true),
            user_visible: Some(true),
            provider: None,
            provider_code: None,
            http_status: None,
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct AppendSessionEventOptions {
    pub turn_id: Option<String>,
    pub status: Option<String>,
    pub failure: Option<FailureInfo>,
    pub actor_kind: Option<String>,
    pub provider: Option<String>,
    pub model: Option<String>,
    pub evidence_refs: Vec<String>,
    pub source_refs: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct AppendedEventMeta {
    pub seq: u64,
    pub event_id: String,
    pub recorded_at: String,
    pub canonical_type: String,
}

#[derive(Debug, Clone)]
pub struct TurnStartContext {
    pub session_id: String,
    pub turn_id: String,
    pub turn_index: u32,
    pub started_at: String,
    pub continuity_mode: String,
    pub resumed_from_turn_id: Option<String>,
    pub resumed_from_partial: bool,
    pub user_message_event_id: String,
    pub event_start_seq: u64,
}

#[derive(Debug, Clone)]
pub struct TurnRecordOutcome {
    pub status: String,
    pub ended_at: String,
    pub summary: String,
    pub failure: Option<FailureInfo>,
    pub degraded: bool,
    pub step_count: u32,
    pub tool_call_count: u32,
    pub replay_seq_start: u64,
    pub replay_seq_end: u64,
    pub event_end_seq: u64,
    pub assistant_final_ref: Option<String>,
    pub result_summary_ref: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
struct SessionSourceCompat {
    legacy_python_metadata: bool,
    desktop_metadata: bool,
    legacy_event_stream_present: bool,
    legacy_replay_stream_present: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
struct SessionCapabilities {
    supports_events_v2: bool,
    supports_replay_v2: bool,
    supports_turns_v2: bool,
    supports_provenance_links: bool,
    supports_failure_taxonomy_v2: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
struct SessionDurability {
    events_jsonl_present: bool,
    replay_jsonl_present: bool,
    turns_jsonl_present: bool,
    partial_records_possible: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
struct SessionMetadataFile {
    #[serde(skip_serializing_if = "Option::is_none")]
    schema_version: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    session_format: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    id: Option<String>,
    #[serde(default)]
    created_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    updated_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    workspace: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    workspace_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    session_origin: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    session_kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    status: Option<String>,
    #[serde(default)]
    turn_count: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    last_turn_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    last_objective: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    continuity_mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    checkpoint_ref: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    source_compat: Option<SessionSourceCompat>,
    #[serde(skip_serializing_if = "Option::is_none")]
    capabilities: Option<SessionCapabilities>,
    #[serde(skip_serializing_if = "Option::is_none")]
    durability: Option<SessionDurability>,
    #[serde(skip_serializing_if = "Option::is_none")]
    investigation_id: Option<String>,
    #[serde(default, flatten)]
    extra: serde_json::Map<String, Value>,
}

impl SessionMetadataFile {
    fn resolved_session_id(&self, fallback_id: &str) -> String {
        self.session_id
            .as_deref()
            .or(self.id.as_deref())
            .unwrap_or(fallback_id)
            .to_string()
    }

    fn resolved_created_at(&self) -> String {
        if !self.created_at.trim().is_empty() {
            self.created_at.clone()
        } else {
            self.updated_at.clone().unwrap_or_default()
        }
    }

    fn to_session_info(&self, fallback_id: &str) -> SessionInfo {
        SessionInfo {
            id: self.resolved_session_id(fallback_id),
            created_at: self.resolved_created_at(),
            turn_count: self.turn_count,
            last_objective: self.last_objective.clone(),
            investigation_id: self.investigation_id.clone(),
        }
    }

    fn refresh_v2(&mut self, session_dir: &Path, fallback_id: &str, updated_at: &str) {
        let had_desktop_id = self.id.is_some();
        let had_legacy_session_id = self.session_id.is_some() && !had_desktop_id;
        let had_workspace = self.workspace.is_some();
        let session_id = self.resolved_session_id(fallback_id);

        self.schema_version = Some(TRACE_SCHEMA_VERSION);
        self.session_format = Some(SESSION_FORMAT.to_string());
        self.id = Some(session_id.clone());
        self.session_id = Some(session_id);
        if self.created_at.trim().is_empty() {
            self.created_at = updated_at.to_string();
        }
        self.updated_at = Some(updated_at.to_string());
        if self.workspace_path.is_none() {
            self.workspace_path = self.workspace.clone();
        }
        self.session_origin
            .get_or_insert_with(|| "desktop".to_string());
        self.session_kind
            .get_or_insert_with(|| "investigation".to_string());
        self.status.get_or_insert_with(|| "active".to_string());
        self.continuity_mode.get_or_insert_with(|| {
            if self.turn_count == 0 {
                "new"
            } else {
                "resume"
            }
            .to_string()
        });
        self.source_compat = Some(SessionSourceCompat {
            legacy_python_metadata: had_legacy_session_id || had_workspace,
            desktop_metadata: had_desktop_id
                || self.turn_count > 0
                || self.last_objective.is_some(),
            legacy_event_stream_present: session_dir.join("events.jsonl").exists()
                && (had_legacy_session_id || had_workspace),
            legacy_replay_stream_present: session_dir.join("replay.jsonl").exists()
                && (had_legacy_session_id || had_workspace),
        });
        self.capabilities = Some(SessionCapabilities {
            supports_events_v2: true,
            supports_replay_v2: true,
            supports_turns_v2: true,
            supports_provenance_links: true,
            supports_failure_taxonomy_v2: true,
        });
        self.durability = Some(durability_flags(session_dir));
    }
}

#[derive(Debug, Clone, Serialize)]
struct TurnRecordV2 {
    schema_version: u32,
    record: String,
    session_id: String,
    turn_id: String,
    turn_index: u32,
    started_at: String,
    ended_at: String,
    objective: String,
    continuity: TurnContinuity,
    inputs: TurnInputs,
    outputs: TurnOutputs,
    execution: TurnExecution,
    outcome: TurnOutcomePayload,
    provenance: TurnProvenance,
}

#[derive(Debug, Clone, Serialize)]
struct TurnContinuity {
    mode: String,
    resumed_from_turn_id: Option<String>,
    resumed_from_partial: bool,
    checkpoint_ref: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct TurnInputs {
    user_message_ref: Option<String>,
    attachments: Vec<String>,
    context_refs: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct TurnOutputs {
    assistant_final_ref: Option<String>,
    result_summary_ref: Option<String>,
    artifact_refs: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct TurnExecution {
    step_count: u32,
    tool_call_count: u32,
    degraded: bool,
    resumed: bool,
}

#[derive(Debug, Clone, Serialize)]
struct TurnOutcomePayload {
    status: String,
    failure_code: Option<String>,
    failure: Option<FailureInfo>,
    summary: String,
}

#[derive(Debug, Clone, Serialize)]
struct TurnProvenance {
    event_span: SeqSpan,
    #[serde(skip_serializing_if = "Option::is_none")]
    replay_span: Option<SeqSpan>,
    evidence_refs: Vec<Value>,
    ontology_refs: Vec<Value>,
}

#[derive(Debug, Clone, Serialize)]
struct SeqSpan {
    start_seq: u64,
    end_seq: u64,
}

/// Get the sessions directory path from config.
pub async fn sessions_dir(state: &State<'_, AppState>) -> PathBuf {
    let cfg = state.config.lock().await;
    let ws = cfg.workspace.clone();
    let root = cfg.session_root_dir.clone();
    ws.join(root).join("sessions")
}

/// Collect sessions from a directory, sorted by created_at descending, limited to `limit`.
pub fn collect_sessions(dir: &Path, limit: usize) -> Vec<SessionInfo> {
    if !dir.exists() {
        return vec![];
    }

    let mut sessions: Vec<SessionInfo> = Vec::new();

    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return vec![],
    };
    for entry in entries.flatten() {
        if !entry.path().is_dir() {
            continue;
        }
        let meta_path = entry.path().join("metadata.json");
        if !meta_path.exists() {
            continue;
        }
        let metadata = match read_metadata_file(&entry.path()) {
            Ok(metadata) => metadata,
            Err(_) => continue,
        };
        let fallback_id = entry.file_name().to_string_lossy().to_string();
        sessions.push(metadata.to_session_info(&fallback_id));
    }

    sessions.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    sessions.truncate(limit);
    sessions
}

/// Create a new session in the given directory, returning the SessionInfo.
pub fn create_session(
    dir: &Path,
    investigation_id: Option<String>,
) -> Result<SessionInfo, std::io::Error> {
    fs::create_dir_all(dir)?;

    let now = chrono::Utc::now().to_rfc3339();
    let new_id = format!(
        "{}-{:08x}",
        chrono::Utc::now().format("%Y%m%d-%H%M%S"),
        rand_hex()
    );

    let session_dir = dir.join(&new_id);
    fs::create_dir_all(&session_dir)?;
    fs::create_dir_all(session_dir.join("artifacts"))?;

    let mut metadata = SessionMetadataFile {
        created_at: now.clone(),
        updated_at: Some(now.clone()),
        turn_count: 0,
        last_objective: None,
        status: Some("active".to_string()),
        continuity_mode: Some("new".to_string()),
        investigation_id,
        ..SessionMetadataFile::default()
    };
    metadata.refresh_v2(&session_dir, &new_id, &now);
    write_metadata_file_sync(&session_dir, &metadata)?;

    Ok(metadata.to_session_info(&new_id))
}

pub fn append_session_event(
    session_dir: &Path,
    event_type: &str,
    payload: Value,
    options: AppendSessionEventOptions,
) -> Result<AppendedEventMeta, std::io::Error> {
    let fallback_id = session_dir_name(session_dir);
    let metadata = read_metadata_file(session_dir).unwrap_or_default();
    let session_id = metadata.resolved_session_id(&fallback_id);
    let canonical_type = canonical_event_type(
        event_type,
        &payload,
        options
            .status
            .as_deref()
            .or_else(|| payload.get("status").and_then(Value::as_str)),
    );
    let status = normalize_event_status(
        options
            .status
            .as_deref()
            .or_else(|| payload.get("status").and_then(Value::as_str)),
        &canonical_type,
        options.failure.as_ref(),
    );
    let actor_kind = options
        .actor_kind
        .unwrap_or_else(|| default_actor_kind(&canonical_type).to_string());
    let turn_id = options.turn_id.or_else(|| {
        if canonical_type.starts_with("session.") {
            None
        } else {
            metadata.last_turn_id.clone()
        }
    });
    let event_path = session_dir.join("events.jsonl");
    let (max_seq, line_count) = jsonl_stats(&event_path)?;
    let seq = max_seq + 1;
    let recorded_at = chrono::Utc::now().to_rfc3339();
    let event_id = format!("evt-{seq:08x}");
    let legacy_kind = if event_type.contains('.') {
        Value::Null
    } else {
        Value::String(event_type.to_string())
    };
    let event = serde_json::json!({
        "ts": recorded_at,
        "type": event_type,
        "payload": payload,
        "schema_version": TRACE_SCHEMA_VERSION,
        "envelope": TRACE_ENVELOPE,
        "event_id": event_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "seq": seq,
        "recorded_at": recorded_at,
        "event_type": canonical_type,
        "channel": "event",
        "status": status,
        "actor": actor_payload(&actor_kind),
        "failure": options.failure,
        "provenance": {
            "record_locator": {
                "file": "events.jsonl",
                "line": line_count + 1,
            },
            "parent_event_id": Value::Null,
            "caused_by": [],
            "source_refs": options.source_refs,
            "evidence_refs": options.evidence_refs,
            "ontology_refs": [],
            "generated_from": {
                "provider": options.provider.as_ref().map(|s| Value::String(s.clone())).unwrap_or(Value::Null),
                "model": options.model.as_ref().map(|s| Value::String(s.clone())).unwrap_or(Value::Null),
                "request_id": Value::Null,
                "conversation_id": Value::Null,
            },
        },
        "compat": {
            "legacy_role": Value::Null,
            "legacy_kind": legacy_kind,
            "source_schema": "desktop-events-v1",
        }
    });
    let mut line = serde_json::to_string(&event).map_err(std::io::Error::other)?;
    line.push('\n');
    use std::io::Write;
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(event_path)?;
    file.write_all(line.as_bytes())?;

    Ok(AppendedEventMeta {
        seq,
        event_id,
        recorded_at,
        canonical_type,
    })
}

/// List recent sessions by scanning session directories.
#[tauri::command]
pub async fn list_sessions(
    limit: Option<u32>,
    state: State<'_, AppState>,
) -> Result<Vec<SessionInfo>, String> {
    let dir = sessions_dir(&state).await;
    let cap = limit.unwrap_or(20) as usize;
    Ok(collect_sessions(&dir, cap))
}

/// Open a session (create new or resume existing).
#[tauri::command]
pub async fn open_session(
    id: Option<String>,
    resume: bool,
    investigation_id: Option<String>,
    state: State<'_, AppState>,
) -> Result<SessionInfo, String> {
    let dir = sessions_dir(&state).await;

    if resume {
        if let Some(ref session_id) = id {
            let session_dir = dir.join(session_id);
            let meta_path = session_dir.join("metadata.json");
            if meta_path.exists() {
                let mut metadata = read_metadata_file(&session_dir).map_err(|e| e.to_string())?;
                let now = chrono::Utc::now().to_rfc3339();
                metadata.continuity_mode = Some("resume".to_string());
                metadata.status = Some("active".to_string());
                if investigation_id.is_some() {
                    metadata.investigation_id = investigation_id.clone();
                }
                metadata.refresh_v2(&session_dir, session_id, &now);
                write_metadata_file(&session_dir, &metadata)
                    .await
                    .map_err(|e| e.to_string())?;
                let info = metadata.to_session_info(session_id);
                let mut session_lock = state.session_id.lock().await;
                *session_lock = Some(info.id.clone());
                let _ = append_session_event(
                    &session_dir,
                    "session_started",
                    serde_json::json!({"resume": true, "created_new": false}),
                    AppendSessionEventOptions::default(),
                );
                return Ok(info);
            }
        }
    }

    let info = create_session(&dir, investigation_id.clone()).map_err(|e| e.to_string())?;
    let mut session_lock = state.session_id.lock().await;
    *session_lock = Some(info.id.clone());
    let _ = append_session_event(
        &dir.join(&info.id),
        "session_started",
        serde_json::json!({"resume": false, "created_new": true}),
        AppendSessionEventOptions::default(),
    );
    Ok(info)
}

/// Delete a session by removing its directory.
#[tauri::command]
pub async fn delete_session(id: String, state: State<'_, AppState>) -> Result<(), String> {
    let dir = sessions_dir(&state).await;
    let session_dir = dir.join(&id);

    if !session_dir.exists() {
        return Err(format!("Session '{id}' not found"));
    }
    if !session_dir.is_dir() {
        return Err(format!("Session '{id}' is not a directory"));
    }
    // Ensure it's actually a session directory (has metadata.json)
    if !session_dir.join("metadata.json").exists() {
        return Err(format!(
            "Session '{id}' has no metadata — refusing to delete"
        ));
    }

    fs::remove_dir_all(&session_dir).map_err(|e| format!("Failed to delete session: {e}"))?;

    // If the deleted session is the current one, clear the active session
    let mut session_lock = state.session_id.lock().await;
    if session_lock.as_deref() == Some(id.as_str()) {
        *session_lock = None;
    }

    Ok(())
}

/// Get message history for a session from replay.jsonl.
#[tauri::command]
pub async fn get_session_history(
    session_id: String,
    state: State<'_, AppState>,
) -> Result<Vec<ReplayEntry>, String> {
    let dir = sessions_dir(&state).await.join(&session_id);
    ReplayLogger::read_all(&dir)
        .await
        .map_err(|e| e.to_string())
}

/// Start a turn by appending durable lifecycle events and refreshing metadata.
pub async fn update_session_metadata(
    session_dir: &Path,
    objective: &str,
) -> Result<TurnStartContext, std::io::Error> {
    let mut metadata = read_metadata_file(session_dir)?;
    let fallback_id = session_dir_name(session_dir);
    let session_id = metadata.resolved_session_id(&fallback_id);
    let resumed_from_turn_id = metadata.last_turn_id.clone();
    let resumed_from_partial = metadata.status.as_deref() == Some("partial");
    let continuity_mode = if metadata.turn_count == 0 {
        "new".to_string()
    } else {
        "resume".to_string()
    };
    let turn_index = metadata.turn_count.saturating_add(1);
    let turn_id = format!("turn-{turn_index:06}");
    let started_at = chrono::Utc::now().to_rfc3339();

    let started_meta = append_session_event(
        session_dir,
        "turn.started",
        serde_json::json!({"turn_index": turn_index}),
        AppendSessionEventOptions {
            turn_id: Some(turn_id.clone()),
            status: Some("started".to_string()),
            actor_kind: Some("runtime".to_string()),
            ..AppendSessionEventOptions::default()
        },
    )?;

    if resumed_from_partial {
        let _ = append_session_event(
            session_dir,
            "turn.resumed_from_partial",
            serde_json::json!({
                "turn_index": turn_index,
                "resumed_from_turn_id": resumed_from_turn_id,
            }),
            AppendSessionEventOptions {
                turn_id: Some(turn_id.clone()),
                status: Some("info".to_string()),
                actor_kind: Some("runtime".to_string()),
                ..AppendSessionEventOptions::default()
            },
        )?;
    }

    let objective_meta = append_session_event(
        session_dir,
        "objective",
        serde_json::json!({
            "text": objective,
            "turn_index": turn_index,
        }),
        AppendSessionEventOptions {
            turn_id: Some(turn_id.clone()),
            status: Some("in_progress".to_string()),
            actor_kind: Some("user".to_string()),
            ..AppendSessionEventOptions::default()
        },
    )?;

    metadata.turn_count = turn_index;
    metadata.last_turn_id = Some(turn_id.clone());
    metadata.last_objective = Some(truncate_objective(objective));
    metadata.continuity_mode = Some(continuity_mode.clone());
    metadata.status = Some("active".to_string());
    metadata.refresh_v2(session_dir, &session_id, &started_at);
    write_metadata_file(session_dir, &metadata).await?;

    Ok(TurnStartContext {
        session_id,
        turn_id,
        turn_index,
        started_at,
        continuity_mode,
        resumed_from_turn_id,
        resumed_from_partial,
        user_message_event_id: objective_meta.event_id,
        event_start_seq: started_meta.seq,
    })
}

pub async fn finalize_session_turn(
    session_dir: &Path,
    turn: &TurnStartContext,
    objective: &str,
    outcome: &TurnRecordOutcome,
) -> Result<(), std::io::Error> {
    let turns_path = session_dir.join("turns.jsonl");
    if !turn_record_exists(&turns_path, &turn.turn_id).await? {
        let record = TurnRecordV2 {
            schema_version: TRACE_SCHEMA_VERSION,
            record: TURN_RECORD_FORMAT.to_string(),
            session_id: turn.session_id.clone(),
            turn_id: turn.turn_id.clone(),
            turn_index: turn.turn_index,
            started_at: turn.started_at.clone(),
            ended_at: outcome.ended_at.clone(),
            objective: objective.to_string(),
            continuity: TurnContinuity {
                mode: turn.continuity_mode.clone(),
                resumed_from_turn_id: if turn.resumed_from_partial {
                    turn.resumed_from_turn_id.clone()
                } else {
                    None
                },
                resumed_from_partial: turn.resumed_from_partial,
                checkpoint_ref: None,
            },
            inputs: TurnInputs {
                user_message_ref: Some(turn.user_message_event_id.clone()),
                attachments: Vec::new(),
                context_refs: Vec::new(),
            },
            outputs: TurnOutputs {
                assistant_final_ref: outcome.assistant_final_ref.clone(),
                result_summary_ref: outcome.result_summary_ref.clone(),
                artifact_refs: Vec::new(),
            },
            execution: TurnExecution {
                step_count: outcome.step_count,
                tool_call_count: outcome.tool_call_count,
                degraded: outcome.degraded,
                resumed: turn.continuity_mode != "new",
            },
            outcome: TurnOutcomePayload {
                status: outcome.status.clone(),
                failure_code: outcome.failure.as_ref().map(|failure| failure.code.clone()),
                failure: outcome.failure.clone(),
                summary: outcome.summary.clone(),
            },
            provenance: TurnProvenance {
                event_span: SeqSpan {
                    start_seq: turn.event_start_seq,
                    end_seq: outcome.event_end_seq.max(turn.event_start_seq),
                },
                replay_span: if outcome.replay_seq_end >= outcome.replay_seq_start
                    && outcome.replay_seq_start > 0
                {
                    Some(SeqSpan {
                        start_seq: outcome.replay_seq_start,
                        end_seq: outcome.replay_seq_end,
                    })
                } else {
                    None
                },
                evidence_refs: Vec::new(),
                ontology_refs: Vec::new(),
            },
        };
        let mut line = serde_json::to_string(&record).map_err(std::io::Error::other)?;
        line.push('\n');
        let mut file = tokio_fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&turns_path)
            .await?;
        file.write_all(line.as_bytes()).await?;
        file.flush().await?;
    }

    let mut metadata = read_metadata_file(session_dir)?;
    metadata.turn_count = metadata.turn_count.max(turn.turn_index);
    metadata.last_turn_id = Some(turn.turn_id.clone());
    metadata.last_objective = Some(truncate_objective(objective));
    metadata.continuity_mode = Some(turn.continuity_mode.clone());
    metadata.status = Some(session_status_for_outcome(&outcome.status).to_string());
    metadata.refresh_v2(session_dir, &turn.session_id, &outcome.ended_at);
    write_metadata_file(session_dir, &metadata).await
}

fn session_dir_name(session_dir: &Path) -> String {
    session_dir
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_string()
}

fn truncate_objective(objective: &str) -> String {
    if objective.len() <= MAX_OBJECTIVE_CHARS {
        return objective.to_string();
    }
    let end = objective.floor_char_boundary(MAX_OBJECTIVE_CHARS - 3);
    format!("{}...", &objective[..end])
}

fn actor_payload(actor_kind: &str) -> Value {
    let (id, display) = match actor_kind {
        "user" => ("user", "User"),
        "assistant" => ("default-agent", "OpenPlanter"),
        "curator" => ("curator", "Curator"),
        _ => ("desktop-runtime", "OpenPlanter"),
    };
    serde_json::json!({
        "kind": actor_kind,
        "id": id,
        "display": display,
        "runtime_family": "desktop",
    })
}

fn canonical_event_type(event_type: &str, payload: &Value, raw_status: Option<&str>) -> String {
    if event_type.contains('.') {
        return event_type.to_string();
    }
    match event_type {
        "session_started" => {
            if payload
                .get("resume")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                "session.resumed".to_string()
            } else {
                "session.started".to_string()
            }
        }
        "objective" => "turn.objective".to_string(),
        "trace" => "trace.note".to_string(),
        "step" => "step.summary".to_string(),
        "artifact" => "artifact.created".to_string(),
        "result" => match normalize_terminal_status(raw_status) {
            "cancelled" => "turn.cancelled".to_string(),
            "failed" => "turn.failed".to_string(),
            _ => "turn.completed".to_string(),
        },
        _ => event_type.to_string(),
    }
}

fn normalize_terminal_status(raw_status: Option<&str>) -> &'static str {
    match raw_status.unwrap_or_default() {
        "final" | "completed" => "completed",
        "partial" => "partial",
        "cancelled" => "cancelled",
        "error" | "failed" => "failed",
        "degraded" => "degraded",
        "started" => "started",
        "in_progress" => "in_progress",
        "info" => "info",
        _ => "info",
    }
}

fn normalize_event_status(
    raw_status: Option<&str>,
    canonical_type: &str,
    failure: Option<&FailureInfo>,
) -> String {
    if let Some(raw_status) = raw_status {
        return normalize_terminal_status(Some(raw_status)).to_string();
    }
    if canonical_type == "runtime.degraded" {
        return "degraded".to_string();
    }
    if failure.is_some_and(|failure| failure.code == "degraded") {
        return "partial".to_string();
    }
    match canonical_type {
        "session.started" | "session.resumed" | "turn.started" => "started".to_string(),
        "turn.objective" => "in_progress".to_string(),
        "step.summary" | "artifact.created" => "completed".to_string(),
        "turn.completed" => "completed".to_string(),
        "turn.failed" => "failed".to_string(),
        "turn.cancelled" => "cancelled".to_string(),
        _ => "info".to_string(),
    }
}

fn default_actor_kind(canonical_type: &str) -> &'static str {
    match canonical_type {
        "turn.objective" | "user.message" => "user",
        "step.summary" | "turn.completed" | "turn.failed" | "turn.cancelled" => "assistant",
        "curator.note" => "curator",
        _ => "runtime",
    }
}

fn read_metadata_file(session_dir: &Path) -> Result<SessionMetadataFile, std::io::Error> {
    let meta_path = session_dir.join("metadata.json");
    if !meta_path.exists() {
        return Ok(SessionMetadataFile::default());
    }
    let content = fs::read_to_string(&meta_path)?;
    serde_json::from_str(&content)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))
}

fn write_metadata_file_sync(
    session_dir: &Path,
    metadata: &SessionMetadataFile,
) -> Result<(), std::io::Error> {
    let json = serde_json::to_string_pretty(metadata).map_err(std::io::Error::other)?;
    fs::write(session_dir.join("metadata.json"), json)
}

async fn write_metadata_file(
    session_dir: &Path,
    metadata: &SessionMetadataFile,
) -> Result<(), std::io::Error> {
    let json = serde_json::to_string_pretty(metadata).map_err(std::io::Error::other)?;
    tokio_fs::write(session_dir.join("metadata.json"), json).await
}

fn jsonl_stats(path: &Path) -> Result<(u64, usize), std::io::Error> {
    if !path.exists() {
        return Ok((0, 0));
    }
    let content = fs::read_to_string(path)?;
    let mut max_seq = 0_u64;
    let mut line_count = 0_usize;
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        line_count += 1;
        if let Ok(value) = serde_json::from_str::<Value>(trimmed) {
            if let Some(seq) = value.get("seq").and_then(Value::as_u64) {
                max_seq = max_seq.max(seq);
            }
        }
    }
    Ok((max_seq, line_count))
}

fn durability_flags(session_dir: &Path) -> SessionDurability {
    SessionDurability {
        events_jsonl_present: session_dir.join("events.jsonl").exists(),
        replay_jsonl_present: session_dir.join("replay.jsonl").exists(),
        turns_jsonl_present: session_dir.join("turns.jsonl").exists(),
        partial_records_possible: true,
    }
}

pub(crate) fn session_capabilities_value() -> Value {
    serde_json::to_value(SessionCapabilities {
        supports_events_v2: true,
        supports_replay_v2: true,
        supports_turns_v2: true,
        supports_provenance_links: true,
        supports_failure_taxonomy_v2: true,
    })
    .unwrap_or_else(|_| serde_json::json!({}))
}

pub(crate) fn session_durability_value(session_dir: &Path) -> Value {
    serde_json::to_value(durability_flags(session_dir)).unwrap_or_else(|_| serde_json::json!({}))
}

fn session_status_for_outcome(status: &str) -> &'static str {
    match status {
        "failed" => "failed",
        "cancelled" => "cancelled",
        "partial" | "resumed_from_partial" => "partial",
        _ => "active",
    }
}

async fn turn_record_exists(path: &Path, turn_id: &str) -> Result<bool, std::io::Error> {
    if !path.exists() {
        return Ok(false);
    }
    let content = tokio_fs::read_to_string(path).await?;
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let Ok(value) = serde_json::from_str::<Value>(trimmed) else {
            continue;
        };
        if value
            .get("turn_id")
            .and_then(Value::as_str)
            .is_some_and(|existing| existing == turn_id)
        {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Simple pseudo-random hex value using system time.
fn rand_hex() -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let d = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    // Mix nanos for some randomness
    (d.subsec_nanos() ^ 0xDEAD_BEEF) & 0xFFFF_FFFF
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn write_session(dir: &Path, id: &str, created_at: &str) {
        let session_dir = dir.join(id);
        fs::create_dir_all(session_dir.join("artifacts")).unwrap();
        let mut metadata = SessionMetadataFile {
            id: Some(id.to_string()),
            session_id: Some(id.to_string()),
            created_at: created_at.to_string(),
            updated_at: Some(created_at.to_string()),
            turn_count: 0,
            last_objective: None,
            status: Some("active".to_string()),
            continuity_mode: Some("resume".to_string()),
            ..SessionMetadataFile::default()
        };
        metadata.refresh_v2(&session_dir, id, created_at);
        write_metadata_file_sync(&session_dir, &metadata).unwrap();
    }

    // ── collect_sessions ──

    #[test]
    fn test_empty_dir_returns_empty() {
        let tmp = tempdir().unwrap();
        let sessions_dir = tmp.path().join("sessions");
        fs::create_dir_all(&sessions_dir).unwrap();
        let result = collect_sessions(&sessions_dir, 20);
        assert!(result.is_empty());
    }

    #[test]
    fn test_nonexistent_dir_returns_empty() {
        let tmp = tempdir().unwrap();
        let result = collect_sessions(&tmp.path().join("nope"), 20);
        assert!(result.is_empty());
    }

    #[test]
    fn test_single_session() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(&dir).unwrap();
        write_session(&dir, "20260101-120000-deadbeef", "2026-01-01T12:00:00Z");
        let result = collect_sessions(&dir, 20);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "20260101-120000-deadbeef");
    }

    #[test]
    fn test_multiple_sessions_sorted_desc() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(&dir).unwrap();
        write_session(&dir, "s1", "2026-01-01T10:00:00Z");
        write_session(&dir, "s2", "2026-01-01T12:00:00Z");
        write_session(&dir, "s3", "2026-01-01T11:00:00Z");
        let result = collect_sessions(&dir, 20);
        assert_eq!(result.len(), 3);
        assert_eq!(result[0].id, "s2");
        assert_eq!(result[1].id, "s3");
        assert_eq!(result[2].id, "s1");
    }

    #[test]
    fn test_limit_truncates() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(&dir).unwrap();
        for i in 0..5 {
            write_session(&dir, &format!("s{i}"), &format!("2026-01-01T1{i}:00:00Z"));
        }
        let result = collect_sessions(&dir, 2);
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn test_skips_dirs_without_metadata() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(dir.join("no-metadata")).unwrap();
        write_session(&dir, "has-meta", "2026-01-01T12:00:00Z");
        let result = collect_sessions(&dir, 20);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "has-meta");
    }

    #[test]
    fn test_skips_invalid_json() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let bad_dir = dir.join("bad-json");
        fs::create_dir_all(&bad_dir).unwrap();
        fs::write(bad_dir.join("metadata.json"), "not valid json").unwrap();
        write_session(&dir, "good", "2026-01-01T12:00:00Z");
        let result = collect_sessions(&dir, 20);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "good");
    }

    #[test]
    fn test_skips_non_directories() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("some-file.txt"), "not a dir").unwrap();
        write_session(&dir, "real-session", "2026-01-01T12:00:00Z");
        let result = collect_sessions(&dir, 20);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "real-session");
    }

    #[test]
    fn test_collect_sessions_reads_legacy_python_metadata() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let legacy_dir = dir.join("legacy-session");
        fs::create_dir_all(legacy_dir.join("artifacts")).unwrap();
        fs::write(
            legacy_dir.join("metadata.json"),
            r#"{
                "session_id": "legacy-session",
                "workspace": "/tmp/legacy",
                "created_at": "2026-01-01T12:00:00Z",
                "updated_at": "2026-01-01T12:05:00Z"
            }"#,
        )
        .unwrap();

        let result = collect_sessions(&dir, 20);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "legacy-session");
        assert_eq!(result[0].created_at, "2026-01-01T12:00:00Z");
        assert_eq!(result[0].turn_count, 0);
    }

    // ── create_session ──

    #[test]
    fn test_creates_session_dir() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let info = create_session(&dir, None).unwrap();
        let session_dir = dir.join(&info.id);
        assert!(session_dir.exists(), "session dir should exist");
        assert!(
            session_dir.join("artifacts").exists(),
            "artifacts/ should exist"
        );
        assert!(
            session_dir.join("metadata.json").exists(),
            "metadata.json should exist"
        );
    }

    #[test]
    fn test_session_id_format() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let info = create_session(&dir, None).unwrap();
        let re = regex::Regex::new(r"^\d{8}-\d{6}-[0-9a-f]{8}$").unwrap();
        assert!(
            re.is_match(&info.id),
            "session ID '{}' doesn't match expected format",
            info.id
        );
    }

    #[test]
    fn test_metadata_json_valid() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let info = create_session(&dir, None).unwrap();
        let meta_path = dir.join(&info.id).join("metadata.json");
        let content = fs::read_to_string(&meta_path).unwrap();
        let deserialized: SessionInfo = serde_json::from_str(&content).unwrap();
        assert_eq!(deserialized.id, info.id);
    }

    #[test]
    fn test_session_turn_count_zero() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let info = create_session(&dir, None).unwrap();
        assert_eq!(info.turn_count, 0);
        assert!(info.last_objective.is_none());
    }

    #[test]
    fn test_create_session_writes_v2_metadata_fields() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let info = create_session(&dir, None).unwrap();
        let meta_path = dir.join(&info.id).join("metadata.json");
        let value: Value = serde_json::from_str(&fs::read_to_string(meta_path).unwrap()).unwrap();
        assert_eq!(value["schema_version"], 2);
        assert_eq!(value["session_format"], SESSION_FORMAT);
        assert_eq!(value["id"], info.id);
        assert_eq!(value["session_id"], info.id);
        assert_eq!(value["status"], "active");
        assert_eq!(value["capabilities"]["supports_turns_v2"], true);
    }

    // ── delete_session helpers ──

    #[test]
    fn test_delete_session_removes_dir() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        write_session(&dir, "to-delete", "2026-01-01T12:00:00Z");
        assert!(dir.join("to-delete").exists());
        fs::remove_dir_all(dir.join("to-delete")).unwrap();
        assert!(!dir.join("to-delete").exists());
        let sessions = collect_sessions(&dir, 20);
        assert!(sessions.is_empty());
    }

    #[test]
    fn test_delete_session_does_not_affect_others() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        write_session(&dir, "keep-me", "2026-01-01T12:00:00Z");
        write_session(&dir, "delete-me", "2026-01-01T13:00:00Z");
        fs::remove_dir_all(dir.join("delete-me")).unwrap();
        let sessions = collect_sessions(&dir, 20);
        assert_eq!(sessions.len(), 1);
        assert_eq!(sessions[0].id, "keep-me");
    }

    #[tokio::test]
    async fn test_update_session_metadata_appends_turn_events_and_writes_turn_state() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let info = create_session(&dir, None).unwrap();
        let session_dir = dir.join(&info.id);

        let turn = update_session_metadata(&session_dir, "Investigate donor network")
            .await
            .unwrap();

        assert_eq!(turn.turn_id, "turn-000001");
        assert_eq!(turn.turn_index, 1);

        let metadata: Value = serde_json::from_str(
            &tokio_fs::read_to_string(session_dir.join("metadata.json"))
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(metadata["turn_count"], 1);
        assert_eq!(metadata["last_turn_id"], "turn-000001");
        assert_eq!(metadata["last_objective"], "Investigate donor network");

        let events = tokio_fs::read_to_string(session_dir.join("events.jsonl"))
            .await
            .unwrap();
        assert!(events.contains("\"event_type\":\"turn.started\""));
        assert!(events.contains("\"event_type\":\"turn.objective\""));
        assert!(events.contains("\"turn_id\":\"turn-000001\""));
    }

    #[tokio::test]
    async fn test_update_session_metadata_emits_resumed_from_partial_notice() {
        let tmp = tempdir().unwrap();
        let session_dir = tmp.path().join("legacy");
        fs::create_dir_all(session_dir.join("artifacts")).unwrap();
        fs::write(
            session_dir.join("metadata.json"),
            r#"{
                "id": "legacy",
                "session_id": "legacy",
                "created_at": "2026-01-01T12:00:00Z",
                "updated_at": "2026-01-01T12:05:00Z",
                "turn_count": 1,
                "last_turn_id": "turn-000001",
                "status": "partial"
            }"#,
        )
        .unwrap();

        let turn = update_session_metadata(&session_dir, "Resume partial turn")
            .await
            .unwrap();
        assert!(turn.resumed_from_partial);
        assert_eq!(turn.resumed_from_turn_id.as_deref(), Some("turn-000001"));

        let events = tokio_fs::read_to_string(session_dir.join("events.jsonl"))
            .await
            .unwrap();
        assert!(events.contains("\"event_type\":\"turn.resumed_from_partial\""));
    }

    #[tokio::test]
    async fn test_finalize_session_turn_appends_turn_record_and_updates_metadata() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().join("sessions");
        let info = create_session(&dir, None).unwrap();
        let session_dir = dir.join(&info.id);
        let turn = update_session_metadata(&session_dir, "Investigate Acme")
            .await
            .unwrap();

        finalize_session_turn(
            &session_dir,
            &turn,
            "Investigate Acme",
            &TurnRecordOutcome {
                status: "cancelled".to_string(),
                ended_at: "2026-01-01T12:10:00Z".to_string(),
                summary: "Task cancelled.".to_string(),
                failure: Some(FailureInfo::cancelled("Task cancelled.")),
                degraded: false,
                step_count: 2,
                tool_call_count: 1,
                replay_seq_start: 1,
                replay_seq_end: 3,
                event_end_seq: 4,
                assistant_final_ref: None,
                result_summary_ref: Some("evt-00000004".to_string()),
            },
        )
        .await
        .unwrap();

        let turns = tokio_fs::read_to_string(session_dir.join("turns.jsonl"))
            .await
            .unwrap();
        assert!(turns.contains("\"record\":\"openplanter.trace.turn.v2\""));
        assert!(turns.contains("\"turn_id\":\"turn-000001\""));
        assert!(turns.contains("\"status\":\"cancelled\""));
        assert!(turns.contains("\"failure_code\":\"cancelled\""));

        let metadata: Value = serde_json::from_str(
            &tokio_fs::read_to_string(session_dir.join("metadata.json"))
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(metadata["status"], "cancelled");
        assert_eq!(metadata["durability"]["turns_jsonl_present"], true);
    }

    #[test]
    fn test_append_session_event_writes_canonical_envelope() {
        let tmp = tempdir().unwrap();
        fs::create_dir_all(tmp.path()).unwrap();
        fs::write(
            tmp.path().join("metadata.json"),
            r#"{"id":"sid","created_at":"2026-01-01T00:00:00Z","turn_count":0}"#,
        )
        .unwrap();

        let meta = append_session_event(
            tmp.path(),
            "result",
            serde_json::json!({"status": "cancelled", "text": "Task cancelled."}),
            AppendSessionEventOptions {
                failure: Some(FailureInfo::cancelled("Task cancelled.")),
                ..AppendSessionEventOptions::default()
            },
        )
        .unwrap();

        assert_eq!(meta.seq, 1);
        assert_eq!(meta.canonical_type, "turn.cancelled");

        let events = fs::read_to_string(tmp.path().join("events.jsonl")).unwrap();
        assert!(events.contains("\"envelope\":\"openplanter.trace.event.v2\""));
        assert!(events.contains("\"event_type\":\"turn.cancelled\""));
        assert!(events.contains("\"failure\":{"));
        assert!(events.contains("\"code\":\"cancelled\""));
    }

    #[tokio::test]
    async fn test_write_and_read_session_artifact_allow_nested_relative_paths() {
        let tmp = tempdir().unwrap();
        let session_dir = tmp.path().join("session");
        fs::create_dir_all(&session_dir).unwrap();

        write_session_artifact(
            session_dir.display().to_string(),
            "artifacts/patches/example.patch".to_string(),
            "diff --git".to_string(),
        )
        .await
        .unwrap();

        let content = read_session_artifact(
            session_dir.display().to_string(),
            "artifacts/patches/example.patch".to_string(),
        )
        .await
        .unwrap();

        assert_eq!(content.as_deref(), Some("diff --git"));
        assert!(session_dir.join("artifacts/patches/example.patch").exists());
    }

    #[test]
    fn test_normalize_session_artifact_path_rejects_traversal_and_absolute_paths() {
        let tmp = tempdir().unwrap();
        let session_dir = tmp.path().join("session");
        fs::create_dir_all(&session_dir).unwrap();
        let session_dir_str = session_dir.display().to_string();

        for invalid in [
            "",
            "../escape.txt",
            "artifacts/../../escape.txt",
            "/tmp/escape.txt",
            "C:\\temp\\escape.txt",
            "\\\\server\\share\\escape.txt",
        ] {
            assert!(
                normalize_session_artifact_path(&session_dir_str, invalid).is_err(),
                "expected invalid artifact path to fail: {invalid}"
            );
        }
    }

    #[tokio::test]
    async fn test_read_session_event_by_path_returns_matching_event() {
        let tmp = tempdir().unwrap();
        tokio_fs::write(
            tmp.path().join("events.jsonl"),
            concat!(
                "{\"event_id\":\"evt-000001\",\"event_type\":\"turn.started\"}\n",
                "{\"event_id\":\"evt-000002\",\"event_type\":\"turn.completed\",\"payload\":{\"status\":\"ok\"}}\n"
            ),
        )
        .await
        .unwrap();

        let event = read_session_event_by_path(tmp.path(), "evt-000002")
            .await
            .unwrap()
            .expect("event should be present");

        assert_eq!(event["event_id"], "evt-000002");
        assert_eq!(event["event_type"], "turn.completed");
        assert_eq!(event["payload"]["status"], "ok");
    }
}
