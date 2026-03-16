use std::env;
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, anyhow};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Lines};
use tokio::process::{Child, ChildStderr, ChildStdin, ChildStdout, Command};
use tokio::sync::Mutex;
use tokio::task::JoinHandle;
use tokio::time::timeout;

use crate::config::{
    AgentConfig, normalize_chrome_mcp_browser_url, normalize_chrome_mcp_channel,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChromeMcpConfigKey {
    pub enabled: bool,
    pub auto_connect: bool,
    pub browser_url: Option<String>,
    pub channel: String,
    pub connect_timeout_sec: i64,
    pub rpc_timeout_sec: i64,
}

impl ChromeMcpConfigKey {
    pub fn from_config(config: &AgentConfig) -> Self {
        Self {
            enabled: config.chrome_mcp_enabled,
            auto_connect: config.chrome_mcp_auto_connect,
            browser_url: normalize_chrome_mcp_browser_url(config.chrome_mcp_browser_url.as_deref()),
            channel: normalize_chrome_mcp_channel(Some(&config.chrome_mcp_channel)),
            connect_timeout_sec: config.chrome_mcp_connect_timeout_sec.max(1),
            rpc_timeout_sec: config.chrome_mcp_rpc_timeout_sec.max(1),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChromeMcpToolDef {
    pub name: String,
    pub description: String,
    pub parameters: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChromeMcpStatus {
    pub status: String,
    pub detail: String,
    pub tool_count: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_refresh_ms: Option<i64>,
}

impl ChromeMcpStatus {
    fn disabled() -> Self {
        Self {
            status: "disabled".into(),
            detail: "Chrome DevTools MCP is disabled.".into(),
            tool_count: 0,
            last_refresh_ms: None,
        }
    }

    fn pending() -> Self {
        Self {
            status: "ready".into(),
            detail: "Chrome DevTools MCP will initialize on the next solve.".into(),
            tool_count: 0,
            last_refresh_ms: None,
        }
    }
}

struct ChromeMcpInner {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout: Option<Lines<BufReader<ChildStdout>>>,
    stderr_task: Option<JoinHandle<()>>,
    stderr_tail: Arc<Mutex<Vec<String>>>,
    next_request_id: u64,
    tools: Vec<ChromeMcpToolDef>,
    last_refresh_ms: Option<i64>,
    status: ChromeMcpStatus,
}

impl ChromeMcpInner {
    fn new(enabled: bool) -> Self {
        Self {
            child: None,
            stdin: None,
            stdout: None,
            stderr_task: None,
            stderr_tail: Arc::new(Mutex::new(Vec::new())),
            next_request_id: 1,
            tools: Vec::new(),
            last_refresh_ms: None,
            status: if enabled {
                ChromeMcpStatus::pending()
            } else {
                ChromeMcpStatus::disabled()
            },
        }
    }
}

pub struct ChromeMcpManager {
    config: ChromeMcpConfigKey,
    inner: Mutex<ChromeMcpInner>,
}

impl ChromeMcpManager {
    pub fn new(config: ChromeMcpConfigKey) -> Self {
        let enabled = config.enabled;
        Self {
            config,
            inner: Mutex::new(ChromeMcpInner::new(enabled)),
        }
    }

    pub async fn status_snapshot(&self) -> ChromeMcpStatus {
        self.inner.lock().await.status.clone()
    }

    pub async fn list_tools(&self, force_refresh: bool) -> anyhow::Result<Vec<ChromeMcpToolDef>> {
        if !self.config.enabled {
            return Ok(Vec::new());
        }
        let mut last_error: Option<anyhow::Error> = None;
        for attempt in 0..2 {
            let mut inner = self.inner.lock().await;
            match self.list_tools_locked(&mut inner, force_refresh).await {
                Ok(tools) => return Ok(tools),
                Err(err) => {
                    last_error = Some(err);
                    self.shutdown_locked(&mut inner).await;
                    if attempt == 0 {
                        continue;
                    }
                }
            }
        }
        Err(last_error.unwrap_or_else(|| anyhow!("Chrome DevTools MCP tools/list failed")))
    }

    pub async fn call_tool(&self, name: &str, arguments: &Value) -> anyhow::Result<String> {
        if !self.config.enabled {
            return Err(anyhow!("Chrome DevTools MCP is disabled."));
        }
        let mut last_error: Option<anyhow::Error> = None;
        for attempt in 0..2 {
            let mut inner = self.inner.lock().await;
            match self.call_tool_locked(&mut inner, name, arguments).await {
                Ok(result) => return Ok(result),
                Err(err) => {
                    last_error = Some(err);
                    self.shutdown_locked(&mut inner).await;
                    if attempt == 0 {
                        continue;
                    }
                }
            }
        }
        Err(last_error.unwrap_or_else(|| anyhow!("Chrome DevTools MCP tools/call failed")))
    }

    pub async fn shutdown(&self) {
        let mut inner = self.inner.lock().await;
        self.shutdown_locked(&mut inner).await;
    }

    async fn list_tools_locked(
        &self,
        inner: &mut ChromeMcpInner,
        force_refresh: bool,
    ) -> anyhow::Result<Vec<ChromeMcpToolDef>> {
        if !force_refresh && !inner.tools.is_empty() {
            return Ok(inner.tools.clone());
        }
        self.ensure_connected_locked(inner).await?;
        let mut tools = Vec::new();
        let mut cursor: Option<String> = None;
        loop {
            let mut params = serde_json::Map::new();
            if let Some(current) = cursor.as_deref() {
                params.insert("cursor".into(), Value::String(current.to_string()));
            }
            let result = self
                .request_locked(
                    inner,
                    "tools/list",
                    Value::Object(params),
                    self.config.rpc_timeout_sec,
                )
                .await?;
            if let Some(items) = result.get("tools").and_then(|value| value.as_array()) {
                for item in items {
                    let Some(name) = item.get("name").and_then(|value| value.as_str()) else {
                        continue;
                    };
                    let description = item
                        .get("description")
                        .and_then(|value| value.as_str())
                        .unwrap_or_default()
                        .to_string();
                    let parameters = item
                        .get("inputSchema")
                        .cloned()
                        .unwrap_or_else(|| json!({"type":"object","properties":{},"required":[]}));
                    tools.push(ChromeMcpToolDef {
                        name: name.to_string(),
                        description,
                        parameters,
                    });
                }
            }
            cursor = result
                .get("nextCursor")
                .and_then(|value| value.as_str())
                .map(str::to_string);
            if cursor.is_none() {
                break;
            }
        }
        let status = ChromeMcpStatus {
            status: "ready".into(),
            detail: format!(
                "Chrome DevTools MCP ready with {} tool(s) via {}.",
                tools.len(),
                if self.config.browser_url.is_some() {
                    "browser_url"
                } else {
                    "auto-connect"
                }
            ),
            tool_count: tools.len(),
            last_refresh_ms: Some(Utc::now().timestamp_millis()),
        };
        inner.last_refresh_ms = status.last_refresh_ms;
        inner.status = status;
        inner.tools = tools.clone();
        Ok(tools)
    }

    async fn call_tool_locked(
        &self,
        inner: &mut ChromeMcpInner,
        name: &str,
        arguments: &Value,
    ) -> anyhow::Result<String> {
        self.ensure_connected_locked(inner).await?;
        if inner.tools.is_empty() {
            let _ = self.list_tools_locked(inner, false).await?;
        }
        let result = self
            .request_locked(
                inner,
                "tools/call",
                json!({
                    "name": name,
                    "arguments": arguments,
                }),
                self.config.rpc_timeout_sec,
            )
            .await?;
        Ok(parse_call_result(&result))
    }

    async fn ensure_connected_locked(&self, inner: &mut ChromeMcpInner) -> anyhow::Result<()> {
        if !self.config.enabled {
            inner.status = ChromeMcpStatus::disabled();
            return Ok(());
        }
        if inner.child.is_some() && inner.stdin.is_some() && inner.stdout.is_some() {
            return Ok(());
        }
        if self.config.browser_url.is_none() && !self.config.auto_connect {
            let detail = "Chrome DevTools MCP is enabled but cannot attach: set `chrome_mcp_browser_url` or enable `chrome_mcp_auto_connect`.".to_string();
            inner.status = ChromeMcpStatus {
                status: "unavailable".into(),
                detail: detail.clone(),
                tool_count: inner.tools.len(),
                last_refresh_ms: inner.last_refresh_ms,
            };
            return Err(anyhow!(detail));
        }
        self.spawn_locked(inner).await?;
        if let Err(err) = self
            .request_locked(
                inner,
                "initialize",
                json!({
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": { "name": "openplanter-desktop", "version": "1.0" }
                }),
                self.config.connect_timeout_sec,
            )
            .await
        {
            let detail = self.status_detail_from_error(&err, inner).await;
            inner.status = ChromeMcpStatus {
                status: "unavailable".into(),
                detail: detail.clone(),
                tool_count: inner.tools.len(),
                last_refresh_ms: inner.last_refresh_ms,
            };
            return Err(anyhow!(detail));
        }
        self.notify_locked(inner, "notifications/initialized", json!({}))
            .await?;
        inner.status = ChromeMcpStatus::pending();
        Ok(())
    }

    async fn request_locked(
        &self,
        inner: &mut ChromeMcpInner,
        method: &str,
        params: Value,
        timeout_sec: i64,
    ) -> anyhow::Result<Value> {
        let request_id = inner.next_request_id;
        inner.next_request_id += 1;
        let payload = json!({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        });
        let stdin = inner
            .stdin
            .as_mut()
            .ok_or_else(|| anyhow!("Chrome DevTools MCP stdin is unavailable"))?;
        stdin
            .write_all(format!("{}\n", payload).as_bytes())
            .await
            .with_context(|| format!("failed to write Chrome DevTools MCP request {method}"))?;
        stdin.flush().await?;

        let stdout = inner
            .stdout
            .as_mut()
            .ok_or_else(|| anyhow!("Chrome DevTools MCP stdout is unavailable"))?;
        let response = timeout(
            Duration::from_secs(timeout_sec.max(1) as u64),
            async {
                loop {
                    let maybe_line = stdout.next_line().await?;
                    let line = maybe_line.ok_or_else(|| anyhow!("Chrome DevTools MCP closed stdout"))?;
                    let Ok(payload): Result<Value, _> = serde_json::from_str(&line) else {
                        continue;
                    };
                    let Some(id) = payload.get("id").and_then(|value| value.as_u64()) else {
                        continue;
                    };
                    if id == request_id {
                        return Ok::<Value, anyhow::Error>(payload);
                    }
                }
            },
        )
        .await
        .map_err(|_| anyhow!("Timed out waiting for Chrome DevTools MCP {method} response."))??;

        if let Some(err) = response.get("error") {
            return Err(anyhow!(format_protocol_error(err)));
        }

        Ok(response.get("result").cloned().unwrap_or(Value::Null))
    }

    async fn notify_locked(
        &self,
        inner: &mut ChromeMcpInner,
        method: &str,
        params: Value,
    ) -> anyhow::Result<()> {
        let stdin = inner
            .stdin
            .as_mut()
            .ok_or_else(|| anyhow!("Chrome DevTools MCP stdin is unavailable"))?;
        let payload = json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        });
        stdin
            .write_all(format!("{}\n", payload).as_bytes())
            .await
            .with_context(|| format!("failed to write Chrome DevTools MCP notification {method}"))?;
        stdin.flush().await?;
        Ok(())
    }

    async fn spawn_locked(&self, inner: &mut ChromeMcpInner) -> anyhow::Result<()> {
        self.shutdown_locked(inner).await;
        let command = env::var("OPENPLANTER_CHROME_MCP_COMMAND").unwrap_or_else(|_| "npx".into());
        let package = env::var("OPENPLANTER_CHROME_MCP_PACKAGE")
            .unwrap_or_else(|_| "chrome-devtools-mcp@latest".into());
        let mut args = vec!["-y".to_string(), package];
        if let Some(browser_url) = self.config.browser_url.as_deref() {
            args.push(format!("--browserUrl={browser_url}"));
        } else {
            args.push("--autoConnect".into());
            args.push(format!("--channel={}", self.config.channel));
        }
        if let Ok(extra_args) = env::var("OPENPLANTER_CHROME_MCP_EXTRA_ARGS") {
            args.extend(extra_args.split_whitespace().map(str::to_string));
        }
        let mut child = Command::new(&command)
            .args(&args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .with_context(|| {
                format!(
                    "failed to spawn Chrome DevTools MCP command `{}`. Install Node.js/npm so `npx` is available locally.",
                    command
                )
            })?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("Chrome DevTools MCP stdin pipe is unavailable"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("Chrome DevTools MCP stdout pipe is unavailable"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| anyhow!("Chrome DevTools MCP stderr pipe is unavailable"))?;
        let stderr_tail = inner.stderr_tail.clone();
        inner.stderr_task = Some(tokio::spawn(async move {
            let _ = read_stderr(stderr, stderr_tail).await;
        }));
        inner.stdin = Some(stdin);
        inner.stdout = Some(BufReader::new(stdout).lines());
        inner.child = Some(child);
        Ok(())
    }

    async fn shutdown_locked(&self, inner: &mut ChromeMcpInner) {
        if let Some(task) = inner.stderr_task.take() {
            task.abort();
        }
        inner.stdin = None;
        inner.stdout = None;
        if let Some(mut child) = inner.child.take() {
            let _ = child.kill().await;
            let _ = child.wait().await;
        }
    }

    async fn status_detail_from_error(
        &self,
        error: &anyhow::Error,
        inner: &ChromeMcpInner,
    ) -> String {
        let mut detail = error.to_string();
        let stderr_tail = inner.stderr_tail.lock().await.clone();
        let stderr_text = stderr_tail
            .iter()
            .rev()
            .take(4)
            .cloned()
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect::<Vec<_>>()
            .join(" ");
        let lower = format!("{detail} {stderr_text}").to_lowercase();
        if !stderr_text.trim().is_empty() {
            detail = format!("{detail} stderr: {stderr_text}");
        }
        if lower.contains("timed out") || lower.contains("timeout") {
            if self.config.browser_url.is_some() {
                detail.push_str(" Confirm the configured browser URL is reachable.");
            } else {
                detail.push_str(
                    " Enable Chrome remote debugging at chrome://inspect/#remote-debugging and allow the connection prompt in Chrome.",
                );
            }
        }
        if lower.contains("no such file") || lower.contains("not found") || lower.contains("spawn") {
            detail.push_str(" Install Node.js/npm so `npx` is available locally.");
        }
        if self.config.browser_url.is_none() && !lower.contains("inspect/#remote-debugging") {
            detail.push_str(
                " Chrome 144+ must have remote debugging enabled at chrome://inspect/#remote-debugging.",
            );
        }
        detail
    }
}

async fn read_stderr(stderr: ChildStderr, sink: Arc<Mutex<Vec<String>>>) -> anyhow::Result<()> {
    let mut lines = BufReader::new(stderr).lines();
    while let Some(line) = lines.next_line().await? {
        let mut sink = sink.lock().await;
        sink.push(line);
        if sink.len() > 20 {
            let excess = sink.len() - 20;
            sink.drain(0..excess);
        }
    }
    Ok(())
}

fn format_protocol_error(error: &Value) -> String {
    let message = error
        .get("message")
        .and_then(|value| value.as_str())
        .unwrap_or("Unknown MCP error");
    match error.get("code").and_then(|value| value.as_i64()) {
        Some(code) => format!("{message} (code {code})"),
        None => message.to_string(),
    }
}

fn parse_call_result(result: &Value) -> String {
    let mut content_parts: Vec<String> = Vec::new();
    if let Some(content) = result.get("content").and_then(|value| value.as_array()) {
        for item in content {
            if let Some(text) = item.as_str() {
                if !text.trim().is_empty() {
                    content_parts.push(text.trim().to_string());
                }
                continue;
            }
            let item_type = item
                .get("type")
                .and_then(|value| value.as_str())
                .unwrap_or_default()
                .to_lowercase();
            match item_type.as_str() {
                "text" => {
                    if let Some(text) = item.get("text").and_then(|value| value.as_str()) {
                        if !text.trim().is_empty() {
                            content_parts.push(text.trim().to_string());
                        }
                    }
                }
                "image" => {
                    let media_type = item
                        .get("mimeType")
                        .or_else(|| item.get("mediaType"))
                        .and_then(|value| value.as_str())
                        .unwrap_or("image");
                    content_parts.push(format!("[{media_type} attached]"));
                }
                _ => {
                    if let Some(uri) = item
                        .get("uri")
                        .or_else(|| item.get("url"))
                        .and_then(|value| value.as_str())
                    {
                        let label = item
                            .get("name")
                            .and_then(|value| value.as_str())
                            .unwrap_or("resource");
                        content_parts.push(format!("{label}: {uri}"));
                    }
                }
            }
        }
    }
    if content_parts.is_empty() {
        if let Some(structured) = result.get("structuredContent") {
            content_parts.push(
                serde_json::to_string_pretty(structured)
                    .unwrap_or_else(|_| structured.to_string()),
            );
        }
    }
    let mut content = if content_parts.is_empty() {
        "Chrome DevTools MCP tool completed with no textual output.".to_string()
    } else {
        content_parts.join("\n")
    };
    if result
        .get("isError")
        .and_then(|value| value.as_bool())
        .unwrap_or(false)
    {
        content = format!("Chrome DevTools MCP tool error: {content}");
    }
    content
}
