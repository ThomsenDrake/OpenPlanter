use crate::events::{OrchestratorSnapshotEvent, OrchestratorTotalsView};
use crate::workflow_spec::{WorkflowSpec, WorkflowSpecError};
use chrono::{Duration as ChronoDuration, Utc};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::task::JoinHandle;
use tokio::time::{Duration, sleep};
use tokio_util::sync::CancellationToken;

const MIN_POLL_INTERVAL_MS: u64 = 1_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OrchestratorConfig {
    pub workflow_path: PathBuf,
}

impl OrchestratorConfig {
    pub fn new(workflow_path: PathBuf) -> Self {
        Self { workflow_path }
    }
}

pub trait OrchestratorEmitter: Send + Sync {
    fn emit_snapshot(&self, snapshot: OrchestratorSnapshotEvent);
}

pub struct OrchestratorRuntime {
    cancel: CancellationToken,
    snapshot: Arc<Mutex<OrchestratorSnapshotEvent>>,
    emitter: Arc<dyn OrchestratorEmitter>,
    task: Option<JoinHandle<()>>,
}

impl OrchestratorRuntime {
    pub async fn start(
        config: OrchestratorConfig,
        emitter: Arc<dyn OrchestratorEmitter>,
    ) -> Result<Self, WorkflowSpecError> {
        let initial_spec = WorkflowSpec::load_from_path_async(&config.workflow_path).await?;
        Ok(Self::start_with_spec(config, initial_spec, emitter))
    }

    pub fn start_with_spec(
        config: OrchestratorConfig,
        initial_spec: WorkflowSpec,
        emitter: Arc<dyn OrchestratorEmitter>,
    ) -> Self {
        let initial_snapshot =
            build_snapshot(&config.workflow_path, &initial_spec, &[], "idle", Some(0));
        emitter.emit_snapshot(initial_snapshot.clone());

        let cancel = CancellationToken::new();
        let snapshot = Arc::new(Mutex::new(initial_snapshot));
        let task = tokio::spawn(run_loop(
            config,
            initial_spec,
            snapshot.clone(),
            cancel.clone(),
            emitter.clone(),
        ));

        Self {
            cancel,
            snapshot,
            emitter,
            task: Some(task),
        }
    }

    pub async fn snapshot(&self) -> OrchestratorSnapshotEvent {
        self.snapshot.lock().await.clone()
    }

    pub fn snapshot_handle(&self) -> Arc<Mutex<OrchestratorSnapshotEvent>> {
        self.snapshot.clone()
    }

    pub async fn stop(mut self) -> OrchestratorSnapshotEvent {
        self.cancel.cancel();
        if let Some(task) = self.task.take() {
            let _ = task.await;
        }

        let mut snapshot = self.snapshot.lock().await.clone();
        snapshot.status = "stopped".to_string();
        snapshot.next_poll_at = None;
        snapshot.updated_at = Utc::now().to_rfc3339();
        self.emitter.emit_snapshot(snapshot.clone());
        snapshot
    }
}

impl Drop for OrchestratorRuntime {
    fn drop(&mut self) {
        self.cancel.cancel();
        if let Some(task) = self.task.take() {
            task.abort();
        }
    }
}

async fn run_loop(
    config: OrchestratorConfig,
    mut spec: WorkflowSpec,
    snapshot: Arc<Mutex<OrchestratorSnapshotEvent>>,
    cancel: CancellationToken,
    emitter: Arc<dyn OrchestratorEmitter>,
) {
    loop {
        let sleep_for = Duration::from_millis(effective_poll_interval_ms(spec.polling.interval_ms));
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = sleep(sleep_for) => {}
        }

        let warnings = match WorkflowSpec::load_from_path_async(&config.workflow_path).await {
            Ok(next_spec) => {
                spec = next_spec;
                Vec::new()
            }
            Err(err) => vec![format!(
                "workflow reload failed for {}: {err}",
                config.workflow_path.display()
            )],
        };
        let next_snapshot =
            build_snapshot(&config.workflow_path, &spec, &warnings, "idle", Some(0));
        *snapshot.lock().await = next_snapshot.clone();
        emitter.emit_snapshot(next_snapshot);
    }
}

fn build_snapshot(
    workflow_path: &PathBuf,
    spec: &WorkflowSpec,
    warnings: &[String],
    status: &str,
    running_count: Option<u32>,
) -> OrchestratorSnapshotEvent {
    let now = Utc::now();
    let next_poll_at = now
        + ChronoDuration::milliseconds(effective_poll_interval_ms(spec.polling.interval_ms) as i64);
    OrchestratorSnapshotEvent {
        status: status.to_string(),
        workflow_path: workflow_path.display().to_string(),
        poll_interval_ms: spec.polling.interval_ms,
        max_concurrent: spec.agent.max_concurrent_agents,
        updated_at: now.to_rfc3339(),
        next_poll_at: Some(next_poll_at.to_rfc3339()),
        running: Vec::new(),
        retrying: Vec::new(),
        totals: OrchestratorTotalsView {
            queued: 0,
            running: running_count.unwrap_or(0),
            retrying: 0,
            succeeded: 0,
            failed: 0,
        },
        warnings: warnings.to_vec(),
    }
}

fn effective_poll_interval_ms(interval_ms: u64) -> u64 {
    interval_ms.max(MIN_POLL_INTERVAL_MS)
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{DateTime, Utc};
    use std::fs;
    use tempfile::tempdir;

    #[derive(Default)]
    struct TestEmitter {
        snapshots: std::sync::Mutex<Vec<OrchestratorSnapshotEvent>>,
    }

    impl OrchestratorEmitter for TestEmitter {
        fn emit_snapshot(&self, snapshot: OrchestratorSnapshotEvent) {
            self.snapshots.lock().unwrap().push(snapshot);
        }
    }

    fn write_workflow(path: &std::path::Path, interval_ms: u64) {
        fs::write(
            path,
            format!(
                r#"---
polling:
  interval_ms: {interval_ms}
agent:
  max_concurrent_agents: 2
  max_turns: 4
---
# Workflow

Investigate and implement.
"#
            ),
        )
        .unwrap();
    }

    #[tokio::test]
    async fn starts_with_idle_snapshot_and_emits_updates() {
        let dir = tempdir().unwrap();
        let workflow_path = dir.path().join("WORKFLOW.md");
        write_workflow(&workflow_path, 20);
        let emitter = Arc::new(TestEmitter::default());

        let runtime = OrchestratorRuntime::start(
            OrchestratorConfig::new(workflow_path.clone()),
            emitter.clone(),
        )
        .await
        .unwrap();

        tokio::time::sleep(Duration::from_millis(1_100)).await;
        let snapshot = runtime.snapshot().await;

        assert_eq!(snapshot.status, "idle");
        assert_eq!(snapshot.workflow_path, workflow_path.display().to_string());
        assert_eq!(snapshot.max_concurrent, 2);
        assert!(snapshot.next_poll_at.is_some());
        assert!(emitter.snapshots.lock().unwrap().len() >= 2);

        let stopped = runtime.stop().await;
        assert_eq!(stopped.status, "stopped");
        assert!(stopped.next_poll_at.is_none());
    }

    #[tokio::test]
    async fn preserves_last_good_snapshot_when_reload_fails() {
        let dir = tempdir().unwrap();
        let workflow_path = dir.path().join("WORKFLOW.md");
        write_workflow(&workflow_path, 20);
        let emitter = Arc::new(TestEmitter::default());

        let runtime = OrchestratorRuntime::start(
            OrchestratorConfig::new(workflow_path.clone()),
            emitter.clone(),
        )
        .await
        .unwrap();

        fs::write(&workflow_path, "---\npolling:\n").unwrap();
        tokio::time::sleep(Duration::from_millis(1_100)).await;

        let snapshot = runtime.snapshot().await;
        assert_eq!(snapshot.poll_interval_ms, 20);
        assert_eq!(snapshot.max_concurrent, 2);
        assert_eq!(snapshot.warnings.len(), 1);

        let _ = runtime.stop().await;
    }

    #[tokio::test]
    async fn snapshot_uses_effective_poll_interval_for_next_poll_at() {
        let dir = tempdir().unwrap();
        let workflow_path = dir.path().join("WORKFLOW.md");
        write_workflow(&workflow_path, 20);
        let emitter = Arc::new(TestEmitter::default());

        let runtime =
            OrchestratorRuntime::start(OrchestratorConfig::new(workflow_path.clone()), emitter)
                .await
                .unwrap();

        let snapshot = runtime.snapshot().await;
        let updated_at = DateTime::parse_from_rfc3339(&snapshot.updated_at)
            .unwrap()
            .with_timezone(&Utc);
        let next_poll_at = DateTime::parse_from_rfc3339(snapshot.next_poll_at.as_deref().unwrap())
            .unwrap()
            .with_timezone(&Utc);

        assert_eq!(snapshot.poll_interval_ms, 20);
        assert!(
            next_poll_at >= updated_at + ChronoDuration::milliseconds(MIN_POLL_INTERVAL_MS as i64)
        );

        let _ = runtime.stop().await;
    }
}
