use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use thiserror::Error;

const FRONTMATTER_DELIMITER: &str = "---";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct WorkflowSpec {
    pub source_path: PathBuf,
    pub tracker: TrackerConfig,
    pub polling: PollingConfig,
    pub workspace: WorkspaceConfig,
    pub hooks: HookConfig,
    pub agent: WorkflowAgentConfig,
    pub template: String,
}

impl Default for WorkflowSpec {
    fn default() -> Self {
        Self {
            source_path: PathBuf::new(),
            tracker: TrackerConfig::default(),
            polling: PollingConfig::default(),
            workspace: WorkspaceConfig::default(),
            hooks: HookConfig::default(),
            agent: WorkflowAgentConfig::default(),
            template: String::new(),
        }
    }
}

impl WorkflowSpec {
    pub fn load_from_path(path: impl AsRef<Path>) -> Result<Self, WorkflowSpecError> {
        let path = path.as_ref();
        let content = fs::read_to_string(path)?;
        Self::parse(path, &content)
    }

    pub fn parse(path: impl AsRef<Path>, content: &str) -> Result<Self, WorkflowSpecError> {
        let path = path.as_ref();
        let (frontmatter, template) = split_frontmatter(content)?;
        let mut spec = if let Some(frontmatter) = frontmatter {
            let mut doc: WorkflowSpecDocument = serde_yaml::from_str(frontmatter)?;
            doc.template = normalize_template(template);
            doc.into_spec(path)
        } else {
            WorkflowSpec {
                source_path: path.to_path_buf(),
                template: normalize_template(template),
                ..WorkflowSpec::default()
            }
        };

        if spec.template.trim().is_empty() {
            return Err(WorkflowSpecError::MissingTemplate);
        }

        if spec.source_path.as_os_str().is_empty() {
            spec.source_path = path.to_path_buf();
        }

        Ok(spec)
    }

    pub fn resolved_workspace_root(&self) -> PathBuf {
        let base_dir = self
            .source_path
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_default();
        match self.workspace.root.as_deref().map(str::trim) {
            Some("") | None => base_dir.join(".openplanter").join("workspaces"),
            Some(root) => {
                let candidate = PathBuf::from(root);
                if candidate.is_absolute() {
                    candidate
                } else {
                    base_dir.join(candidate)
                }
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct TrackerConfig {
    pub kind: String,
    pub active_states: Vec<String>,
    pub terminal_states: Vec<String>,
}

impl TrackerConfig {
    fn default_kind() -> String {
        "memory".to_string()
    }
}

impl Default for TrackerConfig {
    fn default() -> Self {
        Self {
            kind: Self::default_kind(),
            active_states: Vec::new(),
            terminal_states: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct PollingConfig {
    pub interval_ms: u64,
}

impl Default for PollingConfig {
    fn default() -> Self {
        Self {
            interval_ms: 30_000,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct WorkspaceConfig {
    pub root: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct HookConfig {
    pub after_create: Vec<String>,
    pub before_remove: Vec<String>,
    pub before_run: Vec<String>,
    pub after_run: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct WorkflowAgentConfig {
    #[serde(alias = "max_concurrent")]
    pub max_concurrent_agents: u32,
    pub max_turns: u32,
}

impl Default for WorkflowAgentConfig {
    fn default() -> Self {
        Self {
            max_concurrent_agents: 1,
            max_turns: 1,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
struct WorkflowSpecDocument {
    tracker: TrackerConfig,
    polling: PollingConfig,
    workspace: WorkspaceConfig,
    hooks: HookConfig,
    agent: WorkflowAgentConfig,
    #[serde(skip)]
    template: String,
}

impl WorkflowSpecDocument {
    fn into_spec(self, path: &Path) -> WorkflowSpec {
        WorkflowSpec {
            source_path: path.to_path_buf(),
            tracker: self.tracker,
            polling: self.polling,
            workspace: self.workspace,
            hooks: self.hooks,
            agent: self.agent,
            template: self.template,
        }
    }
}

#[derive(Debug, Error)]
pub enum WorkflowSpecError {
    #[error("failed to read workflow spec: {0}")]
    Io(#[from] std::io::Error),
    #[error("workflow frontmatter is missing a closing `---` delimiter")]
    UnterminatedFrontmatter,
    #[error("failed to parse workflow frontmatter: {0}")]
    InvalidFrontmatter(#[from] serde_yaml::Error),
    #[error("workflow template body is empty")]
    MissingTemplate,
}

fn normalize_template(template: &str) -> String {
    template.trim().to_string()
}

fn split_frontmatter(content: &str) -> Result<(Option<&str>, &str), WorkflowSpecError> {
    if !content.starts_with(FRONTMATTER_DELIMITER) {
        return Ok((None, content));
    }

    let mut lines = content.lines();
    let Some(first_line) = lines.next() else {
        return Ok((None, content));
    };
    if first_line.trim() != FRONTMATTER_DELIMITER {
        return Ok((None, content));
    }

    let mut offset = first_line.len();
    if content.as_bytes().get(offset) == Some(&b'\n') {
        offset += 1;
    }

    let remainder = &content[offset..];
    if let Some(end) = remainder.find("\n---\n") {
        let frontmatter = &remainder[..end];
        let body = &remainder[(end + 5)..];
        return Ok((Some(frontmatter), body));
    }

    if let Some(stripped) = remainder.strip_suffix("\n---") {
        return Ok((Some(stripped), ""));
    }

    Err(WorkflowSpecError::UnterminatedFrontmatter)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn parses_frontmatter_and_template() {
        let dir = tempdir().unwrap();
        let workflow_path = dir.path().join("WORKFLOW.md");
        let content = r#"---
tracker:
  kind: github
  active_states:
    - todo
    - in_progress
  terminal_states:
    - done
polling:
  interval_ms: 15000
workspace:
  root: task-workspaces
hooks:
  after_create:
    - uv sync
  after_run:
    - cargo test
agent:
  max_concurrent_agents: 3
  max_turns: 8
---
# Workflow

Implement the issue carefully.
"#;

        let spec = WorkflowSpec::parse(&workflow_path, content).unwrap();

        assert_eq!(spec.tracker.kind, "github");
        assert_eq!(spec.tracker.active_states, vec!["todo", "in_progress"]);
        assert_eq!(spec.polling.interval_ms, 15_000);
        assert_eq!(spec.agent.max_concurrent_agents, 3);
        assert_eq!(spec.agent.max_turns, 8);
        assert_eq!(spec.hooks.after_create, vec!["uv sync"]);
        assert_eq!(spec.hooks.after_run, vec!["cargo test"]);
        assert_eq!(
            spec.resolved_workspace_root(),
            dir.path().join("task-workspaces")
        );
        assert_eq!(
            spec.template,
            "# Workflow\n\nImplement the issue carefully."
        );
    }

    #[test]
    fn falls_back_to_defaults_without_frontmatter() {
        let dir = tempdir().unwrap();
        let workflow_path = dir.path().join("WORKFLOW.md");
        let content = "# Prompt\n\nDo the thing.";

        let spec = WorkflowSpec::parse(&workflow_path, content).unwrap();

        assert_eq!(spec.tracker.kind, "memory");
        assert_eq!(spec.polling.interval_ms, 30_000);
        assert_eq!(spec.agent.max_concurrent_agents, 1);
        assert_eq!(
            spec.resolved_workspace_root(),
            dir.path().join(".openplanter").join("workspaces")
        );
        assert_eq!(spec.template, "# Prompt\n\nDo the thing.");
    }

    #[test]
    fn rejects_unterminated_frontmatter() {
        let err = WorkflowSpec::parse(
            "WORKFLOW.md",
            r#"---
polling:
  interval_ms: 5000
"#,
        )
        .unwrap_err();

        assert!(matches!(err, WorkflowSpecError::UnterminatedFrontmatter));
    }

    #[test]
    fn rejects_empty_template_body() {
        let err = WorkflowSpec::parse(
            "WORKFLOW.md",
            r#"---
agent:
  max_turns: 4
---
"#,
        )
        .unwrap_err();

        assert!(matches!(err, WorkflowSpecError::MissingTemplate));
    }
}
