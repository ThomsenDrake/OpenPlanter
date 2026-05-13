use std::env;
use std::process::Stdio;
use std::time::Duration;

use anyhow::{Context, anyhow};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::io::AsyncWriteExt;
use tokio::process::Command;
use tokio::sync::Mutex;
use tokio::time::timeout;

use crate::config::{AgentConfig, normalize_chrome_mcp_browser_url, normalize_chrome_mcp_channel};

const RESULT_PREFIX: &str = "__OPENPLANTER_BROWSER_HARNESS_RESULT__";
const DEFAULT_HARNESS_NAME: &str = "openplanter";

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
            detail: "Browser Harness is disabled.".into(),
            tool_count: 0,
            last_refresh_ms: None,
        }
    }

    fn pending() -> Self {
        Self {
            status: "ready".into(),
            detail: "Browser Harness will initialize on the next solve.".into(),
            tool_count: 0,
            last_refresh_ms: None,
        }
    }
}

struct ChromeMcpInner {
    tools: Vec<ChromeMcpToolDef>,
    last_refresh_ms: Option<i64>,
    status: ChromeMcpStatus,
}

impl ChromeMcpInner {
    fn new(enabled: bool) -> Self {
        Self {
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

#[derive(Debug, Deserialize)]
struct HarnessPayload {
    ok: bool,
    #[serde(default)]
    content: Option<Value>,
    #[serde(default)]
    error: Option<String>,
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
        let mut inner = self.inner.lock().await;
        self.list_tools_locked(&mut inner, force_refresh).await
    }

    pub async fn call_tool(&self, name: &str, arguments: &Value) -> anyhow::Result<String> {
        if !self.config.enabled {
            return Err(anyhow!("Browser Harness is disabled."));
        }
        let mut inner = self.inner.lock().await;
        let tools = if inner.tools.is_empty() {
            self.list_tools_locked(&mut inner, false).await?
        } else {
            inner.tools.clone()
        };
        if !tools.iter().any(|tool| tool.name == name) {
            return Err(anyhow!("Unknown Browser Harness tool `{name}`."));
        }
        let script = build_harness_script(name, arguments)?;
        match self
            .run_harness_script(&script, self.config.rpc_timeout_sec)
            .await
        {
            Ok(payload) => {
                if payload.ok {
                    Ok(format_harness_content(payload.content.as_ref()))
                } else {
                    let detail = payload
                        .error
                        .unwrap_or_else(|| "Browser Harness tool failed.".into());
                    inner.status = ChromeMcpStatus {
                        status: "unavailable".into(),
                        detail: self.status_detail_from_error(&detail),
                        tool_count: inner.tools.len(),
                        last_refresh_ms: inner.last_refresh_ms,
                    };
                    Err(anyhow!(detail))
                }
            }
            Err(err) => {
                let detail = self.status_detail_from_error(&err.to_string());
                inner.status = ChromeMcpStatus {
                    status: "unavailable".into(),
                    detail: detail.clone(),
                    tool_count: inner.tools.len(),
                    last_refresh_ms: inner.last_refresh_ms,
                };
                Err(anyhow!(detail))
            }
        }
    }

    pub async fn shutdown(&self) {
        // Browser Harness owns its daemon. Cestus only invokes short commands.
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
        let tools = browser_harness_tool_defs();
        let status = ChromeMcpStatus {
            status: "ready".into(),
            detail: format!(
                "Browser Harness ready with {} tool(s) via {}.",
                tools.len(),
                if self.config.browser_url.is_some() {
                    "BU_CDP_URL"
                } else {
                    "auto-discovery"
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

    async fn ensure_connected_locked(&self, inner: &mut ChromeMcpInner) -> anyhow::Result<()> {
        if !self.config.enabled {
            inner.status = ChromeMcpStatus::disabled();
            return Ok(());
        }
        if self.config.browser_url.is_none() && !self.config.auto_connect {
            let detail = "Browser Harness is enabled but cannot attach: set `chrome_mcp_browser_url` (used as BU_CDP_URL) or enable `chrome_mcp_auto_connect`.".to_string();
            inner.status = ChromeMcpStatus {
                status: "unavailable".into(),
                detail: detail.clone(),
                tool_count: inner.tools.len(),
                last_refresh_ms: inner.last_refresh_ms,
            };
            return Err(anyhow!(detail));
        }
        let script = build_harness_script("browser_page_info", &json!({}))?;
        match self
            .run_harness_script(
                &script,
                self.config
                    .connect_timeout_sec
                    .max(self.config.rpc_timeout_sec),
            )
            .await
        {
            Ok(payload) if payload.ok => {
                inner.status = ChromeMcpStatus::pending();
                Ok(())
            }
            Ok(payload) => {
                let detail = self.status_detail_from_error(
                    payload
                        .error
                        .as_deref()
                        .unwrap_or("Browser Harness probe failed."),
                );
                inner.status = ChromeMcpStatus {
                    status: "unavailable".into(),
                    detail: detail.clone(),
                    tool_count: inner.tools.len(),
                    last_refresh_ms: inner.last_refresh_ms,
                };
                Err(anyhow!(detail))
            }
            Err(err) => {
                let detail = self.status_detail_from_error(&err.to_string());
                inner.status = ChromeMcpStatus {
                    status: "unavailable".into(),
                    detail: detail.clone(),
                    tool_count: inner.tools.len(),
                    last_refresh_ms: inner.last_refresh_ms,
                };
                Err(anyhow!(detail))
            }
        }
    }

    async fn run_harness_script(
        &self,
        script: &str,
        timeout_sec: i64,
    ) -> anyhow::Result<HarnessPayload> {
        let command_name = env::var("OPENPLANTER_BROWSER_HARNESS_COMMAND")
            .unwrap_or_else(|_| "browser-harness".into());
        let mut command = Command::new(&command_name);
        if let Ok(extra_args) = env::var("OPENPLANTER_BROWSER_HARNESS_EXTRA_ARGS") {
            command.args(extra_args.split_whitespace());
        }
        command
            .kill_on_drop(true)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let harness_name = env::var("OPENPLANTER_BROWSER_HARNESS_NAME")
            .unwrap_or_else(|_| DEFAULT_HARNESS_NAME.into());
        command.env("BU_NAME", harness_name);
        if let Some(browser_url) = self
            .config
            .browser_url
            .as_deref()
            .filter(|value| !value.trim().is_empty())
            .map(str::to_string)
            .or_else(|| env::var("OPENPLANTER_BROWSER_HARNESS_CDP_URL").ok())
        {
            command.env("BU_CDP_URL", browser_url);
        }
        if let Ok(cdp_ws) = env::var("OPENPLANTER_BROWSER_HARNESS_CDP_WS") {
            if !cdp_ws.trim().is_empty() {
                command.env("BU_CDP_WS", cdp_ws);
            }
        }

        let output = timeout(Duration::from_secs(timeout_sec.max(1) as u64), async {
            let mut child = command.spawn().with_context(|| {
                format!("failed to run Browser Harness command `{}`", command_name)
            })?;
            let mut stdin = child.stdin.take().ok_or_else(|| {
                anyhow!(
                    "failed to open stdin for Browser Harness command `{}`",
                    command_name
                )
            })?;
            stdin.write_all(script.as_bytes()).await.with_context(|| {
                format!(
                    "failed to send script to Browser Harness command `{}`",
                    command_name
                )
            })?;
            drop(stdin);
            child.wait_with_output().await.with_context(|| {
                format!("failed to run Browser Harness command `{}`", command_name)
            })
        })
        .await
        .map_err(|_| anyhow!("Timed out waiting for Browser Harness after {timeout_sec}s."))??;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        extract_harness_payload(&stdout, &stderr, output.status.code())
    }

    fn status_detail_from_error(&self, error: &str) -> String {
        let mut detail = error.trim().to_string();
        if detail.is_empty() {
            detail = "Browser Harness failed.".into();
        }
        let lower = detail.to_lowercase();
        if lower.contains("not found")
            || lower.contains("no such file")
            || lower.contains("failed to run")
            || lower.contains("not installed")
        {
            detail.push_str(
                " Install Browser Harness so `browser-harness` is on PATH (for example: `uv tool install -e <browser-harness checkout>`).",
            );
        }
        if lower.contains("timed out") || lower.contains("timeout") || lower.contains("unreachable")
        {
            if self.config.browser_url.is_some() {
                detail.push_str(" Confirm the configured endpoint is reachable as BU_CDP_URL.");
            } else {
                detail.push_str(
                    " Enable Chrome remote debugging at chrome://inspect/#remote-debugging and click Allow if Chrome prompts for Browser Harness access.",
                );
            }
        }
        if lower.contains("devtoolsactiveport")
            || lower.contains("remote-debugging")
            || lower.contains("allow")
        {
            detail.push_str(
                " Browser Harness connects through Chrome remote debugging; use chrome://inspect/#remote-debugging or set BU_CDP_URL for a dedicated browser.",
            );
        }
        detail
    }
}

fn schema(properties: Value, required: Vec<&str>) -> Value {
    json!({
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": false,
    })
}

fn browser_harness_tool_defs() -> Vec<ChromeMcpToolDef> {
    vec![
        ChromeMcpToolDef {
            name: "browser_page_info".into(),
            description: "Return the current Browser Harness tab URL, title, viewport, scroll position, and page dimensions.".into(),
            parameters: schema(json!({}), vec![]),
        },
        ChromeMcpToolDef {
            name: "browser_new_tab".into(),
            description: "Open a URL in a new browser tab through Browser Harness and return page info.".into(),
            parameters: schema(
                json!({
                    "url": { "type": "string", "description": "URL to open. Defaults to about:blank." },
                    "wait_for_load": { "type": "boolean", "description": "Wait for document.readyState=complete before returning.", "default": true }
                }),
                vec!["url"],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_capture_screenshot".into(),
            description: "Capture a Browser Harness screenshot of the current tab.".into(),
            parameters: schema(
                json!({
                    "full": { "type": "boolean", "description": "Capture beyond the viewport.", "default": false },
                    "max_dim": { "type": "integer", "description": "Optional maximum image dimension after resizing.", "minimum": 1 }
                }),
                vec![],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_click_at_xy".into(),
            description: "Click visible page coordinates using Browser Harness compositor-level input.".into(),
            parameters: schema(
                json!({
                    "x": { "type": "number", "description": "Viewport x coordinate." },
                    "y": { "type": "number", "description": "Viewport y coordinate." },
                    "button": { "type": "string", "enum": ["left", "middle", "right"], "default": "left" },
                    "clicks": { "type": "integer", "minimum": 1, "default": 1 }
                }),
                vec!["x", "y"],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_type_text".into(),
            description: "Insert text at the focused browser element through Browser Harness.".into(),
            parameters: schema(
                json!({ "text": { "type": "string", "description": "Text to type." } }),
                vec!["text"],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_press_key".into(),
            description: "Press a key in the current browser tab through Browser Harness.".into(),
            parameters: schema(
                json!({
                    "key": { "type": "string", "description": "Key name, such as Enter, Tab, Escape, ArrowDown, Backspace, or a single character." },
                    "modifiers": { "type": "integer", "description": "Browser Harness modifier bitfield: 1=Alt, 2=Ctrl, 4=Meta/Cmd, 8=Shift.", "default": 0 }
                }),
                vec!["key"],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_scroll".into(),
            description: "Scroll at a viewport coordinate using Browser Harness mouse wheel input.".into(),
            parameters: schema(
                json!({
                    "x": { "type": "number", "description": "Viewport x coordinate." },
                    "y": { "type": "number", "description": "Viewport y coordinate." },
                    "dy": { "type": "number", "description": "Vertical wheel delta.", "default": -300 },
                    "dx": { "type": "number", "description": "Horizontal wheel delta.", "default": 0 }
                }),
                vec!["x", "y"],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_wait_for_load".into(),
            description: "Wait for the current document to finish loading and return whether it completed.".into(),
            parameters: schema(
                json!({ "timeout": { "type": "number", "description": "Maximum seconds to wait.", "default": 15 } }),
                vec![],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_js".into(),
            description: "Evaluate JavaScript in the current Browser Harness tab and return the JSON-serializable result.".into(),
            parameters: schema(
                json!({ "expression": { "type": "string", "description": "JavaScript expression or snippet." } }),
                vec!["expression"],
            ),
        },
        ChromeMcpToolDef {
            name: "browser_cdp".into(),
            description: "Send a raw Chrome DevTools Protocol method through Browser Harness.".into(),
            parameters: schema(
                json!({
                    "method": { "type": "string", "description": "CDP method, for example Page.navigate." },
                    "params": { "type": "object", "description": "CDP params object.", "default": {} },
                    "session_id": { "type": "string", "description": "Optional CDP session id." }
                }),
                vec!["method"],
            ),
        },
    ]
}

fn build_harness_script(name: &str, arguments: &Value) -> anyhow::Result<String> {
    let name_literal = serde_json::to_string(name)?;
    let args_json = serde_json::to_string(arguments)?;
    let args_literal = serde_json::to_string(&args_json)?;
    let prefix_literal = serde_json::to_string(RESULT_PREFIX)?;
    let script = r#"
import base64, json

_OPENPLANTER_RESULT_PREFIX = __PREFIX_LITERAL__
_OPENPLANTER_TOOL = __NAME_LITERAL__
_OPENPLANTER_ARGS = json.loads(__ARGS_LITERAL__)
if not isinstance(_OPENPLANTER_ARGS, dict):
    raise TypeError("Browser Harness arguments must be an object")

def _openplanter_emit(ok, content=None, error=None):
    print(_OPENPLANTER_RESULT_PREFIX + json.dumps({"ok": ok, "content": content, "error": error}, ensure_ascii=True))

try:
    if _OPENPLANTER_TOOL == "browser_page_info":
        ensure_real_tab()
        _openplanter_emit(True, page_info())
    elif _OPENPLANTER_TOOL == "browser_new_tab":
        target_id = new_tab(str(_OPENPLANTER_ARGS.get("url") or "about:blank"))
        if _OPENPLANTER_ARGS.get("wait_for_load", True):
            wait_for_load(float(_OPENPLANTER_ARGS.get("timeout") or 15))
        _openplanter_emit(True, {"target_id": target_id, "page": page_info()})
    elif _OPENPLANTER_TOOL == "browser_capture_screenshot":
        ensure_real_tab()
        path = capture_screenshot(
            full=bool(_OPENPLANTER_ARGS.get("full", False)),
            max_dim=_OPENPLANTER_ARGS.get("max_dim"),
        )
        with open(path, "rb") as fh:
            image_base64 = base64.b64encode(fh.read()).decode("ascii")
        _openplanter_emit(True, {
            "path": path,
            "media_type": "image/png",
            "image_base64": image_base64,
            "page": page_info(),
        })
    elif _OPENPLANTER_TOOL == "browser_click_at_xy":
        ensure_real_tab()
        click_at_xy(
            float(_OPENPLANTER_ARGS["x"]),
            float(_OPENPLANTER_ARGS["y"]),
            button=str(_OPENPLANTER_ARGS.get("button") or "left"),
            clicks=int(_OPENPLANTER_ARGS.get("clicks") or 1),
        )
        _openplanter_emit(True, {"action": "clicked", "page": page_info()})
    elif _OPENPLANTER_TOOL == "browser_type_text":
        ensure_real_tab()
        type_text(str(_OPENPLANTER_ARGS.get("text") or ""))
        _openplanter_emit(True, {"action": "typed", "page": page_info()})
    elif _OPENPLANTER_TOOL == "browser_press_key":
        ensure_real_tab()
        press_key(str(_OPENPLANTER_ARGS["key"]), modifiers=int(_OPENPLANTER_ARGS.get("modifiers") or 0))
        _openplanter_emit(True, {"action": "pressed", "page": page_info()})
    elif _OPENPLANTER_TOOL == "browser_scroll":
        ensure_real_tab()
        scroll(
            float(_OPENPLANTER_ARGS["x"]),
            float(_OPENPLANTER_ARGS["y"]),
            dy=float(_OPENPLANTER_ARGS.get("dy", -300)),
            dx=float(_OPENPLANTER_ARGS.get("dx", 0)),
        )
        _openplanter_emit(True, {"action": "scrolled", "page": page_info()})
    elif _OPENPLANTER_TOOL == "browser_wait_for_load":
        ensure_real_tab()
        completed = wait_for_load(float(_OPENPLANTER_ARGS.get("timeout") or 15))
        _openplanter_emit(True, {"completed": bool(completed), "page": page_info()})
    elif _OPENPLANTER_TOOL == "browser_js":
        ensure_real_tab()
        _openplanter_emit(True, js(str(_OPENPLANTER_ARGS["expression"])))
    elif _OPENPLANTER_TOOL == "browser_cdp":
        params = _OPENPLANTER_ARGS.get("params") or {}
        if not isinstance(params, dict):
            raise TypeError("params must be an object")
        _openplanter_emit(True, cdp(str(_OPENPLANTER_ARGS["method"]), session_id=_OPENPLANTER_ARGS.get("session_id"), **params))
    else:
        raise ValueError(f"Unknown Browser Harness tool: {_OPENPLANTER_TOOL}")
except BaseException as exc:
    _openplanter_emit(False, error=f"{type(exc).__name__}: {exc}")
"#;
    Ok(script
        .replace("__PREFIX_LITERAL__", &prefix_literal)
        .replace("__NAME_LITERAL__", &name_literal)
        .replace("__ARGS_LITERAL__", &args_literal))
}

fn extract_harness_payload(
    stdout: &str,
    stderr: &str,
    exit_code: Option<i32>,
) -> anyhow::Result<HarnessPayload> {
    for line in stdout.lines().rev() {
        let trimmed = line.trim();
        if let Some(payload) = trimmed.strip_prefix(RESULT_PREFIX) {
            return serde_json::from_str(payload)
                .with_context(|| "failed to parse Browser Harness result marker");
        }
    }
    let stderr = stderr.trim();
    let stdout = stdout.trim();
    if let Some(code) = exit_code {
        if code != 0 {
            let detail = if !stderr.is_empty() {
                stderr
            } else if !stdout.is_empty() {
                stdout
            } else {
                "no output"
            };
            return Err(anyhow!("Browser Harness exited with code {code}. {detail}"));
        }
    }
    Err(anyhow!(
        "Browser Harness did not return a Cestus result marker."
    ))
}

fn format_harness_content(content: Option<&Value>) -> String {
    let Some(content) = content else {
        return "Browser Harness tool completed with no textual output.".into();
    };
    if let Some(text) = content.as_str() {
        let trimmed = text.trim();
        if trimmed.is_empty() {
            return "Browser Harness tool completed with no textual output.".into();
        }
        return trimmed.to_string();
    }
    if let Some(object) = content.as_object() {
        let mut display = object.clone();
        let has_image = display.remove("image_base64").is_some();
        let media_type = display
            .get("media_type")
            .and_then(Value::as_str)
            .unwrap_or("image/png")
            .to_string();
        let path = display
            .get("path")
            .and_then(Value::as_str)
            .map(str::to_string);
        let rendered = serde_json::to_string_pretty(&Value::Object(display))
            .unwrap_or_else(|_| content.to_string());
        if has_image {
            let mut suffix = format!("\n[{media_type} screenshot attached");
            if let Some(path) = path {
                suffix.push_str(&format!(" from {path}"));
            }
            suffix.push(']');
            return format!("{rendered}{suffix}");
        }
        return rendered;
    }
    serde_json::to_string_pretty(content).unwrap_or_else(|_| content.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::sync::{LazyLock, Mutex};

    static ENV_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

    fn write_fake_harness(dir: &tempfile::TempDir) -> String {
        let path = dir.path().join("browser-harness");
        fs::write(
            &path,
            format!(
                r#"#!/bin/sh
if [ "$#" -ne 0 ]; then
  echo "unexpected arguments: $*" >&2
  exit 2
fi
script="$(cat)"
if printf '%s' "$script" | grep -q '_OPENPLANTER_TOOL = "browser_capture_screenshot"'; then
  printf '%s{{"ok":true,"content":{{"path":"/tmp/openplanter-shot.png","media_type":"image/png","image_base64":"ZmFrZQ=="}},"error":null}}\n' '{}'
else
  printf '%s{{"ok":true,"content":{{"url":"https://example.com","title":"Example","bu_cdp_url":"%s","bu_name":"%s"}},"error":null}}\n' '{}' "$BU_CDP_URL" "$BU_NAME"
fi
"#,
                RESULT_PREFIX, RESULT_PREFIX
            ),
        )
        .unwrap();
        let mut permissions = fs::metadata(&path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&path, permissions).unwrap();
        path.to_string_lossy().to_string()
    }

    fn manager_with_url(browser_url: Option<&str>) -> ChromeMcpManager {
        ChromeMcpManager::new(ChromeMcpConfigKey {
            enabled: true,
            auto_connect: browser_url.is_none(),
            browser_url: browser_url.map(str::to_string),
            channel: "stable".into(),
            connect_timeout_sec: 3,
            rpc_timeout_sec: 3,
        })
    }

    #[tokio::test]
    async fn list_tools_probes_browser_harness_and_uses_browser_url_as_cdp_url() {
        let _guard = ENV_LOCK.lock().unwrap();
        let tempdir = tempfile::tempdir().unwrap();
        let fake_harness = write_fake_harness(&tempdir);
        unsafe {
            env::set_var("OPENPLANTER_BROWSER_HARNESS_COMMAND", &fake_harness);
            env::set_var("OPENPLANTER_BROWSER_HARNESS_NAME", "test-openplanter");
        }
        let manager = manager_with_url(Some("http://127.0.0.1:9222"));

        let tools = manager.list_tools(true).await.unwrap();
        assert!(tools.iter().any(|tool| tool.name == "browser_page_info"));
        assert!(tools.iter().any(|tool| tool.name == "browser_cdp"));

        let content = manager
            .call_tool("browser_page_info", &json!({}))
            .await
            .unwrap();
        assert!(content.contains("\"bu_cdp_url\": \"http://127.0.0.1:9222\""));
        assert!(content.contains("\"bu_name\": \"test-openplanter\""));
        unsafe {
            env::remove_var("OPENPLANTER_BROWSER_HARNESS_COMMAND");
            env::remove_var("OPENPLANTER_BROWSER_HARNESS_NAME");
        }
    }

    #[tokio::test]
    async fn screenshot_result_omits_base64_from_text_content() {
        let _guard = ENV_LOCK.lock().unwrap();
        let tempdir = tempfile::tempdir().unwrap();
        let fake_harness = write_fake_harness(&tempdir);
        unsafe {
            env::set_var("OPENPLANTER_BROWSER_HARNESS_COMMAND", &fake_harness);
        }
        let manager = manager_with_url(None);

        let content = manager
            .call_tool("browser_capture_screenshot", &json!({}))
            .await
            .unwrap();
        assert!(content.contains("screenshot attached"));
        assert!(content.contains("/tmp/openplanter-shot.png"));
        assert!(!content.contains("ZmFrZQ"));
        unsafe {
            env::remove_var("OPENPLANTER_BROWSER_HARNESS_COMMAND");
        }
    }

    #[tokio::test]
    async fn manual_disabled_without_browser_url_is_unavailable() {
        let manager = ChromeMcpManager::new(ChromeMcpConfigKey {
            enabled: true,
            auto_connect: false,
            browser_url: None,
            channel: "stable".into(),
            connect_timeout_sec: 1,
            rpc_timeout_sec: 1,
        });

        let err = manager.list_tools(true).await.unwrap_err();
        assert!(err.to_string().contains("cannot attach"));
        let status = manager.status_snapshot().await;
        assert_eq!(status.status, "unavailable");
        assert!(status.detail.contains("BU_CDP_URL"));
    }
}
