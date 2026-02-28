// Anthropic model implementation.
//
// Uses the Anthropic Messages API with SSE streaming.

use anyhow::{anyhow, Context};
use reqwest_eventsource::{Event, RequestBuilderExt};
use tokio_util::sync::CancellationToken;

use crate::events::{DeltaEvent, DeltaKind};
use super::{BaseModel, Message, ModelTurn, ToolCall};

pub struct AnthropicModel {
    client: reqwest::Client,
    model: String,
    base_url: String,
    api_key: String,
    reasoning_effort: Option<String>,
    max_tokens: u64,
}

impl AnthropicModel {
    pub fn new(
        model: String,
        base_url: String,
        api_key: String,
        reasoning_effort: Option<String>,
    ) -> Self {
        Self {
            client: reqwest::Client::new(),
            model,
            base_url,
            api_key,
            reasoning_effort,
            max_tokens: 16384,
        }
    }

    fn is_opus_46(&self) -> bool {
        let lower = self.model.to_lowercase();
        lower.contains("opus-4-6") || lower.contains("opus-4.6")
    }

    /// Extract the system prompt from messages (Anthropic uses a top-level `system` field).
    fn extract_system(messages: &[Message]) -> Option<String> {
        for msg in messages {
            if let Message::System { content } = msg {
                return Some(content.clone());
            }
        }
        None
    }

    /// Convert messages to Anthropic format, excluding system messages.
    fn convert_messages(messages: &[Message]) -> Vec<serde_json::Value> {
        messages
            .iter()
            .filter_map(|msg| match msg {
                Message::System { .. } => None,
                Message::User { content } => Some(serde_json::json!({
                    "role": "user",
                    "content": content,
                })),
                Message::Assistant { content, tool_calls } => {
                    let mut blocks: Vec<serde_json::Value> = Vec::new();
                    if !content.is_empty() {
                        blocks.push(serde_json::json!({
                            "type": "text",
                            "text": content,
                        }));
                    }
                    if let Some(tcs) = tool_calls {
                        for tc in tcs {
                            // Parse arguments string as JSON object for Anthropic's input field
                            let input: serde_json::Value =
                                serde_json::from_str(&tc.arguments).unwrap_or(serde_json::json!({}));
                            blocks.push(serde_json::json!({
                                "type": "tool_use",
                                "id": tc.id,
                                "name": tc.name,
                                "input": input,
                            }));
                        }
                    }
                    Some(serde_json::json!({
                        "role": "assistant",
                        "content": blocks,
                    }))
                }
                Message::Tool { tool_call_id, content } => Some(serde_json::json!({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": content,
                    }],
                })),
            })
            .collect()
    }

    fn build_payload(
        &self,
        messages: &[Message],
        tools: &[serde_json::Value],
    ) -> serde_json::Value {
        let effort = self
            .reasoning_effort
            .as_deref()
            .map(|e| e.trim().to_lowercase())
            .unwrap_or_default();
        let use_thinking = matches!(effort.as_str(), "low" | "medium" | "high");

        let mut payload = serde_json::json!({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": Self::convert_messages(messages),
            "stream": true,
        });

        if let Some(system) = Self::extract_system(messages) {
            payload["system"] = serde_json::json!(system);
        }

        if !tools.is_empty() {
            payload["tools"] = serde_json::Value::Array(tools.to_vec());
        }

        if use_thinking {
            if self.is_opus_46() {
                payload["thinking"] = serde_json::json!({"type": "adaptive"});
                payload["output_config"] = serde_json::json!({"effort": effort});
            } else {
                let budget: u64 = match effort.as_str() {
                    "low" => 1024,
                    "medium" => 4096,
                    _ => 8192,
                };
                let max_tokens = if self.max_tokens <= budget {
                    budget + 8192
                } else {
                    self.max_tokens
                };
                payload["max_tokens"] = serde_json::json!(max_tokens);
                payload["thinking"] = serde_json::json!({
                    "type": "enabled",
                    "budget_tokens": budget,
                });
            }
            // Thinking is incompatible with temperature
        } else {
            payload["temperature"] = serde_json::json!(0.0);
        }

        payload
    }
}

#[async_trait::async_trait]
impl BaseModel for AnthropicModel {
    async fn chat(
        &self,
        messages: &[Message],
        tools: &[serde_json::Value],
    ) -> anyhow::Result<ModelTurn> {
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
        let url = format!("{}/messages", self.base_url.trim_end_matches('/'));
        let payload = self.build_payload(messages, tools);

        let request = self
            .client
            .post(&url)
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", "2023-06-01")
            .header("Content-Type", "application/json");

        let mut es = request.json(&payload).eventsource()?;

        let mut text = String::new();
        let mut thinking = String::new();
        let mut input_tokens: u64 = 0;
        let mut output_tokens: u64 = 0;

        // Track content blocks by index for tool calls
        struct BlockState {
            block_type: String,
            tool_id: String,
            tool_name: String,
            input_json: String,
        }
        let mut blocks: std::collections::HashMap<u64, BlockState> = std::collections::HashMap::new();
        let mut tool_calls: Vec<ToolCall> = Vec::new();

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
                    let data: serde_json::Value = serde_json::from_str(&msg.data)
                        .with_context(|| format!("Failed to parse SSE chunk: {}", &msg.data))?;

                    let msg_type = data
                        .get("type")
                        .and_then(|t| t.as_str())
                        .unwrap_or(&msg.event);

                    match msg_type {
                        "message_start" => {
                            if let Some(usage) = data.pointer("/message/usage") {
                                if let Some(it) = usage.get("input_tokens").and_then(|v| v.as_u64()) {
                                    input_tokens = it;
                                }
                            }
                        }

                        "content_block_start" => {
                            let idx = data.get("index").and_then(|i| i.as_u64()).unwrap_or(0);
                            let block = data.get("content_block").unwrap_or(&serde_json::Value::Null);
                            let btype = block.get("type").and_then(|t| t.as_str()).unwrap_or("text");

                            let state = match btype {
                                "tool_use" => {
                                    let name = block.get("name").and_then(|n| n.as_str()).unwrap_or("").to_string();
                                    let id = block.get("id").and_then(|i| i.as_str()).unwrap_or("").to_string();
                                    if !name.is_empty() {
                                        on_delta(DeltaEvent {
                                            kind: DeltaKind::ToolCallStart,
                                            text: name.clone(),
                                        });
                                    }
                                    BlockState {
                                        block_type: "tool_use".to_string(),
                                        tool_id: id,
                                        tool_name: name,
                                        input_json: String::new(),
                                    }
                                }
                                "thinking" => BlockState {
                                    block_type: "thinking".to_string(),
                                    tool_id: String::new(),
                                    tool_name: String::new(),
                                    input_json: String::new(),
                                },
                                _ => BlockState {
                                    block_type: "text".to_string(),
                                    tool_id: String::new(),
                                    tool_name: String::new(),
                                    input_json: String::new(),
                                },
                            };
                            blocks.insert(idx, state);
                        }

                        "content_block_delta" => {
                            let idx = data.get("index").and_then(|i| i.as_u64()).unwrap_or(0);
                            let delta = match data.get("delta") {
                                Some(d) => d,
                                None => continue,
                            };
                            let delta_type = delta.get("type").and_then(|t| t.as_str()).unwrap_or("");

                            match delta_type {
                                "text_delta" => {
                                    if let Some(t) = delta.get("text").and_then(|t| t.as_str()) {
                                        if !t.is_empty() {
                                            text.push_str(t);
                                            on_delta(DeltaEvent {
                                                kind: DeltaKind::Text,
                                                text: t.to_string(),
                                            });
                                        }
                                    }
                                }
                                "thinking_delta" => {
                                    if let Some(t) = delta.get("thinking").and_then(|t| t.as_str()) {
                                        if !t.is_empty() {
                                            thinking.push_str(t);
                                            on_delta(DeltaEvent {
                                                kind: DeltaKind::Thinking,
                                                text: t.to_string(),
                                            });
                                        }
                                    }
                                }
                                "input_json_delta" => {
                                    if let Some(chunk) = delta.get("partial_json").and_then(|j| j.as_str()) {
                                        if !chunk.is_empty() {
                                            if let Some(block) = blocks.get_mut(&idx) {
                                                block.input_json.push_str(chunk);
                                            }
                                            on_delta(DeltaEvent {
                                                kind: DeltaKind::ToolCallArgs,
                                                text: chunk.to_string(),
                                            });
                                        }
                                    }
                                }
                                _ => {}
                            }
                        }

                        "content_block_stop" => {
                            let idx = data.get("index").and_then(|i| i.as_u64()).unwrap_or(0);
                            if let Some(block) = blocks.get(&idx) {
                                if block.block_type == "tool_use" {
                                    tool_calls.push(ToolCall {
                                        id: block.tool_id.clone(),
                                        name: block.tool_name.clone(),
                                        arguments: block.input_json.clone(),
                                    });
                                }
                            }
                        }

                        "message_delta" => {
                            if let Some(usage) = data.get("usage") {
                                if let Some(ot) = usage.get("output_tokens").and_then(|v| v.as_u64()) {
                                    output_tokens = ot;
                                }
                            }
                        }

                        "error" => {
                            let err_msg = data
                                .pointer("/error/message")
                                .and_then(|m| m.as_str())
                                .unwrap_or("Unknown API error");
                            es.close();
                            return Err(anyhow!("Anthropic API error: {err_msg}"));
                        }

                        _ => {}
                    }
                }
            }
        }

        Ok(ModelTurn {
            text,
            thinking: if thinking.is_empty() { None } else { Some(thinking) },
            tool_calls,
            input_tokens,
            output_tokens,
        })
    }

    fn model_name(&self) -> &str {
        &self.model
    }

    fn provider_name(&self) -> &str {
        "anthropic"
    }
}
