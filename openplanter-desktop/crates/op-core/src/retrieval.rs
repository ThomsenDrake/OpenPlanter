use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use anyhow::Context;
use async_trait::async_trait;
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use tokio::time::sleep;
use tokio_util::sync::CancellationToken;
use walkdir::WalkDir;

use crate::config::{AgentConfig, normalize_embeddings_provider};

pub const VOYAGE_EMBEDDING_MODEL: &str = "voyage-4";
pub const MISTRAL_EMBEDDING_MODEL: &str = "mistral-embed";
pub const RETRIEVAL_PACKET_VERSION: &str = "retrieval-v3";
pub const RETRIEVAL_MODE: &str = "documents+ontology";

const INDEX_VERSION: &str = "embeddings-v3";
const CHUNK_TARGET_CHARS: usize = 1200;
const CHUNK_OVERLAP_CHARS: usize = 200;
const STRUCTURED_RECORD_MAX_CHARS: usize = CHUNK_TARGET_CHARS + CHUNK_OVERLAP_CHARS;
const MAX_EXCERPT_CHARS: usize = 280;
const WORKSPACE_TOP_K: usize = 4;
const SESSION_TOP_K: usize = 4;
const FUSED_DOCUMENT_TOP_K: usize = WORKSPACE_TOP_K + SESSION_TOP_K;
const ONTOLOGY_TOP_K: usize = 6;
const MAX_HITS_PER_SOURCE: usize = 2;
const MAX_HITS_PER_OBJECT: usize = 2;
const MAX_GRAPH_RELATED_IDS: usize = 8;
const BATCH_SIZE: usize = 32;
const RETRIEVAL_MAX_TRANSIENT_RETRIES: usize = 4;
const RETRIEVAL_STARTUP_RETRY_DELAY_CAP_SEC: f64 = 10.0;

const TEXT_EXTENSIONS: &[&str] = &["md", "txt", "json", "csv", "tsv", "yaml", "yml", "patch"];
const EXCLUDED_DIR_NAMES: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
];
const IGNORED_FILE_NAMES: &[&str] = &[".DS_Store", "Thumbs.db"];
const IGNORED_FILE_PREFIXES: &[&str] = &["._"];

#[derive(Debug, Clone, Copy)]
struct EmbeddingsProviderLimits {
    batch_size: usize,
    input_char_limit: usize,
    emergency_input_char_limit: usize,
}

#[derive(Debug, Clone, Copy)]
struct EmbeddingsRetryPolicy {
    max_retries: usize,
    backoff_base_sec: f64,
    backoff_max_sec: f64,
    retry_after_cap_sec: f64,
}

impl EmbeddingsRetryPolicy {
    fn from_config(config: &AgentConfig) -> Self {
        Self {
            max_retries: (config.rate_limit_max_retries.max(0) as usize)
                .min(RETRIEVAL_MAX_TRANSIENT_RETRIES),
            backoff_base_sec: config.rate_limit_backoff_base_sec.max(0.0),
            backoff_max_sec: config.rate_limit_backoff_max_sec.max(0.0),
            retry_after_cap_sec: config.rate_limit_retry_after_cap_sec.max(0.0),
        }
    }

    fn compute_delay_sec(&self, retry_count: usize, retry_after_sec: Option<f64>) -> f64 {
        let delay = retry_after_sec
            .map(|value| value.max(0.0).min(self.retry_after_cap_sec))
            .unwrap_or_else(|| {
                self.backoff_base_sec * 2_f64.powi((retry_count.saturating_sub(1)) as i32)
            });
        delay
            .min(self.backoff_max_sec)
            .min(RETRIEVAL_STARTUP_RETRY_DELAY_CAP_SEC)
    }
}

#[derive(Debug, Clone, thiserror::Error)]
enum EmbeddingsRequestError {
    #[error("{detail}")]
    Oversize { input_id: usize, detail: String },
    #[error("{detail}")]
    RetryableTransient {
        status_code: Option<u16>,
        provider_code: Option<String>,
        retry_after_sec: Option<f64>,
        detail: String,
    },
    #[error("{detail}")]
    Fatal {
        status_code: Option<u16>,
        detail: String,
    },
}

impl EmbeddingsRequestError {
    fn detail(&self) -> &str {
        match self {
            Self::Oversize { detail, .. }
            | Self::RetryableTransient { detail, .. }
            | Self::Fatal { detail, .. } => detail,
        }
    }

    fn provider_code(&self) -> Option<&str> {
        match self {
            Self::RetryableTransient { provider_code, .. } => provider_code.as_deref(),
            _ => None,
        }
    }

    fn retry_after_sec(&self) -> Option<f64> {
        match self {
            Self::RetryableTransient {
                retry_after_sec, ..
            } => *retry_after_sec,
            _ => None,
        }
    }

    fn status_code(&self) -> Option<u16> {
        match self {
            Self::RetryableTransient { status_code, .. } | Self::Fatal { status_code, .. } => {
                *status_code
            }
            Self::Oversize { .. } => Some(400),
        }
    }
}

#[derive(Debug, Clone)]
enum RefreshIndexOutcome {
    Complete {
        chunks: Vec<ChunkRecord>,
    },
    PartialCached {
        documents_done: usize,
        documents_total: usize,
        chunks_done: usize,
        chunks_total: usize,
        failure_detail: String,
        cached_chunks: Vec<ChunkRecord>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetrievalStatus {
    pub provider: String,
    pub model: String,
    pub status: String,
    pub detail: String,
}

#[derive(Debug, Clone)]
pub struct RetrievalBuildResult {
    pub packet: Option<Value>,
    pub status: RetrievalStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetrievalProgress {
    pub corpus: String,
    pub phase: String,
    pub documents_done: usize,
    pub documents_total: usize,
    pub chunks_done: usize,
    pub chunks_total: usize,
    pub reused_documents: usize,
    pub message: String,
}

impl RetrievalProgress {
    pub fn percent(&self) -> u32 {
        if self.documents_total == 0 {
            return 0;
        }
        (((self.documents_done as f64 / self.documents_total as f64) * 100.0).round() as i64)
            .clamp(0, 100) as u32
    }

    pub fn to_trace_message(&self) -> String {
        format!(
            "[retrieval:progress] {}",
            json!({
                "corpus": self.corpus,
                "phase": self.phase,
                "documents_done": self.documents_done,
                "documents_total": self.documents_total,
                "chunks_done": self.chunks_done,
                "chunks_total": self.chunks_total,
                "reused_documents": self.reused_documents,
                "percent": self.percent(),
                "message": self.message,
            })
        )
    }
}

#[derive(Debug, Clone, Default)]
struct RetrievalQuery {
    text: String,
    focus_question_ids: Vec<String>,
    focus_claim_ids: Vec<String>,
    focus_entity_ids: Vec<String>,
    boost_object_ids: Vec<String>,
}

#[derive(Debug, Clone)]
struct SourceDocument {
    source_id: String,
    path: String,
    title: String,
    text: String,
    fingerprint: String,
    kind: String,
    metadata: Map<String, Value>,
}

#[derive(Debug, Clone)]
struct SemanticRecord {
    record_path: String,
    content_role: String,
    text: String,
    metadata: Map<String, Value>,
}

#[derive(Debug, Clone)]
struct PendingChunk {
    source_id: String,
    path: String,
    title: String,
    text: String,
    fingerprint: String,
    kind: String,
    metadata: Map<String, Value>,
    record_path: String,
    content_role: String,
    vector: Vec<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChunkRecord {
    chunk_id: String,
    source_id: String,
    path: String,
    title: String,
    text: String,
    excerpt: String,
    fingerprint: String,
    kind: String,
    metadata: Map<String, Value>,
    #[serde(default)]
    record_path: String,
    #[serde(default)]
    content_role: String,
    #[serde(default)]
    subchunk_index: usize,
    vector: Vec<f64>,
}

impl ChunkRecord {
    fn hit_payload(&self, score: f64) -> Value {
        json!({
            "path": self.path,
            "title": self.title,
            "score": ((score * 10_000.0).round()) / 10_000.0,
            "excerpt": self.excerpt,
            "source_id": self.source_id,
            "kind": self.kind,
            "record_path": self.record_path,
            "content_role": self.content_role,
            "subchunk_index": self.subchunk_index,
            "metadata": self.metadata,
        })
    }
}

struct EmbeddingsClient {
    provider: String,
    model: String,
    api_key: String,
    limits: EmbeddingsProviderLimits,
    http: Client,
}

impl EmbeddingsClient {
    fn new(provider: &str, api_key: &str) -> Self {
        let normalized = normalize_embeddings_provider(Some(provider));
        let model = embedding_model_for_provider(&normalized).to_string();
        Self {
            provider: normalized,
            model,
            api_key: api_key.trim().to_string(),
            limits: provider_limits(provider),
            http: Client::new(),
        }
    }

    async fn embed(
        &self,
        texts: &[String],
        input_type: &str,
    ) -> Result<Vec<Vec<f64>>, EmbeddingsRequestError> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }
        let mut all = Vec::new();
        for batch in texts.chunks(self.limits.batch_size) {
            let mut payload = json!({
                "model": self.model,
                "input": batch,
            });
            if self.provider == "voyage" {
                payload["input_type"] = Value::String(input_type.to_string());
            }

            let response = self
                .http
                .post(self.endpoint())
                .bearer_auth(&self.api_key)
                .json(&payload)
                .send()
                .await
                .map_err(|err| classify_embeddings_transport_error(&self.provider, err))?;
            let status = response.status();
            let headers = response.headers().clone();
            let text = response
                .text()
                .await
                .map_err(|err| classify_embeddings_transport_error(&self.provider, err))?;
            if !status.is_success() {
                return Err(classify_embeddings_http_error(
                    &self.provider,
                    status,
                    &headers,
                    &text,
                ));
            }
            let parsed: Value =
                serde_json::from_str(&text).map_err(|_| EmbeddingsRequestError::Fatal {
                    status_code: Some(status.as_u16()),
                    detail: format!(
                        "{} embeddings returned non-JSON payload: {}",
                        self.provider,
                        truncate(&text, 500)
                    ),
                })?;
            let Some(data) = parsed.get("data").and_then(Value::as_array) else {
                return Err(EmbeddingsRequestError::Fatal {
                    status_code: Some(status.as_u16()),
                    detail: format!(
                        "{} embeddings returned unexpected payload shape",
                        self.provider
                    ),
                });
            };
            let mut ordered: Vec<(usize, Vec<f64>)> = Vec::new();
            for (idx, item) in data.iter().enumerate() {
                let Some(embedding) = item.get("embedding").and_then(Value::as_array) else {
                    continue;
                };
                let vector = normalize_vector(
                    embedding
                        .iter()
                        .filter_map(Value::as_f64)
                        .collect::<Vec<_>>(),
                );
                if vector.is_empty() {
                    continue;
                }
                let order = item
                    .get("index")
                    .and_then(Value::as_u64)
                    .map(|value| value as usize)
                    .unwrap_or(idx);
                ordered.push((order, vector));
            }
            ordered.sort_by_key(|item| item.0);
            if ordered.len() != batch.len() {
                return Err(EmbeddingsRequestError::Fatal {
                    status_code: Some(status.as_u16()),
                    detail: format!(
                        "{} embeddings returned {} vectors for {} inputs",
                        self.provider,
                        ordered.len(),
                        batch.len()
                    ),
                });
            }
            all.extend(ordered.into_iter().map(|(_, vector)| vector));
        }
        Ok(all)
    }

    fn endpoint(&self) -> &'static str {
        if self.provider == "voyage" {
            "https://api.voyageai.com/v1/embeddings"
        } else {
            "https://api.mistral.ai/v1/embeddings"
        }
    }
}

fn provider_limits(provider: &str) -> EmbeddingsProviderLimits {
    if normalize_embeddings_provider(Some(provider)) == "voyage" {
        EmbeddingsProviderLimits {
            batch_size: BATCH_SIZE,
            input_char_limit: 24_000,
            emergency_input_char_limit: 6_000,
        }
    } else {
        EmbeddingsProviderLimits {
            batch_size: BATCH_SIZE,
            input_char_limit: 12_000,
            emergency_input_char_limit: 4_000,
        }
    }
}

#[async_trait]
trait DocumentEmbeddingsBackend: Sync {
    fn provider(&self) -> &str;
    fn model(&self) -> &str;
    fn limits(&self) -> EmbeddingsProviderLimits;
    async fn embed(
        &self,
        texts: &[String],
        input_type: &str,
    ) -> Result<Vec<Vec<f64>>, EmbeddingsRequestError>;
}

#[async_trait]
impl DocumentEmbeddingsBackend for EmbeddingsClient {
    fn provider(&self) -> &str {
        &self.provider
    }

    fn model(&self) -> &str {
        &self.model
    }

    fn limits(&self) -> EmbeddingsProviderLimits {
        self.limits
    }

    async fn embed(
        &self,
        texts: &[String],
        input_type: &str,
    ) -> Result<Vec<Vec<f64>>, EmbeddingsRequestError> {
        self.embed(texts, input_type).await
    }
}

pub fn embedding_model_for_provider(provider: &str) -> &'static str {
    if normalize_embeddings_provider(Some(provider)) == "voyage" {
        VOYAGE_EMBEDDING_MODEL
    } else {
        MISTRAL_EMBEDDING_MODEL
    }
}

pub fn build_embeddings_status(
    provider: &str,
    voyage_api_key: Option<&str>,
    mistral_api_key: Option<&str>,
) -> RetrievalStatus {
    let normalized = normalize_embeddings_provider(Some(provider));
    let model = embedding_model_for_provider(&normalized).to_string();
    let has_key = if normalized == "voyage" {
        has_text(voyage_api_key)
    } else {
        has_text(mistral_api_key)
    };
    if has_key {
        RetrievalStatus {
            provider: normalized.clone(),
            model: model.clone(),
            status: "enabled".to_string(),
            detail: format!(
                "Retrieval enabled via {normalized} ({model}). Hybrid mode: {RETRIEVAL_MODE} ({RETRIEVAL_PACKET_VERSION})."
            ),
        }
    } else {
        let missing = if normalized == "voyage" {
            "VOYAGE_API_KEY"
        } else {
            "MISTRAL_API_KEY"
        };
        RetrievalStatus {
            provider: normalized.clone(),
            model: model.clone(),
            status: "disabled".to_string(),
            detail: format!(
                "Retrieval disabled: {missing} is not configured for {normalized}. Hybrid mode: {RETRIEVAL_MODE} ({RETRIEVAL_PACKET_VERSION})."
            ),
        }
    }
}

pub async fn build_retrieval_packet<F>(
    config: &AgentConfig,
    session_dir: Option<&Path>,
    objective: &str,
    question_reasoning_packet: Option<&Value>,
    cancel: Option<&CancellationToken>,
    mut emit_trace: F,
) -> anyhow::Result<RetrievalBuildResult>
where
    F: FnMut(String),
{
    let status = build_embeddings_status(
        &config.embeddings_provider,
        config.voyage_api_key.as_deref(),
        config.mistral_api_key.as_deref(),
    );
    if status.status != "enabled" {
        return Ok(RetrievalBuildResult {
            packet: None,
            status,
        });
    }

    let api_key = if status.provider == "voyage" {
        config.voyage_api_key.as_deref().unwrap_or_default()
    } else {
        config.mistral_api_key.as_deref().unwrap_or_default()
    };
    let client = EmbeddingsClient::new(&status.provider, api_key);
    let retry_policy = EmbeddingsRetryPolicy::from_config(config);
    build_retrieval_packet_with_backend(
        &config.workspace,
        session_dir,
        &config.session_root_dir,
        objective,
        question_reasoning_packet,
        &client,
        &status,
        retry_policy,
        cancel,
        &mut emit_trace,
    )
    .await
}

async fn build_retrieval_packet_with_backend<B, F>(
    workspace: &Path,
    session_dir: Option<&Path>,
    session_root_dir: &str,
    objective: &str,
    question_reasoning_packet: Option<&Value>,
    client: &B,
    status: &RetrievalStatus,
    retry_policy: EmbeddingsRetryPolicy,
    cancel: Option<&CancellationToken>,
    emit_trace: &mut F,
) -> anyhow::Result<RetrievalBuildResult>
where
    B: DocumentEmbeddingsBackend,
    F: FnMut(String),
{
    emit_retrieval_progress(
        emit_trace,
        RetrievalProgress {
            corpus: "all".to_string(),
            phase: "scan".to_string(),
            documents_done: 0,
            documents_total: 0,
            chunks_done: 0,
            chunks_total: 0,
            reused_documents: 0,
            message: "Scanning workspace and session documents for retrieval.".to_string(),
        },
    );
    let workspace_docs = collect_workspace_documents(workspace, session_root_dir);
    let session_docs = collect_session_documents(workspace, session_dir);
    let ontology_docs = collect_ontology_documents(workspace, session_dir);
    let total_docs = workspace_docs.len() + session_docs.len();
    let total_ontology_objects = ontology_docs.len();
    if total_docs == 0 && total_ontology_objects == 0 {
        return Ok(RetrievalBuildResult {
            packet: None,
            status: RetrievalStatus {
                detail: format!(
                    "Retrieval enabled via {} ({}), but no indexable documents or ontology objects were found.",
                    status.provider, status.model
                ),
                ..status.clone()
            },
        });
    }

    let workspace_index_dir = workspace
        .join(session_root_dir)
        .join("embeddings")
        .join("workspace");
    let (workspace_chunks, workspace_degradation) = resolve_refresh_index_outcome(
        refresh_index(
            Some(&workspace_index_dir),
            &workspace_docs,
            client,
            "workspace",
            retry_policy,
            cancel,
            emit_trace,
        )
        .await?,
        "workspace",
    );

    let (session_chunks, session_degradation) = if let Some(session_dir) = session_dir {
        resolve_refresh_index_outcome(
            refresh_index(
                Some(&session_dir.join("embeddings")),
                &session_docs,
                client,
                "session",
                retry_policy,
                cancel,
                emit_trace,
            )
            .await?,
            "session",
        )
    } else {
        (Vec::new(), None)
    };

    let (ontology_chunks, ontology_degradation) = if let Some(session_dir) = session_dir {
        resolve_refresh_index_outcome(
            refresh_index(
                Some(&session_dir.join("embeddings").join("ontology")),
                &ontology_docs,
                client,
                "ontology",
                retry_policy,
                cancel,
                emit_trace,
            )
            .await?,
            "ontology",
        )
    } else {
        (Vec::new(), None)
    };

    let mut degradation_notes = Vec::new();
    for note in [
        workspace_degradation,
        session_degradation,
        ontology_degradation,
    ]
    .into_iter()
    .flatten()
    {
        degradation_notes.push(note);
    }

    let query = build_query(objective, question_reasoning_packet);
    if query.text.trim().is_empty() {
        return Ok(RetrievalBuildResult {
            packet: None,
            status: RetrievalStatus {
                detail: format!(
                    "Retrieval enabled via {} ({}), but no query text was available.",
                    status.provider, status.model
                ),
                ..status.clone()
            },
        });
    }

    let query_vector = match embed_query_with_retry(
        client,
        &query.text,
        retry_policy,
        cancel,
        emit_trace,
    )
    .await
    {
        Ok(vector) => vector,
        Err(err) => {
            return Ok(RetrievalBuildResult {
                packet: None,
                status: degraded_retrieval_status(
                    status,
                    format!(
                        "Retrieval degraded via {} ({}); indexed {} document(s) and {} ontology object(s), but query embedding failed after retries. Semantic context was skipped for this solve. Last error: {}",
                        status.provider,
                        status.model,
                        total_docs,
                        total_ontology_objects,
                        err.detail()
                    ),
                ),
            });
        }
    };

    let ontology_hits = search_ontology_objects(
        &ontology_chunks,
        &query_vector,
        ONTOLOGY_TOP_K,
        MAX_HITS_PER_OBJECT,
        &query.boost_object_ids,
    );
    let top_ontology_ids = ontology_hits
        .iter()
        .filter_map(|hit| hit.get("object_id").and_then(Value::as_str))
        .map(ToString::to_string)
        .collect::<Vec<_>>();
    let workspace_hits = search_chunks(
        &workspace_chunks,
        &query_vector,
        WORKSPACE_TOP_K,
        MAX_HITS_PER_SOURCE,
    );
    let session_hits = search_chunks(
        &session_chunks,
        &query_vector,
        SESSION_TOP_K,
        MAX_HITS_PER_SOURCE,
    );
    let document_hits = fuse_document_hits(
        &workspace_chunks,
        &session_chunks,
        &query_vector,
        &top_ontology_ids,
        &query.boost_object_ids,
        FUSED_DOCUMENT_TOP_K,
        MAX_HITS_PER_SOURCE,
    );
    let graph_expansions = build_graph_expansions(&ontology_hits);
    let hit_count = ontology_hits.len() + document_hits.len();
    let packet_status = if degradation_notes.is_empty() {
        "ready"
    } else {
        "degraded"
    };
    let packet = json!({
        "version": RETRIEVAL_PACKET_VERSION,
        "mode": RETRIEVAL_MODE,
        "status": packet_status,
        "provider": status.provider,
        "model": status.model,
        "query": {
            "text": query.text,
            "focus_question_ids": query.focus_question_ids,
            "focus_claim_ids": query.focus_claim_ids,
            "focus_entity_ids": query.focus_entity_ids,
        },
        "query_text": query.text,
        "hits": {
            "documents": document_hits,
            "ontology_objects": ontology_hits,
            "graph_expansions": graph_expansions,
        },
        "coverage": {
            "documents_indexed": total_docs,
            "ontology_objects_indexed": total_ontology_objects,
        },
        "workspace_hits": workspace_hits,
        "session_hits": session_hits,
    });

    let detail = if !degradation_notes.is_empty() {
        format!(
            "Retrieval degraded via {} ({}); {} Selected {} hybrid semantic match(es).",
            status.provider,
            status.model,
            degradation_notes.join(" "),
            hit_count
        )
    } else if hit_count == 0 {
        format!(
            "Retrieval enabled via {} ({}); indexed {} document(s) and {} ontology object(s), but found no strong semantic matches.",
            status.provider, status.model, total_docs, total_ontology_objects
        )
    } else {
        format!(
            "Retrieval enabled via {} ({}); indexed {} document(s) and {} ontology object(s) and selected {} hybrid semantic match(es).",
            status.provider, status.model, total_docs, total_ontology_objects, hit_count
        )
    };

    Ok(RetrievalBuildResult {
        packet: Some(packet),
        status: RetrievalStatus {
            detail,
            status: packet_status.to_string(),
            ..status.clone()
        },
    })
}

fn resolve_refresh_index_outcome(
    outcome: RefreshIndexOutcome,
    corpus: &str,
) -> (Vec<ChunkRecord>, Option<String>) {
    match outcome {
        RefreshIndexOutcome::Complete { chunks } => (chunks, None),
        RefreshIndexOutcome::PartialCached {
            documents_done,
            documents_total,
            chunks_done,
            chunks_total,
            failure_detail,
            cached_chunks,
        } => (
            cached_chunks,
            Some(format!(
                "{corpus} indexing failed after retries and cached {documents_done}/{documents_total} record(s) ({chunks_done}/{chunks_total} chunks) for a future run. Last error: {failure_detail}"
            )),
        ),
    }
}

fn degraded_retrieval_status(status: &RetrievalStatus, detail: String) -> RetrievalStatus {
    RetrievalStatus {
        provider: status.provider.clone(),
        model: status.model.clone(),
        status: "degraded".to_string(),
        detail,
    }
}

async fn embed_query_with_retry<B>(
    client: &B,
    text: &str,
    retry_policy: EmbeddingsRetryPolicy,
    cancel: Option<&CancellationToken>,
    emit_trace: &mut impl FnMut(String),
) -> Result<Vec<f64>, EmbeddingsRequestError>
where
    B: DocumentEmbeddingsBackend,
{
    let mut windows = split_query_windows(text, client.limits().input_char_limit);
    loop {
        let vectors = match embed_texts_with_retry(
            client,
            &windows,
            "query",
            "query",
            retry_policy,
            cancel,
            emit_trace,
        )
        .await
        {
            Ok(vectors) => vectors,
            Err(err) => {
                if retry_oversized_query_windows(&mut windows, &err, client.limits(), emit_trace) {
                    continue;
                }
                return Err(err);
            }
        };
        if vectors.is_empty() {
            return Err(EmbeddingsRequestError::Fatal {
                status_code: None,
                detail: "embeddings provider returned no query vector".to_string(),
            });
        }
        if vectors.len() == 1 {
            return Ok(vectors.into_iter().next().unwrap_or_default());
        }
        return Ok(mean_pool_vectors(&vectors));
    }
}

async fn embed_texts_with_retry<B>(
    client: &B,
    texts: &[String],
    input_type: &str,
    scope: &str,
    retry_policy: EmbeddingsRetryPolicy,
    cancel: Option<&CancellationToken>,
    emit_trace: &mut impl FnMut(String),
) -> Result<Vec<Vec<f64>>, EmbeddingsRequestError>
where
    B: DocumentEmbeddingsBackend,
{
    let mut retries = 0usize;
    loop {
        match client.embed(texts, input_type).await {
            Ok(vectors) => return Ok(vectors),
            Err(err @ EmbeddingsRequestError::RetryableTransient { .. }) => {
                if retries >= retry_policy.max_retries {
                    emit_retrieval_trace(
                        emit_trace,
                        format!(
                            "[retrieval] degraded provider={} scope={} attempts={} status={} detail={}",
                            client.provider(),
                            scope,
                            retries + 1,
                            err.status_code()
                                .map(|code| code.to_string())
                                .unwrap_or_else(|| "n/a".to_string()),
                            truncate(err.detail(), 240)
                        ),
                    );
                    return Err(err);
                }
                retries += 1;
                let delay_sec = retry_policy.compute_delay_sec(retries, err.retry_after_sec());
                let provider_code = err
                    .provider_code()
                    .map(|code| format!(" ({code})"))
                    .unwrap_or_default();
                emit_retrieval_trace(
                    emit_trace,
                    format!(
                        "[retrieval] transient embeddings failure provider={}{} scope={} status={} detail={} retry {}/{} in {:.1}s",
                        client.provider(),
                        provider_code,
                        scope,
                        err.status_code()
                            .map(|code| code.to_string())
                            .unwrap_or_else(|| "n/a".to_string()),
                        truncate(err.detail(), 240),
                        retries,
                        retry_policy.max_retries,
                        delay_sec
                    ),
                );
                if delay_sec > 0.0 {
                    if let Some(cancel) = cancel {
                        tokio::select! {
                            _ = cancel.cancelled() => {
                                emit_retrieval_trace(
                                    emit_trace,
                                    format!(
                                        "[retrieval] retry wait cancelled provider={} scope={}",
                                        client.provider(),
                                        scope
                                    ),
                                );
                                return Err(EmbeddingsRequestError::Fatal {
                                    status_code: None,
                                    detail: "Cancelled".to_string(),
                                });
                            }
                            _ = sleep(Duration::from_secs_f64(delay_sec)) => {}
                        }
                    } else {
                        sleep(Duration::from_secs_f64(delay_sec)).await;
                    }
                }
            }
            Err(err) => return Err(err),
        }
    }
}

fn collect_workspace_documents(workspace: &Path, session_root_dir: &str) -> Vec<SourceDocument> {
    let mut docs = Vec::new();
    let runtime_wiki = workspace.join(session_root_dir).join("wiki");
    if runtime_wiki.exists() {
        docs.extend(documents_from_walk(&runtime_wiki, workspace, "wiki"));
    }
    for entry in WalkDir::new(workspace)
        .into_iter()
        .filter_entry(|entry| !should_skip_walk_entry(entry.path(), workspace, session_root_dir))
        .filter_map(Result::ok)
    {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        if runtime_wiki.exists() && path.starts_with(&runtime_wiki) {
            continue;
        }
        docs.extend(documents_from_file(path, workspace, "workspace"));
    }
    docs
}

fn collect_session_documents(workspace: &Path, session_dir: Option<&Path>) -> Vec<SourceDocument> {
    let Some(session_dir) = session_dir else {
        return Vec::new();
    };
    let mut docs = Vec::new();
    let state_path = session_dir.join("investigation_state.json");
    if state_path.exists() {
        docs.extend(documents_from_investigation_state(&state_path, workspace));
    }
    let artifacts_dir = session_dir.join("artifacts");
    if artifacts_dir.exists() {
        docs.extend(documents_from_walk(&artifacts_dir, workspace, "artifact"));
    }
    docs
}

fn documents_from_walk(root: &Path, workspace: &Path, kind: &str) -> Vec<SourceDocument> {
    WalkDir::new(root)
        .into_iter()
        .filter_map(Result::ok)
        .filter(|entry| entry.path().is_file())
        .flat_map(|entry| documents_from_file(entry.path(), workspace, kind))
        .collect()
}

fn documents_from_file(path: &Path, workspace: &Path, kind: &str) -> Vec<SourceDocument> {
    if is_junk_path(path) {
        return Vec::new();
    }
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !TEXT_EXTENSIONS.iter().any(|value| *value == extension) {
        return Vec::new();
    }
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    if text.trim().is_empty() {
        return Vec::new();
    }
    let rel_path = relative_path(path, workspace);
    let mut metadata = Map::new();
    metadata.insert(
        "extension".to_string(),
        Value::String(format!(".{extension}")),
    );
    vec![SourceDocument {
        source_id: rel_path.clone(),
        path: rel_path,
        title: path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("document")
            .to_string(),
        text: text.clone(),
        fingerprint: fingerprint_text(&text),
        kind: kind.to_string(),
        metadata,
    }]
}

fn documents_from_investigation_state(path: &Path, workspace: &Path) -> Vec<SourceDocument> {
    let Ok(raw) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(parsed) = serde_json::from_str::<Value>(&raw) else {
        return Vec::new();
    };
    let Some(obj) = parsed.as_object() else {
        return Vec::new();
    };

    let mut docs = Vec::new();
    let rel_path = relative_path(path, workspace);
    if let Some(observations) = obj
        .get("legacy")
        .and_then(Value::as_object)
        .and_then(|legacy| legacy.get("external_observations"))
        .and_then(Value::as_array)
    {
        for (index, item) in observations.iter().enumerate() {
            let text = item.as_str().unwrap_or_default().trim();
            if text.is_empty() {
                continue;
            }
            let mut metadata = Map::new();
            metadata.insert(
                "record_type".to_string(),
                Value::String("legacy_observation".to_string()),
            );
            docs.push(SourceDocument {
                source_id: format!("{rel_path}#legacy:{index}"),
                path: format!("{rel_path}#legacy:{index}"),
                title: format!("legacy observation {}", index + 1),
                text: text.to_string(),
                fingerprint: fingerprint_text(text),
                kind: "session_memory".to_string(),
                metadata,
            });
        }
    }
    if let Some(evidence) = obj.get("evidence").and_then(Value::as_object) {
        for (evidence_id, record) in evidence {
            let Some(record_obj) = record.as_object() else {
                continue;
            };
            let body = join_nonempty(&[
                string_field(record_obj, "title"),
                string_field(record_obj, "summary"),
                string_field(record_obj, "content"),
                string_field(record_obj, "source_uri"),
            ]);
            if body.trim().is_empty() {
                continue;
            }
            let mut metadata = Map::new();
            metadata.insert(
                "record_type".to_string(),
                Value::String("evidence".to_string()),
            );
            metadata.insert(
                "evidence_id".to_string(),
                Value::String(evidence_id.to_string()),
            );
            metadata.insert(
                "evidence_type".to_string(),
                Value::String(string_field(record_obj, "evidence_type")),
            );
            metadata.insert(
                "linked_object_ids".to_string(),
                Value::Array(
                    record_related_object_ids("evidence", record_obj, &BTreeSet::new())
                        .into_iter()
                        .map(Value::String)
                        .collect(),
                ),
            );
            docs.push(SourceDocument {
                source_id: format!("{rel_path}#evidence:{evidence_id}"),
                path: format!("{rel_path}#evidence:{evidence_id}"),
                title: nonempty_or(record_obj.get("title").and_then(Value::as_str), evidence_id),
                text: body.clone(),
                fingerprint: fingerprint_text(&body),
                kind: "evidence".to_string(),
                metadata,
            });
        }
    }
    docs
}

fn collect_ontology_documents(workspace: &Path, session_dir: Option<&Path>) -> Vec<SourceDocument> {
    let mut docs = Vec::new();
    let mut seen_object_ids = BTreeSet::new();

    if let Some(session_dir) = session_dir {
        let investigation_path = session_dir.join("investigation_state.json");
        for doc in ontology_documents_from_investigation_state(&investigation_path, workspace) {
            if let Some(object_id) = ontology_object_id(&doc) {
                seen_object_ids.insert(object_id.to_string());
            }
            docs.push(doc);
        }
    }

    let workspace_ontology_path = workspace.join(".openplanter").join("ontology.json");
    for doc in ontology_documents_from_workspace_ontology(&workspace_ontology_path, workspace) {
        let Some(object_id) = ontology_object_id(&doc) else {
            docs.push(doc);
            continue;
        };
        if seen_object_ids.insert(object_id.to_string()) {
            docs.push(doc);
        }
    }

    docs
}

fn ontology_documents_from_investigation_state(
    path: &Path,
    workspace: &Path,
) -> Vec<SourceDocument> {
    ontology_documents_from_state_like(
        path,
        workspace,
        "session",
        &[
            ("question", "questions"),
            ("claim", "claims"),
            ("evidence", "evidence"),
            ("entity", "entities"),
            ("link", "links"),
        ],
        None,
    )
}

fn ontology_documents_from_workspace_ontology(
    path: &Path,
    workspace: &Path,
) -> Vec<SourceDocument> {
    let Ok(raw) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(parsed) = serde_json::from_str::<Value>(&raw) else {
        return Vec::new();
    };
    if !parsed.is_object() {
        return Vec::new();
    }

    let top_level_source_sessions = value_string_list(parsed.get("source_sessions"));
    ontology_documents_from_state_like(
        path,
        workspace,
        "workspace",
        &[
            ("question", "questions"),
            ("claim", "claims"),
            ("evidence", "evidence"),
            ("entity", "entities"),
            ("link", "links"),
            ("hypothesis", "hypotheses"),
            ("provenance", "provenance_nodes"),
        ],
        Some(&top_level_source_sessions),
    )
}

fn ontology_documents_from_state_like(
    path: &Path,
    workspace: &Path,
    scope: &str,
    collections: &[(&str, &str)],
    top_level_source_sessions: Option<&[String]>,
) -> Vec<SourceDocument> {
    let Ok(raw) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(parsed) = serde_json::from_str::<Value>(&raw) else {
        return Vec::new();
    };
    let Some(state) = parsed.as_object() else {
        return Vec::new();
    };

    let rel_path = relative_path(path, workspace);
    let existing_ids = collect_existing_state_ids(state);
    let label_index = build_state_label_index(state);
    let mut docs = Vec::new();

    for (object_type, key) in collections {
        let Some(records) = state.get(*key).and_then(Value::as_object) else {
            continue;
        };
        for (object_id, raw_record) in records {
            let Some(record) = raw_record.as_object() else {
                continue;
            };
            let source_sessions = if scope == "workspace" {
                let record_source_sessions = value_string_list(record.get("source_sessions"));
                if record_source_sessions.is_empty() {
                    top_level_source_sessions.map(|value| value.to_vec())
                } else {
                    Some(record_source_sessions)
                }
            } else {
                None
            };
            if let Some(doc) = ontology_document_from_record(
                &rel_path,
                object_type,
                object_id,
                record,
                &label_index,
                &existing_ids,
                scope,
                source_sessions.as_deref(),
            ) {
                docs.push(doc);
            }
        }
    }

    docs
}

fn ontology_document_from_record(
    rel_path: &str,
    object_type: &str,
    object_id: &str,
    record: &Map<String, Value>,
    label_index: &BTreeMap<String, String>,
    existing_ids: &BTreeSet<String>,
    scope: &str,
    source_sessions: Option<&[String]>,
) -> Option<SourceDocument> {
    let related_ids = record_related_object_ids(object_type, record, existing_ids);
    let provenance_ids = value_string_list(record.get("provenance_ids"));
    let label = record_label(record).unwrap_or_else(|| object_id.to_string());
    let text = build_ontology_text(
        object_type,
        object_id,
        record,
        label_index,
        &related_ids,
        &provenance_ids,
    );
    if text.trim().is_empty() {
        return None;
    }

    let mut metadata = Map::new();
    metadata.insert(
        "object_id".to_string(),
        Value::String(object_id.to_string()),
    );
    metadata.insert(
        "object_type".to_string(),
        Value::String(object_type.to_string()),
    );
    metadata.insert("object_label".to_string(), Value::String(label.clone()));
    metadata.insert(
        "related_object_ids".to_string(),
        Value::Array(related_ids.iter().cloned().map(Value::String).collect()),
    );
    metadata.insert(
        "linked_object_ids".to_string(),
        Value::Array(
            related_ids
                .iter()
                .cloned()
                .chain(std::iter::once(object_id.to_string()))
                .map(Value::String)
                .collect(),
        ),
    );
    metadata.insert(
        "provenance_ids".to_string(),
        Value::Array(provenance_ids.iter().cloned().map(Value::String).collect()),
    );
    metadata.insert("scope".to_string(), Value::String(scope.to_string()));
    if let Some(source_sessions) = source_sessions {
        metadata.insert(
            "source_sessions".to_string(),
            Value::Array(source_sessions.iter().cloned().map(Value::String).collect()),
        );
    }

    let fingerprint = fingerprint_text(&format!(
        "{text}\n{}\n{}",
        related_ids.join(","),
        provenance_ids.join(",")
    ));
    Some(SourceDocument {
        source_id: format!("{rel_path}#ontology:{object_type}:{object_id}"),
        path: format!("{rel_path}#ontology:{object_type}:{object_id}"),
        title: label,
        text,
        fingerprint,
        kind: format!("ontology_{object_type}"),
        metadata,
    })
}

fn ontology_object_id(doc: &SourceDocument) -> Option<&str> {
    doc.metadata.get("object_id").and_then(Value::as_str)
}

fn collect_existing_state_ids(state: &Map<String, Value>) -> BTreeSet<String> {
    let mut ids = BTreeSet::new();
    for key in [
        "questions",
        "claims",
        "evidence",
        "entities",
        "links",
        "hypotheses",
        "provenance_nodes",
        "confidence_profiles",
    ] {
        let Some(records) = state.get(key).and_then(Value::as_object) else {
            continue;
        };
        ids.extend(records.keys().cloned());
    }
    ids
}

fn build_state_label_index(state: &Map<String, Value>) -> BTreeMap<String, String> {
    let mut labels = BTreeMap::new();
    for key in [
        "questions",
        "claims",
        "evidence",
        "entities",
        "links",
        "hypotheses",
        "provenance_nodes",
        "confidence_profiles",
    ] {
        let Some(records) = state.get(key).and_then(Value::as_object) else {
            continue;
        };
        for (record_id, raw_record) in records {
            if let Some(label) = record_label_from_value(raw_record) {
                labels.insert(record_id.clone(), label);
            }
        }
    }
    labels
}

fn build_ontology_text(
    object_type: &str,
    object_id: &str,
    record: &Map<String, Value>,
    label_index: &BTreeMap<String, String>,
    related_ids: &[String],
    provenance_ids: &[String],
) -> String {
    let mut lines = vec![
        format!("object_type: {object_type}"),
        format!("object_id: {object_id}"),
    ];
    if let Some(label) = record_label(record) {
        lines.push(format!("label: {label}"));
    }
    for key in [
        "status",
        "priority",
        "kind",
        "predicate",
        "evidence_type",
        "canonical_name",
        "question_text",
        "question",
        "claim_text",
        "summary",
        "source_uri",
    ] {
        if let Some(value) = record.get(key).and_then(Value::as_str) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                lines.push(format!("{key}: {trimmed}"));
            }
        }
    }
    if let Some(text) = record.get("content").and_then(Value::as_str) {
        let trimmed = text.trim();
        if !trimmed.is_empty() {
            lines.push(format!("content: {trimmed}"));
        }
    }
    if let Some(aliases) = record.get("aliases").and_then(Value::as_array) {
        let alias_text = aliases
            .iter()
            .filter_map(Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .collect::<Vec<_>>();
        if !alias_text.is_empty() {
            lines.push(format!("aliases: {}", alias_text.join(", ")));
        }
    }
    if let Some(source_entity_id) = record.get("source_entity_id").and_then(Value::as_str) {
        lines.push(format!(
            "source_entity: {}",
            label_index
                .get(source_entity_id)
                .cloned()
                .unwrap_or_else(|| source_entity_id.to_string())
        ));
    }
    if let Some(target_entity_id) = record.get("target_entity_id").and_then(Value::as_str) {
        lines.push(format!(
            "target_entity: {}",
            label_index
                .get(target_entity_id)
                .cloned()
                .unwrap_or_else(|| target_entity_id.to_string())
        ));
    }
    if let Some(attributes) = record
        .get("attributes")
        .and_then(|value| compact_json(value, 320))
    {
        lines.push(format!("attributes: {attributes}"));
    }
    if let Some(external_refs) = record
        .get("external_refs")
        .and_then(|value| compact_json(value, 320))
    {
        lines.push(format!("external_refs: {external_refs}"));
    }
    let related_labels = related_ids
        .iter()
        .take(MAX_GRAPH_RELATED_IDS)
        .map(|id| label_index.get(id).cloned().unwrap_or_else(|| id.clone()))
        .collect::<Vec<_>>();
    if !related_labels.is_empty() {
        lines.push(format!("related_objects: {}", related_labels.join(" | ")));
    }
    if !provenance_ids.is_empty() {
        lines.push(format!("provenance_ids: {}", provenance_ids.join(", ")));
    }
    join_nonempty(&lines)
}

fn record_related_object_ids(
    object_type: &str,
    record: &Map<String, Value>,
    existing_ids: &BTreeSet<String>,
) -> Vec<String> {
    let mut ids = Vec::new();
    let mut push_known = |value: Option<&Value>| {
        for id in value_string_list(value) {
            if looks_like_state_object_id(&id) || existing_ids.contains(&id) {
                ids.push(id);
            }
        }
    };

    match object_type {
        "question" => {
            for key in [
                "claim_ids",
                "evidence_ids",
                "related_entity_ids",
                "related_hypothesis_ids",
                "triggers",
            ] {
                push_known(record.get(key));
            }
            if let Some(value) = record.get("resolution_claim_id") {
                push_known(Some(value));
            }
        }
        "claim" => {
            for key in [
                "subject_refs",
                "support_evidence_ids",
                "contradiction_evidence_ids",
                "evidence_support_ids",
                "evidence_contra_ids",
                "evidence_ids",
            ] {
                push_known(record.get(key));
            }
        }
        "evidence" => {
            for key in ["claim_ids", "entity_ids", "link_ids", "provenance_ids"] {
                push_known(record.get(key));
            }
            if let Some(value) = record.get("confidence_id") {
                push_known(Some(value));
            }
        }
        "entity" => {
            for key in ["entity_ids", "related_entity_ids", "provenance_ids"] {
                push_known(record.get(key));
            }
            if let Some(value) = record.get("confidence_id") {
                push_known(Some(value));
            }
        }
        "link" => {
            for key in ["provenance_ids"] {
                push_known(record.get(key));
            }
            for key in ["source_entity_id", "target_entity_id", "confidence_id"] {
                if let Some(value) = record.get(key) {
                    push_known(Some(value));
                }
            }
        }
        _ => {}
    }

    for (key, value) in record {
        if key.ends_with("_id") || key.ends_with("_ids") {
            push_known(Some(value));
        }
    }

    dedupe_strings(ids)
}

fn looks_like_state_object_id(value: &str) -> bool {
    [
        "q_", "cl_", "ev_", "ent_", "lnk_", "pv_", "conf_", "hyp_", "gap_",
    ]
    .iter()
    .any(|prefix| value.starts_with(prefix))
}

fn record_label(record: &Map<String, Value>) -> Option<String> {
    record_label_from_value(&Value::Object(record.clone()))
}

fn record_label_from_value(value: &Value) -> Option<String> {
    let obj = value.as_object()?;
    for key in [
        "title",
        "label",
        "name",
        "canonical_name",
        "question_text",
        "question",
        "claim_text",
        "summary",
        "content",
        "source_uri",
    ] {
        if let Some(value) = obj.get(key).and_then(Value::as_str) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                return Some(truncate(trimmed, 96));
            }
        }
    }
    None
}

async fn refresh_index<B>(
    index_dir: Option<&Path>,
    documents: &[SourceDocument],
    client: &B,
    corpus: &str,
    retry_policy: EmbeddingsRetryPolicy,
    cancel: Option<&CancellationToken>,
    emit_trace: &mut impl FnMut(String),
) -> anyhow::Result<RefreshIndexOutcome>
where
    B: DocumentEmbeddingsBackend,
{
    let Some(index_dir) = index_dir else {
        return Ok(RefreshIndexOutcome::Complete { chunks: Vec::new() });
    };
    fs::create_dir_all(index_dir).with_context(|| {
        format!(
            "failed to create embeddings index directory {}",
            index_dir.display()
        )
    })?;
    let meta_path = index_dir.join("meta.json");
    let chunks_path = index_dir.join("chunks.jsonl");
    let existing = if load_meta(&meta_path, client.provider(), client.model(), corpus) {
        load_existing_chunks(&chunks_path)
    } else {
        HashMap::new()
    };

    let mut resolved = Vec::new();
    let mut pending_records = Vec::new();
    let mut reused_documents = 0usize;
    let mut reused_chunks = 0usize;
    for doc in documents {
        if let Some(prior) = existing.get(&doc.source_id) {
            if prior
                .iter()
                .all(|chunk| chunk.fingerprint == doc.fingerprint)
            {
                reused_documents += 1;
                reused_chunks += prior.len();
                resolved.extend(prior.clone());
                continue;
            }
        }
        pending_records.extend(build_pending_chunks_for_document(doc));
    }
    pending_records = preflight_pending_chunks(
        pending_records,
        client.limits().input_char_limit,
        emit_trace,
        "preflight",
    );

    let total_documents = documents.len();
    let total_chunks = reused_chunks + pending_records.len();
    if pending_records.is_empty() {
        emit_retrieval_progress(
            emit_trace,
            RetrievalProgress {
                corpus: corpus.to_string(),
                phase: "writing".to_string(),
                documents_done: total_documents,
                documents_total: total_documents,
                chunks_done: total_chunks,
                chunks_total: total_chunks,
                reused_documents,
                message: format!("Writing cached {corpus} retrieval index."),
            },
        );
    } else {
        emit_retrieval_progress(
            emit_trace,
            RetrievalProgress {
                corpus: corpus.to_string(),
                phase: "embedding".to_string(),
                documents_done: reused_documents,
                documents_total: total_documents,
                chunks_done: reused_chunks,
                chunks_total: total_chunks,
                reused_documents,
                message: format!("Embedding {corpus} retrieval index."),
            },
        );
        let mut batch_start = 0usize;
        while batch_start < pending_records.len() {
            let chunk_boundaries = pending_chunk_boundaries(&pending_records);
            let chunks_total = reused_chunks + pending_records.len();
            let batch_end = (batch_start + client.limits().batch_size).min(pending_records.len());
            let prepared = preflight_pending_chunks(
                pending_records[batch_start..batch_end].to_vec(),
                client.limits().input_char_limit,
                emit_trace,
                "batch",
            );
            if prepared.len() != (batch_end - batch_start) {
                pending_records.splice(batch_start..batch_end, prepared);
                continue;
            }

            let texts = pending_records[batch_start..batch_end]
                .iter()
                .map(|record| record.text.clone())
                .collect::<Vec<_>>();
            let vectors = match embed_texts_with_retry(
                client,
                &texts,
                "document",
                corpus,
                retry_policy,
                cancel,
                emit_trace,
            )
            .await
            {
                Ok(vectors) => vectors,
                Err(err) => {
                    if retry_oversized_batch(
                        &mut pending_records,
                        batch_start,
                        &err,
                        client.limits(),
                        emit_trace,
                    ) {
                        continue;
                    }
                    let completed_pending_docs =
                        chunk_boundaries.partition_point(|boundary| *boundary <= batch_start);
                    let documents_done = reused_documents + completed_pending_docs;
                    let chunks_done = reused_chunks + batch_start;
                    let failure_detail = err.detail().to_string();
                    if chunks_done > 0 {
                        let mut cached_chunks = resolved.clone();
                        cached_chunks.extend(finalize_pending_chunks(
                            pending_records[..batch_start].to_vec(),
                        ));
                        sort_chunk_records(&mut cached_chunks);
                        write_index_snapshot(
                            &meta_path,
                            &chunks_path,
                            client.provider(),
                            client.model(),
                            corpus,
                            "partial",
                            documents_done,
                            total_documents,
                            chunks_done,
                            reused_chunks + pending_records.len(),
                            Some(&failure_detail),
                            &cached_chunks,
                        )?;
                        emit_retrieval_trace(
                            emit_trace,
                            format!(
                                "[retrieval] cached partial {corpus} index provider={} documents_done={documents_done}/{total_documents} chunks_done={chunks_done}/{}",
                                client.provider(),
                                reused_chunks + pending_records.len()
                            ),
                        );
                    }
                    let mut cached_chunks = resolved.clone();
                    if batch_start > 0 {
                        cached_chunks.extend(finalize_pending_chunks(
                            pending_records[..batch_start].to_vec(),
                        ));
                        sort_chunk_records(&mut cached_chunks);
                    }
                    emit_retrieval_progress(
                        emit_trace,
                        RetrievalProgress {
                            corpus: corpus.to_string(),
                            phase: "failed".to_string(),
                            documents_done,
                            documents_total: total_documents,
                            chunks_done,
                            chunks_total: reused_chunks + pending_records.len(),
                            reused_documents,
                            message: if chunks_done > 0 {
                                format!(
                                    "{corpus} retrieval indexing failed after retries; cached {documents_done}/{total_documents} docs for future runs."
                                )
                            } else {
                                format!(
                                    "{corpus} retrieval indexing failed before any cacheable chunks were written."
                                )
                            },
                        },
                    );
                    return Ok(RefreshIndexOutcome::PartialCached {
                        documents_done,
                        documents_total: total_documents,
                        chunks_done,
                        chunks_total: reused_chunks + pending_records.len(),
                        failure_detail,
                        cached_chunks,
                    });
                }
            };
            for (record, vector) in pending_records[batch_start..batch_end]
                .iter_mut()
                .zip(vectors.into_iter())
            {
                record.vector = vector;
            }
            batch_start = batch_end;
            let completed_pending_docs =
                chunk_boundaries.partition_point(|boundary| *boundary <= batch_start);
            emit_retrieval_progress(
                emit_trace,
                RetrievalProgress {
                    corpus: corpus.to_string(),
                    phase: "embedding".to_string(),
                    documents_done: reused_documents + completed_pending_docs,
                    documents_total: total_documents,
                    chunks_done: reused_chunks + batch_start,
                    chunks_total,
                    reused_documents,
                    message: format!("Embedding {corpus} retrieval index."),
                },
            );
        }
    }
    resolved.extend(finalize_pending_chunks(pending_records));
    sort_chunk_records(&mut resolved);
    let final_chunks_total = resolved.len();

    emit_retrieval_progress(
        emit_trace,
        RetrievalProgress {
            corpus: corpus.to_string(),
            phase: "writing".to_string(),
            documents_done: total_documents,
            documents_total: total_documents,
            chunks_done: final_chunks_total,
            chunks_total: final_chunks_total,
            reused_documents,
            message: format!("Writing {corpus} retrieval index files."),
        },
    );

    write_index_snapshot(
        &meta_path,
        &chunks_path,
        client.provider(),
        client.model(),
        corpus,
        "complete",
        total_documents,
        total_documents,
        final_chunks_total,
        final_chunks_total,
        None,
        &resolved,
    )?;
    emit_retrieval_progress(
        emit_trace,
        RetrievalProgress {
            corpus: corpus.to_string(),
            phase: "done".to_string(),
            documents_done: total_documents,
            documents_total: total_documents,
            chunks_done: final_chunks_total,
            chunks_total: final_chunks_total,
            reused_documents,
            message: format!("{} retrieval index ready.", capitalize(corpus)),
        },
    );
    Ok(RefreshIndexOutcome::Complete { chunks: resolved })
}

fn sort_chunk_records(chunks: &mut [ChunkRecord]) {
    chunks.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then_with(|| left.chunk_id.cmp(&right.chunk_id))
    });
}

fn write_index_snapshot(
    meta_path: &Path,
    chunks_path: &Path,
    provider: &str,
    model: &str,
    corpus: &str,
    completion: &str,
    documents_done: usize,
    documents_total: usize,
    chunks_done: usize,
    chunks_total: usize,
    last_failure: Option<&str>,
    chunks: &[ChunkRecord],
) -> anyhow::Result<()> {
    let meta = json!({
        "version": INDEX_VERSION,
        "provider": provider,
        "model": model,
        "corpus": corpus,
        "chunk_target_chars": CHUNK_TARGET_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "completion": completion,
        "documents_done": documents_done,
        "documents_total": documents_total,
        "chunks_done": chunks_done,
        "chunks_total": chunks_total,
        "last_failure": last_failure,
    });
    write_text_atomically(meta_path, &serde_json::to_string_pretty(&meta)?)
        .with_context(|| format!("failed to write {}", meta_path.display()))?;

    let serialized = chunks
        .iter()
        .map(|chunk| serde_json::to_string(chunk))
        .collect::<Result<Vec<_>, _>>()?
        .join("\n");
    write_text_atomically(chunks_path, &serialized)
        .with_context(|| format!("failed to write {}", chunks_path.display()))?;
    Ok(())
}

fn write_text_atomically(path: &Path, contents: &str) -> anyhow::Result<()> {
    let tmp_path = atomic_temp_path(path);
    fs::write(&tmp_path, contents)?;
    if let Err(err) = fs::rename(&tmp_path, path) {
        if path.exists() {
            fs::remove_file(path)?;
            fs::rename(&tmp_path, path)?;
        } else {
            return Err(err.into());
        }
    }
    Ok(())
}

fn atomic_temp_path(path: &Path) -> PathBuf {
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("index");
    let tmp_name = format!(".{file_name}.{}.tmp", uuid::Uuid::new_v4());
    path.parent()
        .unwrap_or_else(|| Path::new("."))
        .join(tmp_name)
}

fn load_meta(meta_path: &Path, provider: &str, model: &str, corpus: &str) -> bool {
    let Ok(raw) = fs::read_to_string(meta_path) else {
        return false;
    };
    let Ok(parsed) = serde_json::from_str::<Value>(&raw) else {
        return false;
    };
    let Some(obj) = parsed.as_object() else {
        return false;
    };
    obj.get("version").and_then(Value::as_str) == Some(INDEX_VERSION)
        && obj.get("provider").and_then(Value::as_str) == Some(provider)
        && obj.get("model").and_then(Value::as_str) == Some(model)
        && obj.get("corpus").and_then(Value::as_str) == Some(corpus)
        && obj.get("chunk_target_chars").and_then(Value::as_u64) == Some(CHUNK_TARGET_CHARS as u64)
        && obj.get("chunk_overlap_chars").and_then(Value::as_u64)
            == Some(CHUNK_OVERLAP_CHARS as u64)
}

fn load_existing_chunks(chunks_path: &Path) -> HashMap<String, Vec<ChunkRecord>> {
    let Ok(raw) = fs::read_to_string(chunks_path) else {
        return HashMap::new();
    };
    let mut grouped: HashMap<String, Vec<ChunkRecord>> = HashMap::new();
    for line in raw.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let Ok(chunk) = serde_json::from_str::<ChunkRecord>(trimmed) else {
            continue;
        };
        grouped
            .entry(chunk.source_id.clone())
            .or_default()
            .push(chunk);
    }
    grouped
}

fn score_chunks<'a>(
    chunks: &'a [ChunkRecord],
    query_vector: &[f64],
) -> Vec<(f64, &'a ChunkRecord)> {
    let mut scored: Vec<(f64, &ChunkRecord)> = chunks
        .iter()
        .filter(|chunk| !chunk.vector.is_empty())
        .map(|chunk| (dot(query_vector, &chunk.vector), chunk))
        .collect();
    scored.sort_by(|left, right| right.0.total_cmp(&left.0));
    scored
}

fn search_chunks(
    chunks: &[ChunkRecord],
    query_vector: &[f64],
    top_k: usize,
    per_source_cap: usize,
) -> Vec<Value> {
    let scored = score_chunks(chunks, query_vector);

    let mut hits = Vec::new();
    let mut per_source: BTreeMap<String, usize> = BTreeMap::new();
    for (score, chunk) in scored {
        let count = per_source.get(&chunk.source_id).copied().unwrap_or(0);
        if count >= per_source_cap {
            continue;
        }
        hits.push(chunk.hit_payload(score));
        per_source.insert(chunk.source_id.clone(), count + 1);
        if hits.len() >= top_k {
            break;
        }
    }
    hits
}

fn search_ontology_objects(
    chunks: &[ChunkRecord],
    query_vector: &[f64],
    top_k: usize,
    per_object_cap: usize,
    boost_object_ids: &[String],
) -> Vec<Value> {
    let boost_ids = boost_object_ids.iter().cloned().collect::<BTreeSet<_>>();
    let mut per_object: BTreeMap<String, (f64, &ChunkRecord)> = BTreeMap::new();

    for (base_score, chunk) in score_chunks(chunks, query_vector) {
        let object_id = chunk
            .metadata
            .get("object_id")
            .and_then(Value::as_str)
            .unwrap_or(chunk.source_id.as_str())
            .to_string();
        let related_ids = linked_object_ids(&chunk.metadata);
        let boosted_score = boosted_object_score(base_score, &object_id, &related_ids, &boost_ids);
        let replace = per_object
            .get(&object_id)
            .map(|(existing, _)| boosted_score > *existing)
            .unwrap_or(true);
        if replace {
            per_object.insert(object_id, (boosted_score, chunk));
        }
    }

    let mut ranked = per_object
        .into_iter()
        .map(|(_, value)| value)
        .collect::<Vec<_>>();
    ranked.sort_by(|left, right| right.0.total_cmp(&left.0));

    let mut hits = Vec::new();
    let mut per_type: BTreeMap<String, usize> = BTreeMap::new();
    for (score, chunk) in ranked {
        let object_type = chunk
            .metadata
            .get("object_type")
            .and_then(Value::as_str)
            .unwrap_or("ontology")
            .to_string();
        let count = per_type.get(&object_type).copied().unwrap_or(0);
        if count >= per_object_cap {
            continue;
        }
        let related_ids = linked_object_ids(&chunk.metadata);
        hits.push(json!({
            "object_id": chunk.metadata.get("object_id").and_then(Value::as_str).unwrap_or(chunk.source_id.as_str()),
            "object_type": object_type,
            "score": ((score * 10_000.0).round()) / 10_000.0,
            "summary": chunk.excerpt,
            "title": chunk.title,
            "path": chunk.path,
            "source_id": chunk.source_id,
            "record_path": chunk.record_path,
            "content_role": chunk.content_role,
            "related_object_ids": related_ids,
            "provenance_ids": value_string_list(chunk.metadata.get("provenance_ids")),
            "metadata": chunk.metadata,
        }));
        per_type.insert(
            chunk
                .metadata
                .get("object_type")
                .and_then(Value::as_str)
                .unwrap_or("ontology")
                .to_string(),
            count + 1,
        );
        if hits.len() >= top_k {
            break;
        }
    }
    hits
}

fn fuse_document_hits(
    workspace_chunks: &[ChunkRecord],
    session_chunks: &[ChunkRecord],
    query_vector: &[f64],
    top_ontology_ids: &[String],
    boost_object_ids: &[String],
    top_k: usize,
    per_source_cap: usize,
) -> Vec<Value> {
    let ontology_ids = top_ontology_ids.iter().cloned().collect::<BTreeSet<_>>();
    let boost_ids = boost_object_ids.iter().cloned().collect::<BTreeSet<_>>();
    let mut scored = score_chunks(workspace_chunks, query_vector);
    scored.extend(score_chunks(session_chunks, query_vector));
    let mut reranked = scored
        .into_iter()
        .map(|(score, chunk)| {
            let linked_ids = linked_object_ids(&chunk.metadata);
            let mut boosted = score;
            if linked_ids.iter().any(|id| ontology_ids.contains(id)) {
                boosted += 0.08;
            }
            if linked_ids.iter().any(|id| boost_ids.contains(id)) {
                boosted += 0.05;
            }
            (boosted, chunk)
        })
        .collect::<Vec<_>>();
    reranked.sort_by(|left, right| right.0.total_cmp(&left.0));

    let mut hits = Vec::new();
    let mut per_source: BTreeMap<String, usize> = BTreeMap::new();
    for (score, chunk) in reranked {
        let count = per_source.get(&chunk.source_id).copied().unwrap_or(0);
        if count >= per_source_cap {
            continue;
        }
        hits.push(chunk.hit_payload(score));
        per_source.insert(chunk.source_id.clone(), count + 1);
        if hits.len() >= top_k {
            break;
        }
    }
    hits
}

fn build_graph_expansions(ontology_hits: &[Value]) -> Vec<Value> {
    ontology_hits
        .iter()
        .filter_map(|hit| {
            let object_id = hit.get("object_id").and_then(Value::as_str)?;
            let related = hit
                .get("related_object_ids")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(Value::as_str)
                        .take(MAX_GRAPH_RELATED_IDS)
                        .map(ToString::to_string)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if related.is_empty() {
                return None;
            }
            Some(json!({
                "seed_object_id": object_id,
                "seed_object_type": hit.get("object_type").and_then(Value::as_str).unwrap_or("ontology"),
                "hops": 1,
                "related_object_ids": related,
            }))
        })
        .collect()
}

fn boosted_object_score(
    base_score: f64,
    object_id: &str,
    related_ids: &[String],
    boost_ids: &BTreeSet<String>,
) -> f64 {
    let mut boosted = base_score;
    if boost_ids.contains(object_id) {
        boosted += 0.12;
    }
    if related_ids.iter().any(|id| boost_ids.contains(id)) {
        boosted += 0.06;
    }
    boosted
}

fn linked_object_ids(metadata: &Map<String, Value>) -> Vec<String> {
    dedupe_strings(
        value_string_list(metadata.get("linked_object_ids"))
            .into_iter()
            .chain(value_string_list(metadata.get("related_object_ids")))
            .collect(),
    )
}

fn build_query(objective: &str, question_reasoning_packet: Option<&Value>) -> RetrievalQuery {
    let mut query = RetrievalQuery {
        text: objective.trim().to_string(),
        ..RetrievalQuery::default()
    };
    let Some(packet) = question_reasoning_packet.and_then(Value::as_object) else {
        return query;
    };

    query.focus_question_ids = value_string_list(packet.get("focus_question_ids"));
    let mut parts = vec![query.text.clone()];
    let mut focus_claim_ids = Vec::new();
    let mut focus_entity_ids = Vec::new();
    let mut boost_object_ids = query.focus_question_ids.clone();

    if let Some(questions) = packet.get("unresolved_questions").and_then(Value::as_array) {
        for question in questions.iter().take(4) {
            let text = question
                .get("question")
                .and_then(Value::as_str)
                .or_else(|| question.get("text").and_then(Value::as_str))
                .or_else(|| question.get("question_text").and_then(Value::as_str))
                .unwrap_or_default()
                .trim()
                .to_string();
            if !text.is_empty() {
                parts.push(text);
            }
            focus_claim_ids.extend(value_string_list(question.get("claim_ids")));
            boost_object_ids.extend(value_string_list(question.get("evidence_ids")));
            boost_object_ids.extend(value_string_list(question.get("triggers")));
        }
    }
    if let Some(findings) = packet.get("findings").and_then(Value::as_object) {
        for bucket in ["unresolved", "contested"] {
            if let Some(items) = findings.get(bucket).and_then(Value::as_array) {
                for item in items.iter().take(3) {
                    let summary = item
                        .get("summary")
                        .and_then(Value::as_str)
                        .or_else(|| item.get("claim").and_then(Value::as_str))
                        .or_else(|| item.get("claim_text").and_then(Value::as_str))
                        .unwrap_or_default()
                        .trim()
                        .to_string();
                    if !summary.is_empty() {
                        parts.push(summary);
                    }
                    if let Some(claim_id) = item.get("id").and_then(Value::as_str) {
                        focus_claim_ids.push(claim_id.to_string());
                    }
                    boost_object_ids.extend(value_string_list(item.get("support_evidence_ids")));
                    boost_object_ids
                        .extend(value_string_list(item.get("contradiction_evidence_ids")));
                }
            }
        }
    }
    if let Some(actions) = packet.get("candidate_actions").and_then(Value::as_array) {
        for action in actions.iter().take(6) {
            if let Some(required_inputs) = action.get("required_inputs").and_then(Value::as_object)
            {
                focus_claim_ids.extend(value_string_list(required_inputs.get("claim_ids")));
                focus_entity_ids.extend(value_string_list(required_inputs.get("entity_ids")));
                boost_object_ids.extend(value_string_list(required_inputs.get("evidence_ids")));
            }
            if let Some(refs) = action.get("ontology_object_refs").and_then(Value::as_array) {
                for object_ref in refs {
                    let Some(object_ref) = object_ref.as_object() else {
                        continue;
                    };
                    if let Some(label) = object_ref.get("label").and_then(Value::as_str) {
                        if !label.trim().is_empty() {
                            parts.push(label.trim().to_string());
                        }
                    }
                    let object_id = object_ref
                        .get("object_id")
                        .and_then(Value::as_str)
                        .unwrap_or_default();
                    if object_id.is_empty() {
                        continue;
                    }
                    boost_object_ids.push(object_id.to_string());
                    match object_ref.get("object_type").and_then(Value::as_str) {
                        Some("claim") => focus_claim_ids.push(object_id.to_string()),
                        Some("entity") => focus_entity_ids.push(object_id.to_string()),
                        _ => {}
                    }
                }
            }
        }
    }

    query.focus_claim_ids = dedupe_strings(focus_claim_ids);
    query.focus_entity_ids = dedupe_strings(focus_entity_ids);
    query.boost_object_ids = dedupe_strings(boost_object_ids);
    query.text = parts
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n");
    query
}

fn emit_retrieval_progress(emit_trace: &mut impl FnMut(String), progress: RetrievalProgress) {
    emit_trace(progress.to_trace_message());
}

fn emit_retrieval_trace(emit_trace: &mut impl FnMut(String), message: String) {
    emit_trace(message);
}

fn classify_embeddings_transport_error(
    provider: &str,
    err: reqwest::Error,
) -> EmbeddingsRequestError {
    let detail = format!("{provider} embeddings request failed: {err}");
    let lowered = detail.to_ascii_lowercase();
    if err.is_timeout()
        || err.is_connect()
        || lowered.contains("connection reset")
        || lowered.contains("disconnect")
        || lowered.contains("reset before headers")
        || lowered.contains("upstream connect error")
        || lowered.contains("overflow")
        || lowered.contains("gateway")
        || lowered.contains("temporarily unavailable")
        || lowered.contains("service unavailable")
    {
        return EmbeddingsRequestError::RetryableTransient {
            status_code: None,
            provider_code: None,
            retry_after_sec: None,
            detail,
        };
    }
    EmbeddingsRequestError::Fatal {
        status_code: None,
        detail,
    }
}

fn classify_embeddings_http_error(
    provider: &str,
    status: reqwest::StatusCode,
    headers: &reqwest::header::HeaderMap,
    body: &str,
) -> EmbeddingsRequestError {
    let parsed = serde_json::from_str::<Value>(body).ok();
    let (message, provider_code, body_retry_after) = parsed
        .as_ref()
        .map(extract_provider_error_fields)
        .unwrap_or_else(|| (String::new(), None, None));
    let retry_after_sec = parse_retry_after_header(headers).or(body_retry_after);
    let detail_body = if !message.is_empty() {
        message
    } else if !body.trim().is_empty() {
        truncate(body, 500)
    } else {
        status.to_string()
    };
    let detail = format!(
        "{provider} embeddings HTTP {}: {detail_body}",
        status.as_u16()
    );
    if let Some(input_id) = extract_oversize_input_id(&detail) {
        return EmbeddingsRequestError::Oversize { input_id, detail };
    }
    if is_retryable_status_code(status.as_u16()) || is_retryable_transient_text(&detail) {
        return EmbeddingsRequestError::RetryableTransient {
            status_code: Some(status.as_u16()),
            provider_code,
            retry_after_sec,
            detail,
        };
    }
    EmbeddingsRequestError::Fatal {
        status_code: Some(status.as_u16()),
        detail,
    }
}

fn is_retryable_status_code(status_code: u16) -> bool {
    matches!(status_code, 408 | 429 | 500 | 502 | 503 | 504)
}

fn is_retryable_transient_text(detail: &str) -> bool {
    let lowered = detail.to_ascii_lowercase();
    lowered.contains("timeout")
        || lowered.contains("timed out")
        || lowered.contains("service unavailable")
        || lowered.contains("temporarily unavailable")
        || lowered.contains("upstream connect error")
        || lowered.contains("disconnect")
        || lowered.contains("connection reset")
        || lowered.contains("reset before headers")
        || lowered.contains("gateway")
        || lowered.contains("overflow")
}

fn extract_provider_error_fields(payload: &Value) -> (String, Option<String>, Option<f64>) {
    if let Some(obj) = payload.as_object() {
        if let Some(error) = obj.get("error") {
            let message = error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_string();
            let provider_code = extract_provider_code(error.get("code"));
            let retry_after = parse_retry_after_value(error.get("retry_after"))
                .or_else(|| parse_retry_after_value(obj.get("retry_after")));
            return (message, provider_code, retry_after);
        }
        let message = obj
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_string();
        let provider_code = extract_provider_code(obj.get("code"));
        let retry_after = parse_retry_after_value(obj.get("retry_after"));
        return (message, provider_code, retry_after);
    }
    (String::new(), None, None)
}

fn extract_provider_code(value: Option<&Value>) -> Option<String> {
    match value {
        Some(Value::String(text)) => {
            Some(text.trim().to_string()).filter(|value| !value.is_empty())
        }
        Some(Value::Number(num)) => Some(num.to_string()),
        _ => None,
    }
}

fn parse_retry_after_value(value: Option<&Value>) -> Option<f64> {
    match value {
        Some(Value::Number(num)) => num.as_f64().map(|v| v.max(0.0)),
        Some(Value::String(text)) => parse_retry_after_text(text),
        _ => None,
    }
}

fn parse_retry_after_text(text: &str) -> Option<f64> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return None;
    }
    if let Ok(seconds) = trimmed.parse::<f64>() {
        return Some(seconds.max(0.0));
    }
    let parsed = DateTime::parse_from_rfc2822(trimmed).ok()?;
    Some(
        (parsed.with_timezone(&Utc) - Utc::now())
            .num_milliseconds()
            .max(0) as f64
            / 1000.0,
    )
}

fn parse_retry_after_header(headers: &reqwest::header::HeaderMap) -> Option<f64> {
    let value = headers.get(reqwest::header::RETRY_AFTER)?;
    let text = value.to_str().ok()?;
    parse_retry_after_text(text)
}

fn retry_oversized_query_windows(
    windows: &mut Vec<String>,
    error: &EmbeddingsRequestError,
    limits: EmbeddingsProviderLimits,
    emit_trace: &mut impl FnMut(String),
) -> bool {
    let EmbeddingsRequestError::Oversize { input_id, .. } = error else {
        return false;
    };
    let Some(offending) = windows.get(*input_id).cloned() else {
        return false;
    };
    let emergency_limit = limits
        .emergency_input_char_limit
        .min((offending.chars().count() / 2).max(400));
    let replacements = split_text_for_limit(&offending, emergency_limit);
    if replacements.len() <= 1 {
        return false;
    }
    windows.splice(*input_id..*input_id + 1, replacements.clone());
    emit_retrieval_trace(
        emit_trace,
        format!(
            "[retrieval] retrying query after provider oversize input_id={} chars={} retry_limit={} windows={}",
            input_id,
            offending.chars().count(),
            emergency_limit,
            replacements.len()
        ),
    );
    true
}

fn split_text_for_limit(text: &str, max_chars: usize) -> Vec<String> {
    if text.chars().count() <= max_chars {
        return vec![text.to_string()];
    }
    let target_chars = CHUNK_TARGET_CHARS.min(max_chars).max(400);
    let overlap_chars = CHUNK_OVERLAP_CHARS
        .min((target_chars / 5).max(80))
        .min(target_chars.saturating_sub(1));
    let windows = sliding_windows(text, target_chars, overlap_chars);
    if windows.len() <= 1 {
        return vec![text.to_string()];
    }
    windows
        .into_iter()
        .map(|window| window.trim().to_string())
        .filter(|window| !window.is_empty())
        .collect()
}

fn build_pending_chunks_for_document(doc: &SourceDocument) -> Vec<PendingChunk> {
    let mut pending = Vec::new();
    for record in semantic_records_for_document(doc) {
        for text in chunk_semantic_record(&record, doc) {
            let stripped = text.trim();
            if stripped.is_empty() {
                continue;
            }
            pending.push(PendingChunk {
                source_id: doc.source_id.clone(),
                path: doc.path.clone(),
                title: doc.title.clone(),
                text: stripped.to_string(),
                fingerprint: doc.fingerprint.clone(),
                kind: doc.kind.clone(),
                metadata: record.metadata.clone(),
                record_path: record.record_path.clone(),
                content_role: record.content_role.clone(),
                vector: Vec::new(),
            });
        }
    }
    pending
}

fn finalize_pending_chunks(chunks: Vec<PendingChunk>) -> Vec<ChunkRecord> {
    let mut finalized = Vec::new();
    let mut chunk_indexes: HashMap<String, usize> = HashMap::new();
    let mut record_subchunks: HashMap<(String, String), usize> = HashMap::new();
    for chunk in chunks {
        let chunk_index = chunk_indexes.get(&chunk.source_id).copied().unwrap_or(0);
        let record_key = (chunk.source_id.clone(), chunk.record_path.clone());
        let subchunk_index = record_subchunks.get(&record_key).copied().unwrap_or(0);
        let mut metadata = chunk.metadata.clone();
        metadata.insert(
            "chunk_index".to_string(),
            Value::Number((chunk_index as u64).into()),
        );
        metadata.insert(
            "record_path".to_string(),
            Value::String(chunk.record_path.clone()),
        );
        metadata.insert(
            "content_role".to_string(),
            Value::String(chunk.content_role.clone()),
        );
        metadata.insert(
            "subchunk_index".to_string(),
            Value::Number((subchunk_index as u64).into()),
        );
        finalized.push(ChunkRecord {
            chunk_id: format!("{}::chunk:{chunk_index}", chunk.source_id),
            source_id: chunk.source_id.clone(),
            path: chunk.path.clone(),
            title: chunk.title.clone(),
            text: chunk.text.clone(),
            excerpt: make_excerpt(&chunk.text),
            fingerprint: chunk.fingerprint.clone(),
            kind: chunk.kind.clone(),
            metadata,
            record_path: chunk.record_path.clone(),
            content_role: chunk.content_role.clone(),
            subchunk_index,
            vector: chunk.vector.clone(),
        });
        chunk_indexes.insert(chunk.source_id.clone(), chunk_index + 1);
        record_subchunks.insert(record_key, subchunk_index + 1);
    }
    finalized
}

fn pending_chunk_boundaries(chunks: &[PendingChunk]) -> Vec<usize> {
    if chunks.is_empty() {
        return Vec::new();
    }
    let mut boundaries = Vec::new();
    let mut running = 0usize;
    for (index, chunk) in chunks.iter().enumerate() {
        running += 1;
        let next_source = chunks.get(index + 1).map(|item| item.source_id.as_str());
        if next_source != Some(chunk.source_id.as_str()) {
            boundaries.push(running);
        }
    }
    boundaries
}

fn preflight_pending_chunks(
    chunks: Vec<PendingChunk>,
    max_chars: usize,
    emit_trace: &mut impl FnMut(String),
    reason: &str,
) -> Vec<PendingChunk> {
    let mut prepared = Vec::new();
    for chunk in chunks {
        if chunk.text.chars().count() <= max_chars {
            prepared.push(chunk);
            continue;
        }
        let replacements = split_pending_chunk_for_limit(&chunk, max_chars);
        if replacements.len() > 1 {
            emit_retrieval_trace(
                emit_trace,
                format!(
                    "[retrieval] auto-resplit oversized chunk reason={reason} source={} record_path={} chars={} limit={} chunks={}",
                    chunk.path,
                    chunk.record_path,
                    chunk.text.chars().count(),
                    max_chars,
                    replacements.len()
                ),
            );
        }
        prepared.extend(replacements);
    }
    prepared
}

fn retry_oversized_batch(
    pending_records: &mut Vec<PendingChunk>,
    batch_start: usize,
    error: &EmbeddingsRequestError,
    limits: EmbeddingsProviderLimits,
    emit_trace: &mut impl FnMut(String),
) -> bool {
    let EmbeddingsRequestError::Oversize { input_id, .. } = error else {
        return false;
    };
    let absolute_index = batch_start + *input_id;
    let Some(offending) = pending_records.get(absolute_index).cloned() else {
        return false;
    };
    let emergency_limit = limits
        .emergency_input_char_limit
        .min((offending.text.chars().count() / 2).max(400));
    let replacements = split_pending_chunk_for_limit(&offending, emergency_limit);
    if replacements.len() <= 1 {
        return false;
    }
    pending_records.splice(absolute_index..absolute_index + 1, replacements.clone());
    emit_retrieval_trace(
        emit_trace,
        format!(
            "[retrieval] retrying batch after provider oversize source={} record_path={} input_id={} chars={} retry_limit={} chunks={}",
            offending.path,
            offending.record_path,
            input_id,
            offending.text.chars().count(),
            emergency_limit,
            replacements.len()
        ),
    );
    true
}

fn split_pending_chunk_for_limit(chunk: &PendingChunk, max_chars: usize) -> Vec<PendingChunk> {
    if chunk.text.chars().count() <= max_chars {
        return vec![chunk.clone()];
    }
    let target_chars = CHUNK_TARGET_CHARS.min(max_chars).max(400);
    let overlap_chars = CHUNK_OVERLAP_CHARS
        .min((target_chars / 5).max(80))
        .min(target_chars.saturating_sub(1));
    let windows = sliding_windows(&chunk.text, target_chars, overlap_chars);
    if windows.len() <= 1 {
        return vec![chunk.clone()];
    }
    windows
        .into_iter()
        .map(|window| PendingChunk {
            source_id: chunk.source_id.clone(),
            path: chunk.path.clone(),
            title: chunk.title.clone(),
            text: window,
            fingerprint: chunk.fingerprint.clone(),
            kind: chunk.kind.clone(),
            metadata: chunk.metadata.clone(),
            record_path: chunk.record_path.clone(),
            content_role: chunk.content_role.clone(),
            vector: Vec::new(),
        })
        .collect()
}

fn semantic_records_for_document(doc: &SourceDocument) -> Vec<SemanticRecord> {
    let suffix = doc
        .path
        .split('#')
        .next()
        .and_then(|value| Path::new(value).extension())
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    match doc.kind.as_str() {
        "evidence" | "session_memory" => body_semantic_records(&doc.text, &doc.metadata),
        _ if suffix == "json" => {
            let Ok(parsed) = serde_json::from_str::<Value>(&doc.text) else {
                return body_semantic_records(&doc.text, &doc.metadata);
            };
            if let Some(obj) = parsed.as_object() {
                let records = semantic_records_from_wrapper_payload(obj, &doc.metadata);
                if !records.is_empty() {
                    return records;
                }
            }
            let records =
                semantic_records_from_json_value(&parsed, "root", "structured", &doc.metadata);
            if records.is_empty() {
                body_semantic_records(&doc.text, &doc.metadata)
            } else {
                records
            }
        }
        _ if suffix == "csv" => {
            let records = semantic_records_from_delimited(&doc.text, ',', &doc.metadata);
            if records.is_empty() {
                body_semantic_records(&doc.text, &doc.metadata)
            } else {
                records
            }
        }
        _ if suffix == "tsv" => {
            let records = semantic_records_from_delimited(&doc.text, '\t', &doc.metadata);
            if records.is_empty() {
                body_semantic_records(&doc.text, &doc.metadata)
            } else {
                records
            }
        }
        _ => body_semantic_records(&doc.text, &doc.metadata),
    }
}

fn body_semantic_records(text: &str, metadata: &Map<String, Value>) -> Vec<SemanticRecord> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    vec![SemanticRecord {
        record_path: "body".to_string(),
        content_role: "body".to_string(),
        text: trimmed.to_string(),
        metadata: metadata.clone(),
    }]
}

fn semantic_records_from_wrapper_payload(
    payload: &Map<String, Value>,
    metadata: &Map<String, Value>,
) -> Vec<SemanticRecord> {
    if !is_wrapper_artifact(payload) {
        return Vec::new();
    }
    let mut records = Vec::new();
    let mut summary_lines = Vec::new();
    for key in ["provider", "service", "operation", "model", "path"] {
        if let Some(value) = payload.get(key).and_then(Value::as_str) {
            if !value.trim().is_empty() {
                summary_lines.push(format!("{key}: {}", value.trim()));
            }
        }
    }
    for key in ["file", "options", "artifacts"] {
        if let Some(value) = payload.get(key) {
            if let Some(compact) = compact_json(value, 320) {
                summary_lines.push(format!("{key}: {compact}"));
            }
        }
    }
    if !summary_lines.is_empty() {
        records.push(SemanticRecord {
            record_path: "summary".to_string(),
            content_role: "summary".to_string(),
            text: summary_lines.join("\n"),
            metadata: metadata.clone(),
        });
    }
    if let Some(text_value) = payload.get("text") {
        records.extend(semantic_records_from_json_value(
            text_value, "text", "body", metadata,
        ));
    }
    if let Some(response) = payload.get("response") {
        records.extend(semantic_records_from_json_value(
            response,
            "response",
            "structured",
            metadata,
        ));
    }
    for extra in ["pages", "segments", "document_annotation"] {
        if let Some(value) = payload.get(extra) {
            if extra == "response" || extra == "text" {
                continue;
            }
            records.extend(semantic_records_from_json_value(
                value,
                extra,
                &json_child_role(extra, "structured"),
                metadata,
            ));
        }
    }
    records
}

fn semantic_records_from_json_value(
    value: &Value,
    record_path: &str,
    content_role: &str,
    metadata: &Map<String, Value>,
) -> Vec<SemanticRecord> {
    match value {
        Value::Object(map) => {
            let serialized = json_text(value, true);
            if serialized.chars().count() <= STRUCTURED_RECORD_MAX_CHARS {
                return vec![SemanticRecord {
                    record_path: record_path.to_string(),
                    content_role: content_role.to_string(),
                    text: serialized,
                    metadata: metadata.clone(),
                }];
            }
            let mut records = Vec::new();
            for (key, child) in map {
                let child_path = if record_path.is_empty() {
                    key.to_string()
                } else {
                    format!("{record_path}.{key}")
                };
                records.extend(semantic_records_from_json_value(
                    child,
                    &child_path,
                    &json_child_role(key, content_role),
                    metadata,
                ));
            }
            records
        }
        Value::Array(items) => {
            let serialized = json_text(value, true);
            if serialized.chars().count() <= STRUCTURED_RECORD_MAX_CHARS {
                return vec![SemanticRecord {
                    record_path: record_path.to_string(),
                    content_role: content_role.to_string(),
                    text: serialized,
                    metadata: metadata.clone(),
                }];
            }
            let mut records = Vec::new();
            for (index, child) in items.iter().enumerate() {
                let child_path = format!("{record_path}[{index}]");
                records.extend(semantic_records_from_json_value(
                    child,
                    &child_path,
                    &json_list_role(record_path, content_role),
                    metadata,
                ));
            }
            records
        }
        Value::String(text) => {
            let stripped = text.trim();
            if stripped.is_empty() {
                return Vec::new();
            }
            let leaf = format_leaf_text(stripped, record_path, content_role);
            if leaf.chars().count() <= STRUCTURED_RECORD_MAX_CHARS {
                return vec![SemanticRecord {
                    record_path: record_path.to_string(),
                    content_role: content_role.to_string(),
                    text: leaf,
                    metadata: metadata.clone(),
                }];
            }
            sliding_windows(&leaf, CHUNK_TARGET_CHARS, CHUNK_OVERLAP_CHARS)
                .into_iter()
                .map(|window| SemanticRecord {
                    record_path: record_path.to_string(),
                    content_role: content_role.to_string(),
                    text: window,
                    metadata: metadata.clone(),
                })
                .collect()
        }
        _ => {
            let Some(scalar) = json_scalar_text(value) else {
                return Vec::new();
            };
            vec![SemanticRecord {
                record_path: record_path.to_string(),
                content_role: content_role.to_string(),
                text: format_leaf_text(&scalar, record_path, content_role),
                metadata: metadata.clone(),
            }]
        }
    }
}

fn semantic_records_from_delimited(
    text: &str,
    delimiter: char,
    metadata: &Map<String, Value>,
) -> Vec<SemanticRecord> {
    let mut lines = text.lines();
    let Some(header_line) = lines.next() else {
        return Vec::new();
    };
    let headers: Vec<&str> = header_line.split(delimiter).collect();
    if headers.is_empty() {
        return body_semantic_records(text, metadata);
    }
    let mut records = vec![SemanticRecord {
        record_path: "schema".to_string(),
        content_role: "table_schema".to_string(),
        text: format!("columns: {}", headers.join(&delimiter.to_string())),
        metadata: metadata.clone(),
    }];
    for (row_index, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let values: Vec<&str> = line.split(delimiter).collect();
        let mut row = BTreeMap::new();
        for (idx, header) in headers.iter().enumerate() {
            row.insert(
                header.trim().to_string(),
                values
                    .get(idx)
                    .copied()
                    .unwrap_or_default()
                    .trim()
                    .to_string(),
            );
        }
        records.extend(semantic_records_from_table_row(
            &row,
            &format!("row[{row_index}]"),
            metadata,
        ));
    }
    records
}

fn semantic_records_from_table_row(
    row: &BTreeMap<String, String>,
    record_path: &str,
    metadata: &Map<String, Value>,
) -> Vec<SemanticRecord> {
    let serialized = serde_json::to_string(row).unwrap_or_default();
    if serialized.chars().count() <= STRUCTURED_RECORD_MAX_CHARS {
        return vec![SemanticRecord {
            record_path: record_path.to_string(),
            content_role: "table_row".to_string(),
            text: serialized,
            metadata: metadata.clone(),
        }];
    }
    let mut records = Vec::new();
    let mut current = BTreeMap::new();
    for (key, value) in row {
        let trimmed = value.trim().to_string();
        let field_path = format!("{record_path}.{key}");
        if trimmed.chars().count() > STRUCTURED_RECORD_MAX_CHARS {
            if !current.is_empty() {
                records.push(SemanticRecord {
                    record_path: record_path.to_string(),
                    content_role: "table_row".to_string(),
                    text: serde_json::to_string(&current).unwrap_or_default(),
                    metadata: metadata.clone(),
                });
                current.clear();
            }
            records.extend(semantic_records_from_json_value(
                &Value::String(trimmed),
                &field_path,
                "table_field",
                metadata,
            ));
            continue;
        }
        let mut candidate = current.clone();
        candidate.insert(key.clone(), trimmed.clone());
        if !current.is_empty()
            && serde_json::to_string(&candidate)
                .unwrap_or_default()
                .chars()
                .count()
                > STRUCTURED_RECORD_MAX_CHARS
        {
            records.push(SemanticRecord {
                record_path: record_path.to_string(),
                content_role: "table_row".to_string(),
                text: serde_json::to_string(&current).unwrap_or_default(),
                metadata: metadata.clone(),
            });
            current.clear();
        }
        current.insert(key.clone(), trimmed);
    }
    if !current.is_empty() {
        records.push(SemanticRecord {
            record_path: record_path.to_string(),
            content_role: "table_row".to_string(),
            text: serde_json::to_string(&current).unwrap_or_default(),
            metadata: metadata.clone(),
        });
    }
    records
}

fn chunk_semantic_record(record: &SemanticRecord, doc: &SourceDocument) -> Vec<String> {
    let trimmed = record.text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    if matches!(doc.kind.as_str(), "evidence" | "session_memory") {
        return chunk_atomic_text(trimmed);
    }
    if matches!(
        record.content_role.as_str(),
        "body" | "page_markdown" | "annotation" | "summary" | "table_schema"
    ) {
        return chunk_paragraph_text(trimmed);
    }
    chunk_atomic_text(trimmed)
}

fn chunk_atomic_text(text: &str) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    if trimmed.chars().count() <= STRUCTURED_RECORD_MAX_CHARS {
        return vec![trimmed.to_string()];
    }
    sliding_windows(trimmed, CHUNK_TARGET_CHARS, CHUNK_OVERLAP_CHARS)
}

fn chunk_paragraph_text(text: &str) -> Vec<String> {
    let paragraphs = split_paragraphs(text);
    if paragraphs.is_empty() {
        return Vec::new();
    }
    let mut chunks = Vec::new();
    let mut current = String::new();
    for paragraph in paragraphs {
        let candidate = if current.is_empty() {
            paragraph.clone()
        } else {
            format!("{current}\n\n{paragraph}")
        };
        if !current.is_empty() && candidate.len() > CHUNK_TARGET_CHARS {
            chunks.push(current.clone());
            let overlap = tail_chars(&current, CHUNK_OVERLAP_CHARS);
            current = if overlap.is_empty() {
                paragraph
            } else {
                format!("{overlap}\n\n{paragraph}")
            };
        } else {
            current = candidate;
        }
    }
    if !current.is_empty() {
        chunks.push(current);
    }

    let mut expanded = Vec::new();
    for chunk in chunks {
        if chunk.chars().count() <= STRUCTURED_RECORD_MAX_CHARS {
            expanded.push(chunk);
        } else {
            expanded.extend(sliding_windows(
                &chunk,
                CHUNK_TARGET_CHARS,
                CHUNK_OVERLAP_CHARS,
            ));
        }
    }
    expanded
}

fn sliding_windows(text: &str, target_chars: usize, overlap_chars: usize) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    let step = target_chars.saturating_sub(overlap_chars).max(1);
    let mut windows = Vec::new();
    let mut start = 0usize;
    while start < trimmed.len() {
        let end = clamp_boundary(trimmed, (start + target_chars).min(trimmed.len()));
        let slice = trimmed[start..end].trim();
        if !slice.is_empty() {
            windows.push(slice.to_string());
        }
        if end >= trimmed.len() {
            break;
        }
        start = clamp_boundary(trimmed, start + step);
    }
    windows
}

fn split_query_windows(text: &str, max_chars: usize) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    if trimmed.chars().count() <= max_chars {
        return vec![trimmed.to_string()];
    }
    let overlap_chars = max_chars
        .saturating_div(4)
        .clamp(1, 400)
        .min(max_chars.saturating_sub(1));
    sliding_windows(trimmed, max_chars, overlap_chars)
}

fn json_text(value: &Value, pretty: bool) -> String {
    if pretty {
        serde_json::to_string_pretty(value).unwrap_or_else(|_| value.to_string())
    } else {
        serde_json::to_string(value).unwrap_or_else(|_| value.to_string())
    }
}

fn compact_json(value: &Value, max_chars: usize) -> Option<String> {
    let compact = json_text(value, false);
    if compact.trim().is_empty() {
        return None;
    }
    if compact.chars().count() <= max_chars {
        return Some(compact);
    }
    Some(truncate(&compact, max_chars))
}

fn json_scalar_text(value: &Value) -> Option<String> {
    match value {
        Value::Null => None,
        Value::Bool(flag) => Some(if *flag {
            "true".to_string()
        } else {
            "false".to_string()
        }),
        Value::Number(number) => Some(number.to_string()),
        Value::String(text) => {
            let trimmed = text.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.to_string())
            }
        }
        other => Some(json_text(other, false)),
    }
}

fn format_leaf_text(value: &str, record_path: &str, content_role: &str) -> String {
    if matches!(
        content_role,
        "body" | "page_markdown" | "annotation" | "summary" | "transcript_segment"
    ) {
        return value.to_string();
    }
    let mut label = record_path
        .rsplit('.')
        .next()
        .unwrap_or(record_path)
        .to_string();
    if let Some((prefix, _)) = label.split_once('[') {
        label = prefix.to_string();
    }
    if !label.is_empty() && !matches!(label.as_str(), "root" | "body") {
        format!("{label}: {value}")
    } else {
        value.to_string()
    }
}

fn json_child_role(key: &str, parent_role: &str) -> String {
    let lowered = key.to_ascii_lowercase();
    if lowered == "markdown" {
        return "page_markdown".to_string();
    }
    if matches!(
        lowered.as_str(),
        "text" | "content" | "summary" | "description" | "body"
    ) {
        return "body".to_string();
    }
    if matches!(lowered.as_str(), "document_annotation" | "annotation") {
        return "annotation".to_string();
    }
    if matches!(
        lowered.as_str(),
        "segment" | "segments" | "transcript" | "transcription"
    ) {
        return "transcript_segment".to_string();
    }
    if matches!(
        lowered.as_str(),
        "provider"
            | "service"
            | "model"
            | "operation"
            | "options"
            | "artifacts"
            | "usage_info"
            | "file"
            | "path"
    ) {
        return "metadata".to_string();
    }
    if parent_role == "transcript_segment" {
        return "transcript_segment".to_string();
    }
    "structured".to_string()
}

fn json_list_role(record_path: &str, parent_role: &str) -> String {
    if record_path.ends_with(".pages") {
        return "page_markdown".to_string();
    }
    if record_path.ends_with(".segments") {
        return "transcript_segment".to_string();
    }
    parent_role.to_string()
}

fn is_wrapper_artifact(payload: &Map<String, Value>) -> bool {
    let mut count = 0usize;
    for key in [
        "provider",
        "operation",
        "response",
        "text",
        "artifacts",
        "service",
    ] {
        if payload.contains_key(key) {
            count += 1;
        }
    }
    count >= 3
}

fn extract_oversize_input_id(message: &str) -> Option<usize> {
    let lowered = message.to_ascii_lowercase();
    let start = lowered.find("input id ")? + "input id ".len();
    let digits = lowered[start..]
        .chars()
        .take_while(|ch| ch.is_ascii_digit())
        .collect::<String>();
    if digits.is_empty() || !lowered.contains("exceeding max") {
        return None;
    }
    digits.parse::<usize>().ok()
}

fn mean_pool_vectors(vectors: &[Vec<f64>]) -> Vec<f64> {
    let width = vectors.iter().map(Vec::len).min().unwrap_or(0);
    if width == 0 {
        return Vec::new();
    }
    let pooled = (0..width)
        .map(|index| vectors.iter().map(|vector| vector[index]).sum::<f64>() / vectors.len() as f64)
        .collect::<Vec<_>>();
    normalize_vector(pooled)
}

fn split_paragraphs(text: &str) -> Vec<String> {
    let mut paragraphs = Vec::new();
    let mut current = Vec::new();
    for line in text.lines() {
        if line.trim().is_empty() {
            if !current.is_empty() {
                paragraphs.push(current.join("\n").trim().to_string());
                current.clear();
            }
            continue;
        }
        current.push(line.to_string());
    }
    if !current.is_empty() {
        paragraphs.push(current.join("\n").trim().to_string());
    }
    paragraphs
        .into_iter()
        .filter(|value| !value.is_empty())
        .collect()
}

fn should_skip_walk_entry(path: &Path, workspace: &Path, session_root_dir: &str) -> bool {
    if path == workspace {
        return false;
    }
    let Ok(rel) = path.strip_prefix(workspace) else {
        return false;
    };
    let parts = rel
        .iter()
        .filter_map(|part| part.to_str())
        .collect::<Vec<_>>();
    if parts.iter().any(|part| EXCLUDED_DIR_NAMES.contains(part)) {
        return true;
    }
    if parts.iter().any(|part| is_junk_name(part)) {
        return true;
    }
    if parts.first().copied() == Some(session_root_dir) {
        return !(parts.get(1).copied() == Some("wiki"));
    }
    false
}

fn is_junk_name(name: &str) -> bool {
    IGNORED_FILE_NAMES.contains(&name)
        || IGNORED_FILE_PREFIXES
            .iter()
            .any(|prefix| name.starts_with(prefix))
}

fn is_junk_path(path: &Path) -> bool {
    path.file_name()
        .and_then(|value| value.to_str())
        .is_some_and(is_junk_name)
}

fn make_excerpt(text: &str) -> String {
    let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
    truncate(&collapsed, MAX_EXCERPT_CHARS)
}

fn fingerprint_text(text: &str) -> String {
    let mut crc = crc32fast::Hasher::new();
    crc.update(text.as_bytes());
    format!("{:08x}:{}", crc.finalize(), text.len())
}

fn relative_path(path: &Path, workspace: &Path) -> String {
    path.strip_prefix(workspace)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn has_text(value: Option<&str>) -> bool {
    value.map(str::trim).is_some_and(|value| !value.is_empty())
}

fn string_field(map: &Map<String, Value>, key: &str) -> String {
    map.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn nonempty_or(value: Option<&str>, fallback: &str) -> String {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(fallback)
        .to_string()
}

fn join_nonempty(values: &[String]) -> String {
    values
        .iter()
        .filter(|value| !value.trim().is_empty())
        .cloned()
        .collect::<Vec<_>>()
        .join("\n")
}

fn value_string_list(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|item| match item {
                Value::String(text) => Some(text.trim().to_string()),
                Value::Number(number) => Some(number.to_string()),
                _ => None,
            })
            .filter(|value| !value.is_empty())
            .collect(),
        Some(Value::String(text)) if !text.trim().is_empty() => vec![text.trim().to_string()],
        Some(Value::Number(number)) => vec![number.to_string()],
        _ => Vec::new(),
    }
}

fn dedupe_strings(values: Vec<String>) -> Vec<String> {
    let mut seen = BTreeSet::new();
    values
        .into_iter()
        .filter(|value| !value.trim().is_empty())
        .filter(|value| seen.insert(value.clone()))
        .collect()
}

fn normalize_vector(values: Vec<f64>) -> Vec<f64> {
    let norm = values.iter().map(|value| value * value).sum::<f64>().sqrt();
    if norm <= 0.0 {
        return values;
    }
    values.into_iter().map(|value| value / norm).collect()
}

fn dot(left: &[f64], right: &[f64]) -> f64 {
    left.iter()
        .zip(right.iter())
        .map(|(lv, rv)| lv * rv)
        .sum::<f64>()
}

fn truncate(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    text.chars()
        .take(max_chars.saturating_sub(3))
        .collect::<String>()
        + "..."
}

fn capitalize(text: &str) -> String {
    let mut chars = text.chars();
    let Some(first) = chars.next() else {
        return String::new();
    };
    first.to_uppercase().collect::<String>() + chars.as_str()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;
    use std::sync::{Arc, Mutex};
    use tempfile::tempdir;

    #[test]
    fn test_documents_from_file_ignores_junk_files() {
        let tmp = tempdir().unwrap();
        let root = tmp.path();
        fs::write(root.join("._notes.md"), "junk").unwrap();
        fs::write(root.join(".DS_Store"), "junk").unwrap();
        fs::write(root.join("notes.md"), "hello").unwrap();

        assert!(documents_from_file(&root.join("._notes.md"), root, "workspace").is_empty());
        assert!(documents_from_file(&root.join(".DS_Store"), root, "workspace").is_empty());
        let docs = documents_from_file(&root.join("notes.md"), root, "workspace");
        assert_eq!(docs.len(), 1);
        assert_eq!(docs[0].path, "notes.md");
    }

    #[test]
    fn test_retrieval_progress_formats_trace_message() {
        let line = RetrievalProgress {
            corpus: "workspace".to_string(),
            phase: "embedding".to_string(),
            documents_done: 12,
            documents_total: 48,
            chunks_done: 80,
            chunks_total: 320,
            reused_documents: 0,
            message: "Embedding workspace retrieval index.".to_string(),
        }
        .to_trace_message();

        assert!(line.starts_with("[retrieval:progress] "));
        assert!(line.contains("\"percent\":25"));
    }

    #[test]
    fn test_build_pending_chunks_normalizes_ocr_wrapper_json() {
        let doc = SourceDocument {
            source_id: "scan.pdf.ocr.json".to_string(),
            path: "scan.pdf.ocr.json".to_string(),
            title: "scan.pdf.ocr.json".to_string(),
            text: json!({
                "provider": "mistral",
                "service": "document_ai",
                "operation": "ocr",
                "model": "mistral-ocr-latest",
                "path": "scan.pdf",
                "artifacts": {"markdown_path": "scan.pdf.ocr.md"},
                "text": "OCR text ".repeat(4000),
                "response": {
                    "pages": [
                        {"index": 0, "markdown": format!("# Page 1\n{}", "Alpha ".repeat(1500))},
                        {"index": 1, "markdown": format!("# Page 2\n{}", "Beta ".repeat(1500))},
                    ],
                    "usage_info": {"pages_processed": 2}
                }
            })
            .to_string(),
            fingerprint: "ocr-doc".to_string(),
            kind: "workspace".to_string(),
            metadata: {
                let mut metadata = Map::new();
                metadata.insert("extension".to_string(), Value::String(".json".to_string()));
                metadata
            },
        };

        let pending = build_pending_chunks_for_document(&doc);

        assert!(!pending.is_empty());
        assert!(pending.iter().any(|chunk| chunk.record_path == "summary"));
        assert!(
            pending
                .iter()
                .any(|chunk| chunk.record_path.starts_with("text"))
        );
        assert!(
            pending
                .iter()
                .any(|chunk| chunk.record_path.contains("response.pages"))
        );
        assert!(
            pending
                .iter()
                .all(|chunk| chunk.text.chars().count() <= STRUCTURED_RECORD_MAX_CHARS)
        );
    }

    #[test]
    fn test_build_pending_chunks_recursively_splits_large_json_field() {
        let doc = SourceDocument {
            source_id: "records.json".to_string(),
            path: "records.json".to_string(),
            title: "records.json".to_string(),
            text: json!({
                "items": [
                    {
                        "id": "42",
                        "note": "Alpha ".repeat(1500),
                        "status": "open"
                    }
                ]
            })
            .to_string(),
            fingerprint: "json-doc".to_string(),
            kind: "workspace".to_string(),
            metadata: {
                let mut metadata = Map::new();
                metadata.insert("extension".to_string(), Value::String(".json".to_string()));
                metadata
            },
        };

        let pending = build_pending_chunks_for_document(&doc);

        assert!(
            pending
                .iter()
                .any(|chunk| chunk.record_path.contains("items[0].note"))
        );
        assert!(
            pending
                .iter()
                .all(|chunk| chunk.text.chars().count() <= STRUCTURED_RECORD_MAX_CHARS)
        );
    }

    #[test]
    fn test_build_pending_chunks_recursively_splits_large_csv_field() {
        let doc = SourceDocument {
            source_id: "records.csv".to_string(),
            path: "records.csv".to_string(),
            title: "records.csv".to_string(),
            text: format!("id,notes,status\n1,{},open\n", "value ".repeat(1500)),
            fingerprint: "csv-doc".to_string(),
            kind: "workspace".to_string(),
            metadata: {
                let mut metadata = Map::new();
                metadata.insert("extension".to_string(), Value::String(".csv".to_string()));
                metadata
            },
        };

        let pending = build_pending_chunks_for_document(&doc);

        assert!(
            pending
                .iter()
                .any(|chunk| chunk.record_path.ends_with(".notes"))
        );
        assert!(
            pending
                .iter()
                .all(|chunk| chunk.text.chars().count() <= STRUCTURED_RECORD_MAX_CHARS)
        );
    }

    #[test]
    fn test_query_windows_and_mean_pool() {
        let windows = split_query_windows("0123456789abcdef", 12);
        assert_eq!(windows.len(), 2);
        let pooled = mean_pool_vectors(&[vec![1.0, 0.0], vec![0.0, 1.0]]);
        assert!((pooled[0] - std::f64::consts::FRAC_1_SQRT_2).abs() < 1e-6);
        assert!((pooled[1] - std::f64::consts::FRAC_1_SQRT_2).abs() < 1e-6);
    }

    #[test]
    fn test_build_query_uses_question_claim_and_entity_focus() {
        let packet = json!({
            "focus_question_ids": ["q_1"],
            "unresolved_questions": [
                {
                    "id": "q_1",
                    "question": "Who controls the shell company?",
                    "claim_ids": ["cl_1"],
                    "evidence_ids": ["ev_1"],
                }
            ],
            "findings": {
                "unresolved": [{"id": "cl_1", "claim": "Control remains unclear"}],
                "contested": [],
            },
            "candidate_actions": [
                {
                    "required_inputs": {
                        "claim_ids": ["cl_1"],
                        "entity_ids": ["ent_1"],
                        "evidence_ids": ["ev_1"],
                    },
                    "ontology_object_refs": [
                        {"object_id": "ent_1", "object_type": "entity", "label": "Acme Holdings"}
                    ]
                }
            ]
        });

        let query = build_query("Investigate beneficial ownership", Some(&packet));

        assert!(query.text.contains("Investigate beneficial ownership"));
        assert!(query.text.contains("Who controls the shell company?"));
        assert!(query.text.contains("Acme Holdings"));
        assert_eq!(query.focus_question_ids, vec!["q_1"]);
        assert_eq!(query.focus_claim_ids, vec!["cl_1"]);
        assert_eq!(query.focus_entity_ids, vec!["ent_1"]);
        assert!(query.boost_object_ids.contains(&"ev_1".to_string()));
    }

    #[test]
    fn test_collect_ontology_documents_includes_workspace_scope_and_extra_types() {
        let tmp = tempdir().unwrap();
        let workspace = tmp.path();
        let session_dir = workspace.join(".openplanter/sessions/session-1");
        fs::create_dir_all(&session_dir).unwrap();
        fs::create_dir_all(workspace.join(".openplanter")).unwrap();

        fs::write(
            session_dir.join("investigation_state.json"),
            r#"{
                "entities": {
                    "ent_session": {
                        "id": "ent_session",
                        "canonical_name": "Session Entity"
                    }
                }
            }"#,
        )
        .unwrap();

        fs::write(
            workspace.join(".openplanter/ontology.json"),
            r#"{
                "source_sessions": ["session-1", "session-2"],
                "entities": {
                    "ent_workspace": {
                        "id": "ent_workspace",
                        "canonical_name": "Workspace Entity"
                    }
                },
                "hypotheses": {
                    "hyp_1": {
                        "id": "hyp_1",
                        "summary": "Hypothesis summary",
                        "source_sessions": ["session-2"]
                    }
                },
                "provenance_nodes": {
                    "prov_1": {
                        "id": "prov_1",
                        "summary": "Captured from archive"
                    }
                }
            }"#,
        )
        .unwrap();

        let docs = collect_ontology_documents(workspace, Some(&session_dir));
        let workspace_entity = docs
            .iter()
            .find(|doc| ontology_object_id(doc) == Some("ent_workspace"))
            .expect("workspace ontology entity");
        assert_eq!(
            workspace_entity
                .metadata
                .get("scope")
                .and_then(Value::as_str),
            Some("workspace")
        );
        assert_eq!(
            value_string_list(workspace_entity.metadata.get("source_sessions")),
            vec!["session-1".to_string(), "session-2".to_string()]
        );
        assert!(docs.iter().any(|doc| doc.kind == "ontology_hypothesis"));
        assert!(docs.iter().any(|doc| doc.kind == "ontology_provenance"));
    }

    #[test]
    fn test_collect_ontology_documents_prefers_session_copy_over_workspace() {
        let tmp = tempdir().unwrap();
        let workspace = tmp.path();
        let session_dir = workspace.join(".openplanter/sessions/session-1");
        fs::create_dir_all(&session_dir).unwrap();
        fs::create_dir_all(workspace.join(".openplanter")).unwrap();

        fs::write(
            session_dir.join("investigation_state.json"),
            r#"{
                "entities": {
                    "ent_shared": {
                        "id": "ent_shared",
                        "canonical_name": "Session Copy"
                    }
                }
            }"#,
        )
        .unwrap();
        fs::write(
            workspace.join(".openplanter/ontology.json"),
            r#"{
                "entities": {
                    "ent_shared": {
                        "id": "ent_shared",
                        "canonical_name": "Workspace Copy"
                    }
                }
            }"#,
        )
        .unwrap();

        let docs = collect_ontology_documents(workspace, Some(&session_dir));
        let shared = docs
            .iter()
            .filter(|doc| ontology_object_id(doc) == Some("ent_shared"))
            .collect::<Vec<_>>();
        assert_eq!(shared.len(), 1);
        assert_eq!(
            shared[0].metadata.get("scope").and_then(Value::as_str),
            Some("session")
        );
        assert!(shared[0].text.contains("Session Copy"));
    }

    #[derive(Clone)]
    enum FakeResponse {
        Success,
        Error(EmbeddingsRequestError),
    }

    struct FakeBackend {
        limits: EmbeddingsProviderLimits,
        responses: Arc<Mutex<VecDeque<FakeResponse>>>,
        calls: Arc<Mutex<Vec<(String, Vec<String>)>>>,
    }

    impl FakeBackend {
        fn new(limits: EmbeddingsProviderLimits, responses: Vec<FakeResponse>) -> Self {
            Self {
                limits,
                responses: Arc::new(Mutex::new(responses.into())),
                calls: Arc::new(Mutex::new(Vec::new())),
            }
        }
    }

    #[async_trait]
    impl DocumentEmbeddingsBackend for FakeBackend {
        fn provider(&self) -> &str {
            "mistral"
        }

        fn model(&self) -> &str {
            MISTRAL_EMBEDDING_MODEL
        }

        fn limits(&self) -> EmbeddingsProviderLimits {
            self.limits
        }

        async fn embed(
            &self,
            texts: &[String],
            input_type: &str,
        ) -> Result<Vec<Vec<f64>>, EmbeddingsRequestError> {
            self.calls
                .lock()
                .unwrap()
                .push((input_type.to_string(), texts.to_vec()));
            match self
                .responses
                .lock()
                .unwrap()
                .pop_front()
                .unwrap_or(FakeResponse::Success)
            {
                FakeResponse::Success => Ok(texts.iter().map(|_| vec![1.0, 0.0]).collect()),
                FakeResponse::Error(err) => Err(err),
            }
        }
    }

    fn test_retry_policy(max_retries: usize) -> EmbeddingsRetryPolicy {
        EmbeddingsRetryPolicy {
            max_retries,
            backoff_base_sec: 0.0,
            backoff_max_sec: 0.0,
            retry_after_cap_sec: 10.0,
        }
    }

    fn test_limits(batch_size: usize) -> EmbeddingsProviderLimits {
        EmbeddingsProviderLimits {
            batch_size,
            input_char_limit: 5_000,
            emergency_input_char_limit: 800,
        }
    }

    fn test_doc(name: &str, text: &str) -> SourceDocument {
        SourceDocument {
            source_id: name.to_string(),
            path: name.to_string(),
            title: name.to_string(),
            text: text.to_string(),
            fingerprint: fingerprint_text(text),
            kind: "workspace".to_string(),
            metadata: {
                let mut metadata = Map::new();
                metadata.insert("extension".to_string(), Value::String(".md".to_string()));
                metadata
            },
        }
    }

    fn enabled_status() -> RetrievalStatus {
        RetrievalStatus {
            provider: "mistral".to_string(),
            model: MISTRAL_EMBEDDING_MODEL.to_string(),
            status: "enabled".to_string(),
            detail: "enabled".to_string(),
        }
    }

    #[tokio::test]
    async fn test_embed_texts_with_retry_retries_transient_503_then_succeeds() {
        let backend = FakeBackend::new(
            test_limits(32),
            vec![
                FakeResponse::Error(EmbeddingsRequestError::RetryableTransient {
                    status_code: Some(503),
                    provider_code: None,
                    retry_after_sec: None,
                    detail: "mistral embeddings HTTP 503: upstream overflow".to_string(),
                }),
                FakeResponse::Success,
            ],
        );
        let mut events = Vec::new();

        let vectors = embed_texts_with_retry(
            &backend,
            &[String::from("hello world")],
            "document",
            "workspace",
            test_retry_policy(1),
            None,
            &mut |message: String| events.push(message),
        )
        .await
        .unwrap();

        assert_eq!(vectors.len(), 1);
        assert_eq!(backend.calls.lock().unwrap().len(), 2);
        assert!(
            events
                .iter()
                .any(|line| line.contains("transient embeddings failure"))
        );
    }

    #[tokio::test(start_paused = true)]
    async fn test_embed_texts_with_retry_honors_retry_after_for_429() {
        let backend = FakeBackend::new(
            test_limits(32),
            vec![
                FakeResponse::Error(EmbeddingsRequestError::RetryableTransient {
                    status_code: Some(429),
                    provider_code: Some("rate_limit".to_string()),
                    retry_after_sec: Some(4.0),
                    detail: "mistral embeddings HTTP 429: too many requests".to_string(),
                }),
                FakeResponse::Success,
            ],
        );
        let mut events = Vec::new();
        let retry_policy = EmbeddingsRetryPolicy {
            max_retries: 1,
            backoff_base_sec: 0.0,
            backoff_max_sec: 10.0,
            retry_after_cap_sec: 10.0,
        };

        let vectors = embed_texts_with_retry(
            &backend,
            &[String::from("hello world")],
            "document",
            "workspace",
            retry_policy,
            None,
            &mut |message: String| events.push(message),
        )
        .await
        .unwrap();

        assert_eq!(vectors.len(), 1);
        assert!(events.iter().any(|line| line.contains("in 4.0s")));
    }

    #[tokio::test]
    async fn test_embed_texts_with_retry_does_not_retry_non_retryable_401() {
        let backend = FakeBackend::new(
            test_limits(32),
            vec![FakeResponse::Error(EmbeddingsRequestError::Fatal {
                status_code: Some(401),
                detail: "mistral embeddings HTTP 401: unauthorized".to_string(),
            })],
        );

        let err = embed_texts_with_retry(
            &backend,
            &[String::from("hello world")],
            "document",
            "workspace",
            test_retry_policy(2),
            None,
            &mut |_message: String| {},
        )
        .await
        .unwrap_err();

        assert!(matches!(
            err,
            EmbeddingsRequestError::Fatal {
                status_code: Some(401),
                ..
            }
        ));
        assert_eq!(backend.calls.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn test_refresh_index_retries_after_oversize_error() {
        let tmp = tempdir().unwrap();
        let index_dir = tmp.path().join(".openplanter/embeddings/workspace");
        let doc = test_doc("notes.md", &"Long paragraph ".repeat(300));
        let backend = FakeBackend::new(
            test_limits(32),
            vec![
                FakeResponse::Error(EmbeddingsRequestError::Oversize {
                    input_id: 0,
                    detail: "mistral embeddings HTTP 400: input too large".to_string(),
                }),
                FakeResponse::Success,
            ],
        );
        let mut events = Vec::new();

        let outcome = refresh_index(
            Some(&index_dir),
            &[doc],
            &backend,
            "workspace",
            test_retry_policy(0),
            None,
            &mut |message: String| events.push(message),
        )
        .await
        .unwrap();
        let RefreshIndexOutcome::Complete { chunks } = outcome else {
            panic!("expected complete index outcome");
        };

        assert!(chunks.len() > 1);
        assert!(
            events
                .iter()
                .any(|line| line.contains("retrying batch after provider oversize"))
        );
    }

    #[tokio::test]
    async fn test_build_retrieval_packet_returns_degraded_and_writes_partial_snapshot() {
        let tmp = tempdir().unwrap();
        fs::write(tmp.path().join("a.md"), "alpha document").unwrap();
        fs::write(tmp.path().join("b.md"), "beta document").unwrap();
        let backend = FakeBackend::new(
            test_limits(1),
            vec![
                FakeResponse::Success,
                FakeResponse::Error(EmbeddingsRequestError::RetryableTransient {
                    status_code: Some(503),
                    provider_code: None,
                    retry_after_sec: None,
                    detail: "mistral embeddings HTTP 503: upstream overflow".to_string(),
                }),
            ],
        );
        let mut events = Vec::new();

        let result = build_retrieval_packet_with_backend(
            tmp.path(),
            None,
            ".openplanter",
            "alpha",
            None,
            &backend,
            &enabled_status(),
            test_retry_policy(0),
            None,
            &mut |message: String| events.push(message),
        )
        .await
        .unwrap();

        let packet = result.packet.expect("hybrid retrieval packet");
        assert_eq!(result.status.status, "degraded");
        assert!(
            result
                .status
                .detail
                .contains("workspace indexing failed after retries")
        );
        assert!(
            events
                .iter()
                .any(|line| line.contains("\"phase\":\"failed\""))
        );
        assert_eq!(
            packet["version"],
            Value::String(RETRIEVAL_PACKET_VERSION.to_string())
        );
        assert_eq!(packet["status"], Value::String("degraded".to_string()));
        assert_eq!(packet["coverage"]["documents_indexed"], Value::from(2));

        let meta = fs::read_to_string(
            tmp.path()
                .join(".openplanter/embeddings/workspace/meta.json"),
        )
        .unwrap();
        let chunks = fs::read_to_string(
            tmp.path()
                .join(".openplanter/embeddings/workspace/chunks.jsonl"),
        )
        .unwrap();
        assert!(meta.contains("\"completion\": \"partial\""));
        assert_eq!(chunks.lines().count(), 1);
    }

    #[tokio::test]
    async fn test_refresh_index_reuses_partial_snapshot_and_completes_follow_up_run() {
        let tmp = tempdir().unwrap();
        let index_dir = tmp.path().join(".openplanter/embeddings/workspace");
        let docs = vec![
            test_doc("a.md", "alpha document"),
            test_doc("b.md", "beta document"),
        ];

        let first_backend = FakeBackend::new(
            test_limits(1),
            vec![
                FakeResponse::Success,
                FakeResponse::Error(EmbeddingsRequestError::RetryableTransient {
                    status_code: Some(503),
                    provider_code: None,
                    retry_after_sec: None,
                    detail: "mistral embeddings HTTP 503: upstream overflow".to_string(),
                }),
            ],
        );
        let first = refresh_index(
            Some(&index_dir),
            &docs,
            &first_backend,
            "workspace",
            test_retry_policy(0),
            None,
            &mut |_message: String| {},
        )
        .await
        .unwrap();
        assert!(matches!(first, RefreshIndexOutcome::PartialCached { .. }));

        let second_backend = FakeBackend::new(test_limits(1), vec![FakeResponse::Success]);
        let second = refresh_index(
            Some(&index_dir),
            &docs,
            &second_backend,
            "workspace",
            test_retry_policy(0),
            None,
            &mut |_message: String| {},
        )
        .await
        .unwrap();
        let RefreshIndexOutcome::Complete { chunks } = second else {
            panic!("expected complete index outcome");
        };

        assert_eq!(chunks.len(), 2);
        assert_eq!(second_backend.calls.lock().unwrap().len(), 1);
        let meta = fs::read_to_string(index_dir.join("meta.json")).unwrap();
        assert!(meta.contains("\"completion\": \"complete\""));
    }

    #[tokio::test]
    async fn test_build_retrieval_packet_degrades_when_query_embedding_fails() {
        let tmp = tempdir().unwrap();
        fs::write(tmp.path().join("notes.md"), "alpha retrieval note").unwrap();
        let backend = FakeBackend::new(
            test_limits(32),
            vec![
                FakeResponse::Success,
                FakeResponse::Error(EmbeddingsRequestError::RetryableTransient {
                    status_code: Some(503),
                    provider_code: None,
                    retry_after_sec: None,
                    detail: "mistral embeddings HTTP 503: upstream overflow".to_string(),
                }),
            ],
        );

        let result = build_retrieval_packet_with_backend(
            tmp.path(),
            None,
            ".openplanter",
            "alpha",
            None,
            &backend,
            &enabled_status(),
            test_retry_policy(0),
            None,
            &mut |_message: String| {},
        )
        .await
        .unwrap();

        assert!(result.packet.is_none());
        assert_eq!(result.status.status, "degraded");
        assert!(result.status.detail.contains("query embedding failed"));
    }
}

fn tail_chars(text: &str, count: usize) -> String {
    let total = text.chars().count();
    if total <= count {
        return text.to_string();
    }
    text.chars().skip(total - count).collect()
}

fn clamp_boundary(text: &str, mut index: usize) -> usize {
    while index > 0 && !text.is_char_boundary(index) {
        index -= 1;
    }
    index
}
