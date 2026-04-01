// Replay logger — append-only JSONL log of session messages.
//
// Each session directory contains a `replay.jsonl` file with one JSON object
// per line. This enables message history reload when switching sessions.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};
use tokio::fs;
use tokio::io::AsyncWriteExt;

/// A single entry in the replay log.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayEntry {
    pub seq: u64,
    pub timestamp: String,
    pub role: String,
    pub content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_rendered: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_number: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_depth: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub conversation_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_tokens_in: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_tokens_out: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_elapsed: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_model_preview: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_tool_calls: Option<Vec<StepToolCallEntry>>,
}

/// A tool call within a step summary entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepToolCallEntry {
    pub name: String,
    pub key_arg: String,
    pub elapsed: u64,
}

/// Append-only JSONL logger for session replay.
pub struct ReplayLogger {
    path: PathBuf,
    seq: u64,
    seq_initialized: bool,
}

impl ReplayLogger {
    /// Create a new replay logger for the given session directory.
    pub fn new(session_dir: &Path) -> Self {
        Self {
            path: session_dir.join("replay.jsonl"),
            seq: 0,
            seq_initialized: false,
        }
    }

    /// Append an entry to the replay log.
    pub async fn append(&mut self, mut entry: ReplayEntry) -> std::io::Result<()> {
        if !self.seq_initialized {
            self.seq = Self::max_seq_from_file(&self.path).await?;
            self.seq_initialized = true;
        }
        self.seq += 1;
        entry.seq = self.seq;
        if entry.timestamp.is_empty() {
            entry.timestamp = chrono::Utc::now().to_rfc3339();
        }
        let mut line = serde_json::to_string(&entry).map_err(std::io::Error::other)?;
        line.push('\n');

        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .await?;
        file.write_all(line.as_bytes()).await?;
        file.flush().await?;
        Ok(())
    }

    /// Append a raw JSON value to the replay log.
    ///
    /// This is used for writing v2 envelopes directly. The method manages
    /// sequence number tracking and fills in `seq` and `recorded_at` fields
    /// if present in the value.
    pub async fn append_raw(&mut self, mut value: Value) -> std::io::Result<u64> {
        if !self.seq_initialized {
            self.seq = Self::max_seq_from_file(&self.path).await?;
            self.seq_initialized = true;
        }
        self.seq += 1;
        let seq = self.seq;
        let timestamp = chrono::Utc::now().to_rfc3339();

        // Fill seq and recorded_at if the value has these fields
        if let Some(obj) = value.as_object_mut() {
            if obj.contains_key("seq") {
                obj.insert("seq".to_string(), Value::Number(seq.into()));
            }
            if obj.contains_key("recorded_at") {
                obj.insert("recorded_at".to_string(), Value::String(timestamp));
            }
        }

        let mut line = serde_json::to_string(&value).map_err(std::io::Error::other)?;
        line.push('\n');

        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .await?;
        file.write_all(line.as_bytes()).await?;
        file.flush().await?;
        Ok(seq)
    }

    /// Return the highest sequence number currently recorded for a session.
    pub async fn max_seq(session_dir: &Path) -> std::io::Result<u64> {
        Self::max_seq_from_file(&session_dir.join("replay.jsonl")).await
    }

    async fn max_seq_from_file(path: &Path) -> std::io::Result<u64> {
        if !path.exists() {
            return Ok(0);
        }
        let content = fs::read_to_string(path).await?;
        let mut max_seq = 0_u64;
        for (line_no, line) in content.lines().enumerate() {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            match serde_json::from_str::<Value>(trimmed) {
                Ok(value) => {
                    max_seq = max_seq.max(extracted_or_line_seq(&value, (line_no + 1) as u64));
                }
                Err(err) => {
                    eprintln!("[replay] skipping malformed line while scanning seq: {err}");
                }
            }
        }
        Ok(max_seq)
    }

    /// Read all entries from a session's replay log.
    pub async fn read_all(session_dir: &Path) -> std::io::Result<Vec<ReplayEntry>> {
        let path = session_dir.join("replay.jsonl");
        if !path.exists() {
            return Ok(vec![]);
        }
        let content = fs::read_to_string(&path).await?;
        let mut entries = Vec::new();
        for (line_no, line) in content.lines().enumerate() {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            match serde_json::from_str::<Value>(trimmed) {
                Ok(value) => match adapt_replay_value(&value, (line_no + 1) as u64) {
                    Some(entry) => entries.push(entry),
                    None => eprintln!("[replay] skipping unsupported replay line"),
                },
                Err(err) => {
                    eprintln!("[replay] skipping malformed line: {err}");
                }
            }
        }
        Ok(entries)
    }
}

fn adapt_replay_value(value: &Value, line_seq: u64) -> Option<ReplayEntry> {
    if let Ok(mut entry) = serde_json::from_value::<ReplayEntry>(value.clone()) {
        if entry.seq == 0 {
            entry.seq = line_seq;
        }
        if entry.timestamp.is_empty() {
            entry.timestamp = recorded_at(value);
        }
        return Some(entry);
    }

    if is_legacy_header(value) {
        return adapt_legacy_header(value, line_seq);
    }
    if is_legacy_call(value) {
        return adapt_legacy_call(value, line_seq);
    }
    if value.get("envelope").is_some() || value.get("event_type").is_some() {
        return adapt_enveloped_entry(value, line_seq);
    }

    None
}

fn is_legacy_header(value: &Value) -> bool {
    value
        .get("type")
        .and_then(Value::as_str)
        .is_some_and(|kind| kind == "header")
        || value
            .get("compat")
            .and_then(Value::as_object)
            .and_then(|compat| compat.get("legacy_kind"))
            .and_then(Value::as_str)
            .is_some_and(|kind| kind == "header")
        || value
            .get("event_type")
            .and_then(Value::as_str)
            .is_some_and(|event_type| event_type == "session.started")
            && value.get("response").is_none()
            && value
                .get("payload")
                .and_then(Value::as_object)
                .is_some_and(|payload| payload.contains_key("system_prompt"))
}

fn is_legacy_call(value: &Value) -> bool {
    value
        .get("type")
        .and_then(Value::as_str)
        .is_some_and(|kind| kind == "call")
        || value
            .get("compat")
            .and_then(Value::as_object)
            .and_then(|compat| compat.get("legacy_kind"))
            .and_then(Value::as_str)
            .is_some_and(|kind| kind == "call")
        || value
            .get("payload")
            .and_then(Value::as_object)
            .is_some_and(|payload| {
                payload.contains_key("messages_snapshot")
                    || payload.contains_key("messages_delta")
                    || payload.contains_key("response")
            })
}

fn adapt_legacy_header(value: &Value, line_seq: u64) -> Option<ReplayEntry> {
    let provider = string_field(value, "provider");
    let model = string_field(value, "model");
    let prompt = string_field(value, "system_prompt")
        .or_else(|| payload_string_field(value, "system_prompt"));
    let content = prompt
        .as_deref()
        .map(|text| truncate_text(text, 240))
        .filter(|text| !text.trim().is_empty())
        .or_else(|| match (provider.as_deref(), model.as_deref()) {
            (Some(provider), Some(model)) => Some(format!("{provider}/{model}")),
            (Some(provider), None) => Some(provider.to_string()),
            (None, Some(model)) => Some(model.to_string()),
            _ => None,
        })
        .unwrap_or_else(|| "Session started".to_string());

    Some(ReplayEntry {
        seq: extracted_or_line_seq(value, line_seq),
        timestamp: recorded_at(value),
        role: "system".into(),
        content,
        tool_name: None,
        is_rendered: Some(false),
        step_number: None,
        step_depth: None,
        conversation_path: string_field(value, "conversation_id"),
        step_tokens_in: None,
        step_tokens_out: None,
        step_elapsed: None,
        step_model_preview: None,
        step_tool_calls: None,
    })
}

fn adapt_legacy_call(value: &Value, line_seq: u64) -> Option<ReplayEntry> {
    let preview = extract_response_preview(
        value
            .get("response")
            .or_else(|| payload_field(value, "response")),
    )
    .or_else(|| payload_string_field(value, "text"));
    let conversation_path = string_field(value, "conversation_path")
        .or_else(|| string_field(value, "conversation_id"))
        .or_else(|| payload_string_field(value, "conversation_path"))
        .or_else(|| payload_string_field(value, "conversation_id"));

    Some(ReplayEntry {
        seq: extracted_or_line_seq(value, line_seq),
        timestamp: recorded_at(value),
        role: "step-summary".into(),
        content: preview.clone().unwrap_or_default(),
        tool_name: None,
        is_rendered: Some(false),
        step_number: u32_field(value, "step").or_else(|| payload_u32_field(value, "step")),
        step_depth: u32_field(value, "depth").or_else(|| payload_u32_field(value, "depth")),
        conversation_path,
        step_tokens_in: u64_field(value, "input_tokens")
            .or_else(|| payload_u64_field(value, "input_tokens")),
        step_tokens_out: u64_field(value, "output_tokens")
            .or_else(|| payload_u64_field(value, "output_tokens")),
        step_elapsed: u64_field(value, "elapsed_ms")
            .or_else(|| payload_u64_field(value, "elapsed_ms"))
            .or_else(|| elapsed_sec_ms(value.get("elapsed_sec")))
            .or_else(|| elapsed_sec_ms(payload_field(value, "elapsed_sec"))),
        step_model_preview: preview,
        step_tool_calls: None,
    })
}

fn adapt_enveloped_entry(value: &Value, line_seq: u64) -> Option<ReplayEntry> {
    let event_type = value.get("event_type").and_then(Value::as_str)?;
    let role = value
        .get("compat")
        .and_then(Value::as_object)
        .and_then(|compat| compat.get("legacy_role"))
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .or_else(|| canonical_role_for_event(event_type, status_field(value)))
        .unwrap_or_else(|| "system".to_string());

    let payload = value.get("payload");
    let preview = payload
        .and_then(|payload| {
            payload_string_field(payload, "step_model_preview")
                .or_else(|| payload_string_field(payload, "text"))
                .or_else(|| payload_string_field(payload, "summary"))
                .or_else(|| payload_string_field(payload, "message"))
        })
        .or_else(|| extract_response_preview(payload.and_then(|payload| payload.get("response"))));

    let content = match role.as_str() {
        "step-summary" => preview.clone().unwrap_or_default(),
        _ => payload
            .and_then(|payload| {
                payload_string_field(payload, "text")
                    .or_else(|| payload_string_field(payload, "summary"))
                    .or_else(|| payload_string_field(payload, "message"))
            })
            .or_else(|| preview.clone())
            .unwrap_or_default(),
    };

    Some(ReplayEntry {
        seq: extracted_or_line_seq(value, line_seq),
        timestamp: recorded_at(value),
        role,
        content,
        tool_name: None,
        is_rendered: Some(!matches!(
            event_type,
            "session.started"
                | "session.resumed"
                | "turn.objective"
                | "step.summary"
                | "runtime.cancel_requested"
        )),
        step_number: payload
            .and_then(|payload| payload_u32_field(payload, "step_index"))
            .or_else(|| payload.and_then(|payload| payload_u32_field(payload, "step_number")))
            .or_else(|| u32_field(value, "step")),
        step_depth: payload
            .and_then(|payload| payload_u32_field(payload, "step_depth"))
            .or_else(|| u32_field(value, "depth")),
        conversation_path: payload
            .and_then(|payload| payload_string_field(payload, "conversation_path"))
            .or_else(|| {
                payload.and_then(|payload| payload_string_field(payload, "conversation_id"))
            }),
        step_tokens_in: payload
            .and_then(|payload| payload_u64_field(payload, "step_tokens_in"))
            .or_else(|| payload.and_then(|payload| payload_u64_field(payload, "input_tokens")))
            .or_else(|| u64_field(value, "input_tokens")),
        step_tokens_out: payload
            .and_then(|payload| payload_u64_field(payload, "step_tokens_out"))
            .or_else(|| payload.and_then(|payload| payload_u64_field(payload, "output_tokens")))
            .or_else(|| u64_field(value, "output_tokens")),
        step_elapsed: payload
            .and_then(|payload| payload_u64_field(payload, "step_elapsed"))
            .or_else(|| payload.and_then(|payload| payload_u64_field(payload, "elapsed_ms")))
            .or_else(|| payload.and_then(|payload| elapsed_sec_ms(payload.get("elapsed_sec"))))
            .or_else(|| elapsed_sec_ms(value.get("elapsed_sec"))),
        step_model_preview: if event_type == "step.summary" {
            preview
        } else {
            None
        },
        step_tool_calls: payload
            .and_then(|payload| payload_step_tool_calls(payload.get("step_tool_calls"))),
    })
}

fn canonical_role_for_event(event_type: &str, status: Option<&str>) -> Option<String> {
    let role = match event_type {
        "session.started" | "session.resumed" | "trace.note" | "trace.warning" | "trace.error" => {
            "system"
        }
        "user.message" | "turn.objective" => "user",
        "step.summary" => "step-summary",
        "curator.note" => "curator",
        "assistant.message" | "assistant.final" | "result.summary" | "turn.completed" => {
            "assistant"
        }
        "turn.cancelled" => "assistant-cancelled",
        "runtime.degraded" => "system",
        "runtime.cancel_requested" => "system",
        "turn.failed" if status == Some("cancelled") => "assistant-cancelled",
        "turn.failed" => "assistant",
        _ => return None,
    };
    Some(role.to_string())
}

fn extract_seq(value: &Value) -> Option<u64> {
    value.get("seq").and_then(Value::as_u64)
}

fn extracted_or_line_seq(value: &Value, line_seq: u64) -> u64 {
    extract_seq(value)
        .filter(|seq| *seq > 0)
        .unwrap_or(line_seq)
}

fn recorded_at(value: &Value) -> String {
    string_field(value, "timestamp")
        .or_else(|| string_field(value, "recorded_at"))
        .or_else(|| string_field(value, "ts"))
        .unwrap_or_default()
}

fn status_field(value: &Value) -> Option<&str> {
    value.get("status").and_then(Value::as_str)
}

fn string_field(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}

fn u64_field(value: &Value, key: &str) -> Option<u64> {
    value.get(key).and_then(Value::as_u64)
}

fn u32_field(value: &Value, key: &str) -> Option<u32> {
    u64_field(value, key).and_then(|value| u32::try_from(value).ok())
}

fn payload_field<'a>(value: &'a Value, key: &str) -> Option<&'a Value> {
    value.get("payload")?.get(key)
}

fn payload_string_field(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}

fn payload_u64_field(value: &Value, key: &str) -> Option<u64> {
    value.get(key).and_then(Value::as_u64)
}

fn payload_u32_field(value: &Value, key: &str) -> Option<u32> {
    payload_u64_field(value, key).and_then(|value| u32::try_from(value).ok())
}

fn payload_step_tool_calls(value: Option<&Value>) -> Option<Vec<StepToolCallEntry>> {
    let calls = value?.as_array()?;
    let entries = calls
        .iter()
        .filter_map(|call| {
            let name = call.get("name")?.as_str()?.to_string();
            let key_arg = call
                .get("key_arg")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string();
            let elapsed = call.get("elapsed").and_then(Value::as_u64).unwrap_or(0);
            Some(StepToolCallEntry {
                name,
                key_arg,
                elapsed,
            })
        })
        .collect::<Vec<_>>();
    if entries.is_empty() {
        None
    } else {
        Some(entries)
    }
}

fn elapsed_sec_ms(value: Option<&Value>) -> Option<u64> {
    let seconds = value?.as_f64()?;
    Some((seconds * 1000.0).round() as u64)
}

fn extract_response_preview(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::String(text) => non_empty_text(text),
        Value::Array(items) => {
            let joined = items
                .iter()
                .filter_map(|item| extract_response_preview(Some(item)))
                .collect::<Vec<_>>()
                .join("\n");
            non_empty_text(&joined)
        }
        Value::Object(map) => {
            for key in ["output_text", "text", "summary", "content"] {
                if let Some(text) = map
                    .get(key)
                    .and_then(|item| extract_response_preview(Some(item)))
                {
                    return Some(text);
                }
            }
            if let Some(choice_text) = map
                .get("choices")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .find_map(|choice| {
                    choice
                        .get("message")
                        .and_then(|message| message.get("content"))
                        .and_then(|item| extract_response_preview(Some(item)))
                })
            {
                return Some(choice_text);
            }
            if let Some(output_text) = map
                .get("output")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .find_map(|item| {
                    item.get("content")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                        .find_map(|content| extract_response_preview(Some(content)))
                })
            {
                return Some(output_text);
            }
            None
        }
        _ => None,
    }
}

fn non_empty_text(text: &str) -> Option<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(truncate_text(trimmed, 240))
    }
}

fn truncate_text(text: &str, max_chars: usize) -> String {
    if text.len() <= max_chars {
        return text.to_string();
    }
    let end = text.floor_char_boundary(max_chars);
    format!("{}...", &text[..end])
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn basic_entry(role: &str, content: &str) -> ReplayEntry {
        ReplayEntry {
            seq: 0,
            timestamp: String::new(),
            role: role.into(),
            content: content.into(),
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
        }
    }

    #[tokio::test]
    async fn test_append_creates_file() {
        let tmp = tempdir().unwrap();
        let mut logger = ReplayLogger::new(tmp.path());
        logger.append(basic_entry("user", "hello")).await.unwrap();
        assert!(tmp.path().join("replay.jsonl").exists());
    }

    #[tokio::test]
    async fn test_append_increments_seq() {
        let tmp = tempdir().unwrap();
        let mut logger = ReplayLogger::new(tmp.path());
        for _ in 0..3 {
            logger.append(basic_entry("user", "test")).await.unwrap();
        }
        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 3);
        assert_eq!(entries[0].seq, 1);
        assert_eq!(entries[1].seq, 2);
        assert_eq!(entries[2].seq, 3);
    }

    #[tokio::test]
    async fn test_max_seq_reads_existing_entries() {
        let tmp = tempdir().unwrap();
        let mut logger = ReplayLogger::new(tmp.path());
        logger.append(basic_entry("user", "hello")).await.unwrap();

        assert_eq!(ReplayLogger::max_seq(tmp.path()).await.unwrap(), 1);
    }

    #[tokio::test]
    async fn test_read_all_empty_dir() {
        let tmp = tempdir().unwrap();
        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert!(entries.is_empty());
    }

    #[tokio::test]
    async fn test_roundtrip_with_step_summary() {
        let tmp = tempdir().unwrap();
        let mut logger = ReplayLogger::new(tmp.path());
        let entry = ReplayEntry {
            seq: 0,
            timestamp: String::new(),
            role: "step-summary".into(),
            content: String::new(),
            tool_name: None,
            is_rendered: None,
            step_number: Some(1),
            step_depth: Some(0),
            conversation_path: Some("0".into()),
            step_tokens_in: Some(12300),
            step_tokens_out: Some(2100),
            step_elapsed: Some(5000),
            step_model_preview: Some("The analysis shows...".into()),
            step_tool_calls: Some(vec![StepToolCallEntry {
                name: "read_file".into(),
                key_arg: "/src/main.ts".into(),
                elapsed: 1200,
            }]),
        };
        logger.append(entry).await.unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].role, "step-summary");
        assert_eq!(entries[0].step_number, Some(1));
        assert_eq!(entries[0].step_tokens_in, Some(12300));
        let tools = entries[0].step_tool_calls.as_ref().unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "read_file");
    }

    #[tokio::test]
    async fn test_read_all_skips_malformed_lines() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let content = format!(
            "{}\nnot valid json\n{}\n",
            serde_json::to_string(&ReplayEntry {
                seq: 1,
                timestamp: "2026-01-01T00:00:00Z".into(),
                role: "user".into(),
                content: "first".into(),
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
            .unwrap(),
            serde_json::to_string(&ReplayEntry {
                seq: 2,
                timestamp: "2026-01-01T00:01:00Z".into(),
                role: "assistant".into(),
                content: "second".into(),
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
            .unwrap(),
        );
        fs::write(&path, content).await.unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].content, "first");
        assert_eq!(entries[1].content, "second");
    }

    #[tokio::test]
    async fn test_timestamp_auto_filled() {
        let tmp = tempdir().unwrap();
        let mut logger = ReplayLogger::new(tmp.path());
        logger.append(basic_entry("user", "test")).await.unwrap();
        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert!(!entries[0].timestamp.is_empty());
    }

    #[tokio::test]
    async fn test_optional_fields_omitted_in_json() {
        let tmp = tempdir().unwrap();
        let mut logger = ReplayLogger::new(tmp.path());
        logger.append(basic_entry("user", "hello")).await.unwrap();

        let content = fs::read_to_string(tmp.path().join("replay.jsonl"))
            .await
            .unwrap();
        assert!(!content.contains("tool_name"));
        assert!(!content.contains("step_number"));
        assert!(!content.contains("step_tool_calls"));
    }

    #[tokio::test]
    async fn test_append_continues_seq_from_existing_file() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let content = format!(
            "{}\n{}\n",
            serde_json::to_string(&ReplayEntry {
                seq: 4,
                timestamp: "2026-01-01T00:00:00Z".into(),
                role: "user".into(),
                content: "first".into(),
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
            .unwrap(),
            serde_json::to_string(&ReplayEntry {
                seq: 6,
                timestamp: "2026-01-01T00:01:00Z".into(),
                role: "assistant".into(),
                content: "second".into(),
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
            .unwrap(),
        );
        fs::write(&path, content).await.unwrap();

        let mut logger = ReplayLogger::new(tmp.path());
        logger.append(basic_entry("user", "third")).await.unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.last().unwrap().seq, 7);
    }

    #[tokio::test]
    async fn test_append_ignores_malformed_lines_when_scanning_seq() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        fs::write(
            &path,
            format!(
                "{}\nnot json\n",
                serde_json::to_string(&ReplayEntry {
                    seq: 2,
                    timestamp: "2026-01-01T00:00:00Z".into(),
                    role: "user".into(),
                    content: "first".into(),
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
                .unwrap()
            ),
        )
        .await
        .unwrap();

        let mut logger = ReplayLogger::new(tmp.path());
        logger
            .append(basic_entry("assistant", "next"))
            .await
            .unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.last().unwrap().seq, 3);
    }

    #[tokio::test]
    async fn test_read_all_adapts_legacy_python_header_and_call() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let header = serde_json::json!({
            "type": "header",
            "conversation_id": "root",
            "provider": "openai",
            "model": "gpt-5.2-codex",
            "system_prompt": "Investigate carefully"
        });
        let call = serde_json::json!({
            "type": "call",
            "conversation_id": "root/d1s2",
            "seq": 3,
            "depth": 1,
            "step": 2,
            "ts": "2026-03-23T10:00:00Z",
            "response": {
                "output_text": "Compared the filings and found a contradiction."
            },
            "input_tokens": 12,
            "output_tokens": 34,
            "elapsed_sec": 1.25
        });
        fs::write(
            &path,
            format!(
                "{}\n{}\n",
                serde_json::to_string(&header).unwrap(),
                serde_json::to_string(&call).unwrap()
            ),
        )
        .await
        .unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].role, "system");
        assert!(entries[0].content.contains("Investigate carefully"));
        assert_eq!(entries[1].role, "step-summary");
        assert_eq!(entries[1].conversation_path.as_deref(), Some("root/d1s2"));
        assert_eq!(entries[1].step_number, Some(2));
        assert_eq!(entries[1].step_depth, Some(1));
        assert_eq!(
            entries[1].step_model_preview.as_deref(),
            Some("Compared the filings and found a contradiction.")
        );
        assert_eq!(entries[1].step_elapsed, Some(1250));
    }

    #[tokio::test]
    async fn test_read_all_maps_zero_seq_legacy_call_to_line_number() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let call = serde_json::json!({
            "type": "call",
            "conversation_id": "root/d1s2",
            "seq": 0,
            "depth": 1,
            "step": 2,
            "ts": "2026-03-23T10:00:00Z",
            "response": {
                "output_text": "Compared the filings and found a contradiction."
            }
        });
        fs::write(
            &path,
            format!("{}\n", serde_json::to_string(&call).unwrap()),
        )
        .await
        .unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].seq, 1);
    }

    #[tokio::test]
    async fn test_read_all_adapts_canonical_cancelled_replay_lines() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let line = serde_json::json!({
            "schema_version": 2,
            "envelope": "openplanter.trace.event.v2",
            "event_id": "evt-1",
            "session_id": "sid",
            "turn_id": "turn-000001",
            "seq": 7,
            "recorded_at": "2026-03-23T10:00:00Z",
            "event_type": "turn.cancelled",
            "channel": "replay",
            "status": "cancelled",
            "payload": {
                "text": "Task cancelled."
            },
            "failure": {
                "code": "cancelled"
            },
            "provenance": {},
            "compat": {
                "legacy_role": "assistant-cancelled",
                "legacy_kind": null,
                "source_schema": "desktop-replay-v1"
            }
        });
        fs::write(
            &path,
            format!("{}\n", serde_json::to_string(&line).unwrap()),
        )
        .await
        .unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].role, "assistant-cancelled");
        assert_eq!(entries[0].content, "Task cancelled.");
        assert_eq!(entries[0].seq, 7);
    }

    #[tokio::test]
    async fn test_read_all_maps_zero_seq_enveloped_replay_line_to_line_number() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let line = serde_json::json!({
            "schema_version": 2,
            "envelope": "openplanter.trace.event.v2",
            "event_id": "evt-1",
            "session_id": "sid",
            "turn_id": "turn-000001",
            "seq": 0,
            "recorded_at": "2026-03-23T10:00:00Z",
            "event_type": "step.summary",
            "channel": "replay",
            "status": "completed",
            "payload": {
                "text": "Reviewed three documents and identified two contradictions.",
                "step_index": 2
            },
            "failure": null,
            "provenance": {},
            "compat": {
                "legacy_role": "step-summary",
                "legacy_kind": null,
                "source_schema": "desktop-replay-v1"
            }
        });
        fs::write(
            &path,
            format!("{}\n", serde_json::to_string(&line).unwrap()),
        )
        .await
        .unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].seq, 1);
        assert_eq!(entries[0].role, "step-summary");
    }

    #[tokio::test]
    async fn test_append_continues_seq_after_legacy_call_lines() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let content = format!(
            "{}\n{}\n",
            serde_json::to_string(&serde_json::json!({
                "type": "header",
                "conversation_id": "root",
                "provider": "openai",
                "model": "gpt-5.2-codex"
            }))
            .unwrap(),
            serde_json::to_string(&serde_json::json!({
                "type": "call",
                "conversation_id": "root",
                "seq": 4,
                "depth": 0,
                "step": 1,
                "ts": "2026-03-23T10:00:00Z",
                "response": {"output_text": "legacy"}
            }))
            .unwrap(),
        );
        fs::write(&path, content).await.unwrap();

        let mut logger = ReplayLogger::new(tmp.path());
        logger
            .append(basic_entry("assistant", "next"))
            .await
            .unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.last().unwrap().seq, 5);
    }

    #[tokio::test]
    async fn test_append_continues_seq_after_zero_seq_legacy_call_line() {
        let tmp = tempdir().unwrap();
        let path = tmp.path().join("replay.jsonl");
        let content = serde_json::to_string(&serde_json::json!({
            "type": "call",
            "conversation_id": "root",
            "seq": 0,
            "depth": 0,
            "step": 1,
            "ts": "2026-03-23T10:00:00Z",
            "response": {"output_text": "legacy"}
        }))
        .unwrap();
        fs::write(&path, format!("{content}\n")).await.unwrap();

        let mut logger = ReplayLogger::new(tmp.path());
        logger
            .append(basic_entry("assistant", "next"))
            .await
            .unwrap();

        let entries = ReplayLogger::read_all(tmp.path()).await.unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].seq, 1);
        assert_eq!(entries[1].seq, 2);
    }
}
