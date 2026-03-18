// Bridge between engine callbacks and Tauri events.
//
// TauriEmitter wraps an AppHandle and implements SolveEmitter so that
// the engine can stream events to the frontend without depending on Tauri.
//
// LoggingEmitter wraps any SolveEmitter + ReplayLogger to persist messages
// to replay.jsonl as they stream.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter};

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
        let _ = self.handle.emit(
            "agent:error",
            ErrorEvent {
                message: message.to_string(),
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

/// Wraps any SolveEmitter + ReplayLogger to persist events as they stream.
///
/// Collects streaming text and tool calls during a step, then logs
/// the full step summary and final assistant message to replay.jsonl.
pub struct LoggingEmitter<E: SolveEmitter> {
    inner: E,
    replay: Arc<tokio::sync::Mutex<ReplayLogger>>,
    /// Per-conversation-path streaming state used to build replay step summaries.
    step_states: Mutex<HashMap<String, StepCaptureState>>,
    /// Final completion payload emitted during the solve.
    completion: Mutex<Option<CompletionSnapshot>>,
}

/// A tool call being accumulated during streaming.
struct PendingToolCall {
    name: String,
    key_arg: String,
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
pub struct CompletionSnapshot {
    pub result: String,
    pub loop_metrics: Option<LoopMetrics>,
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
    pub fn new(inner: E, replay: ReplayLogger) -> Self {
        Self {
            inner,
            replay: Arc::new(tokio::sync::Mutex::new(replay)),
            step_states: Mutex::new(HashMap::new()),
            completion: Mutex::new(None),
        }
    }

    pub fn take_completion(&self) -> Option<CompletionSnapshot> {
        self.completion.lock().unwrap().take()
    }
}

impl<E: SolveEmitter> SolveEmitter for LoggingEmitter<E> {
    fn emit_trace(&self, message: &str) {
        self.inner.emit_trace(message);
    }

    fn emit_delta(&self, event: DeltaEvent) {
        // Accumulate streaming data for step summary logging (sync — no I/O)
        let mut step_states = self.step_states.lock().unwrap();
        let state = step_states
            .entry(ROOT_CONVERSATION_PATH.to_string())
            .or_default();
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
                if let Some(key_arg) =
                    extract_key_arg(&state.current_tool, &state.current_args_buf)
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

        let model_preview =
            format_model_preview(&state.streaming_buf, state.streaming_truncated);

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
            step_model_preview: model_preview,
            step_tool_calls: if step_tools.is_empty() {
                None
            } else {
                Some(step_tools)
            },
        };

        // Async file I/O — use block_in_place only for this
        let replay = self.replay.clone();
        tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(async {
                if let Err(e) = replay.lock().await.append(entry).await {
                    eprintln!("[bridge] failed to log step: {e}");
                }
            });
        });

        self.inner.emit_step(event);
    }

    fn emit_complete(
        &self,
        result: &str,
        loop_metrics: Option<LoopMetrics>,
        completion: Option<CompletionMeta>,
    ) {
        *self.completion.lock().unwrap() = Some(CompletionSnapshot {
            result: result.to_string(),
            loop_metrics: loop_metrics.clone(),
        });
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

        // Async file I/O
        let replay = self.replay.clone();
        tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(async {
                if let Err(e) = replay.lock().await.append(entry).await {
                    eprintln!("[bridge] failed to log complete: {e}");
                }
            });
        });

        self.inner.emit_complete(result, loop_metrics, completion);
    }

    fn emit_error(&self, message: &str) {
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
        self.inner
            .emit_loop_health(depth, step, conversation_path, phase, metrics, is_final);
    }

    fn emit_curator_update(&self, summary: &str, files_changed: u32) {
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

        let replay = self.replay.clone();
        tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(async {
                if let Err(e) = replay.lock().await.append(entry).await {
                    eprintln!("[bridge] failed to log curator update: {e}");
                }
            });
        });

        self.inner.emit_curator_update(summary, files_changed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use op_core::engine::demo_solve;
    use op_core::session::replay::ReplayLogger;
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
        let emitter = LoggingEmitter::new(NullEmitter, replay);
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
    async fn test_logging_emitter_cancel_no_crash() {
        let tmp = tempdir().unwrap();
        let replay = ReplayLogger::new(tmp.path());
        let emitter = LoggingEmitter::new(NullEmitter, replay);
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
        let emitter = LoggingEmitter::new(NullEmitter, replay);
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
        let emitter = LoggingEmitter::new(inner, replay);
        let big_text = "x".repeat(MAX_STEP_MODEL_PREVIEW_CHARS + 256);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::Text,
            text: big_text.clone(),
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
        let emitter = LoggingEmitter::new(inner, replay);
        let filler = "x".repeat(MAX_TOOL_ARGS_CAPTURE_CHARS + 512);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "read_file".to_string(),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: "{\"path\":\"foo.md\",\"other\":\"".to_string(),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: filler.clone(),
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
        let emitter = LoggingEmitter::new(NullEmitter, replay);

        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::Text,
            text: "root preview".into(),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallStart,
            text: "read_file".into(),
        });
        emitter.emit_delta(DeltaEvent {
            kind: DeltaKind::ToolCallArgs,
            text: r#"{"path":"root.txt"}"#.into(),
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
        assert!(child.step_model_preview.is_none());
        assert!(child.step_tool_calls.is_none());

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
}
