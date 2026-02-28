// OpenAI-compatible model implementation.
//
// Handles openai, openrouter, cerebras, and ollama — all use /chat/completions.

use std::collections::HashMap;

use anyhow::{anyhow, Context};
use reqwest_eventsource::{Event, RequestBuilderExt};
use tokio_util::sync::CancellationToken;

use crate::events::{DeltaEvent, DeltaKind};
use super::{BaseModel, Message, ModelTurn, ToolCall};

pub struct OpenAIModel {
    client: reqwest::Client,
    model: String,
    provider: String,
    base_url: String,
    api_key: String,
    reasoning_effort: Option<String>,
    extra_headers: HashMap<String, String>,
}

impl OpenAIModel {
    pub fn new(
        model: String,
        provider: String,
        base_url: String,
        api_key: String,
        reasoning_effort: Option<String>,
        extra_headers: HashMap<String, String>,
    ) -> Self {
        Self {
            client: reqwest::Client::new(),
            model,
            provider,
            base_url,
            api_key,
            reasoning_effort,
            extra_headers,
        }
    }

    fn is_reasoning_model(&self) -> bool {
        let lower = self.model.to_lowercase();
        if lower.starts_with("o1-") || lower == "o1"
            || lower.starts_with("o3-") || lower == "o3"
            || lower.starts_with("o4-") || lower == "o4"
        {
            return true;
        }
        if lower.starts_with("gpt-5") {
            return true;
        }
        false
    }

    fn convert_messages(messages: &[Message]) -> Vec<serde_json::Value> {
        messages
            .iter()
            .map(|msg| match msg {
                Message::System { content } => serde_json::json!({
                    "role": "system",
                    "content": content,
                }),
                Message::User { content } => serde_json::json!({
                    "role": "user",
                    "content": content,
                }),
                Message::Assistant { content, tool_calls } => {
                    let mut obj = serde_json::json!({
                        "role": "assistant",
                        "content": content,
                    });
                    if let Some(tcs) = tool_calls {
                        let tc_arr: Vec<serde_json::Value> = tcs
                            .iter()
                            .map(|tc| serde_json::json!({
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                }
                            }))
                            .collect();
                        obj["tool_calls"] = serde_json::Value::Array(tc_arr);
                    }
                    obj
                }
                Message::Tool { tool_call_id, content } => serde_json::json!({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content,
                }),
            })
            .collect()
    }

    fn build_payload(
        &self,
        messages: &[Message],
        tools: &[serde_json::Value],
        stream: bool,
    ) -> serde_json::Value {
        let mut payload = serde_json::json!({
            "model": self.model,
            "messages": Self::convert_messages(messages),
        });

        if stream {
            payload["stream"] = serde_json::json!(true);
            payload["stream_options"] = serde_json::json!({"include_usage": true});
        }

        if !tools.is_empty() {
            payload["tools"] = serde_json::Value::Array(tools.to_vec());
            payload["tool_choice"] = serde_json::json!("auto");
        }

        if !self.is_reasoning_model() {
            payload["temperature"] = serde_json::json!(0.0);
        }

        if let Some(ref effort) = self.reasoning_effort {
            let effort_lower = effort.trim().to_lowercase();
            if !effort_lower.is_empty() {
                payload["reasoning_effort"] = serde_json::json!(effort_lower);
            }
        }

        payload
    }
}

#[async_trait::async_trait]
impl BaseModel for OpenAIModel {
    async fn chat(
        &self,
        messages: &[Message],
        tools: &[serde_json::Value],
    ) -> anyhow::Result<ModelTurn> {
        // Default: call chat_stream with a no-op callback
        let noop = |_: DeltaEvent| {};
        let cancel = CancellationToken::new();
        self.chat_stream(messages, tools, &noop, &cancel).await
    }

    async fn chat_stream(
        &self,
        messages: &[Message],
        tools: &[serde_json::Value],
        on_delta: &(dyn Fn(DeltaEvent) + Send + Sync),
        cancel: &CancellationToken,
    ) -> anyhow::Result<ModelTurn> {
        let url = format!("{}/chat/completions", self.base_url.trim_end_matches('/'));
        let payload = self.build_payload(messages, tools, true);

        let mut request = self
            .client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json");

        for (k, v) in &self.extra_headers {
            request = request.header(k.as_str(), v.as_str());
        }

        let mut es = request.json(&payload).eventsource()?;

        let mut text = String::new();
        let mut tool_calls_by_index: HashMap<usize, (String, String, String)> = HashMap::new(); // (id, name, args)
        let mut input_tokens: u64 = 0;
        let mut output_tokens: u64 = 0;

        use futures::StreamExt;
        loop {
            if cancel.is_cancelled() {
                es.close();
                return Err(anyhow!("Cancelled"));
            }

            let event = tokio::select! {
                _ = cancel.cancelled() => {
                    es.close();
                    return Err(anyhow!("Cancelled"));
                }
                ev = es.next() => ev,
            };

            let event = match event {
                Some(Ok(ev)) => ev,
                Some(Err(reqwest_eventsource::Error::StreamEnded)) => break,
                Some(Err(e)) => {
                    es.close();
                    return Err(anyhow!("SSE stream error: {e}"));
                }
                None => break,
            };

            match event {
                Event::Open => {}
                Event::Message(msg) => {
                    if msg.data == "[DONE]" {
                        break;
                    }

                    let chunk: serde_json::Value = serde_json::from_str(&msg.data)
                        .with_context(|| format!("Failed to parse SSE chunk: {}", &msg.data))?;

                    // Extract usage from any chunk that has it
                    if let Some(usage) = chunk.get("usage") {
                        if let Some(pt) = usage.get("prompt_tokens").and_then(|v| v.as_u64()) {
                            input_tokens = pt;
                        }
                        if let Some(ct) = usage.get("completion_tokens").and_then(|v| v.as_u64()) {
                            output_tokens = ct;
                        }
                    }

                    let choices = match chunk.get("choices").and_then(|c| c.as_array()) {
                        Some(c) => c,
                        None => continue,
                    };

                    if choices.is_empty() {
                        continue;
                    }

                    let delta = match choices[0].get("delta") {
                        Some(d) => d,
                        None => continue,
                    };

                    // Text content delta
                    if let Some(content) = delta.get("content").and_then(|c| c.as_str()) {
                        if !content.is_empty() {
                            text.push_str(content);
                            on_delta(DeltaEvent {
                                kind: DeltaKind::Text,
                                text: content.to_string(),
                            });
                        }
                    }

                    // Tool call deltas
                    if let Some(tc_deltas) = delta.get("tool_calls").and_then(|t| t.as_array()) {
                        for tc_delta in tc_deltas {
                            let idx = tc_delta.get("index").and_then(|i| i.as_u64()).unwrap_or(0) as usize;
                            let entry = tool_calls_by_index.entry(idx).or_insert_with(|| {
                                (String::new(), String::new(), String::new())
                            });

                            if let Some(id) = tc_delta.get("id").and_then(|i| i.as_str()) {
                                if !id.is_empty() {
                                    entry.0 = id.to_string();
                                }
                            }

                            if let Some(func) = tc_delta.get("function") {
                                if let Some(name) = func.get("name").and_then(|n| n.as_str()) {
                                    if !name.is_empty() {
                                        entry.1 = name.to_string();
                                        on_delta(DeltaEvent {
                                            kind: DeltaKind::ToolCallStart,
                                            text: name.to_string(),
                                        });
                                    }
                                }
                                if let Some(args) = func.get("arguments").and_then(|a| a.as_str()) {
                                    if !args.is_empty() {
                                        entry.2.push_str(args);
                                        on_delta(DeltaEvent {
                                            kind: DeltaKind::ToolCallArgs,
                                            text: args.to_string(),
                                        });
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Build tool calls from accumulated data
        let mut tool_calls: Vec<ToolCall> = Vec::new();
        let mut indices: Vec<usize> = tool_calls_by_index.keys().copied().collect();
        indices.sort();
        for idx in indices {
            let (id, name, arguments) = tool_calls_by_index.remove(&idx).unwrap();
            tool_calls.push(ToolCall { id, name, arguments });
        }

        Ok(ModelTurn {
            text,
            thinking: None,
            tool_calls,
            input_tokens,
            output_tokens,
        })
    }

    fn model_name(&self) -> &str {
        &self.model
    }

    fn provider_name(&self) -> &str {
        &self.provider
    }
}
