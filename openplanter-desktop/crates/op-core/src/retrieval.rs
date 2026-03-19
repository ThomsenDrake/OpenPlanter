use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::Path;

use anyhow::{Context, anyhow};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use walkdir::WalkDir;

use crate::config::normalize_embeddings_provider;

pub const VOYAGE_EMBEDDING_MODEL: &str = "voyage-4";
pub const MISTRAL_EMBEDDING_MODEL: &str = "mistral-embed";

const INDEX_VERSION: &str = "embeddings-v1";
const CHUNK_TARGET_CHARS: usize = 1200;
const CHUNK_OVERLAP_CHARS: usize = 200;
const MAX_EXCERPT_CHARS: usize = 280;
const WORKSPACE_TOP_K: usize = 4;
const SESSION_TOP_K: usize = 4;
const MAX_HITS_PER_SOURCE: usize = 2;
const BATCH_SIZE: usize = 32;

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
            "metadata": self.metadata,
        })
    }
}

struct EmbeddingsClient {
    provider: String,
    model: String,
    api_key: String,
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
            http: Client::new(),
        }
    }

    async fn embed_documents(&self, texts: &[String]) -> anyhow::Result<Vec<Vec<f64>>> {
        self.embed(texts, "document").await
    }

    async fn embed_query(&self, text: &str) -> anyhow::Result<Vec<f64>> {
        let vectors = self.embed(&[text.to_string()], "query").await?;
        vectors
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("embeddings provider returned no query vector"))
    }

    async fn embed(&self, texts: &[String], input_type: &str) -> anyhow::Result<Vec<Vec<f64>>> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }
        let mut all = Vec::new();
        for batch in texts.chunks(BATCH_SIZE) {
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
                .with_context(|| format!("{} embeddings request failed", self.provider))?;
            let status = response.status();
            let text = response
                .text()
                .await
                .with_context(|| format!("{} embeddings response read failed", self.provider))?;
            if !status.is_success() {
                return Err(anyhow!(
                    "{} embeddings HTTP {}: {}",
                    self.provider,
                    status,
                    truncate(&text, 500)
                ));
            }
            let parsed: Value = serde_json::from_str(&text).with_context(|| {
                format!("{} embeddings returned non-JSON payload", self.provider)
            })?;
            let Some(data) = parsed.get("data").and_then(Value::as_array) else {
                return Err(anyhow!(
                    "{} embeddings returned unexpected payload shape",
                    self.provider
                ));
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
                return Err(anyhow!(
                    "{} embeddings returned {} vectors for {} inputs",
                    self.provider,
                    ordered.len(),
                    batch.len()
                ));
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
            detail: format!("Retrieval enabled via {normalized} ({model})."),
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
                "Retrieval disabled: {missing} is not configured for {normalized}."
            ),
        }
    }
}

pub async fn build_retrieval_packet(
    workspace: &Path,
    session_dir: Option<&Path>,
    session_root_dir: &str,
    objective: &str,
    question_reasoning_packet: Option<&Value>,
    embeddings_provider: &str,
    voyage_api_key: Option<&str>,
    mistral_api_key: Option<&str>,
) -> anyhow::Result<RetrievalBuildResult> {
    let status = build_embeddings_status(
        embeddings_provider,
        voyage_api_key,
        mistral_api_key,
    );
    if status.status != "enabled" {
        return Ok(RetrievalBuildResult {
            packet: None,
            status,
        });
    }

    let api_key = if status.provider == "voyage" {
        voyage_api_key.unwrap_or_default()
    } else {
        mistral_api_key.unwrap_or_default()
    };
    let client = EmbeddingsClient::new(&status.provider, api_key);
    let workspace_docs = collect_workspace_documents(workspace, session_root_dir);
    let session_docs = collect_session_documents(workspace, session_dir);
    let total_docs = workspace_docs.len() + session_docs.len();
    if total_docs == 0 {
        return Ok(RetrievalBuildResult {
            packet: None,
            status: RetrievalStatus {
                detail: format!(
                    "Retrieval enabled via {} ({}), but no indexable documents were found.",
                    status.provider, status.model
                ),
                ..status
            },
        });
    }

    let workspace_index_dir = workspace
        .join(session_root_dir)
        .join("embeddings")
        .join("workspace");
    let workspace_chunks = refresh_index(
        Some(&workspace_index_dir),
        &workspace_docs,
        &client,
        &status.provider,
        &status.model,
        "workspace",
    )
    .await?;

    let session_chunks = if let Some(session_dir) = session_dir {
        refresh_index(
            Some(&session_dir.join("embeddings")),
            &session_docs,
            &client,
            &status.provider,
            &status.model,
            "session",
        )
        .await?
    } else {
        Vec::new()
    };

    let query = build_query(objective, question_reasoning_packet);
    if query.trim().is_empty() {
        return Ok(RetrievalBuildResult {
            packet: None,
            status: RetrievalStatus {
                detail: format!(
                    "Retrieval enabled via {} ({}), but no query text was available.",
                    status.provider, status.model
                ),
                ..status
            },
        });
    }

    let query_vector = client.embed_query(&query).await?;
    let workspace_hits =
        search_chunks(&workspace_chunks, &query_vector, WORKSPACE_TOP_K, MAX_HITS_PER_SOURCE);
    let session_hits =
        search_chunks(&session_chunks, &query_vector, SESSION_TOP_K, MAX_HITS_PER_SOURCE);
    let hit_count = workspace_hits.len() + session_hits.len();
    if hit_count == 0 {
        return Ok(RetrievalBuildResult {
            packet: None,
            status: RetrievalStatus {
                detail: format!(
                    "Retrieval enabled via {} ({}); indexed {} document(s), but found no strong semantic matches.",
                    status.provider, status.model, total_docs
                ),
                ..status
            },
        });
    }

    Ok(RetrievalBuildResult {
        packet: Some(json!({
            "provider": status.provider,
            "model": status.model,
            "query": query,
            "workspace_hits": workspace_hits,
            "session_hits": session_hits,
        })),
        status: RetrievalStatus {
            detail: format!(
                "Retrieval enabled via {} ({}); indexed {} document(s) and selected {} semantic match(es).",
                status.provider, status.model, total_docs, hit_count
            ),
            ..status
        },
    })
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
    metadata.insert("extension".to_string(), Value::String(format!(".{extension}")));
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
            metadata.insert("record_type".to_string(), Value::String("evidence".to_string()));
            metadata.insert(
                "evidence_id".to_string(),
                Value::String(evidence_id.to_string()),
            );
            metadata.insert(
                "evidence_type".to_string(),
                Value::String(string_field(record_obj, "evidence_type")),
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

async fn refresh_index(
    index_dir: Option<&Path>,
    documents: &[SourceDocument],
    client: &EmbeddingsClient,
    provider: &str,
    model: &str,
    corpus: &str,
) -> anyhow::Result<Vec<ChunkRecord>> {
    let Some(index_dir) = index_dir else {
        return Ok(Vec::new());
    };
    fs::create_dir_all(index_dir).with_context(|| {
        format!("failed to create embeddings index directory {}", index_dir.display())
    })?;
    let meta_path = index_dir.join("meta.json");
    let chunks_path = index_dir.join("chunks.jsonl");
    let existing = if load_meta(&meta_path, provider, model, corpus) {
        load_existing_chunks(&chunks_path)
    } else {
        HashMap::new()
    };

    let mut resolved = Vec::new();
    let mut pending_records = Vec::new();
    let mut pending_texts = Vec::new();
    for doc in documents {
        if let Some(prior) = existing.get(&doc.source_id) {
            if prior.iter().all(|chunk| chunk.fingerprint == doc.fingerprint) {
                resolved.extend(prior.clone());
                continue;
            }
        }
        for (chunk_index, text) in chunk_document(doc).into_iter().enumerate() {
            let mut metadata = doc.metadata.clone();
            metadata.insert(
                "chunk_index".to_string(),
                Value::Number((chunk_index as u64).into()),
            );
            pending_records.push(ChunkRecord {
                chunk_id: format!("{}::chunk:{chunk_index}", doc.source_id),
                source_id: doc.source_id.clone(),
                path: doc.path.clone(),
                title: doc.title.clone(),
                text: text.clone(),
                excerpt: make_excerpt(&text),
                fingerprint: doc.fingerprint.clone(),
                kind: doc.kind.clone(),
                metadata,
                vector: Vec::new(),
            });
            pending_texts.push(text);
        }
    }

    if !pending_records.is_empty() {
        let vectors = client.embed_documents(&pending_texts).await?;
        for (record, vector) in pending_records.iter_mut().zip(vectors.into_iter()) {
            record.vector = vector;
        }
        resolved.extend(pending_records);
    }

    resolved.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then_with(|| left.chunk_id.cmp(&right.chunk_id))
    });

    fs::write(
        &meta_path,
        serde_json::to_string_pretty(&json!({
            "version": INDEX_VERSION,
            "provider": provider,
            "model": model,
            "corpus": corpus,
            "chunk_target_chars": CHUNK_TARGET_CHARS,
            "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        }))?,
    )
    .with_context(|| format!("failed to write {}", meta_path.display()))?;

    let serialized = resolved
        .iter()
        .map(|chunk| serde_json::to_string(chunk))
        .collect::<Result<Vec<_>, _>>()?
        .join("\n");
    fs::write(&chunks_path, serialized)
        .with_context(|| format!("failed to write {}", chunks_path.display()))?;
    Ok(resolved)
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
        grouped.entry(chunk.source_id.clone()).or_default().push(chunk);
    }
    grouped
}

fn search_chunks(
    chunks: &[ChunkRecord],
    query_vector: &[f64],
    top_k: usize,
    per_source_cap: usize,
) -> Vec<Value> {
    let mut scored: Vec<(f64, &ChunkRecord)> = chunks
        .iter()
        .filter(|chunk| !chunk.vector.is_empty())
        .map(|chunk| (dot(query_vector, &chunk.vector), chunk))
        .collect();
    scored.sort_by(|left, right| right.0.total_cmp(&left.0));

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

fn build_query(objective: &str, question_reasoning_packet: Option<&Value>) -> String {
    let mut parts = vec![objective.trim().to_string()];
    let Some(packet) = question_reasoning_packet.and_then(Value::as_object) else {
        return parts.into_iter().filter(|part| !part.is_empty()).collect::<Vec<_>>().join("\n\n");
    };
    if let Some(questions) = packet.get("unresolved_questions").and_then(Value::as_array) {
        for question in questions.iter().take(4) {
            if let Some(text) = question.get("text").and_then(Value::as_str) {
                if !text.trim().is_empty() {
                    parts.push(text.trim().to_string());
                }
            }
        }
    }
    if let Some(findings) = packet.get("findings").and_then(Value::as_object) {
        for bucket in ["unresolved", "contested"] {
            if let Some(items) = findings.get(bucket).and_then(Value::as_array) {
                for item in items.iter().take(2) {
                    if let Some(summary) = item
                        .get("summary")
                        .and_then(Value::as_str)
                        .or_else(|| item.get("claim_text").and_then(Value::as_str))
                    {
                        if !summary.trim().is_empty() {
                            parts.push(summary.trim().to_string());
                        }
                    }
                }
            }
        }
    }
    parts
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn chunk_document(doc: &SourceDocument) -> Vec<String> {
    let suffix = doc
        .path
        .split('#')
        .next()
        .and_then(|value| Path::new(value).extension())
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    match doc.kind.as_str() {
        "evidence" | "session_memory" => chunk_atomic_text(&doc.text),
        _ if suffix == "json" => chunk_json(&doc.text),
        _ if suffix == "csv" => chunk_delimited(&doc.text, ','),
        _ if suffix == "tsv" => chunk_delimited(&doc.text, '\t'),
        _ => chunk_paragraph_text(&doc.text),
    }
}

fn chunk_atomic_text(text: &str) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    if trimmed.len() <= CHUNK_TARGET_CHARS {
        return vec![trimmed.to_string()];
    }
    sliding_windows(trimmed)
}

fn chunk_json(text: &str) -> Vec<String> {
    let Ok(parsed) = serde_json::from_str::<Value>(text) else {
        return chunk_paragraph_text(text);
    };
    let mut records = Vec::new();
    match parsed {
        Value::Array(items) => {
            for item in items {
                records.push(
                    serde_json::to_string_pretty(&item).unwrap_or_else(|_| item.to_string())
                );
            }
        }
        Value::Object(map) => {
            for (key, value) in map {
                records.push(
                    serde_json::to_string_pretty(&json!({ key: value }))
                        .unwrap_or_else(|_| value.to_string())
                );
            }
        }
        other => records.push(
            serde_json::to_string_pretty(&other).unwrap_or_else(|_| other.to_string())
        ),
    }
    group_records(&records)
}

fn chunk_delimited(text: &str, delimiter: char) -> Vec<String> {
    let mut lines = text.lines();
    let Some(header_line) = lines.next() else {
        return Vec::new();
    };
    let headers: Vec<&str> = header_line.split(delimiter).collect();
    if headers.is_empty() {
        return chunk_paragraph_text(text);
    }
    let mut records = vec![header_line.to_string()];
    for line in lines {
        if line.trim().is_empty() {
            continue;
        }
        let values: Vec<&str> = line.split(delimiter).collect();
        let mut record = Map::new();
        for (idx, header) in headers.iter().enumerate() {
            record.insert(
                header.trim().to_string(),
                Value::String(values.get(idx).copied().unwrap_or_default().trim().to_string()),
            );
        }
        records.push(Value::Object(record).to_string());
    }
    group_records(&records)
}

fn group_records(records: &[String]) -> Vec<String> {
    let mut chunks = Vec::new();
    let mut current = String::new();
    for record in records {
        let value = record.trim();
        if value.is_empty() {
            continue;
        }
        let candidate = if current.is_empty() {
            value.to_string()
        } else {
            format!("{current}\n{value}")
        };
        if !current.is_empty() && candidate.len() > CHUNK_TARGET_CHARS {
            chunks.push(current.clone());
            let overlap = tail_chars(&current, CHUNK_OVERLAP_CHARS);
            current = if overlap.is_empty() {
                value.to_string()
            } else {
                format!("{overlap}\n{value}")
            };
        } else {
            current = candidate;
        }
    }
    if !current.is_empty() {
        chunks.push(current);
    }
    chunks
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
        if chunk.len() <= (CHUNK_TARGET_CHARS + CHUNK_OVERLAP_CHARS) {
            expanded.push(chunk);
        } else {
            expanded.extend(sliding_windows(&chunk));
        }
    }
    expanded
}

fn sliding_windows(text: &str) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    let step = CHUNK_TARGET_CHARS.saturating_sub(CHUNK_OVERLAP_CHARS).max(1);
    let mut windows = Vec::new();
    let mut start = 0usize;
    while start < trimmed.len() {
        let end = clamp_boundary(trimmed, (start + CHUNK_TARGET_CHARS).min(trimmed.len()));
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
    paragraphs.into_iter().filter(|value| !value.is_empty()).collect()
}

fn should_skip_walk_entry(path: &Path, workspace: &Path, session_root_dir: &str) -> bool {
    if path == workspace {
        return false;
    }
    let Ok(rel) = path.strip_prefix(workspace) else {
        return false;
    };
    let parts = rel.iter().filter_map(|part| part.to_str()).collect::<Vec<_>>();
    if parts.iter().any(|part| EXCLUDED_DIR_NAMES.contains(part)) {
        return true;
    }
    if parts.first().copied() == Some(session_root_dir) {
        return !(parts.get(1).copied() == Some("wiki"));
    }
    false
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
    text.chars().take(max_chars.saturating_sub(3)).collect::<String>() + "..."
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
