from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from agent.retrieval import (
    MISTRAL_EMBEDDING_MODEL,
    ChunkRecord,
    EmbeddingsClient,
    EmbeddingsProviderLimits,
    RETRIEVAL_PACKET_VERSION,
    RetrievalError,
    SourceDocument,
    _build_query,
    _build_pending_chunks_for_document,
    _documents_from_file,
    _refresh_index,
    _skip_workspace_path,
)
from agent.tui import _clip_event


class FakeEmbeddingsClient:
    def __init__(
        self,
        *,
        provider: str = "mistral",
        model: str = MISTRAL_EMBEDDING_MODEL,
        input_char_limit: int = 12_000,
        emergency_input_char_limit: int = 4_000,
        fail_first_batch: bool = False,
    ) -> None:
        self.provider = provider
        self.model = model
        self.limits = EmbeddingsProviderLimits(
            batch_size=32,
            input_char_limit=input_char_limit,
            emergency_input_char_limit=emergency_input_char_limit,
        )
        self.fail_first_batch = fail_first_batch
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail_first_batch:
            self.fail_first_batch = False
            raise RetrievalError(
                'mistral embeddings HTTP 400: {"message":"Input id 0 has 9000 tokens, exceeding max 8192 tokens."}'
            )
        return [[1.0, 0.0] for _ in texts]


class QueryPoolingClient(EmbeddingsClient):
    def __init__(self) -> None:
        self.provider = "mistral"
        self.api_key = "test-key"
        self.model = MISTRAL_EMBEDDING_MODEL
        self.limits = EmbeddingsProviderLimits(
            batch_size=32,
            input_char_limit=12,
            emergency_input_char_limit=6,
        )
        self.calls: list[list[str]] = []

    def _embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        self.calls.append(list(texts))
        if input_type != "query":
            return [[1.0, 0.0] for _ in texts]
        if len(texts) == 2:
            return [[1.0, 0.0], [0.0, 1.0]]
        return [[1.0, 0.0] for _ in texts]


class RetrievalTests(unittest.TestCase):
    def test_documents_from_file_ignores_macos_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sidecar = root / "._notes.md"
            sidecar.write_text("junk", encoding="utf-8")
            ds_store = root / ".DS_Store"
            ds_store.write_text("junk", encoding="utf-8")
            real_doc = root / "notes.md"
            real_doc.write_text("hello world", encoding="utf-8")

            self.assertEqual(_documents_from_file(sidecar, workspace=root, kind="workspace"), [])
            self.assertEqual(_documents_from_file(ds_store, workspace=root, kind="workspace"), [])
            docs = _documents_from_file(real_doc, workspace=root, kind="workspace")
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].path, "notes.md")

    def test_skip_workspace_path_ignores_junk_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "research" / "._sidecar.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("junk", encoding="utf-8")

            self.assertTrue(
                _skip_workspace_path(
                    path,
                    workspace=root,
                    session_root_dir=".openplanter",
                )
            )

    def test_clip_event_formats_retrieval_progress(self) -> None:
        formatted = _clip_event(
            '[retrieval:progress] {"corpus":"workspace","phase":"embedding","documents_done":12,"documents_total":48,"chunks_done":80,"chunks_total":320,"reused_documents":0,"percent":25,"message":"Embedding workspace retrieval index."}'
        )
        self.assertEqual(
            formatted,
            "vectorizing workspace: embedding 25% (12/48 docs) - Embedding workspace retrieval index.",
        )

    def test_refresh_index_normalizes_ocr_wrapper_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index_dir = root / ".openplanter" / "embeddings" / "workspace"
            doc = SourceDocument(
                source_id="scan.pdf.ocr.json",
                path="scan.pdf.ocr.json",
                title="scan.pdf.ocr.json",
                text=json.dumps(
                    {
                        "provider": "mistral",
                        "service": "document_ai",
                        "operation": "ocr",
                        "model": "mistral-ocr-latest",
                        "path": "scan.pdf",
                        "artifacts": {"markdown_path": "scan.pdf.ocr.md"},
                        "text": "OCR text " * 4_000,
                        "response": {
                            "pages": [
                                {"index": 0, "markdown": "# Page 1\n" + ("Alpha " * 1_500)},
                                {"index": 1, "markdown": "# Page 2\n" + ("Beta " * 1_500)},
                            ],
                            "usage_info": {"pages_processed": 2},
                        },
                    },
                    ensure_ascii=False,
                ),
                fingerprint="ocr-doc",
                kind="workspace",
                metadata={"extension": ".json"},
            )
            client = FakeEmbeddingsClient(input_char_limit=3_000, emergency_input_char_limit=1_200)
            events: list[str] = []

            result = _refresh_index(
                index_dir=index_dir,
                documents=[doc],
                client=client,
                provider="mistral",
                model=MISTRAL_EMBEDDING_MODEL,
                corpus="workspace",
                on_event=events.append,
            )
            chunks = result.chunks

            self.assertTrue(chunks)
            self.assertTrue(any(chunk.record_path == "summary" for chunk in chunks))
            self.assertTrue(any(chunk.record_path.startswith("text") for chunk in chunks))
            self.assertTrue(any("response.pages" in chunk.record_path for chunk in chunks))
            self.assertTrue(all(len(chunk.text) <= client.limits.input_char_limit for chunk in chunks))
            self.assertTrue((index_dir / "meta.json").exists())
            self.assertTrue((index_dir / "chunks.jsonl").exists())
            self.assertEqual(result.completion, "complete")

    def test_build_pending_chunks_recursively_splits_large_json_field(self) -> None:
        doc = SourceDocument(
            source_id="records.json",
            path="records.json",
            title="records.json",
            text=json.dumps(
                {
                    "items": [
                        {
                            "id": "42",
                            "note": "Alpha " * 1_500,
                            "status": "open",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            fingerprint="json-doc",
            kind="workspace",
            metadata={"extension": ".json"},
        )

        pending = _build_pending_chunks_for_document(doc)

        self.assertTrue(pending)
        self.assertTrue(any("items[0].note" in chunk.record_path for chunk in pending))
        self.assertTrue(all(len(chunk.text) <= 1_400 for chunk in pending))

    def test_build_pending_chunks_recursively_splits_large_csv_field(self) -> None:
        doc = SourceDocument(
            source_id="records.csv",
            path="records.csv",
            title="records.csv",
            text="id,notes,status\n1," + ("value " * 1_500) + ",open\n",
            fingerprint="csv-doc",
            kind="workspace",
            metadata={"extension": ".csv"},
        )

        pending = _build_pending_chunks_for_document(doc)

        self.assertTrue(pending)
        self.assertTrue(any(chunk.record_path.endswith(".notes") for chunk in pending))
        self.assertTrue(all(len(chunk.text) <= 1_400 for chunk in pending))

    def test_refresh_index_retries_batch_after_provider_oversize_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index_dir = root / ".openplanter" / "embeddings" / "workspace"
            doc = SourceDocument(
                source_id="notes.md",
                path="notes.md",
                title="notes.md",
                text=("Long paragraph " * 300),
                fingerprint="notes-doc",
                kind="workspace",
                metadata={"extension": ".md"},
            )
            client = FakeEmbeddingsClient(
                input_char_limit=5_000,
                emergency_input_char_limit=800,
                fail_first_batch=True,
            )
            events: list[str] = []

            result = _refresh_index(
                index_dir=index_dir,
                documents=[doc],
                client=client,
                provider="mistral",
                model=MISTRAL_EMBEDDING_MODEL,
                corpus="workspace",
                on_event=events.append,
            )
            chunks = result.chunks

            self.assertGreater(len(chunks), 1)
            self.assertTrue(any("retrying batch after provider oversize" in event for event in events))
            self.assertEqual(result.completion, "complete")

    def test_query_embedding_pools_multiple_windows(self) -> None:
        client = QueryPoolingClient()

        vector = client.embed_query("0123456789abcdef")

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(client.calls[0]), 2)
        self.assertAlmostEqual(vector[0], math.sqrt(0.5), places=6)
        self.assertAlmostEqual(vector[1], math.sqrt(0.5), places=6)

    def test_build_query_extracts_hybrid_focus_ids(self) -> None:
        query = _build_query(
            "Investigate beneficial ownership",
            {
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
                            {
                                "object_id": "ent_1",
                                "object_type": "entity",
                                "label": "Acme Holdings",
                            }
                        ],
                    }
                ],
            },
        )

        self.assertIn("Who controls the shell company?", query.text)
        self.assertIn("Acme Holdings", query.text)
        self.assertEqual(query.focus_question_ids, ["q_1"])
        self.assertEqual(query.focus_claim_ids, ["cl_1"])
        self.assertEqual(query.focus_entity_ids, ["ent_1"])
        self.assertIn("ev_1", query.boost_object_ids)
        self.assertEqual(RETRIEVAL_PACKET_VERSION, "retrieval-v3")


if __name__ == "__main__":
    unittest.main()
