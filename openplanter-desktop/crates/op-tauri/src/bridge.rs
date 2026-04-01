// Bridge between engine callbacks and Tauri events.
//
// TauriEmitter wraps an AppHandle and implements SolveEmitter so that
// the engine can stream events to the frontend without depending on Tauri.
//
// LoggingEmitter wraps any SolveEmitter + ReplayLogger to persist messages
// to replay.jsonl as they stream.

use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter};

use crate::commands::session::{
    AppendSessionEventOptions, AppendedEventMeta, FailureInfo, append_session_event,
};
use op_core::engine::SolveEmitter;
use op_core::events::{
    CompleteEvent, CompletionMeta, CuratorUpdateEvent, DeltaEvent, DeltaKind, ErrorEvent,
    LoopHealthEvent, LoopMetrics, LoopPhase, StepEvent, TraceEvent,
};
use op_core::session::replay::{ReplayEntry, ReplayLogger, StepToolCallEntry};

const MAX_STEP_MODEL_PREVIEW_CHARS: usize = 4 * 1024;
const MAX_TOOL_ARGS_CAPTURE_CHARS: usize = 16 * 1024;
const MAX_DELTA_LOG_CHARS: usize = 120;
const ROOT_CONVERSATION_PATH: &str = "0";

fn preview_text(text: &str, max_chars: usize) -> String {
    if text.len() <= max_chars {
        return text.to_string();
    }

    let end = text.floor_char_boundary(max_chars);
    format!("{}...[truncated {} chars]", &text[..end], text.len() - end)
}

fn append_with_cap(buffer: &mut String, text: &str, max_chars: usize, truncated: &mut bool) {
    if *truncated {
        return;
    }
    if buffer.len() >= max_chars {
        *truncated = true;
        return;
    }

    let remaining = max_chars - buffer.len();
    let end = text.floor_char_boundary(text.len().min(remaining));
    buffer.push_str(&text[..end]);
    if end < text.len() {
        *truncated = true;
    }
}

fn format_model_preview(buffer: &str, truncated: bool) -> Option<String> {
    let trimmed = buffer.trim();
    if trimmed.is_empty() {
        None
    } else if truncated {
        Some(format!("{trimmed}\n...[truncated]"))
    } else {
        Some(trimmed.to_string())
    }
}

fn classify_error(message: &str) -> FailureInfo {
    let lowered = message.to_ascii_lowercase();
    if lowered == "cancelled" || lowered.contains("cancelled") {
        return FailureInfo::cancelled("Task cancelled.");
    }
    if lowered.contains("429")
        || lowered.contains("rate limit")
        || lowered.contains("too many requests")
    {
        return FailureInfo {
            code: "rate_limit".to_string(),
            category: "transient".to_string(),
            phase: "model_completion".to_string(),
            retryable: true,
            message: message.to_string(),
            details: serde_json::json!({}),
            resumable: Some(true),
            user_visible: Some(true),
            provider: None,
            provider_code: Some("429".to_string()),
            http_status: Some(429),
        };
    }
    if lowered.contains("timeout") || lowered.contains("timed out") {
        return FailureInfo {
            code: "timeout".to_string(),
            category: "transient".to_string(),
            phase: "model_completion".to_string(),
            retryable: true,
            message: message.to_string(),
            details: serde_json::json!({}),
            resumable: Some(true),
            user_visible: Some(true),
            provider: None,
            provider_code: None,
            http_status: None,
        };
    }
    FailureInfo {
        code: "unknown_error".to_string(),
        category: "unknown".to_string(),
        phase: "session_finalize".to_string(),
        retryable: false,
        message: message.to_string(),
        details: serde_json::json!({}),
        resumable: Some(true),
        user_visible: Some(true),
        provider: None,
        provider_code: None,
        http_status: None,
    }
}

fn degraded_failure(result: &str, completion: Option<&CompletionMeta>) -> FailureInfo {
    let reason = completion
        .map(|completion| completion.reason.as_str())
        .filter(|reason| !reason.is_empty())
        .unwrap_or("partial_result");
    let mut failure = FailureInfo::degraded(format!("Solve completed partially: {reason}"));
    failure.details = serde_json::json!({
        "reason": reason,
        "result_preview": preview_text(result, 240),
    });
    failure
}

pub struct TauriEmitter {
    handle: AppHandle,
}

impl TauriEmitter {
    pub fn new(handle: AppHandle) -> Self {
        Self { handle }
    }
}

impl SolveEmitter for TauriEmitter {
    fn emit_trace(&self, message: &str) {
        eprintln!("[bridge] trace: {message}");
        let _ = self.handle.emit(
            "agent:trace",
            TraceEvent {
                message: message.to_string(),
            },
        );
    }

    fn emit_delta(&self, event: DeltaEvent) {
        match event.kind {
            DeltaKind::ToolCallArgs => eprintln!(
                "[bridge] delta: kind={:?} len={} preview={:?}",
                event.kind,
                event.text.len(),
                preview_text(&event.text, MAX_DELTA_LOG_CHARS)
            ),
            _ if event.text.len() > MAX_DELTA_LOG_CHARS => eprintln!(
                "[bridge] delta: kind={:?} len={} preview={:?}",
                event.kind,
                event.text.len(),
                preview_text(&event.text, MAX_DELTA_LOG_CHARS)
            ),
            _ => eprintln!(
                "[bridge] delta: kind={:?} text={:?}",
                event.kind, event.text
            ),
        }
        let _ = self.handle.emit("agent:delta", event);
    }

    fn emit_step(&self, event: StepEvent) {
        eprintln!(
            "[bridge] step: depth={} step={} is_final={}",
            event.depth, event.step, event.is_final
        );
        let _ = self.handle.emit("agent:step", event);
    }

    fn emit_complete(
        &self,
        result: &str,
        loop_metrics: Option<LoopMetrics>,
        completion: Option<CompletionMeta>,
    ) {
        eprintln!("[bridge] complete: {result}");
        let _ = self.handle.emit(
            "agent:complete",
            CompleteEvent {
                result: result.to_string(),
                loop_metrics,
                completion,
            },
        );
    }

    fn emit_error(&self, message: &str) {
        eprintln!("[bridge] error: {message}");
        let failure = classify_error(message);
        let _ = self.handle.emit(
            "agent:error",
            ErrorEvent {
                message: message.to_string(),
                failure_code: Some(failure.code),
                failure_phase: Some(failure.phase),
            },
        );
    }

    fn emit_loop_health(
        &self,
        depth: u32,
        step: u32,
        conversation_path: Option<String>,
        phase: LoopPhase,
        metrics: LoopMetrics,
        is_final: bool,
    ) {
        let _ = self.handle.emit(
            "agent:loop-health",
            LoopHealthEvent {
                depth,
                step,
                conversation_path,
                phase,
                metrics,
                is_final,
            },
        );
    }

    fn emit_curator_update(&self, summary: &str, files_changed: u32) {
        eprintln!("[bridge] curator update: {summary} ({files_changed} files)");
        let _ = self.handle.emit(
            "agent:curator-update",
            CuratorUpdateEvent {
                summary: summary.to_string(),
                files_changed,
            },
        );
    }
}

/// Active turn context shared with the replay envelope writer.
#[derive(Debug, Clone)]
pub struct TurnContext {
    pub turn_id: String,
    pub session_id: String,
    pub event_start_seq: u64,
}

/// Wraps any SolveEmitter + ReplayLogger to persist events as they stream.
///
/// Collects streaming text and tool calls during a step, then logs
/// the full step summary and final assistant message to replay.jsonl.
pub struct LoggingEmitter<E: SolveEmitter> {
    inner: E,
    replay: Arc<tokio::sync::Mutex<ReplayLogger>>,
    session_dir: PathBuf,
    /// Per-conversation-path streaming state used to build replay step summaries.
    step_states: Mutex<HashMap<String, StepCaptureState>>,
    /// Final completion payload emitted during the solve.
    terminal: Mutex<Option<TerminalSnapshot>>,
    observations: Mutex<Vec<String>>,
    last_loop_metrics: Mutex<Option<LoopMetrics>>,
    turn_context: Arc<std::sync::Mutex<Option<TurnContext>>>,
    /// Provider name for model attribution in events.
    provider: Option<String>,
    /// Model name for model attribution in events.
    model: Option<String>,
}

/// A tool call being accumulated during streaming.
struct PendingToolCall {
    name: String,
    key_arg: String,
    raw_args: String,
    args_truncated: bool,
    start_time: std::time::Instant,
}

#[derive(Default)]
struct StepCaptureState {
    streaming_buf: String,
    streaming_truncated: bool,
    step_tool_calls: Vec<PendingToolCall>,
    current_tool: String,
    current_args_buf: String,
    current_args_truncated: bool,
}

#[derive(Clone)]
pub enum TerminalStatus {
    Final,
    Partial,
    Cancelled,
    Error,
}

#[derive(Clone)]
pub struct TerminalSnapshot {
    pub status: TerminalStatus,
    pub result: String,
    pub loop_metrics: Option<LoopMetrics>,
    pub completion: Option<CompletionMeta>,
    pub result_event: Option<AppendedEventMeta>,
    pub failure: Option<FailureInfo>,
    pub degraded: bool,
    pub observations: Vec<String>,
}

fn terminal_status_label(status: &TerminalStatus) -> &'static str {
    match status {
        TerminalStatus::Final => "final",
        TerminalStatus::Partial => "partial",
        TerminalStatus::Cancelled => "cancelled",
        TerminalStatus::Error => "error",
    }
}

/// Key argument names for tool call display (mirrors frontend KEY_ARGS).
fn extract_key_arg(tool_name: &str, args_json: &str) -> Option<String> {
    let key_name = match tool_name {
        "read_file" | "write_file" | "edit_file" | "apply_patch" | "hashline_edit" => Some("path"),
        "list_files" => Some("directory"),
        "run_shell" | "run_shell_bg" => Some("command"),
        "kill_shell_bg" => Some("pid"),
        "web_search" => Some("query"),
        "fetch_url" => Some("url"),
        _ => None,
    };
    if let Ok(value) = serde_json::from_str::<serde_json::Value>(args_json) {
        if let Some(key) = key_name {
            if let Some(found) = value
                .get(key)
                .and_then(preview_value)
                .filter(|value| !value.is_empty())
            {
                return Some(found);
            }
        }
        return first_informative_value(&value);
    }
    if let Some(key) = key_name {
        let pattern = format!("\"{}\"\\s*:\\s*\"([^\"]*)\"?", regex::escape(key));
        let re = regex::Regex::new(&pattern).ok()?;
        if let Some(captures) = re.captures(args_json) {
            return captures.get(1).map(|capture| capture.as_str().to_string());
        }
    }
    let re = regex::Regex::new(r#""[^"]+"\s*:\s*"([^"]+)""#).ok()?;
    re.captures(args_json)
        .and_then(|captures| captures.get(1))
        .map(|capture| capture.as_str().to_string())
}

fn preview_value(value: &serde_json::Value) -> Option<String> {
    match value {
        serde_json::Value::String(text) => {
            let trimmed = text.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.chars().take(60).collect())
            }
        }
        serde_json::Value::Array(items) => {
            let collected = items
                .iter()
                .filter_map(|item| item.as_str().map(str::trim).filter(|text| !text.is_empty()))
                .take(3)
                .collect::<Vec<_>>();
            if collected.is_empty() {
                None
            } else {
                Some(collected.join(", "))
            }
        }
        serde_json::Value::Number(number) => Some(number.to_string()),
        _ => None,
    }
}

fn first_informative_value(value: &serde_json::Value) -> Option<String> {
    let object = value.as_object()?;
    object.values().find_map(preview_value)
}

impl<E: SolveEmitter> LoggingEmitter<E> {
    pub fn new(
        inner: E,
        replay: ReplayLogger,
        session_dir: PathBuf,
        provider: Option<String>,
        model: Option<String>,
    ) -> Self {
        Self {
            inner,
            replay: Arc::new(tokio::sync::Mutex::new(replay)),
            session_dir,
            step_states: Mutex::new(HashMap::new()),
            terminal: Mutex::new(None),
            observations: Mutex::new(Vec::new()),
            last_loop_metrics: Mutex::new(None),
            turn_context: Arc::new(std::sync::Mutex::new(None)),
            provider,
            model,
        }
    }

    pub fn take_terminal_snapshot(&self) -> Option<TerminalSnapshot> {
        self.terminal.lock().unwrap().take()
    }

    fn current_observations(&self) -> Vec<String> {
        self.observations.lock().unwrap().clone()
    }

    fn store_terminal_snapshot(&self, snapshot: TerminalSnapshot) -> bool {
        let mut terminal = self.terminal.lock().unwrap();
        if terminal.is_some() {
            return false;
        }
        *terminal = Some(snapshot);
        true
    }

    fn push_observation(&self, message: String) {
        let mut observations = self.observations.lock().unwrap();
        observations.push(message);
        if observations.len() > 400 {
            let drain_count = observations.len() - 400;
            observations.drain(0..drain_count);
        }
    }

    fn append_event_value(
        &self,
        event_type: &str,
        payload: serde_json::Value,
        mut options: AppendSessionEventOptions,
    ) -> Option<AppendedEventMeta> {
        // Merge provider/model from self if not already set in options
        if options.provider.is_none() {
            options.provider = self.provider.clone();
        }
        if options.model.is_none() {
            options.model = self.model.clone();
        }
        match append_session_event(&self.session_dir, event_type, payload, options) {
            Ok(meta) => Some(meta),
            Err(err) => {
                eprintln!("[bridge] failed to append {event_type} event: {err}");
                None
            }
        }
    }

    fn write_patch_artifact(
        &self,
        depth: u32,
        step: u32,
        index: usize,
        patch_text: &str,
    ) -> Option<String> {
        let patch_dir = self.session_dir.join("artifacts").join("patches");
        if let Err(err) = fs::create_dir_all(&patch_dir) {
            eprintln!("[bridge] failed to create patch artifact dir: {err}");
            return None;
        }
        let name = format!("patch-d{depth}-s{step}-{}.patch", index + 1);
        let path = patch_dir.join(&name);
        if let Err(err) = fs::write(&path, patch_text) {
            eprintln!("[bridge] failed to write patch artifact: {err}");
            return None;
        }
        Some(format!("artifacts/patches/{name}"))
    }

    fn flush_partial_replay_on_cancel(&self) {
        let pending = {
            let mut step_states = self.step_states.lock().unwrap();
            step_states.drain().collect::<Vec<_>>()
        };
        if pending.is_empty() {
            return;
        }
        let replay = self.replay.clone();
        tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(async {
                let mut replay = replay.lock().await;
                for (conversation_path, state) in pending {
                    let preview =
                        format_model_preview(&state.streaming_buf, state.streaming_truncated)
                            .unwrap_or_else(|| "Task cancelled.".to_string());
                    let step_tools: Vec<StepToolCallEntry> = state
                        .step_tool_calls
                        .iter()
                        .map(|tc| StepToolCallEntry {
                            name: tc.name.clone(),
                            key_arg: tc.key_arg.clone(),
                            elapsed: tc.start_time.elapsed().as_millis() as u64,
                        })
                        .collect();
                    let entry = ReplayEntry {
                        seq: 0,
                        timestamp: String::new(),
                        role: "assistant-partial".into(),
                        content: preview.clone(),
                        tool_name: None,
                        is_rendered: Some(false),
                        step_number: None,
                        step_depth: None,
                        conversation_path: Some(conversation_path),
                        step_tokens_in: None,
                        step_tokens_out: None,
                        step_elapsed: None,
                        step_model_preview: Some(preview),
                        step_tool_calls: if step_tools.is_empty() {
                            None
                        } else {
                            Some(step_tools)
                        },
                    };
                    if let Err(err) = replay.append(entry).await {
                        eprintln!("[bridge] failed to log cancel partial replay: {err}");
                    }
                }
            });
        });
    }

    /// Set the active turn context for replay envelope enrichment.
    pub fn set_turn_context(&self, ctx: TurnContext) {
        *self.turn_context.lock().unwrap() = Some(ctx);
    }

    /// Clear the active turn context (called at turn end).
    pub fn clear_turn_context(&self) {
        *self.turn_context.lock().unwrap() = None;
    }

    /// Snapshot the current turn context, if any.
    fn snapshot_turn_context(&self) -> Option<TurnContext> {
        self.turn_context.lock().unwrap().clone()
    }

    /// Wrap a ReplayEntry in a v2 envelope for structured trace logging.
    fn wrap_replay_v2_envelope(
        &self,
        entry: &ReplayEntry,
        turn_ctx: Option<&TurnContext>,
        shared_event_id: Option<&str>,
    ) -> serde_json::Value {
        let session_id = turn_ctx.map(|c| c.session_id.as_str()).unwrap_or("unknown");
        let event_id = shared_event_id
            .map(|s| serde_json::Value::String(s.to_string()))
            .unwrap_or(serde_json::Value::Null);

        serde_json::json!({
            "schema_version": 2,
            "envelope": "openplanter.trace.replay.v2",
            "event_id": event_id,
            "session_id": session_id,
            "turn_id": turn_ctx.as_ref().map(|c| c.turn_id.as_str()),
            "seq": entry.seq,
            "recorded_at": &entry.timestamp,
            "event_type": match entry.role.as_str() {
                "step-summary" => "step.summary",
                "assistant" => "assistant.message",
                "assistant-partial" => "assistant.partial",
                "assistant-cancelled" => "turn.cancelled",
                "system" => "system.message",
                "user" => "user.message",
                "curator" => "curator.note",
                _ => "assistant.message",
            },
            "channel": "replay",
            "status": match entry.role.as_str() {
                "assistant-cancelled" => "cancelled",
                "assistant-partial" => "partial",
                _ => "completed",
            },
            "actor": {
                "kind": match entry.role.as_str() {
                    "user" => "user",
                    "system" => "runtime",
                    "curator" => "runtime",
                    _ => "assistant",
                },
                "runtime_family": "desktop",
            },
            "payload": {
                "text": &entry.content,
                "step_number": entry.step_number,
                "step_depth": entry.step_depth,
                "conversation_path": &entry.conversation_path,
                "step_tokens_in": entry.step_tokens_in,
                "step_tokens_out": entry.step_tokens_out,
                "step_elapsed": entry.step_elapsed,
                "step_model_preview": &entry.step_model_preview,
                "step_tool_calls": &entry.step_tool_calls,
            },
            "provenance": {
                "record_locator": serde_json::Value::Null,
                "source_refs": serde_json::json!([]),
                "evidence_refs": serde_json::json!([]),
            },
            "compat": {
                "legacy_role": &entry.role,
                "legacy_kind": "replay",
                "source_schema": "desktop-replay-v1",
            },
        })
    }

    fn append_replay_entry(
        &self,
        entry: ReplayEntry,
        context: &'static str,
        shared_event_id: Option<&str>,
    ) {
        let replay = self.replay.clone();
        let turn_ctx = self.snapshot_turn_context();
        tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(async {
                let envelope =
                    self.wrap_replay_v2_envelope(&entry, turn_ctx.as_ref(), shared_event_id);
                if let Err(err) = replay.lock().await.append_raw(envelope).await {
                    eprintln!("[bridge] failed to log {context}: {err}");
                }
            });
        });
    }

    fn terminal_payload(
        &self,
        status: &TerminalStatus,
        result: &str,
        loop_metrics: Option<&LoopMetrics>,
        completion: Option<&CompletionMeta>,
        failure: Option<&FailureInfo>,
    ) -> serde_json::Value {
        serde_json::json!({
            "status": terminal_status_label(status),
            "text": result,
            "loop_metrics": loop_metrics,
            "completion": completion,
            "failure_code": failure.map(|failure| failure.code.clone()),
            "failure_phase": failure.map(|failure| failure.phase.clone()),
        })
    }
}

impl<E: SolveEmitter> SolveEmitter for LoggingEmitter<E> {
    fn emit_trace(&self, message: &str) {
        self.push_observation(format!("[trace] {message}"));
        self.append_event_value(
            "trace",
            serde_json::json!({ "message": message }),
            AppendSessionEventOptions {
                actor_kind: Some("runtime".to_string()),
                ..AppendSessionEventOptions::default()
            },
        );
        self.inner.emit_trace(message);
    }

    fn emit_delta(&self, event: DeltaEvent) {
        // Accumulate streaming data for step summary logging (sync — no I/O)
        let conversation_path = event
            .conversation_path
            .clone()
            .unwrap_or_else(|| ROOT_CONVERSATION_PATH.to_string());
        let mut step_states = self.step_states.lock().unwrap();
        let state = step_states.entry(conversation_path).or_default();
        match event.kind {
            DeltaKind::Text => {
                append_with_cap(
                    &mut state.streaming_buf,
                    &event.text,
                    MAX_STEP_MODEL_PREVIEW_CHARS,
                    &mut state.streaming_truncated,
                );
            }
            DeltaKind::ToolCallStart => {
                let tool_name = event.text.clone();
                state.current_tool = tool_name.clone();
                state.current_args_buf = String::new();
                state.current_args_truncated = false;
                state.step_tool_calls.push(PendingToolCall {
                    name: tool_name,
                    key_arg: String::new(),
                    raw_args: String::new(),
                    args_truncated: false,
                    start_time: std::time::Instant::now(),
                });
            }
            DeltaKind::ToolCallArgs => {
                append_with_cap(
                    &mut state.current_args_buf,
                    &event.text,
                    MAX_TOOL_ARGS_CAPTURE_CHARS,
                    &mut state.current_args_truncated,
                );
                if let Some(last) = state.step_tool_calls.last_mut() {
                    last.raw_args = state.current_args_buf.clone();
                    last.args_truncated = state.current_args_truncated;
                }
                if let Some(key_arg) = extract_key_arg(&state.current_tool, &state.current_args_buf)
                {
                    if let Some(last) = state.step_tool_calls.last_mut() {
                        last.key_arg = key_arg;
                    }
                }
            }
            DeltaKind::Thinking => {}
        }
        drop(step_states);

        self.inner.emit_delta(event);
    }

    fn emit_step(&self, event: StepEvent) {
        let conversation_path = event
            .conversation_path
            .clone()
            .unwrap_or_else(|| ROOT_CONVERSATION_PATH.to_string());
        let state = self
            .step_states
            .lock()
            .unwrap()
            .remove(&conversation_path)
            .unwrap_or_default();

        let model_preview = format_model_preview(&state.streaming_buf, state.streaming_truncated);

        let step_tools: Vec<StepToolCallEntry> = state
            .step_tool_calls
            .iter()
            .map(|tc| StepToolCallEntry {
                name: tc.name.clone(),
                key_arg: tc.key_arg.clone(),
                elapsed: tc.start_time.elapsed().as_millis() as u64,
            })
            .collect();

        let entry = ReplayEntry {
            seq: 0,
            timestamp: String::new(),
            role: "step-summary".into(),
            content: String::new(),
            tool_name: None,
            is_rendered: None,
            step_number: Some(event.step),
            step_depth: Some(event.depth),
            conversation_path: Some(conversation_path),
            step_tokens_in: Some(event.tokens.input_tokens),
            step_tokens_out: Some(event.tokens.output_tokens),
            step_elapsed: Some(event.elapsed_ms),
            step_model_preview: model_preview.clone(),
            step_tool_calls: if step_tools.is_empty() {
                None
            } else {
                Some(step_tools)
            },
        };

        let mut payload = serde_json::to_value(&event).unwrap_or_else(|_| {
            serde_json::json!({
                "depth": event.depth,
                "step": event.step,
                "is_final": event.is_final,
            })
        });
        if let serde_json::Value::Object(ref mut obj) = payload {
            obj.insert(
                "step_model_preview".to_string(),
                model_preview
                    .as_ref()
                    .map(|value| serde_json::Value::String(value.clone()))
                    .unwrap_or(serde_json::Value::Null),
            );
            obj.insert(
                "step_tool_calls".to_string(),
                serde_json::to_value(
                    &state
                        .step_tool_calls
                        .iter()
                        .map(|tc| {
                            serde_json::json!({
                                "name": tc.name.clone(),
                                "key_arg": tc.key_arg.clone(),
                                "args_truncated": tc.args_truncated,
                            })
                        })
                        .collect::<Vec<_>>(),
                )
                .unwrap_or(serde_json::Value::Null),
            );
        }

        // Collect artifact paths first by pre-scanning step_tool_calls and writing patches
        let mut artifact_refs: Vec<String> = Vec::new();
        let mut patch_index = 0usize;
        for tc in state.step_tool_calls.iter() {
            if tc.name != "apply_patch" || tc.args_truncated || tc.raw_args.trim().is_empty() {
                continue;
            }
            let Ok(value) = serde_json::from_str::<serde_json::Value>(&tc.raw_args) else {
                continue;
            };
            let Some(patch_text) = value.get("patch").and_then(|item| item.as_str()) else {
                continue;
            };
            if patch_text.trim().is_empty() {
                continue;
            }
            if let Some(path) =
                self.write_patch_artifact(event.depth, event.step, patch_index, patch_text)
            {
                artifact_refs.push(format!("artifact:{path}"));
                patch_index += 1;
            }
        }

        // Write step event with evidence_refs
        let event_meta = self.append_event_value(
            "step",
            payload,
            AppendSessionEventOptions {
                status: Some("completed".to_string()),
                actor_kind: Some("assistant".to_string()),
                evidence_refs: artifact_refs.clone(),
                ..AppendSessionEventOptions::default()
            },
        );
        let shared_id = event_meta.as_ref().map(|m| m.event_id.as_str());

        // Write replay entry with shared event_id
        self.append_replay_entry(entry, "step", shared_id);

        // Write artifact events (patches already written above)
        for ref_path in &artifact_refs {
            let path = ref_path.strip_prefix("artifact:").unwrap_or(ref_path);
            self.append_event_value(
                "artifact",
                serde_json::json!({
                    "kind": "patch",
                    "path": path,
                    "depth": event.depth,
                    "step": event.step,
                    "tool": "apply_patch",
                }),
                AppendSessionEventOptions {
                    status: Some("completed".to_string()),
                    actor_kind: Some("runtime".to_string()),
                    ..AppendSessionEventOptions::default()
                },
            );
        }

        if let Some(preview) = model_preview.as_ref() {
            self.push_observation(format!(
                "[step d{} s{}] {}",
                event.depth,
                event.step,
                preview_text(preview, 400)
            ));
        }

        self.inner.emit_step(event);
    }

    fn emit_complete(
        &self,
        result: &str,
        loop_metrics: Option<LoopMetrics>,
        completion: Option<CompletionMeta>,
    ) {
        if self.terminal.lock().unwrap().is_some() {
            self.inner.emit_complete(result, loop_metrics, completion);
            return;
        }
        *self.last_loop_metrics.lock().unwrap() = loop_metrics.clone();
        let status = if completion
            .as_ref()
            .is_some_and(|meta| meta.kind.eq_ignore_ascii_case("partial"))
        {
            TerminalStatus::Partial
        } else {
            TerminalStatus::Final
        };
        let failure = matches!(status, TerminalStatus::Partial)
            .then(|| degraded_failure(result, completion.as_ref()));
        self.push_observation(format!(
            "[result {}] {}",
            terminal_status_label(&status),
            preview_text(result, 400)
        ));

        // Collect source_refs from turn context if available
        let turn_ctx = self.snapshot_turn_context();
        let source_refs = turn_ctx
            .as_ref()
            .map(|ctx| {
                vec![format!(
                    "event_span:{}:{}",
                    ctx.session_id, ctx.event_start_seq
                )]
            })
            .unwrap_or_default();

        // Write event first to get canonical event_id
        let result_event = self.append_event_value(
            "result",
            self.terminal_payload(
                &status,
                result,
                loop_metrics.as_ref(),
                completion.as_ref(),
                failure.as_ref(),
            ),
            AppendSessionEventOptions {
                status: Some(terminal_status_label(&status).to_string()),
                failure: failure.clone(),
                actor_kind: Some("assistant".to_string()),
                source_refs,
                ..AppendSessionEventOptions::default()
            },
        );
        let shared_id = result_event.as_ref().map(|m| m.event_id.as_str());

        let entry = ReplayEntry {
            seq: 0,
            timestamp: String::new(),
            role: "assistant".into(),
            content: result.to_string(),
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
        };

        // Write replay entry with shared event_id
        self.append_replay_entry(entry, "complete", shared_id);
        let snapshot = TerminalSnapshot {
            status: status.clone(),
            result: result.to_string(),
            loop_metrics: loop_metrics.clone(),
            completion: completion.clone(),
            result_event,
            failure,
            degraded: matches!(status, TerminalStatus::Partial),
            observations: self.current_observations(),
        };
        let _ = self.store_terminal_snapshot(snapshot);

        self.inner.emit_complete(result, loop_metrics, completion);
    }

    fn emit_error(&self, message: &str) {
        if self.terminal.lock().unwrap().is_some() {
            self.inner.emit_error(message);
            return;
        }
        self.push_observation(format!("[error] {message}"));
        let is_cancelled = message == "Cancelled";
        let status = if is_cancelled {
            TerminalStatus::Cancelled
        } else {
            TerminalStatus::Error
        };
        let failure = classify_error(message);
        let result_text = if is_cancelled {
            "Task cancelled.".to_string()
        } else {
            message.to_string()
        };
        let mut metrics = self.last_loop_metrics.lock().unwrap().clone();
        if is_cancelled {
            self.flush_partial_replay_on_cancel();
            if metrics.is_none() {
                metrics = Some(LoopMetrics::default());
            }
            if let Some(ref mut current) = metrics {
                if current.termination_reason.is_empty() {
                    current.termination_reason = "cancelled".to_string();
                }
            }
            self.append_replay_entry(
                ReplayEntry {
                    seq: 0,
                    timestamp: String::new(),
                    role: "assistant-cancelled".into(),
                    content: result_text.clone(),
                    tool_name: None,
                    is_rendered: Some(false),
                    step_number: None,
                    step_depth: None,
                    conversation_path: None,
                    step_tokens_in: None,
                    step_tokens_out: None,
                    step_elapsed: None,
                    step_model_preview: None,
                    step_tool_calls: None,
                },
                "cancelled",
                None,
            );
        }
        let result_event = self.append_event_value(
            "result",
            self.terminal_payload(
                &status,
                &result_text,
                metrics.as_ref(),
                None,
                Some(&failure),
            ),
            AppendSessionEventOptions {
                status: Some(terminal_status_label(&status).to_string()),
                failure: Some(failure.clone()),
                actor_kind: Some("assistant".to_string()),
                ..AppendSessionEventOptions::default()
            },
        );
        let snapshot = TerminalSnapshot {
            status: status.clone(),
            result: result_text.clone(),
            loop_metrics: metrics.clone(),
            completion: None,
            result_event,
            failure: Some(failure),
            degraded: false,
            observations: self.current_observations(),
        };
        let _ = self.store_terminal_snapshot(snapshot);
        self.inner.emit_error(message);
    }

    fn emit_loop_health(
        &self,
        depth: u32,
        step: u32,
        conversation_path: Option<String>,
        phase: LoopPhase,
        metrics: LoopMetrics,
        is_final: bool,
    ) {
        *self.last_loop_metrics.lock().unwrap() = Some(metrics.clone());
        self.inner
            .emit_loop_health(depth, step, conversation_path, phase, metrics, is_final);
    }

    fn emit_curator_update(&self, summary: &str, files_changed: u32) {
        self.push_observation(format!(
            "[curator] {} ({files_changed} files)",
            preview_text(summary, 300)
        ));
        // Log curator update to replay
        let entry = ReplayEntry {
            seq: 0,
            timestamp: String::new(),
            role: "curator".into(),
            content: summary.to_string(),
            tool_name: None,
            is_rendered: None,
            step_number: None,
            step_depth: None,
            conversation_path: None,
            step_tokens_in: None,
            step_tokens_out: None,
            step_elapsed: None,
            step_model_preview: None,
            step_tool_calls: None,
        };

        self.append_replay_entry(entry, "curator update", None);

        self.inner.emit_curator_update(summary, files_changed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use op_core::engine::demo_solve;
    use op_core::session::replay::ReplayLogger;
    use std::collections::HashSet;
    use tempfile::tempdir;
    use tokio_util::sync::CancellationToken;

    /// No-op emitter for testing LoggingEmitter without Tauri.
    struct NullEmitter;

    impl SolveEmitter for NullEmitter {
        fn emit_trace(&self, _: &str) {}
        fn emit_delta(&self, _: DeltaEvent) {}
        fn emit_step(&self, _: StepEvent) {}
        fn emit_complete(&self, _: &str, _: Option<LoopMetrics>, _: Option<CompletionMeta>) {}
        fn emit_error(&self, _: &str) {}
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_logging_emitter_persists_replay() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);
        let token = CancellationToken::new();

        demo_solve("Test persistence", &emitter, token).await;

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert!(
            entries.len() >= 2,
            "expected at least 2 replay entries (step-summary + assistant), got {}",
            entries.len()
        );

        let step = entries.iter().find(|e| e.role == "step-summary");
        assert!(step.is_some(), "expected a step-summary entry");
        let step = step.unwrap();
        assert_eq!(step.step_number, Some(1));
        assert!(step.step_tokens_in.is_some());
        assert!(step.step_model_preview.is_some());
        assert!(
            step.step_model_preview
                .as_ref()
                .unwrap()
                .contains("Test persistence")
        );

        let assistant = entries.iter().find(|e| e.role == "assistant");
        assert!(assistant.is_some(), "expected an assistant entry");
        assert!(assistant.unwrap().content.contains("Test persistence"));
        assert_eq!(assistant.unwrap().is_rendered, Some(true));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_logging_emitter_writes_turn_context_into_replay_envelopes() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);
        emitter.set_turn_context(TurnContext {
            turn_id: "turn-000123".to_string(),
            session_id: "session-xyz".to_string(),
            event_start_seq: 7,
        });

        let token = CancellationToken::new();
        demo_solve("Turn context test", &emitter, token).await;

        let raw = std::fs::read_to_string(tmp.path().join("replay.jsonl")).unwrap();
        let lines = raw
            .lines()
            .filter(|line| !line.trim().is_empty())
            .collect::<Vec<_>>();
        assert!(!lines.is_empty(), "expected replay envelopes to be written");

        let first: serde_json::Value = serde_json::from_str(lines[0]).unwrap();
        assert_eq!(first["session_id"], "session-xyz");
        assert_eq!(first["turn_id"], "turn-000123");
        assert_eq!(first["channel"], "replay");
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_logging_emitter_fallback_event_ids_use_final_seq() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);
        emitter.set_turn_context(TurnContext {
            turn_id: "turn-000123".to_string(),
            session_id: "session-xyz".to_string(),
            event_start_seq: 7,
        });

        emitter.emit_curator_update("First curator note", 1);
        emitter.emit_curator_update("Second curator note", 2);
        emitter.emit_error("Cancelled");

        let raw = std::fs::read_to_string(tmp.path().join("replay.jsonl")).unwrap();
        let envelopes = raw
            .lines()
            .filter(|line| !line.trim().is_empty())
            .map(|line| serde_json::from_str::<serde_json::Value>(line).unwrap())
            .collect::<Vec<_>>();
        assert_eq!(envelopes.len(), 3);

        let event_ids = envelopes
            .iter()
            .map(|value| value["event_id"].as_str().unwrap().to_string())
            .collect::<Vec<_>>();
        let unique = event_ids.iter().cloned().collect::<HashSet<_>>();
        assert_eq!(unique.len(), event_ids.len());
        assert!(!event_ids.iter().any(|id| id.ends_with(":000000")));

        for envelope in &envelopes {
            let seq = envelope["seq"].as_u64().unwrap();
            assert_eq!(envelope["session_id"], "session-xyz");
            assert_eq!(envelope["event_id"], format!("evt:session-xyz:{seq:06}"));
        }
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_logging_emitter_cancel_no_crash() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);
        let token = CancellationToken::new();
        token.cancel();

        demo_solve("Cancel test", &emitter, token).await;

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert!(entries.len() <= 2);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_full_session_roundtrip() {
        let tmp = tempdir().unwrap();

        // 1. Log user message
        let mut replay = ReplayLogger::new(tmp.path());
        replay
            .append(ReplayEntry {
                seq: 0,
                timestamp: String::new(),
                role: "user".into(),
                content: "Roundtrip test".into(),
                tool_name: None,
                is_rendered: None,
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
            .unwrap();

        // 2. Run demo_solve through LoggingEmitter
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);
        let token = CancellationToken::new();
        demo_solve("Roundtrip test", &emitter, token).await;

        // 3. Read back full conversation
        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert!(
            entries.len() >= 3,
            "expected user + step-summary + assistant, got {}",
            entries.len()
        );

        assert_eq!(entries[0].role, "user");
        assert_eq!(entries[0].content, "Roundtrip test");
        assert_eq!(entries[0].seq, 1);

        assert_eq!(entries[1].role, "step-summary");
        assert_eq!(entries[1].seq, 2);

        assert_eq!(entries[2].role, "assistant");
        assert_eq!(entries[2].seq, 3);
        assert!(entries[2].content.contains("Roundtrip test"));

        for (i, entry) in entries.iter().enumerate() {
            assert_eq!(entry.seq, (i + 1) as u64);
        }
    }

    #[derive(Default)]
    struct CapturingEmitter {
        deltas: Arc<Mutex<Vec<DeltaEvent>>>,
    }

    impl SolveEmitter for CapturingEmitter {
        fn emit_trace(&self, _: &str) {}
        fn emit_delta(&self, event: DeltaEvent) {
            self.deltas.lock().unwrap().push(event);
        }
        fn emit_step(&self, _: StepEvent) {}
        fn emit_complete(&self, _: &str, _: Option<LoopMetrics>, _: Option<CompletionMeta>) {}
        fn emit_error(&self, _: &str) {}
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_logging_emitter_caps_model_preview_and_preserves_deltas() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let inner = CapturingEmitter::default();
        let deltas = inner.deltas.clone();
        let emitter = LoggingEmitter::new(inner, replay, tmp.path().to_path_buf(), None, None);
        let big_text = "x".repeat(MAX_STEP_MODEL_PREVIEW_CHARS + 256);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::Text,
            text: big_text.clone(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_step(StepEvent {
            depth: 0,
            step: 1,
            conversation_path: Some("0".into()),
            tool_name: None,
            tokens: Default::default(),
            elapsed_ms: 1,
            is_final: false,
            loop_phase: None,
            loop_metrics: None,
        });

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        let step = entries
            .iter()
            .find(|entry| entry.role == "step-summary")
            .unwrap();
        let preview = step.step_model_preview.as_ref().unwrap();
        assert!(preview.contains("[truncated]"));
        assert!(preview.len() < big_text.len());

        let captured = deltas.lock().unwrap();
        assert_eq!(captured.len(), 1);
        assert_eq!(captured[0].text, big_text);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_logging_emitter_caps_tool_args_buffer_and_keeps_key_arg() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let inner = CapturingEmitter::default();
        let deltas = inner.deltas.clone();
        let emitter = LoggingEmitter::new(inner, replay, tmp.path().to_path_buf(), None, None);
        let filler = "x".repeat(MAX_TOOL_ARGS_CAPTURE_CHARS + 512);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "read_file".to_string(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: "{\"path\":\"foo.md\",\"other\":\"".to_string(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: filler.clone(),
            conversation_path: Some("0".into()),
        });

        let step_states = emitter.step_states.lock().unwrap();
        let root_state = step_states.get(ROOT_CONVERSATION_PATH).unwrap();
        assert!(root_state.current_args_buf.len() <= MAX_TOOL_ARGS_CAPTURE_CHARS);
        assert!(root_state.current_args_truncated);
        drop(step_states);

        emitter.emit_step(StepEvent {
            depth: 0,
            step: 1,
            conversation_path: Some("0".into()),
            tool_name: Some("read_file".into()),
            tokens: Default::default(),
            elapsed_ms: 1,
            is_final: false,
            loop_phase: None,
            loop_metrics: None,
        });

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        let step = entries
            .iter()
            .find(|entry| entry.role == "step-summary")
            .unwrap();
        let tool_calls = step.step_tool_calls.as_ref().unwrap();
        assert_eq!(tool_calls[0].key_arg, "foo.md");

        let captured = deltas.lock().unwrap();
        assert_eq!(captured.len(), 3);
        assert_eq!(captured[2].text, filler);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_logging_emitter_keeps_root_buffers_when_child_step_arrives() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::Text,
            text: "root preview".into(),
            conversation_path: Some(ROOT_CONVERSATION_PATH.into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "read_file".into(),
            conversation_path: Some(ROOT_CONVERSATION_PATH.into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: r#"{"path":"root.txt"}"#.into(),
            conversation_path: Some(ROOT_CONVERSATION_PATH.into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::Text,
            text: "child preview".into(),
            conversation_path: Some("0.1".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "run_shell".into(),
            conversation_path: Some("0.1".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: r#"{"command":"npm test"}"#.into(),
            conversation_path: Some("0.1".into()),
        });

        emitter.emit_step(StepEvent {
            depth: 1,
            step: 1,
            conversation_path: Some("0.1".into()),
            tool_name: None,
            tokens: Default::default(),
            elapsed_ms: 1,
            is_final: false,
            loop_phase: None,
            loop_metrics: None,
        });

        emitter.emit_step(StepEvent {
            depth: 0,
            step: 2,
            conversation_path: Some(ROOT_CONVERSATION_PATH.into()),
            tool_name: None,
            tokens: Default::default(),
            elapsed_ms: 1,
            is_final: false,
            loop_phase: None,
            loop_metrics: None,
        });

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        let child = entries
            .iter()
            .find(|entry| entry.conversation_path.as_deref() == Some("0.1"))
            .unwrap();
        assert_eq!(child.step_model_preview.as_deref(), Some("child preview"));
        let child_tool_calls = child.step_tool_calls.as_ref().unwrap();
        assert_eq!(child_tool_calls.len(), 1);
        assert_eq!(child_tool_calls[0].name, "run_shell");
        assert_eq!(child_tool_calls[0].key_arg, "npm test");

        let root = entries
            .iter()
            .find(|entry| entry.conversation_path.as_deref() == Some(ROOT_CONVERSATION_PATH))
            .unwrap();
        assert_eq!(root.step_model_preview.as_deref(), Some("root preview"));
        let tool_calls = root.step_tool_calls.as_ref().unwrap();
        assert_eq!(tool_calls.len(), 1);
        assert_eq!(tool_calls[0].name, "read_file");
        assert_eq!(tool_calls[0].key_arg, "root.txt");
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_emit_step_keeps_patch_artifact_indices_contiguous() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "read_file".into(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: r#"{"path":"notes.txt"}"#.into(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "apply_patch".into(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: serde_json::json!({
                "patch": "*** Begin Patch\n*** Update File: notes.txt\n@@\n-old\n+new\n*** End Patch\n"
            })
            .to_string(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "apply_patch".into(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: serde_json::json!({
                "patch": "*** Begin Patch\n*** Update File: todo.txt\n@@\n-old\n+newer\n*** End Patch\n"
            })
            .to_string(),
            conversation_path: Some("0".into()),
        });

        emitter.emit_step(StepEvent {
            depth: 0,
            step: 1,
            conversation_path: Some("0".into()),
            tool_name: None,
            tokens: Default::default(),
            elapsed_ms: 1,
            is_final: false,
            loop_phase: None,
            loop_metrics: None,
        });

        let patch_one = tmp.path().join("artifacts/patches/patch-d0-s1-1.patch");
        let patch_two = tmp.path().join("artifacts/patches/patch-d0-s1-2.patch");
        let patch_three = tmp.path().join("artifacts/patches/patch-d0-s1-3.patch");
        assert!(patch_one.exists());
        assert!(patch_two.exists());
        assert!(!patch_three.exists());

        let events = std::fs::read_to_string(tmp.path().join("events.jsonl")).unwrap();
        assert!(events.contains("artifact:artifacts/patches/patch-d0-s1-1.patch"));
        assert!(events.contains("artifact:artifacts/patches/patch-d0-s1-2.patch"));
        assert!(!events.contains("artifact:artifacts/patches/patch-d0-s1-3.patch"));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_emit_complete_records_terminal_snapshot_and_result_event() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);

        emitter.emit_complete(
            "final text",
            Some(LoopMetrics {
                steps: 2,
                termination_reason: "success".into(),
                ..LoopMetrics::default()
            }),
            Some(CompletionMeta {
                kind: "final".into(),
                reason: "final_answer".into(),
                steps_used: 2,
                max_steps: 4,
                extensions_granted: 0,
                extension_block_steps: 0,
                extension_max_blocks: 0,
            }),
        );

        let snapshot = emitter.take_terminal_snapshot().expect("terminal snapshot");
        assert!(matches!(snapshot.status, TerminalStatus::Final));
        assert_eq!(snapshot.result, "final text");
        assert!(snapshot.result_event.is_some());
        assert!(snapshot.failure.is_none());
        assert!(!snapshot.degraded);
        assert_eq!(
            snapshot.loop_metrics.as_ref().map(|metrics| metrics.steps),
            Some(2)
        );

        let events = std::fs::read_to_string(tmp.path().join("events.jsonl")).unwrap();
        assert!(events.contains("\"type\":\"result\""));
        assert!(events.contains("\"status\":\"completed\""));
        assert!(events.contains("\"event_type\":\"turn.completed\""));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_emit_error_cancelled_flushes_partial_replay_and_result_event() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::Text,
            text: "drafting".into(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "write_file".into(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: r#"{"path":"draft.txt","content":"hello"}"#.into(),
            conversation_path: Some("0".into()),
        });
        emitter.emit_error("Cancelled");

        let snapshot = emitter
            .take_terminal_snapshot()
            .expect("cancelled snapshot");
        assert!(matches!(snapshot.status, TerminalStatus::Cancelled));
        assert_eq!(snapshot.result, "Task cancelled.");
        assert_eq!(
            snapshot
                .failure
                .as_ref()
                .map(|failure| failure.code.as_str()),
            Some("cancelled")
        );
        assert_eq!(
            snapshot
                .loop_metrics
                .as_ref()
                .map(|metrics| metrics.termination_reason.as_str()),
            Some("cancelled")
        );

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert!(
            entries.iter().any(
                |entry| entry.role == "assistant-partial" && entry.content.contains("drafting")
            )
        );
        assert!(
            entries
                .iter()
                .any(|entry| entry.role == "assistant-cancelled"
                    && entry.content == "Task cancelled.")
        );

        let events = std::fs::read_to_string(tmp.path().join("events.jsonl")).unwrap();
        assert!(events.contains("\"type\":\"result\""));
        assert!(events.contains("\"status\":\"cancelled\""));
        assert!(events.contains("\"event_type\":\"turn.cancelled\""));
        assert!(events.contains("\"failure_code\":\"cancelled\""));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_emit_error_cancelled_flushes_child_partial_replay_by_path() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::Text,
            text: "child drafting".into(),
            conversation_path: Some("0.1".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "write_file".into(),
            conversation_path: Some("0.1".into()),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: r#"{"path":"child.txt","content":"hello"}"#.into(),
            conversation_path: Some("0.1".into()),
        });
        emitter.emit_error("Cancelled");

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        let child_partial = entries
            .iter()
            .find(|entry| {
                entry.role == "assistant-partial"
                    && entry.conversation_path.as_deref() == Some("0.1")
            })
            .unwrap();
        assert!(child_partial.content.contains("child drafting"));
        let tool_calls = child_partial.step_tool_calls.as_ref().unwrap();
        assert_eq!(tool_calls.len(), 1);
        assert_eq!(tool_calls[0].name, "write_file");
        assert_eq!(tool_calls[0].key_arg, "child.txt");
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_emit_complete_partial_marks_degraded_failure() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);

        emitter.emit_complete(
            "partial text",
            Some(LoopMetrics {
                steps: 3,
                tool_calls: 2,
                termination_reason: "budget_cap".into(),
                ..LoopMetrics::default()
            }),
            Some(CompletionMeta {
                kind: "partial".into(),
                reason: "budget_cap".into(),
                steps_used: 3,
                max_steps: 3,
                extensions_granted: 0,
                extension_block_steps: 0,
                extension_max_blocks: 0,
            }),
        );

        let snapshot = emitter.take_terminal_snapshot().expect("partial snapshot");
        assert!(matches!(snapshot.status, TerminalStatus::Partial));
        assert!(snapshot.degraded);
        assert_eq!(
            snapshot
                .failure
                .as_ref()
                .map(|failure| failure.code.as_str()),
            Some("degraded")
        );

        let events = std::fs::read_to_string(tmp.path().join("events.jsonl")).unwrap();
        assert!(events.contains("\"status\":\"partial\""));
        assert!(events.contains("\"failure_code\":\"degraded\""));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_emit_error_classifies_rate_limit_failures() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter =
            LoggingEmitter::new(NullEmitter, replay, tmp.path().to_path_buf(), None, None);

        emitter.emit_error("Provider returned HTTP 429: too many requests");

        let snapshot = emitter.take_terminal_snapshot().expect("error snapshot");
        assert!(matches!(snapshot.status, TerminalStatus::Error));
        assert_eq!(
            snapshot
                .failure
                .as_ref()
                .map(|failure| failure.code.as_str()),
            Some("rate_limit")
        );
        assert_eq!(
            snapshot
                .failure
                .as_ref()
                .map(|failure| failure.phase.as_str()),
            Some("model_completion")
        );

        let events = std::fs::read_to_string(tmp.path().join("events.jsonl")).unwrap();
        assert!(events.contains("\"event_type\":\"turn.failed\""));
        assert!(events.contains("\"failure_code\":\"rate_limit\""));
    }
}
