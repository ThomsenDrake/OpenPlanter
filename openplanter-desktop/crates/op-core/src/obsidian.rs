use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Component, Path, PathBuf};

use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use uuid::Uuid;

use crate::engine::investigation_state::{InvestigationState, build_question_reasoning_packet};

pub const OBSIDIAN_EXPORT_MODE_FRESH: &str = "fresh_vault";
pub const OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER: &str = "existing_vault_folder";
pub const DEFAULT_OBSIDIAN_EXPORT_SUBDIR: &str = "OpenPlanter";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObsidianExportConfig {
    pub enabled: bool,
    pub root: Option<PathBuf>,
    pub mode: String,
    pub subdir: String,
    pub generate_canvas: bool,
}

impl Default for ObsidianExportConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            root: None,
            mode: OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER.to_string(),
            subdir: DEFAULT_OBSIDIAN_EXPORT_SUBDIR.to_string(),
            generate_canvas: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObsidianExportStatus {
    pub enabled: bool,
    pub configured: bool,
    pub root: Option<String>,
    pub target_root: Option<String>,
    pub mode: String,
    pub subdir: String,
    pub generate_canvas: bool,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObsidianExportResult {
    pub exported: bool,
    pub root_path: String,
    pub investigation_dir: String,
    pub home_path: String,
    pub manifest_path: String,
    pub files_written: Vec<String>,
    pub warnings: Vec<String>,
}

#[derive(Debug, Error)]
pub enum ObsidianExportError {
    #[error("Obsidian export root is not configured")]
    MissingRoot,
    #[error("Obsidian export root must not be empty")]
    EmptyRoot,
    #[error("Obsidian export root contains invalid characters")]
    InvalidRoot,
    #[error("Obsidian export subdir must be a relative path")]
    InvalidSubdir,
    #[error("Failed to read session file {path}: {source}")]
    ReadFile {
        path: String,
        source: std::io::Error,
    },
    #[error("Failed to parse session file {path}: {source}")]
    ParseFile {
        path: String,
        source: serde_json::Error,
    },
    #[error("Failed to write Obsidian file {path}: {source}")]
    WriteFile {
        path: String,
        source: std::io::Error,
    },
    #[error("Failed to serialize Obsidian artifact: {0}")]
    Serialize(#[from] serde_json::Error),
}

pub fn normalize_obsidian_export_mode(value: Option<&str>) -> String {
    let cleaned = value
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
        .replace('-', "_");
    match cleaned.as_str() {
        OBSIDIAN_EXPORT_MODE_FRESH | "fresh" | "vault" => OBSIDIAN_EXPORT_MODE_FRESH.to_string(),
        OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER | "existing" | "folder" | "subfolder" => {
            OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER.to_string()
        }
        _ => OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER.to_string(),
    }
}

pub fn normalize_obsidian_export_subdir(value: Option<&str>) -> String {
    let cleaned = value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(DEFAULT_OBSIDIAN_EXPORT_SUBDIR);
    let normalized = cleaned.trim_matches(['/', '\\']).trim();
    if normalized.is_empty() {
        DEFAULT_OBSIDIAN_EXPORT_SUBDIR.to_string()
    } else {
        normalized.to_string()
    }
}

pub fn target_root(
    workspace: &Path,
    config: &ObsidianExportConfig,
) -> Result<PathBuf, ObsidianExportError> {
    let root = config
        .root
        .as_ref()
        .ok_or(ObsidianExportError::MissingRoot)?;
    if root.as_os_str().is_empty() {
        return Err(ObsidianExportError::EmptyRoot);
    }
    let root_text = root.to_string_lossy();
    if root_text.contains('\0') {
        return Err(ObsidianExportError::InvalidRoot);
    }
    let root_path = if root.is_absolute() {
        root.clone()
    } else {
        workspace.join(root)
    };

    match normalize_obsidian_export_mode(Some(&config.mode)).as_str() {
        OBSIDIAN_EXPORT_MODE_FRESH => Ok(root_path),
        _ => Ok(root_path.join(validate_subdir(&config.subdir)?)),
    }
}

pub fn export_status(workspace: &Path, config: &ObsidianExportConfig) -> ObsidianExportStatus {
    let mut warnings = Vec::new();
    let target = match target_root(workspace, config) {
        Ok(path) => Some(path),
        Err(error) => {
            if config.enabled {
                warnings.push(error.to_string());
            }
            None
        }
    };
    ObsidianExportStatus {
        enabled: config.enabled,
        configured: target.is_some(),
        root: config.root.as_ref().map(|path| path.display().to_string()),
        target_root: target.map(|path| path.display().to_string()),
        mode: normalize_obsidian_export_mode(Some(&config.mode)),
        subdir: normalize_obsidian_export_subdir(Some(&config.subdir)),
        generate_canvas: config.generate_canvas,
        warnings,
    }
}

pub fn investigation_slug(investigation_id: &str) -> String {
    let slug = safe_component(investigation_id).to_ascii_lowercase();
    format!("{}-{}", slug, stable_slug_suffix(investigation_id))
}

pub fn markdown_link(label: &str, target: &str) -> String {
    format!(
        "[{}]({})",
        markdown_label(label),
        percent_encode_markdown_target(target)
    )
}

pub fn obsidian_open_uri_for_path(path: &Path) -> String {
    format!(
        "obsidian://open?path={}",
        percent_encode_uri_component(&path.display().to_string())
    )
}

pub fn export_investigation_pack(
    workspace: &Path,
    session_dir: &Path,
    state: &InvestigationState,
    config: &ObsidianExportConfig,
) -> Result<ObsidianExportResult, ObsidianExportError> {
    let target_root = target_root(workspace, config)?;
    let session_id = if state.session_id.trim().is_empty() {
        session_dir
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("session")
            .to_string()
    } else {
        state.session_id.clone()
    };
    let investigation_id = state
        .active_investigation_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(session_id.as_str())
        .to_string();
    let slug = investigation_slug(&investigation_id);
    let investigation_dir = target_root.join("Investigations").join(&slug);
    let generated_at = Utc::now().to_rfc3339();
    let packet = build_question_reasoning_packet(state, 64, 12);
    let graph_projection = read_optional_json(&session_dir.join("graph_projection.json"))?;
    let replay_entries = read_recent_replay_entries(&session_dir.join("replay.jsonl"), 20)?;

    let mut files: Vec<(PathBuf, String)> = vec![
        (
            investigation_dir.join("Home.md"),
            render_home(
                state,
                &packet,
                &investigation_id,
                &session_id,
                &generated_at,
                config.generate_canvas,
            ),
        ),
        (
            investigation_dir.join("Findings.md"),
            render_findings(&packet, &investigation_id, &session_id, &generated_at),
        ),
        (
            investigation_dir.join("Questions.md"),
            render_questions(
                state,
                &packet,
                &investigation_id,
                &session_id,
                &generated_at,
            ),
        ),
        (
            investigation_dir.join("Evidence.md"),
            render_evidence(state, &investigation_id, &session_id, &generated_at),
        ),
        (
            investigation_dir.join("Tasks.md"),
            render_tasks(
                state,
                &packet,
                &investigation_id,
                &session_id,
                &generated_at,
            ),
        ),
        (
            investigation_dir.join("Sessions.md"),
            render_sessions(
                state,
                &replay_entries,
                &investigation_id,
                &session_id,
                &generated_at,
            ),
        ),
    ];

    if config.generate_canvas {
        let canvas = render_canvas(state, graph_projection.as_ref())?;
        files.push((
            investigation_dir.join("Investigation Map.canvas"),
            serde_json::to_string_pretty(&canvas)?,
        ));
    } else {
        remove_generated_file_if_exists(&investigation_dir.join("Investigation Map.canvas"))?;
    }

    let index = render_index(&target_root, &investigation_id, &slug, &generated_at)?;
    files.push((target_root.join("Index.md"), index));

    let manifest_path = investigation_dir.join("Manifest.json");
    let manifest = render_manifest(
        &investigation_id,
        &session_id,
        &generated_at,
        config,
        &files,
        &manifest_path,
        &target_root,
    )?;
    files.push((manifest_path, manifest));

    let mut files_written = Vec::new();
    for (path, content) in &files {
        atomic_write(path, content)?;
        files_written.push(path.display().to_string());
    }

    Ok(ObsidianExportResult {
        exported: true,
        root_path: target_root.display().to_string(),
        investigation_dir: investigation_dir.display().to_string(),
        home_path: investigation_dir.join("Home.md").display().to_string(),
        manifest_path: investigation_dir
            .join("Manifest.json")
            .display()
            .to_string(),
        files_written,
        warnings: Vec::new(),
    })
}

fn validate_subdir(value: &str) -> Result<PathBuf, ObsidianExportError> {
    let cleaned = normalize_obsidian_export_subdir(Some(value));
    let path = Path::new(&cleaned);
    if path.is_absolute() || cleaned.contains('\0') {
        return Err(ObsidianExportError::InvalidSubdir);
    }
    let mut out = PathBuf::new();
    let mut saw_normal = false;
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::Normal(part) => {
                out.push(part);
                saw_normal = true;
            }
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(ObsidianExportError::InvalidSubdir);
            }
        }
    }
    if !saw_normal {
        return Err(ObsidianExportError::InvalidSubdir);
    }
    Ok(out)
}

fn safe_component(text: &str) -> String {
    let mut out = String::new();
    let mut last_dash = false;
    for ch in text.chars() {
        if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-') {
            out.push(ch);
            last_dash = false;
        } else if !last_dash {
            out.push('-');
            last_dash = true;
        }
    }
    let trimmed = out.trim_matches(['.', '-']).to_string();
    if trimmed.is_empty() {
        "investigation".to_string()
    } else {
        trimmed
    }
}

fn stable_slug_suffix(text: &str) -> String {
    let digest = crc32fast::hash(text.as_bytes());
    format!("{digest:08x}")
}

fn yaml_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

fn frontmatter(
    openplanter_type: &str,
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
    title: &str,
) -> String {
    format!(
        "---\nopenplanter_type: {}\ninvestigation_id: {}\nsession_id: {}\ngenerated_at: {}\ntitle: {}\ntags:\n  - openplanter\n  - investigation\n---\n\n",
        yaml_quote(openplanter_type),
        yaml_quote(investigation_id),
        yaml_quote(session_id),
        yaml_quote(generated_at),
        yaml_quote(title),
    )
}

fn render_home(
    state: &InvestigationState,
    packet: &Value,
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
    generate_canvas: bool,
) -> String {
    let supported = array_at(packet, &["findings", "supported"]).len();
    let contested = array_at(packet, &["findings", "contested"]).len();
    let unresolved = array_at(packet, &["findings", "unresolved"]).len();
    let open_questions = array_at(packet, &["unresolved_questions"]).len();
    let candidate_actions = array_at(packet, &["candidate_actions"]).len();
    let objective = state.objective.trim();

    let mut lines = vec![
        frontmatter(
            "investigation",
            investigation_id,
            session_id,
            generated_at,
            &format!("Investigation Home: {investigation_id}"),
        ),
        format!("# Investigation Home: {investigation_id}"),
        String::new(),
        "> Generated by OpenPlanter from `investigation_state.json`. Edits here are not merged back into OpenPlanter.".to_string(),
        String::new(),
        "## Navigation".to_string(),
        format!("- {}", markdown_link("Findings", "Findings.md")),
        format!("- {}", markdown_link("Questions", "Questions.md")),
        format!("- {}", markdown_link("Evidence", "Evidence.md")),
        format!("- {}", markdown_link("Tasks", "Tasks.md")),
        format!("- {}", markdown_link("Sessions", "Sessions.md")),
    ];
    if generate_canvas {
        lines.push(format!(
            "- {}",
            markdown_link("Investigation Map", "Investigation Map.canvas")
        ));
    }
    lines.extend([
        String::new(),
        "## Current Status".to_string(),
        format!("- **Session ID**: `{}`", inline_text(session_id)),
        format!(
            "- **Investigation ID**: `{}`",
            inline_text(investigation_id)
        ),
        format!("- **Generated**: `{}`", inline_text(generated_at)),
        format!(
            "- **Objective**: {}",
            if objective.is_empty() {
                "Not set".to_string()
            } else {
                inline_text(objective)
            }
        ),
        format!("- **Open questions**: {open_questions}"),
        format!("- **Supported conclusions**: {supported}"),
        format!("- **Contested conclusions**: {contested}"),
        format!("- **Unresolved conclusions**: {unresolved}"),
        format!("- **Candidate actions**: {candidate_actions}"),
        String::new(),
        "## Quick Read".to_string(),
    ]);

    if let Some(first) = array_at(packet, &["findings", "supported"]).first() {
        lines.push(format!(
            "- Top supported finding: {}",
            inline_text(&record_label(first, "claim", &["text", "claim_text"]))
        ));
    } else {
        lines.push("- No supported finding has been promoted yet.".to_string());
    }
    if let Some(first) = array_at(packet, &["unresolved_questions"]).first() {
        lines.push(format!(
            "- Next open question: {}",
            inline_text(&record_label(first, "question", &["question_text", "text"]))
        ));
    }

    finish(lines)
}

fn render_findings(
    packet: &Value,
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
) -> String {
    let mut lines = vec![
        frontmatter(
            "findings",
            investigation_id,
            session_id,
            generated_at,
            "Findings",
        ),
        "# Findings".to_string(),
        String::new(),
        format!("Back to {}", markdown_link("Home", "Home.md")),
        String::new(),
    ];
    render_finding_section(
        &mut lines,
        "Supported Findings",
        array_at(packet, &["findings", "supported"]),
    );
    render_finding_section(
        &mut lines,
        "Contested Findings",
        array_at(packet, &["findings", "contested"]),
    );
    render_finding_section(
        &mut lines,
        "Unresolved Findings",
        array_at(packet, &["findings", "unresolved"]),
    );
    finish(lines)
}

fn render_finding_section(lines: &mut Vec<String>, title: &str, claims: &[Value]) {
    lines.push(format!("## {title}"));
    if claims.is_empty() {
        lines.push("- _None recorded._".to_string());
        lines.push(String::new());
        return;
    }
    for claim in claims {
        let id = value_str(claim, "id").unwrap_or("claim");
        let text = record_label(claim, "claim", &["text", "claim_text"]);
        lines.push(format!("### {}", inline_text(id)));
        lines.push(format!("- **Claim**: {}", inline_text(&text)));
        if let Some(status) = value_str(claim, "status") {
            lines.push(format!("- **Status**: `{}`", inline_text(status)));
        }
        if let Some(confidence) = claim.get("confidence").filter(|value| !value.is_null()) {
            lines.push(format!(
                "- **Confidence**: `{}`",
                inline_text(&confidence.to_string())
            ));
        }
        let support = string_list(claim.get("support_evidence_ids"));
        if !support.is_empty() {
            lines.push(format!(
                "- **Supporting evidence**: {}",
                support
                    .iter()
                    .map(|id| markdown_link(id, &format!("Evidence.md#{id}")))
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        let contradictions = string_list(claim.get("contradiction_evidence_ids"));
        if !contradictions.is_empty() {
            lines.push(format!(
                "- **Contradicting evidence**: {}",
                contradictions
                    .iter()
                    .map(|id| markdown_link(id, &format!("Evidence.md#{id}")))
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        lines.push(String::new());
    }
}

fn render_questions(
    state: &InvestigationState,
    packet: &Value,
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
) -> String {
    let mut lines = vec![
        frontmatter(
            "questions",
            investigation_id,
            session_id,
            generated_at,
            "Questions",
        ),
        "# Questions".to_string(),
        String::new(),
        format!("Back to {}", markdown_link("Home", "Home.md")),
        String::new(),
        "## Open Questions".to_string(),
    ];
    let questions = array_at(packet, &["unresolved_questions"]);
    if questions.is_empty() {
        lines.push("- _No open questions recorded._".to_string());
    }
    for question in questions {
        let id = value_str(question, "id").unwrap_or("question");
        let text = record_label(question, "question", &["question_text", "text"]);
        lines.push(format!("### {}", inline_text(id)));
        lines.push(format!("- **Question**: {}", inline_text(&text)));
        if let Some(priority) = value_str(question, "priority") {
            lines.push(format!("- **Priority**: `{}`", inline_text(priority)));
        }
        if let Some(raw_question) = state.questions.get(id) {
            let docs = collect_needed_documents(raw_question);
            if !docs.is_empty() {
                lines.push("- **Needed documents**:".to_string());
                for doc in docs {
                    lines.push(format!("  - {}", inline_text(&doc)));
                }
            }
        }
        lines.push(String::new());
    }
    finish(lines)
}

fn render_evidence(
    state: &InvestigationState,
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
) -> String {
    let mut lines = vec![
        frontmatter(
            "evidence",
            investigation_id,
            session_id,
            generated_at,
            "Evidence",
        ),
        "# Evidence".to_string(),
        String::new(),
        format!("Back to {}", markdown_link("Home", "Home.md")),
        String::new(),
    ];
    if state.evidence.is_empty() {
        lines.push("- _No evidence recorded._".to_string());
    }
    for (evidence_id, record) in &state.evidence {
        lines.push(format!("## {}", inline_text(evidence_id)));
        lines.push(format!(
            "- **Label**: {}",
            inline_text(&record_label(
                record,
                evidence_id,
                &["title", "name", "description", "content", "text"]
            ))
        ));
        for key in ["evidence_type", "type", "confidence", "confidence_id"] {
            if let Some(value) = value_as_display(record.get(key)) {
                lines.push(format!(
                    "- **{}**: `{}`",
                    key.replace('_', " "),
                    inline_text(&value)
                ));
            }
        }
        if let Some(target) = first_target(record) {
            let label = if target.starts_with("http://") || target.starts_with("https://") {
                "External source"
            } else {
                "Source reference"
            };
            lines.push(format!("- **Source**: {}", markdown_link(label, &target)));
        }
        let body = record_label(record, "", &["content", "text", "description"]);
        if !body.is_empty() {
            lines.push(String::new());
            lines.push("```text".to_string());
            lines.push(truncate(&body, 4000));
            lines.push("```".to_string());
        }
        lines.push(String::new());
    }
    finish(lines)
}

fn render_tasks(
    state: &InvestigationState,
    packet: &Value,
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
) -> String {
    let mut lines = vec![
        frontmatter("tasks", investigation_id, session_id, generated_at, "Tasks"),
        "# Tasks".to_string(),
        String::new(),
        format!("Back to {}", markdown_link("Home", "Home.md")),
        String::new(),
        "## Tracked Tasks".to_string(),
    ];
    if state.tasks.is_empty() {
        lines.push("- _No tracked tasks recorded._".to_string());
    }
    for (task_id, task) in &state.tasks {
        lines.push(format!("### {}", inline_text(task_id)));
        lines.push(format!(
            "- **Description**: {}",
            inline_text(&record_label(
                task,
                task_id,
                &["description", "title", "label", "text"]
            ))
        ));
        for key in ["status", "priority", "created_at", "updated_at"] {
            if let Some(value) = value_as_display(task.get(key)) {
                lines.push(format!(
                    "- **{}**: `{}`",
                    key.replace('_', " "),
                    inline_text(&value)
                ));
            }
        }
        lines.push(String::new());
    }

    lines.push("## Candidate Actions".to_string());
    let actions = array_at(packet, &["candidate_actions"]);
    if actions.is_empty() {
        lines.push("- _No candidate actions recorded._".to_string());
    }
    for action in actions {
        let id = value_str(action, "id")
            .or_else(|| value_str(action, "action_id"))
            .unwrap_or("action");
        lines.push(format!("### {}", inline_text(id)));
        lines.push(format!(
            "- **Action**: {}",
            inline_text(&record_label(
                action,
                id,
                &["title", "description", "label", "action_type"]
            ))
        ));
        for key in ["priority", "status", "action_type"] {
            if let Some(value) = value_as_display(action.get(key)) {
                lines.push(format!(
                    "- **{}**: `{}`",
                    key.replace('_', " "),
                    inline_text(&value)
                ));
            }
        }
        let sources = string_list(action.get("required_sources"));
        if !sources.is_empty() {
            lines.push("- **Required sources**:".to_string());
            for source in sources {
                lines.push(format!("  - {}", inline_text(&source)));
            }
        }
        lines.push(String::new());
    }
    finish(lines)
}

fn render_sessions(
    state: &InvestigationState,
    replay_entries: &[ReplaySummary],
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
) -> String {
    let mut lines = vec![
        frontmatter(
            "sessions",
            investigation_id,
            session_id,
            generated_at,
            "Sessions",
        ),
        "# Sessions".to_string(),
        String::new(),
        format!("Back to {}", markdown_link("Home", "Home.md")),
        String::new(),
        "## Current Session".to_string(),
        format!("- **Session ID**: `{}`", inline_text(session_id)),
        format!("- **Generated**: `{}`", inline_text(generated_at)),
        String::new(),
        "## Turn History".to_string(),
    ];
    if state.legacy.turn_history.is_empty() {
        lines.push("- _No turn summaries recorded._".to_string());
    }
    for turn in &state.legacy.turn_history {
        let objective = value_str(turn, "objective").unwrap_or("Untitled turn");
        let timestamp = value_str(turn, "timestamp").unwrap_or("");
        lines.push(format!("### {}", inline_text(objective)));
        if !timestamp.is_empty() {
            lines.push(format!("- **Timestamp**: `{}`", inline_text(timestamp)));
        }
        if let Some(steps) = turn.get("steps_used").and_then(Value::as_u64) {
            lines.push(format!("- **Steps used**: {steps}"));
        }
        if let Some(result) = value_str(turn, "result_preview") {
            lines.push(format!("- **Result**: {}", inline_text(result)));
        }
        lines.push(String::new());
    }

    lines.push("## Recent Replay Summary".to_string());
    if replay_entries.is_empty() {
        lines.push("- _No replay summary available._".to_string());
    }
    for entry in replay_entries {
        lines.push(format!(
            "- `{}` **{}**: {}",
            inline_text(&entry.timestamp),
            inline_text(&entry.role),
            inline_text(&truncate(&entry.content, 180))
        ));
    }
    finish(lines)
}

fn render_manifest(
    investigation_id: &str,
    session_id: &str,
    generated_at: &str,
    config: &ObsidianExportConfig,
    files: &[(PathBuf, String)],
    manifest_path: &Path,
    target_root: &Path,
) -> Result<String, serde_json::Error> {
    let mut relative_files = files
        .iter()
        .filter_map(|(path, _)| path.strip_prefix(target_root).ok())
        .map(|path| path.to_string_lossy().replace('\\', "/"))
        .collect::<Vec<_>>();
    if let Ok(path) = manifest_path.strip_prefix(target_root) {
        relative_files.push(path.to_string_lossy().replace('\\', "/"));
    }
    serde_json::to_string_pretty(&serde_json::json!({
        "schema": "openplanter.obsidian_pack.v1",
        "investigation_id": investigation_id,
        "session_id": session_id,
        "generated_at": generated_at,
        "mode": normalize_obsidian_export_mode(Some(&config.mode)),
        "generate_canvas": config.generate_canvas,
        "files": relative_files,
        "source": {
            "type": "generated_pack",
            "canonical_state": "investigation_state.json"
        }
    }))
}

fn render_index(
    target_root: &Path,
    current_investigation_id: &str,
    current_slug: &str,
    generated_at: &str,
) -> Result<String, ObsidianExportError> {
    let mut rows = BTreeMap::new();
    let investigations_dir = target_root.join("Investigations");
    if let Ok(entries) = fs::read_dir(&investigations_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.join("Home.md").exists() {
                continue;
            }
            let slug = entry.file_name().to_string_lossy().to_string();
            rows.entry(slug.clone()).or_insert_with(|| {
                (
                    slug,
                    format!(
                        "Investigations/{}/Home.md",
                        entry.file_name().to_string_lossy()
                    ),
                )
            });
        }
    }
    rows.insert(
        current_slug.to_string(),
        (
            current_investigation_id.to_string(),
            format!("Investigations/{current_slug}/Home.md"),
        ),
    );

    let mut lines = vec![
        frontmatter(
            "index",
            "workspace",
            "workspace",
            generated_at,
            "OpenPlanter Investigations",
        ),
        "# OpenPlanter Investigations".to_string(),
        String::new(),
        "> Generated by OpenPlanter. This folder is safe to place inside an Obsidian vault."
            .to_string(),
        String::new(),
        "| Investigation | Home |".to_string(),
        "| --- | --- |".to_string(),
    ];
    for (_slug, (label, path)) in rows {
        lines.push(format!(
            "| {} | {} |",
            inline_text(&label).replace('|', "\\|"),
            markdown_link("Open", &path)
        ));
    }
    Ok(finish(lines))
}

fn render_canvas(
    state: &InvestigationState,
    graph_projection: Option<&Value>,
) -> Result<Value, serde_json::Error> {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();
    let file_nodes = [
        ("file-home", "Home.md", 0, 0),
        ("file-findings", "Findings.md", 420, 0),
        ("file-questions", "Questions.md", 840, 0),
        ("file-evidence", "Evidence.md", 0, 340),
        ("file-tasks", "Tasks.md", 420, 340),
        ("file-sessions", "Sessions.md", 840, 340),
    ];
    for (id, file, x, y) in file_nodes {
        nodes.push(serde_json::json!({
            "id": id,
            "type": "file",
            "file": file,
            "x": x,
            "y": y,
            "width": 360,
            "height": 260,
        }));
        if id != "file-home" {
            edges.push(serde_json::json!({
                "id": format!("edge-home-{id}"),
                "fromNode": "file-home",
                "toNode": id,
                "label": "section",
            }));
        }
    }

    let graph_nodes = graph_projection
        .and_then(|value| value.get("nodes"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_else(|| fallback_graph_nodes(state));
    let graph_edges = graph_projection
        .and_then(|value| value.get("edges"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let mut node_id_map = HashMap::new();
    for (index, node) in graph_nodes.iter().take(80).enumerate() {
        let source_id = value_str(node, "id")
            .map(ToString::to_string)
            .unwrap_or_else(|| format!("node-{index}"));
        let canvas_id = format!(
            "graph-{}-{}",
            safe_component(&source_id),
            stable_slug_suffix(&source_id)
        );
        node_id_map.insert(source_id.clone(), canvas_id.clone());
        let label = record_label(node, &source_id, &["label", "type"]);
        let kind = value_str(node, "type").unwrap_or("Node");
        let detail = node
            .get("properties")
            .and_then(|props| props.get("text").or_else(|| props.get("description")))
            .and_then(Value::as_str)
            .unwrap_or_default();
        nodes.push(serde_json::json!({
            "id": canvas_id,
            "type": "text",
            "text": format!("**{}**\n\nType: `{}`\n\n{}", label, kind, truncate(detail, 500)),
            "x": ((index % 4) as i64) * 360,
            "y": 720 + ((index / 4) as i64) * 240,
            "width": 320,
            "height": 180,
        }));
    }

    for (index, edge) in graph_edges.iter().take(160).enumerate() {
        let Some(source) = value_str(edge, "source").or_else(|| value_str(edge, "fromNode")) else {
            continue;
        };
        let Some(target) = value_str(edge, "target").or_else(|| value_str(edge, "toNode")) else {
            continue;
        };
        let (Some(from), Some(to)) = (node_id_map.get(source), node_id_map.get(target)) else {
            continue;
        };
        let label = value_str(edge, "type")
            .or_else(|| value_str(edge, "label"))
            .unwrap_or("relates");
        edges.push(serde_json::json!({
            "id": format!("graph-edge-{index}"),
            "fromNode": from,
            "toNode": to,
            "label": label,
        }));
    }

    Ok(serde_json::json!({
        "nodes": nodes,
        "edges": edges,
    }))
}

fn fallback_graph_nodes(state: &InvestigationState) -> Vec<Value> {
    let mut nodes = Vec::new();
    for (id, claim) in &state.claims {
        nodes.push(serde_json::json!({
            "id": format!("claim:{id}"),
            "type": "Claim",
            "label": record_label(claim, id, &["claim_text", "text"]),
            "properties": {"text": record_label(claim, "", &["claim_text", "text"])}
        }));
    }
    for (id, question) in &state.questions {
        nodes.push(serde_json::json!({
            "id": format!("question:{id}"),
            "type": "Question",
            "label": record_label(question, id, &["question_text", "text", "question"]),
            "properties": {"text": record_label(question, "", &["question_text", "text", "question"])}
        }));
    }
    for (id, evidence) in &state.evidence {
        nodes.push(serde_json::json!({
            "id": format!("evidence:{id}"),
            "type": "Evidence",
            "label": record_label(evidence, id, &["title", "description", "content", "text"]),
            "properties": {"text": record_label(evidence, "", &["content", "text", "description"])}
        }));
    }
    nodes
}

fn atomic_write(path: &Path, content: &str) -> Result<(), ObsidianExportError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| ObsidianExportError::WriteFile {
            path: parent.display().to_string(),
            source,
        })?;
    }
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("openplanter");
    let tmp = path.with_file_name(format!(".{file_name}.tmp-{}", Uuid::new_v4()));
    fs::write(&tmp, content).map_err(|source| ObsidianExportError::WriteFile {
        path: tmp.display().to_string(),
        source,
    })?;
    match fs::rename(&tmp, path) {
        Ok(()) => Ok(()),
        Err(first_error) => {
            if path.exists() {
                if let Err(remove_error) = fs::remove_file(path) {
                    let _ = fs::remove_file(&tmp);
                    return Err(ObsidianExportError::WriteFile {
                        path: path.display().to_string(),
                        source: remove_error,
                    });
                }
                fs::rename(&tmp, path).map_err(|source| {
                    let _ = fs::remove_file(&tmp);
                    ObsidianExportError::WriteFile {
                        path: path.display().to_string(),
                        source,
                    }
                })
            } else {
                let _ = fs::remove_file(&tmp);
                Err(ObsidianExportError::WriteFile {
                    path: path.display().to_string(),
                    source: first_error,
                })
            }
        }
    }
}

fn remove_generated_file_if_exists(path: &Path) -> Result<(), ObsidianExportError> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(source) if source.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(source) => Err(ObsidianExportError::WriteFile {
            path: path.display().to_string(),
            source,
        }),
    }
}

fn read_optional_json(path: &Path) -> Result<Option<Value>, ObsidianExportError> {
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(path).map_err(|source| ObsidianExportError::ReadFile {
        path: path.display().to_string(),
        source,
    })?;
    let parsed =
        serde_json::from_str(&content).map_err(|source| ObsidianExportError::ParseFile {
            path: path.display().to_string(),
            source,
        })?;
    Ok(Some(parsed))
}

#[derive(Debug, Clone)]
struct ReplaySummary {
    role: String,
    timestamp: String,
    content: String,
}

fn read_recent_replay_entries(
    path: &Path,
    limit: usize,
) -> Result<Vec<ReplaySummary>, ObsidianExportError> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let content = fs::read_to_string(path).map_err(|source| ObsidianExportError::ReadFile {
        path: path.display().to_string(),
        source,
    })?;
    let mut entries = Vec::new();
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let Ok(value) = serde_json::from_str::<Value>(trimmed) else {
            continue;
        };
        let payload = value.get("payload").unwrap_or(&value);
        let role = value_str(payload, "role")
            .or_else(|| value_str(payload, "type"))
            .or_else(|| value_str(&value, "role"))
            .unwrap_or("entry");
        let content = value_str(payload, "content")
            .or_else(|| value_str(payload, "text"))
            .or_else(|| value_str(&value, "content"))
            .unwrap_or("");
        if content.trim().is_empty() {
            continue;
        }
        let timestamp = value_str(payload, "timestamp")
            .or_else(|| value_str(&value, "timestamp"))
            .or_else(|| value_str(&value, "recorded_at"))
            .unwrap_or("");
        entries.push(ReplaySummary {
            role: role.to_string(),
            timestamp: timestamp.to_string(),
            content: content.to_string(),
        });
    }
    if entries.len() > limit {
        entries = entries.split_off(entries.len() - limit);
    }
    Ok(entries)
}

fn array_at<'a>(value: &'a Value, path: &[&str]) -> &'a [Value] {
    let mut current = value;
    for key in path {
        let Some(next) = current.get(*key) else {
            return &[];
        };
        current = next;
    }
    current.as_array().map(Vec::as_slice).unwrap_or(&[])
}

fn value_str<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn value_as_display(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::Null => None,
        Value::String(text) => Some(text.trim().to_string()).filter(|value| !value.is_empty()),
        Value::Bool(value) => Some(value.to_string()),
        Value::Number(value) => Some(value.to_string()),
        other => Some(other.to_string()),
    }
}

fn record_label(value: &Value, fallback: &str, keys: &[&str]) -> String {
    for key in keys {
        if let Some(text) = value_str(value, key) {
            return truncate(text, 240);
        }
    }
    fallback.to_string()
}

fn string_list(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToString::to_string)
            .collect(),
        Some(Value::String(text)) if !text.trim().is_empty() => vec![text.trim().to_string()],
        _ => Vec::new(),
    }
}

fn collect_needed_documents(question: &Value) -> Vec<String> {
    [
        "needed_documents",
        "required_documents",
        "documents_needed",
        "missing_documents",
        "required_sources",
        "source_uris",
        "sources",
        "urls",
    ]
    .iter()
    .flat_map(|key| string_list(question.get(*key)))
    .collect()
}

fn first_target(record: &Value) -> Option<String> {
    for key in ["source_uri", "canonical_source_uri", "url", "artifact_path"] {
        if let Some(text) = value_str(record, key) {
            return Some(text.to_string());
        }
    }
    None
}

fn markdown_label(label: &str) -> String {
    inline_text(label).replace('[', "\\[").replace(']', "\\]")
}

fn percent_encode_markdown_target(target: &str) -> String {
    let external = target.starts_with("http://")
        || target.starts_with("https://")
        || target.starts_with("obsidian://");
    let mut out = String::new();
    for byte in target.as_bytes() {
        if byte.is_ascii_alphanumeric()
            || matches!(*byte, b'-' | b'_' | b'.' | b'~' | b'/' | b'#')
            || (external
                && matches!(
                    *byte,
                    b':' | b'?'
                        | b'&'
                        | b'='
                        | b'%'
                        | b'+'
                        | b','
                        | b';'
                        | b'@'
                        | b'!'
                        | b'$'
                        | b'\''
                ))
        {
            out.push(*byte as char);
        } else {
            out.push_str(&format!("%{:02X}", *byte));
        }
    }
    out
}

fn percent_encode_uri_component(target: &str) -> String {
    let mut out = String::new();
    for byte in target.as_bytes() {
        if byte.is_ascii_alphanumeric() || matches!(*byte, b'-' | b'_' | b'.' | b'~') {
            out.push(*byte as char);
        } else {
            out.push_str(&format!("%{:02X}", *byte));
        }
    }
    out
}

fn inline_text(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn truncate(value: &str, max_chars: usize) -> String {
    let mut out = String::new();
    for (index, ch) in value.chars().enumerate() {
        if index >= max_chars {
            out.push_str("...");
            return out;
        }
        out.push(ch);
    }
    out
}

fn finish(lines: Vec<String>) -> String {
    lines.join("\n").trim_end().to_string() + "\n"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slug_is_stable_and_safe() {
        assert_eq!(
            investigation_slug("Freebee / Wire Transfers"),
            investigation_slug("Freebee / Wire Transfers")
        );
        assert!(
            investigation_slug("Freebee / Wire Transfers").starts_with("freebee-wire-transfers-")
        );
    }

    #[test]
    fn markdown_links_are_percent_encoded() {
        assert_eq!(
            markdown_link("Wire records", "Evidence Records.md#ev 1"),
            "[Wire records](Evidence%20Records.md#ev%201)"
        );
        assert_eq!(
            markdown_link(
                "External source",
                "https://example.com/a file?q=one two&ok=1"
            ),
            "[External source](https://example.com/a%20file?q=one%20two&ok=1)"
        );
    }

    #[test]
    fn subdir_normalization_defaults_empty_results() {
        assert_eq!(
            normalize_obsidian_export_subdir(None),
            DEFAULT_OBSIDIAN_EXPORT_SUBDIR
        );
        assert_eq!(
            normalize_obsidian_export_subdir(Some("")),
            DEFAULT_OBSIDIAN_EXPORT_SUBDIR
        );
        assert_eq!(
            normalize_obsidian_export_subdir(Some("/")),
            DEFAULT_OBSIDIAN_EXPORT_SUBDIR
        );
        assert_eq!(
            normalize_obsidian_export_subdir(Some("\\\\")),
            DEFAULT_OBSIDIAN_EXPORT_SUBDIR
        );
        assert_eq!(
            normalize_obsidian_export_subdir(Some("/Research/OpenPlanter/")),
            "Research/OpenPlanter"
        );
    }

    #[test]
    fn target_root_supports_fresh_and_existing_vault_modes() {
        let workspace = Path::new("/tmp/workspace");
        let mut config = ObsidianExportConfig {
            root: Some(PathBuf::from("/tmp/Vault")),
            mode: OBSIDIAN_EXPORT_MODE_FRESH.to_string(),
            ..Default::default()
        };
        assert_eq!(
            target_root(workspace, &config).unwrap(),
            PathBuf::from("/tmp/Vault")
        );

        config.mode = OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER.to_string();
        config.subdir = "Research/OpenPlanter".to_string();
        assert_eq!(
            target_root(workspace, &config).unwrap(),
            PathBuf::from("/tmp/Vault/Research/OpenPlanter")
        );
    }

    #[test]
    fn canvas_graph_node_ids_are_unique_after_sanitizing() {
        let state = InvestigationState::new("session-1");
        let graph = serde_json::json!({
            "nodes": [
                {"id": "a b", "type": "Claim", "label": "A B"},
                {"id": "a-b", "type": "Claim", "label": "A dash B"}
            ],
            "edges": [
                {"source": "a b", "target": "a-b", "type": "related"}
            ]
        });

        let canvas = render_canvas(&state, Some(&graph)).unwrap();
        let graph_node_ids: Vec<String> = canvas["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|node| node["type"] == "text")
            .filter_map(|node| node["id"].as_str().map(ToString::to_string))
            .collect();
        let unique_ids: std::collections::HashSet<String> =
            graph_node_ids.iter().cloned().collect();
        assert_eq!(graph_node_ids.len(), 2);
        assert_eq!(unique_ids.len(), 2);
        assert!(graph_node_ids.iter().all(|id| id.starts_with("graph-a-b-")));

        let graph_edge = canvas["edges"]
            .as_array()
            .unwrap()
            .iter()
            .find(|edge| edge["id"] == "graph-edge-0")
            .unwrap();
        assert_ne!(graph_edge["fromNode"], graph_edge["toNode"]);
        assert!(unique_ids.contains(graph_edge["fromNode"].as_str().unwrap()));
        assert!(unique_ids.contains(graph_edge["toNode"].as_str().unwrap()));
    }

    #[test]
    fn export_pack_writes_markdown_manifest_and_canvas() {
        let workspace = tempfile::tempdir().unwrap();
        let session_dir = workspace.path().join(".openplanter/sessions/session-1");
        fs::create_dir_all(&session_dir).unwrap();
        let mut state = InvestigationState::new("session-1");
        state.active_investigation_id = Some("Freebee / Wire Transfers".to_string());
        state.objective = "Map suspicious wire transfers".to_string();
        state.claims.insert(
            "cl 1".to_string(),
            serde_json::json!({
                "id": "cl 1",
                "claim_text": "Acme received a suspicious transfer.",
                "status": "supported",
                "support_evidence_ids": ["ev 1"],
                "confidence": "medium"
            }),
        );
        state.evidence.insert(
            "ev 1".to_string(),
            serde_json::json!({
                "id": "ev 1",
                "evidence_type": "document",
                "content": "Wire memo",
                "source_uri": "docs/wire memo.md"
            }),
        );
        state.questions.insert(
            "q 1".to_string(),
            serde_json::json!({
                "id": "q 1",
                "question_text": "Who approved the transfer?",
                "priority": "high",
                "needed_documents": ["approval memo"]
            }),
        );
        let config = ObsidianExportConfig {
            enabled: true,
            root: Some(workspace.path().join("Vault")),
            mode: OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER.to_string(),
            subdir: "OpenPlanter".to_string(),
            generate_canvas: true,
        };

        let result = export_investigation_pack(workspace.path(), &session_dir, &state, &config)
            .expect("export should succeed");
        let home = fs::read_to_string(&result.home_path).unwrap();
        assert!(home.contains("openplanter_type: 'investigation'"));
        assert!(home.contains("[Findings](Findings.md)"));
        let findings =
            fs::read_to_string(Path::new(&result.investigation_dir).join("Findings.md")).unwrap();
        assert!(findings.contains("[ev 1](Evidence.md#ev%201)"));
        let canvas: Value = serde_json::from_str(
            &fs::read_to_string(
                Path::new(&result.investigation_dir).join("Investigation Map.canvas"),
            )
            .unwrap(),
        )
        .unwrap();
        assert!(
            canvas["nodes"]
                .as_array()
                .unwrap()
                .iter()
                .any(|node| node["type"] == "file")
        );
        assert!(Path::new(&result.manifest_path).exists());
        let manifest: Value =
            serde_json::from_str(&fs::read_to_string(&result.manifest_path).unwrap()).unwrap();
        let manifest_files = manifest["files"].as_array().unwrap();
        assert!(
            manifest_files
                .iter()
                .any(|path| path.as_str() == Some("Index.md"))
        );
        assert!(manifest_files.iter().any(|path| {
            path.as_str()
                .is_some_and(|path| path.ends_with("/Manifest.json"))
        }));
    }

    #[test]
    fn export_pack_removes_canvas_when_canvas_disabled() {
        let workspace = tempfile::tempdir().unwrap();
        let session_dir = workspace.path().join(".openplanter/sessions/session-1");
        fs::create_dir_all(&session_dir).unwrap();
        let mut state = InvestigationState::new("session-1");
        state.active_investigation_id = Some("Canvas Off".to_string());
        let mut config = ObsidianExportConfig {
            enabled: true,
            root: Some(workspace.path().join("Vault")),
            mode: OBSIDIAN_EXPORT_MODE_EXISTING_FOLDER.to_string(),
            subdir: "OpenPlanter".to_string(),
            generate_canvas: true,
        };

        let first_result =
            export_investigation_pack(workspace.path(), &session_dir, &state, &config)
                .expect("initial export should succeed");
        assert!(
            Path::new(&first_result.investigation_dir)
                .join("Investigation Map.canvas")
                .exists()
        );

        config.generate_canvas = false;
        let result = export_investigation_pack(workspace.path(), &session_dir, &state, &config)
            .expect("export should succeed");
        let home = fs::read_to_string(&result.home_path).unwrap();
        assert!(!home.contains("Investigation Map.canvas"));
        assert!(
            !Path::new(&result.investigation_dir)
                .join("Investigation Map.canvas")
                .exists()
        );
    }

    #[test]
    fn atomic_write_overwrites_existing_files() {
        let workspace = tempfile::tempdir().unwrap();
        let path = workspace.path().join("Vault").join("Index.md");

        atomic_write(&path, "first\n").unwrap();
        atomic_write(&path, "second\n").unwrap();

        assert_eq!(fs::read_to_string(path).unwrap(), "second\n");
    }
}
