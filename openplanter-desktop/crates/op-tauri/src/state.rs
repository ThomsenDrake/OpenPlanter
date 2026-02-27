use std::sync::Arc;
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;
use op_core::config::AgentConfig;

/// Application state shared across Tauri commands.
pub struct AppState {
    pub config: Arc<Mutex<AgentConfig>>,
    pub session_id: Arc<Mutex<Option<String>>>,
    pub cancel_token: Arc<Mutex<CancellationToken>>,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            config: Arc::new(Mutex::new(AgentConfig::from_env("."))),
            session_id: Arc::new(Mutex::new(None)),
            cancel_token: Arc::new(Mutex::new(CancellationToken::new())),
        }
    }
}
