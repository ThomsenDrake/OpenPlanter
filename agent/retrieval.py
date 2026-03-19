from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import normalize_embeddings_provider

VOYAGE_EMBEDDING_MODEL = "voyage-4"
MISTRAL_EMBEDDING_MODEL = "mistral-embed"
_CHUNK_TARGET_CHARS = 1200
_CHUNK_OVERLAP_CHARS = 200
_MAX_EXCERPT_CHARS = 280
_INDEX_VERSION = "embeddings-v1"
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
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_WS_RE = re.compile(r"\s+")


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
class SourceDocument:
    source_id: str
    path: str
    title: str
    text: str
    fingerprint: str
    kind: str
    metadata: dict[str, Any]


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
            vector=_normalize_vector(vector),
        )


class RetrievalError(RuntimeError):
    pass


class EmbeddingsClient:
    def __init__(self, provider: str, api_key: str) -> None:
        self.provider = normalize_embeddings_provider(provider)
        self.api_key = api_key.strip()
        self.model = (
            VOYAGE_EMBEDDING_MODEL
            if self.provider == "voyage"
            else MISTRAL_EMBEDDING_MODEL
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, input_type="document")

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed([text], input_type="query")
        if not vectors:
            raise RetrievalError("Embeddings provider returned no query vector")
        return vectors[0]

    def _endpoint(self) -> str:
        if self.provider == "voyage":
            return "https://api.voyageai.com/v1/embeddings"
        return "https://api.mistral.ai/v1/embeddings"

    def _embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
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
    on_event: callable | None = None,
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
    )
    session_chunks = _refresh_index(
        index_dir=session_index_dir,
        documents=session_docs,
        client=client,
        provider=status.provider,
        model=status.model,
        corpus="session",
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
    pending_texts: list[str] = []
    pending_records: list[ChunkRecord] = []
    for doc in documents:
        prior = existing_chunks.get(doc.source_id, [])
        if prior and all(chunk.fingerprint == doc.fingerprint for chunk in prior):
            resolved_chunks.extend(prior)
            continue
        for chunk_index, text in enumerate(_chunk_document(doc)):
            excerpt = _make_excerpt(text)
            metadata = dict(doc.metadata)
            metadata["chunk_index"] = chunk_index
            pending_records.append(
                ChunkRecord(
                    chunk_id=f"{doc.source_id}::chunk:{chunk_index}",
                    source_id=doc.source_id,
                    path=doc.path,
                    title=doc.title,
                    text=text,
                    excerpt=excerpt,
                    fingerprint=doc.fingerprint,
                    kind=doc.kind,
                    metadata=metadata,
                    vector=[],
                )
            )
            pending_texts.append(text)

    if pending_records:
        vectors = client.embed_documents(pending_texts)
        for record, vector in zip(pending_records, vectors, strict=True):
            record.vector = vector
        resolved_chunks.extend(pending_records)

    resolved_chunks.sort(key=lambda chunk: (chunk.path, chunk.chunk_id))
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


def _chunk_document(doc: SourceDocument) -> list[str]:
    suffix = Path(doc.path.split("#", 1)[0]).suffix.lower()
    if doc.kind in {"evidence", "session_memory"}:
        return _chunk_atomic_text(doc.text)
    if suffix == ".json":
        return _chunk_json(doc.text)
    if suffix in {".csv", ".tsv"}:
        return _chunk_delimited(doc.text, delimiter="," if suffix == ".csv" else "\t")
    return _chunk_paragraph_text(doc.text)


def _chunk_atomic_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= _CHUNK_TARGET_CHARS:
        return [text]
    return _sliding_windows(text)


def _chunk_json(text: str) -> list[str]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _chunk_paragraph_text(text)
    records: list[str] = []
    if isinstance(parsed, list):
        records = [
            json.dumps(item, indent=2, ensure_ascii=False)
            for item in parsed
        ]
    elif isinstance(parsed, dict):
        records = [
            json.dumps({key: value}, indent=2, ensure_ascii=False)
            for key, value in parsed.items()
        ]
    else:
        records = [json.dumps(parsed, indent=2, ensure_ascii=False)]
    return _group_records(records)


def _chunk_delimited(text: str, *, delimiter: str) -> list[str]:
    rows: list[str] = []
    try:
        reader = csv.reader(text.splitlines(), delimiter=delimiter)
        header: list[str] | None = None
        for index, row in enumerate(reader):
            if index == 0:
                header = row
                rows.append(delimiter.join(row))
                continue
            if header:
                record = {
                    header[col]: row[col] if col < len(row) else ""
                    for col in range(len(header))
                }
                rows.append(json.dumps(record, ensure_ascii=False))
            else:
                rows.append(delimiter.join(row))
    except csv.Error:
        return _chunk_paragraph_text(text)
    return _group_records(rows)


def _group_records(records: list[str]) -> list[str]:
    chunks: list[str] = []
    current = ""
    for record in records:
        value = record.strip()
        if not value:
            continue
        candidate = value if not current else f"{current}\n{value}"
        if current and len(candidate) > _CHUNK_TARGET_CHARS:
            chunks.append(current)
            overlap = current[-_CHUNK_OVERLAP_CHARS :]
            current = f"{overlap}\n{value}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


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
        if len(chunk) <= (_CHUNK_TARGET_CHARS + _CHUNK_OVERLAP_CHARS):
            expanded.append(chunk)
        else:
            expanded.extend(_sliding_windows(chunk))
    return expanded


def _sliding_windows(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    windows: list[str] = []
    step = max(1, _CHUNK_TARGET_CHARS - _CHUNK_OVERLAP_CHARS)
    for start in range(0, len(stripped), step):
        window = stripped[start : start + _CHUNK_TARGET_CHARS].strip()
        if window:
            windows.append(window)
        if start + _CHUNK_TARGET_CHARS >= len(stripped):
            break
    return windows


def _skip_workspace_path(path: Path, *, workspace: Path, session_root_dir: str) -> bool:
    rel_parts = path.relative_to(workspace).parts
    if any(part in _EXCLUDED_DIR_NAMES for part in rel_parts):
        return True
    if rel_parts and rel_parts[0] == session_root_dir:
        if len(rel_parts) >= 2 and rel_parts[1] == "wiki":
            return False
        return True
    return False


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
