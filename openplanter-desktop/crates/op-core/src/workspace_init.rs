use std::collections::{HashMap, HashSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use chrono::Utc;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio::runtime::Builder as TokioRuntimeBuilder;
use tokio_util::sync::CancellationToken;
use walkdir::WalkDir;

use crate::config::AgentConfig;
use crate::config_hydration::{apply_settings_to_config, merge_credentials_into_config};
use crate::credentials::{CredentialBundle, CredentialStore};
use crate::engine::curator::{CuratorResult, run_curator};
use crate::events::{
    InitGateState, InitStatusView, MigrationInitRequest, MigrationInitResultView,
    MigrationProgressEvent, MigrationProgressStage, MigrationSourceInspection, MigrationSourceKind,
    SessionInfo, StandardInitReportView,
};
use crate::settings::{PersistentSettings, SettingsStore};

const INIT_STATE_FILE: &str = "init-state.json";
const BASELINE_INDEX: &str = include_str!("../../../../wiki/index.md");
const BASELINE_TEMPLATE: &str = include_str!("../../../../wiki/template.md");

#[derive(Debug, Error)]
pub enum WorkspaceInitError {
    #[error("{0}")]
    InvalidRequest(String),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Serialization error: {0}")]
    Serde(#[from] serde_json::Error),
    #[error("Curator rewrite failed: {0}")]
    Curator(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct InitStateFile {
    version: u32,
    initialized_at: String,
    last_standard_init_at: Option<String>,
    onboarding_completed: bool,
    last_migration_target: Option<String>,
}

impl Default for InitStateFile {
    fn default() -> Self {
        Self {
            version: 1,
            initialized_at: now_rfc3339(),
            last_standard_init_at: None,
            onboarding_completed: false,
            last_migration_target: None,
        }
    }
}

#[derive(Debug, Clone)]
struct SourceSpec {
    original: String,
    canonical: PathBuf,
    inspection: MigrationSourceInspection,
}

pub fn run_standard_init(
    workspace: &Path,
    session_root_dir: &str,
    mark_onboarding_complete: bool,
) -> Result<StandardInitReportView, WorkspaceInitError> {
    let workspace = workspace.to_path_buf();
    let root = workspace.join(session_root_dir);
    let wiki_dir = root.join("wiki");
    let index_path = wiki_dir.join("index.md");
    let init_path = root.join(INIT_STATE_FILE);

    let root_preexisting = root.exists();
    let index_preexisting = index_path.exists();
    let mut report = StandardInitReportView {
        workspace: workspace.display().to_string(),
        ..Default::default()
    };

    ensure_dir(&workspace, &mut report.created_paths)?;
    ensure_dir(&root, &mut report.created_paths)?;
    ensure_dir(&root.join("sessions"), &mut report.created_paths)?;
    ensure_dir(&root.join("migration"), &mut report.created_paths)?;
    ensure_dir(
        &root.join("migration").join("raw"),
        &mut report.created_paths,
    )?;
    ensure_dir(&wiki_dir, &mut report.created_paths)?;

    write_text_if_missing(&root.join("settings.json"), "{}", &mut report)?;
    write_text_if_missing(&root.join("credentials.json"), "{}", &mut report)?;
    write_text_if_missing(&index_path, BASELINE_INDEX, &mut report)?;
    write_text_if_missing(
        &wiki_dir.join("template.md"),
        BASELINE_TEMPLATE,
        &mut report,
    )?;

    let mut state = read_init_state(&init_path).unwrap_or_else(|| InitStateFile {
        onboarding_completed: root_preexisting || index_preexisting,
        ..InitStateFile::default()
    });
    if mark_onboarding_complete {
        state.onboarding_completed = true;
    }
    state.last_standard_init_at = Some(now_rfc3339());
    write_init_state(&init_path, &state)?;
    report.onboarding_required = !state.onboarding_completed;

    Ok(report)
}

pub fn complete_first_run_gate(
    workspace: &Path,
    session_root_dir: &str,
) -> Result<InitStatusView, WorkspaceInitError> {
    let _ = run_standard_init(workspace, session_root_dir, true)?;
    get_init_status(workspace, session_root_dir)
}

pub fn get_init_status(
    workspace: &Path,
    session_root_dir: &str,
) -> Result<InitStatusView, WorkspaceInitError> {
    let root = workspace.join(session_root_dir);
    let wiki_dir = root.join("wiki");
    let index_path = wiki_dir.join("index.md");
    let init_path = root.join(INIT_STATE_FILE);
    let mut warnings = Vec::new();
    let init_state = match fs::read_to_string(&init_path) {
        Ok(content) => match serde_json::from_str::<InitStateFile>(&content) {
            Ok(state) => Some(state),
            Err(err) => {
                warnings.push(format!("Failed to parse init state: {err}"));
                None
            }
        },
        Err(_) => None,
    };
    let onboarding_completed = init_state
        .as_ref()
        .map(|state| state.onboarding_completed)
        .unwrap_or_else(|| root.exists() && index_path.exists());
    let gate_state =
        if root.exists() && wiki_dir.exists() && index_path.exists() && onboarding_completed {
            InitGateState::Ready
        } else {
            InitGateState::RequiresAction
        };

    Ok(InitStatusView {
        runtime_workspace: workspace.display().to_string(),
        gate_state: gate_state_name(gate_state).to_string(),
        onboarding_completed,
        has_openplanter_root: root.exists(),
        has_runtime_wiki: wiki_dir.exists(),
        has_runtime_index: index_path.exists(),
        init_state_path: init_path.display().to_string(),
        last_migration_target: init_state.and_then(|state| state.last_migration_target),
        warnings,
    })
}

pub fn inspect_migration_source(path: &Path) -> MigrationSourceInspection {
    let canonical = canonicalize_or_self(path);
    let openplanter_root = canonical.join(".openplanter");
    let runtime_wiki = openplanter_root.join("wiki");
    let baseline_wiki = canonical.join("wiki");
    let markdown_files = count_markdown_files(&canonical);
    let kind = if openplanter_root.exists() {
        MigrationSourceKind::OpenPlanterWorkspace
    } else if markdown_files > 0 {
        MigrationSourceKind::ManualResearch
    } else {
        MigrationSourceKind::Unknown
    };

    MigrationSourceInspection {
        path: canonical.display().to_string(),
        kind: source_kind_name(kind).to_string(),
        has_sessions: openplanter_root.join("sessions").exists(),
        has_settings: openplanter_root.join("settings.json").exists(),
        has_credentials: openplanter_root.join("credentials.json").exists(),
        has_runtime_wiki: runtime_wiki.exists(),
        has_baseline_wiki: baseline_wiki.exists(),
        markdown_files,
        warnings: Vec::new(),
    }
}

pub fn run_migration_init<F>(
    request: &MigrationInitRequest,
    runtime_config: &AgentConfig,
    emit_progress: F,
) -> Result<MigrationInitResultView, WorkspaceInitError>
where
    F: FnMut(MigrationProgressEvent),
{
    run_migration_init_with_runner(request, runtime_config, emit_progress, run_curator_blocking)
}

fn run_migration_init_with_runner<F, R>(
    request: &MigrationInitRequest,
    runtime_config: &AgentConfig,
    mut emit_progress: F,
    mut curator_runner: R,
) -> Result<MigrationInitResultView, WorkspaceInitError>
where
    F: FnMut(MigrationProgressEvent),
    R: FnMut(&str, &AgentConfig) -> Result<CuratorResult, WorkspaceInitError>,
{
    if request.target_workspace.trim().is_empty() {
        return Err(WorkspaceInitError::InvalidRequest(
            "Target workspace is required".to_string(),
        ));
    }
    if request.sources.is_empty() {
        return Err(WorkspaceInitError::InvalidRequest(
            "At least one migration source is required".to_string(),
        ));
    }

    let session_root_dir = runtime_config.session_root_dir.as_str();
    let target = canonicalize_target_path(&expand_home(&request.target_workspace))?;
    let total = request.sources.len() as u32;
    let mut source_specs = Vec::new();
    let mut seen_sources = HashSet::new();

    for (index, source) in request.sources.iter().enumerate() {
        let source_path = expand_home(&source.path);
        if !source_path.exists() {
            return Err(WorkspaceInitError::InvalidRequest(format!(
                "Source does not exist: {}",
                source.path
            )));
        }
        let canonical = canonicalize_or_self(&source_path);
        if canonical == target {
            return Err(WorkspaceInitError::InvalidRequest(
                "Target workspace cannot also be a source".to_string(),
            ));
        }
        if !seen_sources.insert(canonical.clone()) {
            return Err(WorkspaceInitError::InvalidRequest(format!(
                "Duplicate source: {}",
                canonical.display()
            )));
        }
        emit_progress(progress_event(
            MigrationProgressStage::Inspect,
            format!("Inspecting {}", canonical.display()),
            (index + 1) as u32,
            total,
        ));
        source_specs.push(SourceSpec {
            original: source.path.clone(),
            canonical: canonical.clone(),
            inspection: inspect_migration_source(&canonical),
        });
    }

    let _ = run_standard_init(&target, session_root_dir, false)?;
    let root = target.join(session_root_dir);
    let raw_root = root.join("migration").join("raw");
    let target_sessions_dir = root.join("sessions");
    let target_wiki_dir = root.join("wiki");
    let mut warnings = Vec::new();
    let mut raw_specs = Vec::new();

    for (index, spec) in source_specs.iter().enumerate() {
        let slug = format!(
            "{:02}-{}",
            index + 1,
            slugify_component(&display_name(&spec.canonical))
        );
        let raw_dest = raw_root.join(slug);
        emit_progress(progress_event(
            MigrationProgressStage::Copy,
            format!("Copying raw content from {}", spec.canonical.display()),
            (index + 1) as u32,
            total,
        ));
        copy_source_snapshot(&spec.canonical, &raw_dest, &spec.inspection, &mut warnings)?;
        raw_specs.push((spec.clone(), raw_dest));
    }

    emit_progress(progress_event(
        MigrationProgressStage::MergeSessions,
        "Merging sessions".to_string(),
        0,
        total,
    ));
    let mut sessions_copied = 0u64;
    let mut sessions_renamed = 0u64;
    for (_, raw_dest) in &raw_specs {
        let sessions_dir = raw_dest.join(".openplanter").join("sessions");
        if !sessions_dir.exists() {
            continue;
        }
        for entry in fs::read_dir(&sessions_dir)? {
            let entry = entry?;
            if !entry.path().is_dir() {
                continue;
            }
            let original_id = entry.file_name().to_string_lossy().to_string();
            let resolved_id = unique_session_id(&target_sessions_dir, &original_id);
            if resolved_id != original_id {
                sessions_renamed += 1;
            }
            let target_session_dir = target_sessions_dir.join(&resolved_id);
            copy_dir_all(&entry.path(), &target_session_dir)?;
            rewrite_session_metadata_id(&target_session_dir, &resolved_id)?;
            sessions_copied += 1;
        }
    }

    emit_progress(progress_event(
        MigrationProgressStage::MergeSettings,
        "Merging settings".to_string(),
        0,
        total,
    ));
    let settings_store = SettingsStore::new(&target, session_root_dir);
    let mut merged_settings = settings_store.load();
    let mut settings_fields = Vec::new();
    for (_, raw_dest) in &raw_specs {
        let settings_path = raw_dest.join(".openplanter").join("settings.json");
        if settings_path.exists() {
            let incoming = read_settings_from_path(&settings_path)?;
            merge_settings_missing(&mut merged_settings, &incoming, &mut settings_fields);
        }
    }
    settings_store.save(&merged_settings)?;
    settings_fields.sort();
    settings_fields.dedup();

    emit_progress(progress_event(
        MigrationProgressStage::MergeCredentials,
        "Merging credentials".to_string(),
        0,
        total,
    ));
    let credential_store = CredentialStore::new(&target, session_root_dir);
    let mut merged_credentials = credential_store.load();
    let mut credential_fields = Vec::new();
    for (_, raw_dest) in &raw_specs {
        let credentials_path = raw_dest.join(".openplanter").join("credentials.json");
        if credentials_path.exists() {
            let incoming = read_credentials_from_path(&credentials_path)?;
            merge_credentials_missing(&mut merged_credentials, &incoming, &mut credential_fields);
        }
    }
    credential_store.save(&merged_credentials)?;
    credential_fields.sort();
    credential_fields.dedup();

    emit_progress(progress_event(
        MigrationProgressStage::Synthesize,
        "Preparing the target wiki for a one-time curator rewrite".to_string(),
        0,
        1,
    ));
    clear_runtime_wiki_documents(&target_wiki_dir)?;
    let curator_context = build_migration_curator_context(&target, &raw_root, &raw_specs);
    let curator_config = build_target_curator_config(
        runtime_config,
        &target,
        &merged_settings,
        &merged_credentials,
    );

    emit_progress(progress_event(
        MigrationProgressStage::Rewrite,
        "Running a one-time curator rewrite over imported sources".to_string(),
        0,
        1,
    ));
    let curator_result = curator_runner(&curator_context, &curator_config)?;
    let rewrite_summary = normalize_rewrite_summary(&curator_result);
    let wiki_files_synthesized = count_runtime_wiki_pages(&target_wiki_dir);
    emit_progress(progress_event(
        MigrationProgressStage::Rewrite,
        rewrite_summary.clone(),
        1,
        1,
    ));

    let init_path = root.join(INIT_STATE_FILE);
    let mut state = read_init_state(&init_path).unwrap_or_default();
    state.onboarding_completed = true;
    state.last_migration_target = Some(target.display().to_string());
    state.last_standard_init_at = Some(now_rfc3339());
    write_init_state(&init_path, &state)?;

    let result = MigrationInitResultView {
        target_workspace: target.display().to_string(),
        sources: raw_specs
            .iter()
            .map(|(spec, _)| spec.canonical.display().to_string())
            .collect(),
        sessions_copied,
        sessions_renamed,
        settings_merged_fields: settings_fields,
        credentials_merged_fields: credential_fields,
        wiki_files_synthesized,
        raw_preservation_root: raw_root.display().to_string(),
        rewrite_summary,
        restart_required: true,
        restart_message: format!(
            "Migration completed. Restart OpenPlanter with OPENPLANTER_WORKSPACE={} to use the new Desktop workspace.",
            target.display()
        ),
        warnings,
    };

    emit_progress(progress_event(
        MigrationProgressStage::Done,
        "Migration complete".to_string(),
        total,
        total,
    ));
    Ok(result)
}

fn now_rfc3339() -> String {
    Utc::now().to_rfc3339()
}

fn gate_state_name(state: InitGateState) -> &'static str {
    match state {
        InitGateState::Ready => "ready",
        InitGateState::RequiresAction => "requires_action",
        InitGateState::Blocked => "blocked",
    }
}

fn source_kind_name(kind: MigrationSourceKind) -> &'static str {
    match kind {
        MigrationSourceKind::OpenPlanterWorkspace => "openplanter_workspace",
        MigrationSourceKind::ManualResearch => "manual_research",
        MigrationSourceKind::Unknown => "unknown",
    }
}

fn progress_stage_name(stage: MigrationProgressStage) -> &'static str {
    match stage {
        MigrationProgressStage::Inspect => "inspect",
        MigrationProgressStage::Copy => "copy",
        MigrationProgressStage::MergeSessions => "merge_sessions",
        MigrationProgressStage::MergeSettings => "merge_settings",
        MigrationProgressStage::MergeCredentials => "merge_credentials",
        MigrationProgressStage::Synthesize => "synthesize",
        MigrationProgressStage::Rewrite => "rewrite",
        MigrationProgressStage::Done => "done",
    }
}

fn progress_event(
    stage: MigrationProgressStage,
    message: String,
    current: u32,
    total: u32,
) -> MigrationProgressEvent {
    MigrationProgressEvent {
        stage: progress_stage_name(stage).to_string(),
        message,
        current,
        total,
    }
}

fn read_init_state(path: &Path) -> Option<InitStateFile> {
    let content = fs::read_to_string(path).ok()?;
    serde_json::from_str(&content).ok()
}

fn write_init_state(path: &Path, state: &InitStateFile) -> Result<(), WorkspaceInitError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, serde_json::to_string_pretty(state)?)?;
    Ok(())
}

fn ensure_dir(path: &Path, created_paths: &mut Vec<String>) -> Result<(), WorkspaceInitError> {
    if !path.exists() {
        fs::create_dir_all(path)?;
        created_paths.push(path.display().to_string());
    }
    Ok(())
}

fn write_text_if_missing(
    path: &Path,
    contents: &str,
    report: &mut StandardInitReportView,
) -> Result<(), WorkspaceInitError> {
    if path.exists() {
        report.skipped_existing += 1;
        return Ok(());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, contents)?;
    report.copied_paths.push(path.display().to_string());
    Ok(())
}

fn expand_home(raw: &str) -> PathBuf {
    if raw == "~" {
        return home_dir().unwrap_or_else(|| PathBuf::from(raw));
    }
    if let Some(rest) = raw.strip_prefix("~/") {
        if let Some(home) = home_dir() {
            return home.join(rest);
        }
    }
    PathBuf::from(raw)
}

fn home_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        env::var_os("USERPROFILE").map(PathBuf::from)
    }
    #[cfg(not(windows))]
    {
        env::var_os("HOME").map(PathBuf::from)
    }
}

fn canonicalize_or_self(path: &Path) -> PathBuf {
    path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
}

fn canonicalize_target_path(path: &Path) -> Result<PathBuf, WorkspaceInitError> {
    if path.exists() {
        return Ok(canonicalize_or_self(path));
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    Ok(path.to_path_buf())
}

fn count_markdown_files(path: &Path) -> u64 {
    WalkDir::new(path)
        .into_iter()
        .filter_entry(|entry| !should_skip_walk_entry(entry.path()))
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().is_file())
        .filter(|entry| is_markdown(entry.path()))
        .count() as u64
}

fn should_skip_walk_entry(path: &Path) -> bool {
    path.file_name()
        .and_then(|value| value.to_str())
        .map(|name| {
            matches!(
                name,
                ".git" | "node_modules" | "target" | "dist" | "__pycache__"
            )
        })
        .unwrap_or(false)
}

fn is_markdown(path: &Path) -> bool {
    matches!(
        path.extension().and_then(|value| value.to_str()),
        Some("md") | Some("markdown")
    )
}

fn display_name(path: &Path) -> String {
    path.file_name()
        .and_then(|value| value.to_str())
        .map(ToString::to_string)
        .unwrap_or_else(|| path.display().to_string())
}

fn slugify_component(text: &str) -> String {
    let slug = text
        .to_lowercase()
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { '-' })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("-");
    if slug.is_empty() {
        "workspace".to_string()
    } else {
        slug
    }
}

fn copy_source_snapshot(
    source: &Path,
    raw_dest: &Path,
    inspection: &MigrationSourceInspection,
    warnings: &mut Vec<String>,
) -> Result<(), WorkspaceInitError> {
    fs::create_dir_all(raw_dest)?;
    let openplanter_root = source.join(".openplanter");

    if inspection.has_settings {
        copy_file(
            &openplanter_root.join("settings.json"),
            &raw_dest.join(".openplanter").join("settings.json"),
        )?;
    }
    if inspection.has_credentials {
        copy_file(
            &openplanter_root.join("credentials.json"),
            &raw_dest.join(".openplanter").join("credentials.json"),
        )?;
    }
    if inspection.has_sessions {
        copy_dir_all(
            &openplanter_root.join("sessions"),
            &raw_dest.join(".openplanter").join("sessions"),
        )?;
    }
    if inspection.has_runtime_wiki {
        copy_dir_all(
            &openplanter_root.join("wiki"),
            &raw_dest.join(".openplanter").join("wiki"),
        )?;
    } else if inspection.has_baseline_wiki {
        copy_dir_all(&source.join("wiki"), &raw_dest.join("wiki"))?;
    }

    if inspection.kind == source_kind_name(MigrationSourceKind::ManualResearch) {
        let docs_root = raw_dest.join("documents");
        let mut copied_any = false;
        for entry in WalkDir::new(source)
            .into_iter()
            .filter_entry(|entry| !should_skip_walk_entry(entry.path()))
            .filter_map(Result::ok)
        {
            if !entry.file_type().is_file() || !is_markdown(entry.path()) {
                continue;
            }
            let rel = match entry.path().strip_prefix(source) {
                Ok(rel) => rel,
                Err(_) => continue,
            };
            copy_file(entry.path(), &docs_root.join(rel))?;
            copied_any = true;
        }
        if !copied_any {
            warnings.push(format!(
                "No markdown documents found in manual source {}",
                source.display()
            ));
        }
    }

    Ok(())
}

fn copy_file(src: &Path, dst: &Path) -> Result<(), WorkspaceInitError> {
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::copy(src, dst)?;
    Ok(())
}

fn copy_dir_all(src: &Path, dst: &Path) -> Result<(), WorkspaceInitError> {
    if !src.exists() {
        return Ok(());
    }
    for entry in WalkDir::new(src).into_iter().filter_map(Result::ok) {
        let rel = match entry.path().strip_prefix(src) {
            Ok(rel) => rel,
            Err(_) => continue,
        };
        let target = dst.join(rel);
        if entry.file_type().is_dir() {
            fs::create_dir_all(&target)?;
        } else if entry.file_type().is_file() {
            if let Some(parent) = target.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(entry.path(), &target)?;
        }
    }
    Ok(())
}

fn unique_session_id(target_sessions_dir: &Path, original_id: &str) -> String {
    let mut candidate = original_id.to_string();
    let mut suffix = 1u32;
    while target_sessions_dir.join(&candidate).exists() {
        suffix += 1;
        candidate = format!("{original_id}-m{suffix}");
    }
    candidate
}

fn rewrite_session_metadata_id(session_dir: &Path, new_id: &str) -> Result<(), WorkspaceInitError> {
    let metadata_path = session_dir.join("metadata.json");
    if !metadata_path.exists() {
        return Ok(());
    }
    let content = fs::read_to_string(&metadata_path)?;
    let mut info: SessionInfo = serde_json::from_str(&content)?;
    info.id = new_id.to_string();
    fs::write(&metadata_path, serde_json::to_string_pretty(&info)?)?;
    Ok(())
}

fn read_settings_from_path(path: &Path) -> Result<PersistentSettings, WorkspaceInitError> {
    let content = fs::read_to_string(path)?;
    let parsed: serde_json::Value = serde_json::from_str(&content)?;
    Ok(PersistentSettings::from_json(&parsed).unwrap_or_default())
}

fn merge_settings_missing(
    target: &mut PersistentSettings,
    incoming: &PersistentSettings,
    filled_fields: &mut Vec<String>,
) {
    macro_rules! fill {
        ($field:ident) => {
            if target.$field.is_none() && incoming.$field.is_some() {
                target.$field = incoming.$field.clone();
                filled_fields.push(stringify!($field).to_string());
            }
        };
    }
    fill!(default_model);
    fill!(default_reasoning_effort);
    fill!(default_model_openai);
    fill!(default_model_anthropic);
    fill!(default_model_openrouter);
    fill!(default_model_cerebras);
    fill!(default_model_zai);
    fill!(default_model_ollama);
    fill!(zai_plan);
    fill!(web_search_provider);
    fill!(embeddings_provider);
    fill!(mistral_document_ai_use_shared_key);
}

fn read_credentials_from_path(path: &Path) -> Result<CredentialBundle, WorkspaceInitError> {
    let content = fs::read_to_string(path)?;
    let parsed: HashMap<String, serde_json::Value> = serde_json::from_str(&content)?;
    Ok(CredentialBundle::from_json(&parsed))
}

fn merge_credentials_missing(
    target: &mut CredentialBundle,
    incoming: &CredentialBundle,
    filled_fields: &mut Vec<String>,
) {
    macro_rules! fill {
        ($field:ident) => {
            if target.$field.is_none() && incoming.$field.is_some() {
                target.$field = incoming.$field.clone();
                filled_fields.push(stringify!($field).to_string());
            }
        };
    }
    fill!(openai_api_key);
    fill!(openai_oauth_token);
    fill!(anthropic_api_key);
    fill!(openrouter_api_key);
    fill!(cerebras_api_key);
    fill!(zai_api_key);
    fill!(exa_api_key);
    fill!(firecrawl_api_key);
    fill!(brave_api_key);
    fill!(tavily_api_key);
    fill!(voyage_api_key);
    fill!(mistral_api_key);
    fill!(mistral_document_ai_api_key);
}

fn clear_runtime_wiki_documents(wiki_dir: &Path) -> Result<(), WorkspaceInitError> {
    if !wiki_dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(wiki_dir)? {
        let entry = entry?;
        let path = entry.path();
        let name = entry.file_name();
        let keep = name == "index.md" || name == "template.md";
        if keep {
            continue;
        }
        if path.is_dir() {
            fs::remove_dir_all(path)?;
        } else {
            fs::remove_file(path)?;
        }
    }
    Ok(())
}

fn build_target_curator_config(
    runtime_config: &AgentConfig,
    target: &Path,
    merged_settings: &PersistentSettings,
    merged_credentials: &CredentialBundle,
) -> AgentConfig {
    let mut config = runtime_config.clone();
    config.workspace = target.to_path_buf();
    apply_settings_to_config(&mut config, merged_settings);
    merge_credentials_into_config(
        &mut config,
        merged_credentials,
        &CredentialBundle::default(),
    );
    config
}

fn build_migration_curator_context(
    target: &Path,
    raw_root: &Path,
    raw_specs: &[(SourceSpec, PathBuf)],
) -> String {
    let raw_root_display = raw_root
        .strip_prefix(target)
        .unwrap_or(raw_root)
        .display()
        .to_string();
    let mut lines = vec![
        "You are performing a one-time workspace migration rewrite for the Desktop app."
            .to_string(),
        format!("Target workspace: {}", target.display()),
        "Rewrite the canonical Desktop wiki inside `.openplanter/wiki/`.".to_string(),
        format!(
            "Read imported raw material from `{raw_root_display}` and treat it as the source of truth."
        ),
        "Merge duplicate information across sources, keep the result factual and legible, preserve provenance, and update `.openplanter/wiki/index.md` to match the final page set.".to_string(),
        "Do not write outside `.openplanter/wiki/`, and do not modify raw snapshots under `.openplanter/migration/raw/`.".to_string(),
        String::new(),
        "Ordered import sources:".to_string(),
    ];
    for (index, (spec, raw_dest)) in raw_specs.iter().enumerate() {
        let raw_display = raw_dest
            .strip_prefix(target)
            .unwrap_or(raw_dest)
            .display()
            .to_string();
        lines.push(format!(
            "{}. kind={} | source={} | original_input={} | raw_snapshot={}",
            index + 1,
            spec.inspection.kind,
            spec.canonical.display(),
            spec.original,
            raw_display
        ));
    }
    lines.join("\n")
}

fn normalize_rewrite_summary(result: &CuratorResult) -> String {
    let summary = result.summary.trim();
    if summary.is_empty() {
        format!(
            "Curator rewrite completed with {} wiki file(s) changed.",
            result.files_changed
        )
    } else {
        summary.to_string()
    }
}

fn count_runtime_wiki_pages(wiki_dir: &Path) -> u64 {
    WalkDir::new(wiki_dir)
        .into_iter()
        .filter_entry(|entry| !should_skip_walk_entry(entry.path()))
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().is_file())
        .filter(|entry| is_markdown(entry.path()))
        .filter(|entry| {
            entry
                .path()
                .file_name()
                .and_then(|value| value.to_str())
                .map(|name| {
                    !name.eq_ignore_ascii_case("index.md")
                        && !name.eq_ignore_ascii_case("template.md")
                })
                .unwrap_or(true)
        })
        .count() as u64
}

fn run_curator_blocking(
    context: &str,
    config: &AgentConfig,
) -> Result<CuratorResult, WorkspaceInitError> {
    let runtime = TokioRuntimeBuilder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|err| WorkspaceInitError::Curator(err.to_string()))?;
    runtime
        .block_on(run_curator(context, config, CancellationToken::new()))
        .map_err(WorkspaceInitError::Curator)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::MigrationSourceInput;
    use tempfile::tempdir;

    fn runtime_config(workspace: &Path) -> AgentConfig {
        let mut cfg = AgentConfig::from_env(workspace);
        cfg.workspace = workspace.to_path_buf();
        cfg.provider = "auto".to_string();
        cfg.model = "seed-model".to_string();
        cfg.api_key = None;
        cfg.openai_api_key = None;
        cfg.openai_oauth_token = None;
        cfg
    }

    #[test]
    fn standard_init_is_idempotent() {
        let temp = tempdir().unwrap();
        let first = run_standard_init(temp.path(), ".openplanter", false).unwrap();
        assert!(
            temp.path()
                .join(".openplanter")
                .join("wiki")
                .join("index.md")
                .exists()
        );
        assert!(first.onboarding_required);

        let second = run_standard_init(temp.path(), ".openplanter", true).unwrap();
        assert!(!second.onboarding_required);

        let status = get_init_status(temp.path(), ".openplanter").unwrap();
        assert_eq!(status.gate_state, "ready");
    }

    #[test]
    fn inspect_source_detects_openplanter_workspace() {
        let temp = tempdir().unwrap();
        let root = temp.path().join(".openplanter");
        fs::create_dir_all(root.join("sessions")).unwrap();
        fs::write(root.join("settings.json"), "{}").unwrap();
        fs::write(root.join("credentials.json"), "{}").unwrap();
        fs::create_dir_all(root.join("wiki")).unwrap();
        fs::write(root.join("wiki").join("index.md"), BASELINE_INDEX).unwrap();

        let inspection = inspect_migration_source(temp.path());
        assert_eq!(inspection.kind, "openplanter_workspace");
        assert!(inspection.has_sessions);
        assert!(inspection.has_settings);
    }

    #[test]
    fn migration_preserves_sources_and_merges_sessions() {
        let temp = tempdir().unwrap();
        let source_a = temp.path().join("source-a");
        let source_b = temp.path().join("source-b");
        let target = temp.path().join("target");

        for source in [&source_a, &source_b] {
            fs::create_dir_all(source.join(".openplanter").join("sessions").join("same-id"))
                .unwrap();
            fs::create_dir_all(
                source
                    .join(".openplanter")
                    .join("wiki")
                    .join("campaign-finance"),
            )
            .unwrap();
            fs::write(
                source
                    .join(".openplanter")
                    .join("sessions")
                    .join("same-id")
                    .join("metadata.json"),
                serde_json::to_string_pretty(&SessionInfo {
                    id: "same-id".to_string(),
                    created_at: "2026-01-01T00:00:00Z".to_string(),
                    turn_count: 1,
                    last_objective: Some("Investigate".to_string()),
                    investigation_id: None,
                })
                .unwrap(),
            )
            .unwrap();
            fs::write(
                source
                    .join(".openplanter")
                    .join("wiki")
                    .join("campaign-finance")
                    .join(format!("{}.md", display_name(source))),
                format!(
                    "# {}\n\n## Summary\n\nImported from {}\n",
                    display_name(source),
                    source.display()
                ),
            )
            .unwrap();
        }

        fs::write(
            source_a.join(".openplanter").join("settings.json"),
            "{\"default_model\":\"alpha\"}",
        )
        .unwrap();
        fs::write(
            source_b.join(".openplanter").join("credentials.json"),
            "{\"openai_api_key\":\"secret\"}",
        )
        .unwrap();

        let request = MigrationInitRequest {
            target_workspace: target.display().to_string(),
            sources: vec![
                MigrationSourceInput {
                    path: source_a.display().to_string(),
                },
                MigrationSourceInput {
                    path: source_b.display().to_string(),
                },
            ],
        };

        let mut progress = Vec::new();
        let mut run_count = 0u32;
        let source_a_display = source_a.display().to_string();
        let source_b_display = source_b.display().to_string();
        let result = run_migration_init_with_runner(
            &request,
            &runtime_config(temp.path()),
            |event| progress.push(event.stage),
            |context, cfg| {
                run_count += 1;
                assert!(context.contains(".openplanter/migration/raw"));
                assert!(context.contains(&source_a_display));
                assert!(context.contains(&source_b_display));
                assert_eq!(cfg.workspace, target);
                assert_eq!(cfg.model, "alpha");
                assert_eq!(cfg.openai_api_key.as_deref(), Some("secret"));

                let wiki_dir = cfg.workspace.join(&cfg.session_root_dir).join("wiki");
                fs::create_dir_all(wiki_dir.join("campaign-finance")).unwrap();
                fs::write(
                    wiki_dir.join("campaign-finance").join("merged.md"),
                    "# Merged Source\n\n## Overview\n\nCurated output.\n",
                )
                .unwrap();
                fs::write(wiki_dir.join("index.md"), BASELINE_INDEX).unwrap();

                Ok(CuratorResult {
                    summary: "Curator rewrote 1 wiki file from imported sources.".to_string(),
                    files_changed: 1,
                })
            },
        )
        .unwrap();

        assert_eq!(result.sessions_copied, 2);
        assert_eq!(result.sessions_renamed, 1);
        assert_eq!(result.wiki_files_synthesized, 1);
        assert_eq!(
            result.rewrite_summary,
            "Curator rewrote 1 wiki file from imported sources."
        );
        assert_eq!(run_count, 1);
        assert!(
            target
                .join(".openplanter")
                .join("migration")
                .join("raw")
                .exists()
        );
        assert!(
            source_a
                .join(".openplanter")
                .join("sessions")
                .join("same-id")
                .exists()
        );
        assert!(
            target
                .join(".openplanter")
                .join("wiki")
                .join("campaign-finance")
                .exists()
                || target
                    .join(".openplanter")
                    .join("wiki")
                    .join("imported")
                    .exists()
        );
        let settings = SettingsStore::new(&target, ".openplanter").load();
        assert_eq!(settings.default_model.as_deref(), Some("alpha"));
        let creds = CredentialStore::new(&target, ".openplanter").load();
        assert_eq!(creds.openai_api_key.as_deref(), Some("secret"));
        let synth_index = progress
            .iter()
            .position(|stage| stage == "synthesize")
            .unwrap();
        let rewrite_index = progress
            .iter()
            .position(|stage| stage == "rewrite")
            .unwrap();
        assert!(synth_index < rewrite_index);
        assert_eq!(
            progress
                .iter()
                .filter(|stage| stage.as_str() == "rewrite")
                .count(),
            2
        );
        assert_eq!(progress.last().map(String::as_str), Some("done"));
    }

    #[test]
    fn migration_surfaces_curator_errors_after_preserving_raw_sources() {
        let temp = tempdir().unwrap();
        let source = temp.path().join("source-a");
        let target = temp.path().join("target");

        fs::create_dir_all(source.join(".openplanter").join("sessions").join("same-id")).unwrap();
        fs::create_dir_all(source.join(".openplanter").join("wiki")).unwrap();
        fs::write(
            source.join(".openplanter").join("wiki").join("source-a.md"),
            "# Source A\n",
        )
        .unwrap();

        let request = MigrationInitRequest {
            target_workspace: target.display().to_string(),
            sources: vec![MigrationSourceInput {
                path: source.display().to_string(),
            }],
        };

        let result = run_migration_init_with_runner(
            &request,
            &runtime_config(temp.path()),
            |_| {},
            |_context, _cfg| {
                Err(WorkspaceInitError::Curator(
                    "missing credentials".to_string(),
                ))
            },
        );

        assert!(matches!(
            result,
            Err(WorkspaceInitError::Curator(message)) if message == "missing credentials"
        ));
        assert!(
            target
                .join(".openplanter")
                .join("migration")
                .join("raw")
                .exists()
        );
        assert!(
            source
                .join(".openplanter")
                .join("wiki")
                .join("source-a.md")
                .exists()
        );
    }
}
