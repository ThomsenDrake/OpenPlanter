from __future__ import annotations

import bisect
import csv
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .config import normalize_embeddings_provider

VOYAGE_EMBEDDING_MODEL = "voyage-4"
MISTRAL_EMBEDDING_MODEL = "mistral-embed"
_CHUNK_TARGET_CHARS = 1200
_CHUNK_OVERLAP_CHARS = 200
_STRUCTURED_RECORD_MAX_CHARS = _CHUNK_TARGET_CHARS + _CHUNK_OVERLAP_CHARS
_MAX_EXCERPT_CHARS = 280
_INDEX_VERSION = "embeddings-v2"
_WORKSPACE_TOP_K = 4
_SESSION_TOP_K = 4
_MAX_HITS_PER_SOURCE = 2
_BATCH_SIZE = 32
_TEXT_EXTENSIONS = {".md", ".txt", ".json", ".csv", ".tsv", ".yaml", ".yml", ".patch"}
_EXCLUDED_DIR_NAMES = {
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
}
_IGNORED_FILE_NAMES = {".DS_Store", "Thumbs.db"}
_IGNORED_FILE_PREFIXES = ("._",)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_WS_RE = re.compile(r"\s+")
_OVERSIZE_INPUT_ID_RE = re.compile(r"input id\s+(\d+).+exceeding max", re.IGNORECASE)


@dataclass(slots=True)
class EmbeddingsProviderLimits:
    batch_size: int
    input_char_limit: int
    emergency_input_char_limit: int


@dataclass(slots=True)
class RetrievalStatus:
    provider: str
    model: str
    status: str
    detail: str


@dataclass(slots=True)
class RetrievalBuildResult:
    packet: dict[str, Any] | None
    provider: str
    model: str
    status: str
    detail: str


@dataclass(slots=True)
class RetrievalProgress:
    corpus: str
    phase: str
    documents_done: int
    documents_total: int
    chunks_done: int
    chunks_total: int
    reused_documents: int = 0
    message: str = ""

    def percent(self) -> int:
        if self.documents_total <= 0:
            return 0
        return max(
            0,
            min(100, round((self.documents_done / self.documents_total) * 100)),
        )

    def to_trace_message(self) -> str:
        return "[retrieval:progress] " + json.dumps(
            {
                "corpus": self.corpus,
                "phase": self.phase,
                "documents_done": self.documents_done,
                "documents_total": self.documents_total,
                "chunks_done": self.chunks_done,
                "chunks_total": self.chunks_total,
                "reused_documents": self.reused_documents,
                "percent": self.percent(),
                "message": self.message,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )


@dataclass(slots=True)
class SourceDocument:
    source_id: str
    path: str
    title: str
    text: str
    fingerprint: str
    kind: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class SemanticRecord:
    record_path: str
    content_role: str
    text: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class PendingChunk:
    source_id: str
    path: str
    title: str
    text: str
    fingerprint: str
    kind: str
    metadata: dict[str, Any]
    record_path: str
    content_role: str
    vector: list[float]


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    source_id: str
    path: str
    title: str
    text: str
    excerpt: str
    fingerprint: str
    kind: str
    metadata: dict[str, Any]
    record_path: str
    content_role: str
    subchunk_index: int
    vector: list[float]

    def to_json(self, *, provider: str, model: str) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "path": self.path,
            "title": self.title,
            "text": self.text,
            "excerpt": self.excerpt,
            "fingerprint": self.fingerprint,
            "kind": self.kind,
            "metadata": self.metadata,
            "record_path": self.record_path,
            "content_role": self.content_role,
            "subchunk_index": self.subchunk_index,
            "provider": provider,
            "model": model,
            "vector": self.vector,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ChunkRecord" | None:
        try:
            vector = [float(value) for value in payload.get("vector", [])]
        except (TypeError, ValueError):
            return None
        if not vector:
            return None
        return cls(
            chunk_id=str(payload.get("chunk_id") or ""),
            source_id=str(payload.get("source_id") or ""),
            path=str(payload.get("path") or ""),
            title=str(payload.get("title") or ""),
            text=str(payload.get("text") or ""),
            excerpt=str(payload.get("excerpt") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            kind=str(payload.get("kind") or "text"),
            metadata=_as_dict(payload.get("metadata")),
            record_path=str(
                payload.get("record_path")
                or _as_dict(payload.get("metadata")).get("record_path")
                or "body"
            ),
            content_role=str(
                payload.get("content_role")
                or _as_dict(payload.get("metadata")).get("content_role")
                or "body"
            ),
            subchunk_index=int(
                payload.get("subchunk_index")
                or _as_dict(payload.get("metadata")).get("subchunk_index")
                or 0
            ),
            vector=_normalize_vector(vector),
        )


class RetrievalError(RuntimeError):
    pass


def _provider_limits(provider: str) -> EmbeddingsProviderLimits:
    normalized = normalize_embeddings_provider(provider)
    if normalized == "voyage":
        return EmbeddingsProviderLimits(
            batch_size=_BATCH_SIZE,
            input_char_limit=24_000,
            emergency_input_char_limit=6_000,
        )
    return EmbeddingsProviderLimits(
        batch_size=_BATCH_SIZE,
        input_char_limit=12_000,
        emergency_input_char_limit=4_000,
    )


class EmbeddingsClient:
    def __init__(self, provider: str, api_key: str) -> None:
        self.provider = normalize_embeddings_provider(provider)
        self.api_key = api_key.strip()
        self.model = (
            VOYAGE_EMBEDDING_MODEL
            if self.provider == "voyage"
            else MISTRAL_EMBEDDING_MODEL
        )
        self.limits = _provider_limits(self.provider)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, input_type="document")

    def embed_query(self, text: str) -> list[float]:
        query_windows = _split_query_windows(
            text,
            max_chars=self.limits.input_char_limit,
        )
        vectors = self._embed(query_windows, input_type="query")
        if not vectors:
            raise RetrievalError("Embeddings provider returned no query vector")
        if len(vectors) == 1:
            return vectors[0]
        return _mean_pool_vectors(vectors)

    def _endpoint(self) -> str:
        if self.provider == "voyage":
            return "https://api.voyageai.com/v1/embeddings"
        return "https://api.mistral.ai/v1/embeddings"

    def _embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), self.limits.batch_size):
            batch = texts[start : start + self.limits.batch_size]
            payload: dict[str, Any] = {
                "model": self.model,
                "input": batch,
            }
            if self.provider == "voyage":
                payload["input_type"] = input_type
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._endpoint(),
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RetrievalError(
                    f"{self.provider} embeddings HTTP {exc.code}: {body[:500]}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RetrievalError(
                    f"{self.provider} embeddings connection error: {exc}"
                ) from exc
            except OSError as exc:
                raise RetrievalError(
                    f"{self.provider} embeddings network error: {exc}"
                ) from exc

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RetrievalError(
                    f"{self.provider} embeddings returned non-JSON payload: {raw[:500]}"
                ) from exc
            data_items = parsed.get("data")
            if not isinstance(data_items, list):
                raise RetrievalError(
                    f"{self.provider} embeddings returned unexpected payload shape"
                )
            ordered: list[tuple[int, list[float]]] = []
            for idx, item in enumerate(data_items):
                if not isinstance(item, dict):
                    continue
                embedding = item.get("embedding")
                if not isinstance(embedding, list):
                    continue
                try:
                    vector = _normalize_vector([float(value) for value in embedding])
                except (TypeError, ValueError):
                    continue
                ordered.append((int(item.get("index", idx)), vector))
            ordered.sort(key=lambda item: item[0])
            batch_vectors = [vector for _, vector in ordered]
            if len(batch_vectors) != len(batch):
                raise RetrievalError(
                    f"{self.provider} embeddings returned {len(batch_vectors)} vectors for {len(batch)} inputs"
                )
            all_vectors.extend(batch_vectors)
        return all_vectors


def embeddings_model_for_provider(provider: str) -> str:
    return (
        VOYAGE_EMBEDDING_MODEL
        if normalize_embeddings_provider(provider) == "voyage"
        else MISTRAL_EMBEDDING_MODEL
    )


def build_embeddings_status(
    *,
    provider: str,
    voyage_api_key: str | None,
    mistral_api_key: str | None,
) -> RetrievalStatus:
    normalized = normalize_embeddings_provider(provider)
    model = embeddings_model_for_provider(normalized)
    api_key = (
        (voyage_api_key or "").strip()
        if normalized == "voyage"
        else (mistral_api_key or "").strip()
    )
    if api_key:
        return RetrievalStatus(
            provider=normalized,
            model=model,
            status="enabled",
            detail=f"Retrieval enabled via {normalized} ({model}).",
        )
    missing = "VOYAGE_API_KEY" if normalized == "voyage" else "MISTRAL_API_KEY"
    return RetrievalStatus(
        provider=normalized,
        model=model,
        status="disabled",
        detail=f"Retrieval disabled: {missing} is not configured for {normalized}.",
    )


def build_retrieval_packet(
    *,
    workspace: Path,
    session_dir: Path | None,
    session_root_dir: str,
    objective: str,
    question_reasoning_packet: dict[str, Any] | None,
    embeddings_provider: str,
    voyage_api_key: str | None,
    mistral_api_key: str | None,
    on_event: Callable[[str], None] | None = None,
) -> RetrievalBuildResult:
    status = build_embeddings_status(
        provider=embeddings_provider,
        voyage_api_key=voyage_api_key,
        mistral_api_key=mistral_api_key,
    )
    if status.status != "enabled":
        return RetrievalBuildResult(
            packet=None,
            provider=status.provider,
            model=status.model,
            status=status.status,
            detail=status.detail,
        )

    api_key = (voyage_api_key or "").strip() if status.provider == "voyage" else (mistral_api_key or "").strip()
    client = EmbeddingsClient(status.provider, api_key)
    _emit_progress(
        on_event,
        RetrievalProgress(
            corpus="all",
            phase="scan",
            documents_done=0,
            documents_total=0,
            chunks_done=0,
            chunks_total=0,
            message="Scanning workspace and session documents for retrieval.",
        ),
    )
    workspace_docs = _collect_workspace_documents(
        workspace=workspace,
        session_root_dir=session_root_dir,
    )
    session_docs = _collect_session_documents(
        workspace=workspace,
        session_dir=session_dir,
    )
    total_docs = len(workspace_docs) + len(session_docs)
    if total_docs == 0:
        return RetrievalBuildResult(
            packet=None,
            provider=status.provider,
            model=status.model,
            status=status.status,
            detail=f"Retrieval enabled via {status.provider} ({status.model}), but no indexable documents were found.",
        )

    if on_event:
        try:
            on_event(
                f"[retrieval] refreshing {total_docs} indexable document(s) with provider={status.provider}"
            )
        except Exception:
            pass

    workspace_index_dir = (
        workspace / session_root_dir / "embeddings" / "workspace"
    )
    session_index_dir = (
        session_dir / "embeddings" if session_dir is not None else None
    )
    workspace_chunks = _refresh_index(
        index_dir=workspace_index_dir,
        documents=workspace_docs,
        client=client,
        provider=status.provider,
        model=status.model,
        corpus="workspace",
        on_event=on_event,
    )
    session_chunks = _refresh_index(
        index_dir=session_index_dir,
        documents=session_docs,
        client=client,
        provider=status.provider,
        model=status.model,
        corpus="session",
        on_event=on_event,
    )

    query = _build_query(objective, question_reasoning_packet)
    if not query.strip():
        return RetrievalBuildResult(
            packet=None,
            provider=status.provider,
            model=status.model,
            status=status.status,
            detail=f"Retrieval enabled via {status.provider} ({status.model}), but no query text was available.",
        )
    query_vector = client.embed_query(query)
    workspace_hits = _search_chunks(
        workspace_chunks,
        query_vector,
        top_k=_WORKSPACE_TOP_K,
        per_source_cap=_MAX_HITS_PER_SOURCE,
    )
    session_hits = _search_chunks(
        session_chunks,
        query_vector,
        top_k=_SESSION_TOP_K,
        per_source_cap=_MAX_HITS_PER_SOURCE,
    )
    hit_count = len(workspace_hits) + len(session_hits)
    if hit_count == 0:
        return RetrievalBuildResult(
            packet=None,
            provider=status.provider,
            model=status.model,
            status=status.status,
            detail=(
                f"Retrieval enabled via {status.provider} ({status.model}); "
                f"indexed {total_docs} document(s), but found no strong semantic matches."
            ),
        )

    packet = {
        "provider": status.provider,
        "model": status.model,
        "query": query,
        "workspace_hits": workspace_hits,
        "session_hits": session_hits,
    }
    return RetrievalBuildResult(
        packet=packet,
        provider=status.provider,
        model=status.model,
        status=status.status,
        detail=(
            f"Retrieval enabled via {status.provider} ({status.model}); "
            f"indexed {total_docs} document(s) and selected {hit_count} semantic match(es)."
        ),
    )


def _collect_workspace_documents(
    *,
    workspace: Path,
    session_root_dir: str,
) -> list[SourceDocument]:
    docs: list[SourceDocument] = []
    runtime_wiki = workspace / session_root_dir / "wiki"
    if runtime_wiki.exists():
        docs.extend(
            _documents_from_paths(
                runtime_wiki.rglob("*"),
                workspace=workspace,
                kind="wiki",
            )
        )

    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        if runtime_wiki.exists() and _is_subpath(path, runtime_wiki):
            continue
        if _skip_workspace_path(path, workspace=workspace, session_root_dir=session_root_dir):
            continue
        docs.extend(_documents_from_file(path, workspace=workspace, kind="workspace"))
    return docs


def _collect_session_documents(
    *,
    workspace: Path,
    session_dir: Path | None,
) -> list[SourceDocument]:
    if session_dir is None:
        return []
    docs: list[SourceDocument] = []
    investigation_path = session_dir / "investigation_state.json"
    if investigation_path.exists():
        docs.extend(
            _documents_from_investigation_state(
                investigation_path,
                workspace=workspace,
            )
        )

    artifacts_dir = session_dir / "artifacts"
    if artifacts_dir.exists():
        docs.extend(
            _documents_from_paths(
                artifacts_dir.rglob("*"),
                workspace=workspace,
                kind="artifact",
            )
        )
    return docs


def _documents_from_paths(
    paths: Iterable[Path],
    *,
    workspace: Path,
    kind: str,
) -> list[SourceDocument]:
    docs: list[SourceDocument] = []
    for path in paths:
        if not path.is_file():
            continue
        docs.extend(_documents_from_file(path, workspace=workspace, kind=kind))
    return docs


def _documents_from_file(path: Path, *, workspace: Path, kind: str) -> list[SourceDocument]:
    if _is_junk_path(path):
        return []
    if path.suffix.lower() not in _TEXT_EXTENSIONS:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not text.strip():
        return []
    rel_path = _rel_path(path, workspace)
    title = path.name
    fingerprint = _fingerprint_text(text)
    return [
        SourceDocument(
            source_id=rel_path,
            path=rel_path,
            title=title,
            text=text,
            fingerprint=fingerprint,
            kind=kind,
            metadata={"extension": path.suffix.lower()},
        )
    ]


def _documents_from_investigation_state(
    path: Path,
    *,
    workspace: Path,
) -> list[SourceDocument]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(state, dict):
        return []

    docs: list[SourceDocument] = []
    rel_path = _rel_path(path, workspace)
    legacy = state.get("legacy") if isinstance(state.get("legacy"), dict) else {}
    observations = legacy.get("external_observations")
    if isinstance(observations, list):
        for index, value in enumerate(observations):
            text = str(value).strip()
            if not text:
                continue
            source_id = f"{rel_path}#legacy:{index}"
            docs.append(
                SourceDocument(
                    source_id=source_id,
                    path=source_id,
                    title=f"legacy observation {index + 1}",
                    text=text,
                    fingerprint=_fingerprint_text(text),
                    kind="session_memory",
                    metadata={"record_type": "legacy_observation"},
                )
            )

    evidence = state.get("evidence")
    if isinstance(evidence, dict):
        for evidence_id, record in evidence.items():
            if not isinstance(record, dict):
                continue
            body = _join_nonempty(
                [
                    str(record.get("title") or "").strip(),
                    str(record.get("summary") or "").strip(),
                    str(record.get("content") or "").strip(),
                    str(record.get("source_uri") or "").strip(),
                ]
            )
            if not body:
                continue
            source_id = f"{rel_path}#evidence:{evidence_id}"
            docs.append(
                SourceDocument(
                    source_id=source_id,
                    path=source_id,
                    title=str(record.get("title") or evidence_id),
                    text=body,
                    fingerprint=_fingerprint_text(body),
                    kind="evidence",
                    metadata={
                        "record_type": "evidence",
                        "evidence_id": str(evidence_id),
                        "evidence_type": str(record.get("evidence_type") or ""),
                    },
                )
            )
    return docs


def _refresh_index(
    *,
    index_dir: Path | None,
    documents: list[SourceDocument],
    client: EmbeddingsClient,
    provider: str,
    model: str,
    corpus: str,
    on_event: Callable[[str], None] | None = None,
) -> list[ChunkRecord]:
    if index_dir is None:
        return []
    index_dir.mkdir(parents=True, exist_ok=True)
    meta_path = index_dir / "meta.json"
    chunks_path = index_dir / "chunks.jsonl"
    existing_chunks: dict[str, list[ChunkRecord]] = {}
    if _load_meta(meta_path, provider=provider, model=model, corpus=corpus):
        existing_chunks = _load_existing_chunks(chunks_path)

    resolved_chunks: list[ChunkRecord] = []
    pending_records: list[PendingChunk] = []
    reused_documents = 0
    reused_chunks = 0
    for doc in documents:
        prior = existing_chunks.get(doc.source_id, [])
        if prior and all(chunk.fingerprint == doc.fingerprint for chunk in prior):
            reused_documents += 1
            reused_chunks += len(prior)
            resolved_chunks.extend(prior)
            continue
        pending_records.extend(_build_pending_chunks_for_document(doc))

    pending_records = _preflight_pending_chunks(
        pending_records,
        max_chars=client.limits.input_char_limit,
        on_event=on_event,
        reason="preflight",
    )

    total_documents = len(documents)
    total_chunks = reused_chunks + len(pending_records)
    if not pending_records:
        _emit_progress(
            on_event,
            RetrievalProgress(
                corpus=corpus,
                phase="writing",
                documents_done=total_documents,
                documents_total=total_documents,
                chunks_done=total_chunks,
                chunks_total=total_chunks,
                reused_documents=reused_documents,
                message=f"Writing cached {corpus} retrieval index.",
            ),
        )
    else:
        _emit_progress(
            on_event,
            RetrievalProgress(
                corpus=corpus,
                phase="embedding",
                documents_done=reused_documents,
                documents_total=total_documents,
                chunks_done=reused_chunks,
                chunks_total=total_chunks,
                reused_documents=reused_documents,
                message=f"Embedding {corpus} retrieval index.",
            ),
        )
        batch_start = 0
        while batch_start < len(pending_records):
            chunk_boundaries = _pending_chunk_boundaries(pending_records)
            total_chunks = reused_chunks + len(pending_records)
            batch_records = pending_records[batch_start : batch_start + client.limits.batch_size]
            prepared = _preflight_pending_chunks(
                batch_records,
                max_chars=client.limits.input_char_limit,
                on_event=on_event,
                reason="batch",
            )
            if len(prepared) != len(batch_records):
                pending_records[batch_start : batch_start + len(batch_records)] = prepared
                continue
            try:
                batch_vectors = client.embed_documents([record.text for record in batch_records])
            except RetrievalError as exc:
                if _retry_oversized_batch(
                    pending_records,
                    batch_start=batch_start,
                    error=exc,
                    client=client,
                    on_event=on_event,
                ):
                    continue
                raise
            for record, vector in zip(batch_records, batch_vectors, strict=True):
                record.vector = vector
            batch_start += len(batch_records)
            completed_pending_docs = bisect.bisect_right(
                chunk_boundaries,
                batch_start,
            )
            _emit_progress(
                on_event,
                RetrievalProgress(
                    corpus=corpus,
                    phase="embedding",
                    documents_done=reused_documents + completed_pending_docs,
                    documents_total=total_documents,
                    chunks_done=reused_chunks + batch_start,
                    chunks_total=total_chunks,
                    reused_documents=reused_documents,
                    message=f"Embedding {corpus} retrieval index.",
                ),
            )
        resolved_chunks.extend(_finalize_pending_chunks(pending_records))

    resolved_chunks.sort(key=lambda chunk: (chunk.path, chunk.chunk_id))
    _emit_progress(
        on_event,
        RetrievalProgress(
            corpus=corpus,
            phase="writing",
            documents_done=total_documents,
            documents_total=total_documents,
            chunks_done=total_chunks,
            chunks_total=total_chunks,
            reused_documents=reused_documents,
            message=f"Writing {corpus} retrieval index files.",
        ),
    )
    meta_path.write_text(
        json.dumps(
            {
                "version": _INDEX_VERSION,
                "provider": provider,
                "model": model,
                "corpus": corpus,
                "chunk_target_chars": _CHUNK_TARGET_CHARS,
                "chunk_overlap_chars": _CHUNK_OVERLAP_CHARS,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    chunks_path.write_text(
        "\n".join(
            json.dumps(
                chunk.to_json(provider=provider, model=model),
                ensure_ascii=False,
            )
            for chunk in resolved_chunks
        ),
        encoding="utf-8",
    )
    _emit_progress(
        on_event,
        RetrievalProgress(
            corpus=corpus,
            phase="done",
            documents_done=total_documents,
            documents_total=total_documents,
            chunks_done=total_chunks,
            chunks_total=total_chunks,
            reused_documents=reused_documents,
            message=f"{corpus.capitalize()} retrieval index ready.",
        ),
    )
    return resolved_chunks


def _load_meta(
    meta_path: Path,
    *,
    provider: str,
    model: str,
    corpus: str,
) -> bool:
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(meta, dict):
        return False
    return (
        meta.get("version") == _INDEX_VERSION
        and meta.get("provider") == provider
        and meta.get("model") == model
        and meta.get("corpus") == corpus
        and int(meta.get("chunk_target_chars") or 0) == _CHUNK_TARGET_CHARS
        and int(meta.get("chunk_overlap_chars") or 0) == _CHUNK_OVERLAP_CHARS
    )


def _load_existing_chunks(chunks_path: Path) -> dict[str, list[ChunkRecord]]:
    if not chunks_path.exists():
        return {}
    grouped: dict[str, list[ChunkRecord]] = {}
    try:
        lines = chunks_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        chunk = ChunkRecord.from_json(parsed)
        if chunk is None or not chunk.source_id:
            continue
        grouped.setdefault(chunk.source_id, []).append(chunk)
    return grouped


def _search_chunks(
    chunks: list[ChunkRecord],
    query_vector: list[float],
    *,
    top_k: int,
    per_source_cap: int,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, ChunkRecord]] = []
    for chunk in chunks:
        if not chunk.vector:
            continue
        scored.append((_dot(query_vector, chunk.vector), chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    hits: list[dict[str, Any]] = []
    per_source: dict[str, int] = {}
    for score, chunk in scored:
        count = per_source.get(chunk.source_id, 0)
        if count >= per_source_cap:
            continue
        hits.append(
            {
                "path": chunk.path,
                "title": chunk.title,
                "score": round(score, 4),
                "excerpt": chunk.excerpt,
                "source_id": chunk.source_id,
                "kind": chunk.kind,
                "record_path": chunk.record_path,
                "content_role": chunk.content_role,
                "subchunk_index": chunk.subchunk_index,
                "metadata": chunk.metadata,
            }
        )
        per_source[chunk.source_id] = count + 1
        if len(hits) >= top_k:
            break
    return hits


def _build_query(objective: str, question_reasoning_packet: dict[str, Any] | None) -> str:
    parts = [objective.strip()]
    if not isinstance(question_reasoning_packet, dict):
        return "\n\n".join(part for part in parts if part)
    for question in question_reasoning_packet.get("unresolved_questions", [])[:4]:
        if isinstance(question, dict):
            text = str(question.get("text") or "").strip()
            if text:
                parts.append(text)
    findings = question_reasoning_packet.get("findings")
    if isinstance(findings, dict):
        for bucket in ("unresolved", "contested"):
            for item in findings.get(bucket, [])[:2]:
                if isinstance(item, dict):
                    summary = str(item.get("summary") or item.get("claim_text") or "").strip()
                    if summary:
                        parts.append(summary)
    return "\n\n".join(part for part in parts if part)


def _build_pending_chunks_for_document(doc: SourceDocument) -> list[PendingChunk]:
    pending: list[PendingChunk] = []
    for record in _semantic_records_for_document(doc):
        for text in _chunk_semantic_record(record, doc=doc):
            stripped = text.strip()
            if not stripped:
                continue
            pending.append(
                PendingChunk(
                    source_id=doc.source_id,
                    path=doc.path,
                    title=doc.title,
                    text=stripped,
                    fingerprint=doc.fingerprint,
                    kind=doc.kind,
                    metadata=dict(record.metadata),
                    record_path=record.record_path,
                    content_role=record.content_role,
                    vector=[],
                )
            )
    return pending


def _finalize_pending_chunks(chunks: list[PendingChunk]) -> list[ChunkRecord]:
    finalized: list[ChunkRecord] = []
    chunk_indexes: dict[str, int] = {}
    record_subchunks: dict[tuple[str, str], int] = {}
    for chunk in chunks:
        chunk_index = chunk_indexes.get(chunk.source_id, 0)
        record_key = (chunk.source_id, chunk.record_path)
        subchunk_index = record_subchunks.get(record_key, 0)
        metadata = dict(chunk.metadata)
        metadata["chunk_index"] = chunk_index
        metadata["record_path"] = chunk.record_path
        metadata["content_role"] = chunk.content_role
        metadata["subchunk_index"] = subchunk_index
        finalized.append(
            ChunkRecord(
                chunk_id=f"{chunk.source_id}::chunk:{chunk_index}",
                source_id=chunk.source_id,
                path=chunk.path,
                title=chunk.title,
                text=chunk.text,
                excerpt=_make_excerpt(chunk.text),
                fingerprint=chunk.fingerprint,
                kind=chunk.kind,
                metadata=metadata,
                record_path=chunk.record_path,
                content_role=chunk.content_role,
                subchunk_index=subchunk_index,
                vector=chunk.vector,
            )
        )
        chunk_indexes[chunk.source_id] = chunk_index + 1
        record_subchunks[record_key] = subchunk_index + 1
    return finalized


def _pending_chunk_boundaries(chunks: list[PendingChunk]) -> list[int]:
    if not chunks:
        return []
    boundaries: list[int] = []
    running = 0
    for index, chunk in enumerate(chunks):
        running += 1
        next_source = chunks[index + 1].source_id if index + 1 < len(chunks) else None
        if next_source != chunk.source_id:
            boundaries.append(running)
    return boundaries


def _preflight_pending_chunks(
    chunks: list[PendingChunk],
    *,
    max_chars: int,
    on_event: Callable[[str], None] | None,
    reason: str,
) -> list[PendingChunk]:
    prepared: list[PendingChunk] = []
    for chunk in chunks:
        if len(chunk.text) <= max_chars:
            prepared.append(chunk)
            continue
        replacements = _split_pending_chunk_for_limit(chunk, max_chars=max_chars)
        if len(replacements) > 1:
            _emit_trace(
                on_event,
                (
                    "[retrieval] auto-resplit oversized chunk "
                    f"reason={reason} source={chunk.path} record_path={chunk.record_path} "
                    f"chars={len(chunk.text)} limit={max_chars} chunks={len(replacements)}"
                ),
            )
        prepared.extend(replacements)
    return prepared


def _retry_oversized_batch(
    pending_records: list[PendingChunk],
    *,
    batch_start: int,
    error: RetrievalError,
    client: EmbeddingsClient,
    on_event: Callable[[str], None] | None,
) -> bool:
    message = str(error)
    input_id = _extract_oversize_input_id(message)
    if input_id is None:
        return False
    absolute_index = batch_start + input_id
    if absolute_index >= len(pending_records):
        return False
    offending = pending_records[absolute_index]
    emergency_limit = min(
        client.limits.emergency_input_char_limit,
        max(400, len(offending.text) // 2),
    )
    replacements = _split_pending_chunk_for_limit(
        offending,
        max_chars=emergency_limit,
    )
    if len(replacements) <= 1:
        return False
    pending_records[absolute_index : absolute_index + 1] = replacements
    _emit_trace(
        on_event,
        (
            "[retrieval] retrying batch after provider oversize "
            f"source={offending.path} record_path={offending.record_path} "
            f"input_id={input_id} chars={len(offending.text)} retry_limit={emergency_limit} "
            f"chunks={len(replacements)}"
        ),
    )
    return True


def _split_pending_chunk_for_limit(chunk: PendingChunk, *, max_chars: int) -> list[PendingChunk]:
    if len(chunk.text) <= max_chars:
        return [chunk]
    target_chars = max(400, min(_CHUNK_TARGET_CHARS, max_chars))
    overlap_chars = min(
        max(0, target_chars - 1),
        min(_CHUNK_OVERLAP_CHARS, max(80, target_chars // 5)),
    )
    windows = _sliding_windows(
        chunk.text,
        target_chars=target_chars,
        overlap_chars=overlap_chars,
    )
    if len(windows) <= 1:
        return [chunk]
    return [
        PendingChunk(
            source_id=chunk.source_id,
            path=chunk.path,
            title=chunk.title,
            text=window,
            fingerprint=chunk.fingerprint,
            kind=chunk.kind,
            metadata=dict(chunk.metadata),
            record_path=chunk.record_path,
            content_role=chunk.content_role,
            vector=[],
        )
        for window in windows
    ]


def _semantic_records_for_document(doc: SourceDocument) -> list[SemanticRecord]:
    suffix = Path(doc.path.split("#", 1)[0]).suffix.lower()
    if doc.kind in {"evidence", "session_memory"}:
        return _body_semantic_records(doc.text, metadata=doc.metadata)
    if suffix == ".json":
        try:
            parsed = json.loads(doc.text)
        except json.JSONDecodeError:
            return _body_semantic_records(doc.text, metadata=doc.metadata)
        if isinstance(parsed, dict) and _is_wrapper_artifact(parsed):
            records = _semantic_records_from_wrapper_payload(parsed, metadata=doc.metadata)
            if records:
                return records
        records = _semantic_records_from_json_value(
            parsed,
            record_path="root",
            content_role="structured",
            metadata=doc.metadata,
        )
        return records or _body_semantic_records(doc.text, metadata=doc.metadata)
    if suffix in {".csv", ".tsv"}:
        records = _semantic_records_from_delimited(
            doc.text,
            delimiter="," if suffix == ".csv" else "\t",
            metadata=doc.metadata,
        )
        return records or _body_semantic_records(doc.text, metadata=doc.metadata)
    return _body_semantic_records(doc.text, metadata=doc.metadata)


def _body_semantic_records(text: str, *, metadata: dict[str, Any]) -> list[SemanticRecord]:
    stripped = text.strip()
    if not stripped:
        return []
    return [SemanticRecord(record_path="body", content_role="body", text=stripped, metadata=dict(metadata))]


def _semantic_records_from_wrapper_payload(
    payload: dict[str, Any],
    *,
    metadata: dict[str, Any],
) -> list[SemanticRecord]:
    records: list[SemanticRecord] = []
    summary_lines: list[str] = []
    for key in ("provider", "service", "operation", "model", "path"):
        value = payload.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            summary_lines.append(f"{key}: {value}")
    for key in ("file", "options", "artifacts"):
        value = payload.get(key)
        compact = _compact_json(value, max_chars=320)
        if compact:
            summary_lines.append(f"{key}: {compact}")
    if summary_lines:
        records.append(
            SemanticRecord(
                record_path="summary",
                content_role="summary",
                text="\n".join(summary_lines),
                metadata=dict(metadata),
            )
        )

    text_value = payload.get("text")
    if isinstance(text_value, str) and text_value.strip():
        records.extend(
            _semantic_records_from_json_value(
                text_value,
                record_path="text",
                content_role="body",
                metadata=metadata,
            )
        )

    response = payload.get("response")
    if response is not None:
        records.extend(
            _semantic_records_from_json_value(
                response,
                record_path="response",
                content_role="structured",
                metadata=metadata,
            )
        )

    for extra_key in ("pages", "segments", "document_annotation"):
        if extra_key in payload and extra_key not in {"text", "response"}:
            records.extend(
                _semantic_records_from_json_value(
                    payload[extra_key],
                    record_path=extra_key,
                    content_role=_json_child_role(extra_key, payload[extra_key], parent_role="structured"),
                    metadata=metadata,
                )
            )
    return [record for record in records if record.text.strip()]


def _semantic_records_from_json_value(
    value: Any,
    *,
    record_path: str,
    content_role: str,
    metadata: dict[str, Any],
) -> list[SemanticRecord]:
    if isinstance(value, dict):
        serialized = _json_text(value)
        if len(serialized) <= _STRUCTURED_RECORD_MAX_CHARS:
            return [
                SemanticRecord(
                    record_path=record_path or "root",
                    content_role=content_role,
                    text=serialized,
                    metadata=dict(metadata),
                )
            ]
        records: list[SemanticRecord] = []
        for key, child in value.items():
            child_path = f"{record_path}.{key}" if record_path else str(key)
            records.extend(
                _semantic_records_from_json_value(
                    child,
                    record_path=child_path,
                    content_role=_json_child_role(str(key), child, parent_role=content_role),
                    metadata=metadata,
                )
            )
        return records

    if isinstance(value, list):
        serialized = _json_text(value)
        if len(serialized) <= _STRUCTURED_RECORD_MAX_CHARS:
            return [
                SemanticRecord(
                    record_path=record_path or "root",
                    content_role=content_role,
                    text=serialized,
                    metadata=dict(metadata),
                )
            ]
        records: list[SemanticRecord] = []
        for index, child in enumerate(value):
            child_path = f"{record_path}[{index}]"
            records.extend(
                _semantic_records_from_json_value(
                    child,
                    record_path=child_path,
                    content_role=_json_list_role(record_path, child, parent_role=content_role),
                    metadata=metadata,
                )
            )
        return records

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        leaf_text = _format_leaf_text(
            stripped,
            record_path=record_path,
            content_role=content_role,
        )
        if len(leaf_text) <= _STRUCTURED_RECORD_MAX_CHARS:
            return [
                SemanticRecord(
                    record_path=record_path or "root",
                    content_role=content_role,
                    text=leaf_text,
                    metadata=dict(metadata),
                )
            ]
        return [
            SemanticRecord(
                record_path=record_path or "root",
                content_role=content_role,
                text=window,
                metadata=dict(metadata),
            )
            for window in _sliding_windows(
                leaf_text,
                target_chars=_CHUNK_TARGET_CHARS,
                overlap_chars=_CHUNK_OVERLAP_CHARS,
            )
        ]

    scalar = _json_scalar_text(value)
    if not scalar:
        return []
    return [
        SemanticRecord(
            record_path=record_path or "root",
            content_role=content_role,
            text=_format_leaf_text(
                scalar,
                record_path=record_path,
                content_role=content_role,
            ),
            metadata=dict(metadata),
        )
    ]


def _semantic_records_from_delimited(
    text: str,
    *,
    delimiter: str,
    metadata: dict[str, Any],
) -> list[SemanticRecord]:
    rows: list[SemanticRecord] = []
    try:
        reader = csv.reader(text.splitlines(), delimiter=delimiter)
        header: list[str] | None = None
        for index, row in enumerate(reader):
            if index == 0:
                header = row
                if header:
                    rows.append(
                        SemanticRecord(
                            record_path="schema",
                            content_role="table_schema",
                            text=f"columns: {delimiter.join(header)}",
                            metadata=dict(metadata),
                        )
                    )
                continue
            if not header:
                continue
            record = {
                header[col]: row[col] if col < len(row) else ""
                for col in range(len(header))
            }
            rows.extend(
                _semantic_records_from_table_row(
                    record,
                    record_path=f"row[{index - 1}]",
                    metadata=metadata,
                )
            )
    except csv.Error:
        return _body_semantic_records(text, metadata=metadata)
    return rows


def _semantic_records_from_table_row(
    row: dict[str, str],
    *,
    record_path: str,
    metadata: dict[str, Any],
) -> list[SemanticRecord]:
    serialized = _json_text(row, pretty=False)
    if len(serialized) <= _STRUCTURED_RECORD_MAX_CHARS:
        return [
            SemanticRecord(
                record_path=record_path,
                content_role="table_row",
                text=serialized,
                metadata=dict(metadata),
            )
        ]
    records: list[SemanticRecord] = []
    current_fields: dict[str, str] = {}
    for key, value in row.items():
        field_value = str(value).strip()
        field_path = f"{record_path}.{key}"
        if len(field_value) > _STRUCTURED_RECORD_MAX_CHARS:
            if current_fields:
                records.append(
                    SemanticRecord(
                        record_path=record_path,
                        content_role="table_row",
                        text=_json_text(current_fields, pretty=False),
                        metadata=dict(metadata),
                    )
                )
                current_fields = {}
            records.extend(
                _semantic_records_from_json_value(
                    field_value,
                    record_path=field_path,
                    content_role="table_field",
                    metadata=metadata,
                )
            )
            continue
        candidate = dict(current_fields)
        candidate[key] = field_value
        if current_fields and len(_json_text(candidate, pretty=False)) > _STRUCTURED_RECORD_MAX_CHARS:
            records.append(
                SemanticRecord(
                    record_path=record_path,
                    content_role="table_row",
                    text=_json_text(current_fields, pretty=False),
                    metadata=dict(metadata),
                )
            )
            current_fields = {key: field_value}
        else:
            current_fields = candidate
    if current_fields:
        records.append(
            SemanticRecord(
                record_path=record_path,
                content_role="table_row",
                text=_json_text(current_fields, pretty=False),
                metadata=dict(metadata),
            )
        )
    return records


def _chunk_semantic_record(record: SemanticRecord, *, doc: SourceDocument) -> list[str]:
    text = record.text.strip()
    if not text:
        return []
    if doc.kind in {"evidence", "session_memory"}:
        return _chunk_atomic_text(text)
    if record.content_role in {"body", "page_markdown", "annotation", "summary", "table_schema"}:
        return _chunk_paragraph_text(text)
    return _chunk_atomic_text(text)


def _chunk_atomic_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= _STRUCTURED_RECORD_MAX_CHARS:
        return [text]
    return _sliding_windows(
        text,
        target_chars=_CHUNK_TARGET_CHARS,
        overlap_chars=_CHUNK_OVERLAP_CHARS,
    )


def _chunk_paragraph_text(text: str) -> list[str]:
    paragraphs = [segment.strip() for segment in _PARAGRAPH_SPLIT_RE.split(text) if segment.strip()]
    if not paragraphs:
        stripped = text.strip()
        return [stripped] if stripped else []
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if current and len(candidate) > _CHUNK_TARGET_CHARS:
            chunks.append(current)
            overlap_text = current[-_CHUNK_OVERLAP_CHARS :].strip()
            current = f"{overlap_text}\n\n{paragraph}".strip() if overlap_text else paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)

    expanded: list[str] = []
    for chunk in chunks:
        if len(chunk) <= _STRUCTURED_RECORD_MAX_CHARS:
            expanded.append(chunk)
        else:
            expanded.extend(
                _sliding_windows(
                    chunk,
                    target_chars=_CHUNK_TARGET_CHARS,
                    overlap_chars=_CHUNK_OVERLAP_CHARS,
                )
            )
    return expanded


def _sliding_windows(
    text: str,
    *,
    target_chars: int,
    overlap_chars: int,
) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    windows: list[str] = []
    step = max(1, target_chars - overlap_chars)
    for start in range(0, len(stripped), step):
        window = stripped[start : start + target_chars].strip()
        if window:
            windows.append(window)
        if start + target_chars >= len(stripped):
            break
    return windows


def _split_query_windows(text: str, *, max_chars: int) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if len(stripped) <= max_chars:
        return [stripped]
    overlap_chars = min(max(0, max_chars - 1), max(1, min(400, max_chars // 4)))
    return _sliding_windows(
        stripped,
        target_chars=max_chars,
        overlap_chars=overlap_chars,
    )


def _emit_trace(on_event: Callable[[str], None] | None, message: str) -> None:
    if on_event is None:
        return
    try:
        on_event(message)
    except Exception:
        pass


def _json_text(value: Any, *, pretty: bool = True) -> str:
    if pretty:
        return json.dumps(value, indent=2, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _compact_json(value: Any, *, max_chars: int) -> str:
    if value is None:
        return ""
    compact = _json_text(value, pretty=False)
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3]}..."


def _json_scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return _json_text(value, pretty=False)


def _format_leaf_text(value: str, *, record_path: str, content_role: str) -> str:
    if content_role in {"body", "page_markdown", "annotation", "summary", "transcript_segment"}:
        return value
    label = record_path.rsplit(".", 1)[-1].strip()
    if "[" in label:
        label = label.split("[", 1)[0]
    if label and label not in {"root", "body"}:
        return f"{label}: {value}"
    return value


def _json_child_role(key: str, value: Any, *, parent_role: str) -> str:
    lowered = key.lower()
    if lowered == "markdown":
        return "page_markdown"
    if lowered in {"text", "content", "summary", "description", "body"}:
        return "body"
    if lowered in {"document_annotation", "annotation"}:
        return "annotation"
    if lowered in {"segment", "segments", "transcript", "transcription"}:
        return "transcript_segment"
    if lowered in {"provider", "service", "model", "operation", "options", "artifacts", "usage_info", "file", "path"}:
        return "metadata"
    if parent_role == "transcript_segment":
        return "transcript_segment"
    return "structured"


def _json_list_role(record_path: str, value: Any, *, parent_role: str) -> str:
    if record_path.endswith(".pages"):
        return "page_markdown"
    if record_path.endswith(".segments"):
        return "transcript_segment"
    return parent_role if parent_role != "structured" else _json_child_role(record_path, value, parent_role=parent_role)


def _is_wrapper_artifact(payload: dict[str, Any]) -> bool:
    keys = {"provider", "operation", "response", "text", "artifacts", "service"}
    return len(keys.intersection(payload.keys())) >= 3


def _extract_oversize_input_id(message: str) -> int | None:
    match = _OVERSIZE_INPUT_ID_RE.search(message)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _mean_pool_vectors(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    width = min((len(vector) for vector in vectors), default=0)
    if width <= 0:
        return []
    pooled = [
        sum(vector[index] for vector in vectors) / len(vectors)
        for index in range(width)
    ]
    return _normalize_vector(pooled)


def _skip_workspace_path(path: Path, *, workspace: Path, session_root_dir: str) -> bool:
    rel_parts = path.relative_to(workspace).parts
    if any(part in _EXCLUDED_DIR_NAMES for part in rel_parts):
        return True
    if any(_is_junk_name(part) for part in rel_parts):
        return True
    if rel_parts and rel_parts[0] == session_root_dir:
        if len(rel_parts) >= 2 and rel_parts[1] == "wiki":
            return False
        return True
    return False


def _emit_progress(
    on_event: Callable[[str], None] | None,
    progress: RetrievalProgress,
) -> None:
    if on_event is None:
        return
    try:
        on_event(progress.to_trace_message())
    except Exception:
        pass


def _is_junk_name(name: str) -> bool:
    return name in _IGNORED_FILE_NAMES or any(
        name.startswith(prefix) for prefix in _IGNORED_FILE_PREFIXES
    )


def _is_junk_path(path: Path) -> bool:
    return _is_junk_name(path.name)


def _make_excerpt(text: str) -> str:
    collapsed = _WS_RE.sub(" ", text).strip()
    if len(collapsed) <= _MAX_EXCERPT_CHARS:
        return collapsed
    return f"{collapsed[:_MAX_EXCERPT_CHARS - 3]}..."


def _fingerprint_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def _rel_path(path: Path, workspace: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return path.as_posix()


def _join_nonempty(values: Iterable[str]) -> str:
    return "\n".join(value for value in values if value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(lv * rv for lv, rv in zip(left, right, strict=False))


def _is_subpath(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
