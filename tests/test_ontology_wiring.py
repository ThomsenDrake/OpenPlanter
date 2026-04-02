"""Tests for ontology wiring across retrieval, investigation_state, defrag, and prompts modules."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Retrieval Tests
# ---------------------------------------------------------------------------


class TestRetrievalOntologyWiring:
    """Tests for ontology document collection and scope tagging in retrieval module."""

    def test_retrieval_includes_workspace_ontology_objects(self, tmp_path: Path) -> None:
        """Create a temp workspace with .openplanter/ontology.json containing entities and claims.
        
        Call _collect_ontology_documents() and verify workspace objects are returned.
        """
        from agent.retrieval import _collect_ontology_documents

        # Set up workspace with ontology.json
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "namespace": "openplanter.workspace",
            "version": "2026-04",
            "entities": {
                "ent_001": {"name": "Test Entity", "type": "Person", "content": "Test content"},
                "ent_002": {"name": "Another Entity", "type": "Organization"},
            },
            "claims": {
                "cl_001": {"claim_text": "Test claim", "status": "supported", "confidence": 0.9},
            },
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
            "indexes": {"by_external_ref": {}, "by_tag": {}, "by_investigation": {}},
            "source_sessions": ["session-001"],
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        # Call the function
        docs = _collect_ontology_documents(workspace=tmp_path, session_dir=None)

        # Verify workspace objects are returned
        assert len(docs) >= 3  # At least 2 entities + 1 claim

        # Check that entity objects are included
        entity_docs = [d for d in docs if d.metadata.get("object_type") == "entity"]
        assert len(entity_docs) >= 2

        # Check that claim objects are included
        claim_docs = [d for d in docs if d.metadata.get("object_type") == "claim"]
        assert len(claim_docs) >= 1

    def test_retrieval_workspace_objects_tagged_with_scope(self, tmp_path: Path) -> None:
        """Verify workspace objects have metadata["scope"] == "workspace" and 
        session objects have metadata["scope"] == "session".
        """
        from agent.retrieval import _collect_ontology_documents

        # Set up workspace with ontology.json
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        workspace_ontology = {
            "namespace": "openplanter.workspace",
            "version": "2026-04",
            "entities": {
                "ent_ws": {"name": "Workspace Entity", "type": "Person"},
            },
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
            "indexes": {"by_external_ref": {}, "by_tag": {}, "by_investigation": {}},
            "source_sessions": [],
        }
        (openplanter_dir / "ontology.json").write_text(
            json.dumps(workspace_ontology), encoding="utf-8"
        )

        # Set up session with investigation_state.json
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        session_dir = sessions_dir / "session-001"
        session_dir.mkdir(parents=True)

        session_state = {
            "session_id": "session-001",
            "entities": {
                "ent_sess": {"name": "Session Entity", "type": "Person"},
            },
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
        }
        (session_dir / "investigation_state.json").write_text(
            json.dumps(session_state), encoding="utf-8"
        )

        # Call the function with both workspace and session
        docs = _collect_ontology_documents(workspace=tmp_path, session_dir=session_dir)

        # Find workspace and session entity docs
        workspace_entity = next(
            (d for d in docs if d.metadata.get("object_id") == "ent_ws"), None
        )
        session_entity = next(
            (d for d in docs if d.metadata.get("object_id") == "ent_sess"), None
        )

        # Verify scope tagging
        assert workspace_entity is not None
        assert workspace_entity.metadata.get("scope") == "workspace"

        assert session_entity is not None
        assert session_entity.metadata.get("scope") == "session"

    def test_retrieval_deduplicates_session_over_workspace(self, tmp_path: Path) -> None:
        """Create both session investigation_state.json and workspace ontology.json 
        with the same object_id. Verify only the session copy is kept.
        """
        from agent.retrieval import _collect_ontology_documents

        # Set up workspace with ontology.json containing an entity
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        workspace_ontology = {
            "namespace": "openplanter.workspace",
            "version": "2026-04",
            "entities": {
                "ent_shared": {"name": "Shared Entity", "type": "Person"},
            },
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
            "indexes": {"by_external_ref": {}, "by_tag": {}, "by_investigation": {}},
            "source_sessions": [],
        }
        (openplanter_dir / "ontology.json").write_text(
            json.dumps(workspace_ontology), encoding="utf-8"
        )

        # Set up session with same entity ID
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        session_dir = sessions_dir / "session-001"
        session_dir.mkdir(parents=True)

        session_state = {
            "session_id": "session-001",
            "entities": {
                "ent_shared": {"name": "Shared Entity (Session)", "type": "Person"},
            },
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
        }
        (session_dir / "investigation_state.json").write_text(
            json.dumps(session_state), encoding="utf-8"
        )

        # Call the function
        docs = _collect_ontology_documents(workspace=tmp_path, session_dir=session_dir)

        # Find all docs with the shared entity ID
        shared_entity_docs = [d for d in docs if d.metadata.get("object_id") == "ent_shared"]

        # Should only have one copy (the session one)
        assert len(shared_entity_docs) == 1
        assert shared_entity_docs[0].metadata.get("scope") == "session"


# ---------------------------------------------------------------------------
# Question Reasoning Packet Tests
# ---------------------------------------------------------------------------


class TestQuestionReasoningPacket:
    """Tests for build_question_reasoning_packet with workspace_ontology support."""

    def test_question_packet_cross_investigation_context(self) -> None:
        """Call build_question_reasoning_packet() with a workspace_ontology dict.
        
        Verify cross_investigation_context has available: True, correct entity/claim counts,
        source_sessions, and investigations list.
        """
        from agent.investigation_state import build_question_reasoning_packet

        # Create a minimal state
        state: dict[str, Any] = {
            "questions": {},
            "claims": {},
            "evidence": {},
            "provenance_nodes": {},
            "entities": {},
            "links": {},
        }

        # Create workspace ontology
        workspace_ontology = {
            "entities": {
                "ent_001": {"name": "Entity 1"},
                "ent_002": {"name": "Entity 2"},
            },
            "claims": {
                "cl_001": {"claim_text": "Claim 1"},
                "cl_002": {"claim_text": "Claim 2"},
                "cl_003": {"claim_text": "Claim 3"},
            },
            "source_sessions": ["session-001", "session-002"],
            "indexes": {
                "by_investigation": {
                    "session-001": ["ent_001"],
                    "session-002": ["ent_002"],
                }
            },
        }

        packet = build_question_reasoning_packet(state, workspace_ontology=workspace_ontology)

        # Verify cross_investigation_context
        cross_ctx = packet.get("cross_investigation_context", {})
        assert cross_ctx.get("available") is True
        assert cross_ctx.get("total_entities") == 2
        assert cross_ctx.get("total_claims") == 3
        assert cross_ctx.get("source_sessions") == ["session-001", "session-002"]
        assert "session-001" in cross_ctx.get("investigations", [])
        assert "session-002" in cross_ctx.get("investigations", [])

    def test_question_packet_no_ontology(self) -> None:
        """Call without workspace_ontology. Verify cross_investigation_context has available: False."""
        from agent.investigation_state import build_question_reasoning_packet

        state: dict[str, Any] = {
            "questions": {},
            "claims": {},
            "evidence": {},
            "provenance_nodes": {},
            "entities": {},
            "links": {},
        }

        packet = build_question_reasoning_packet(state, workspace_ontology=None)

        cross_ctx = packet.get("cross_investigation_context", {})
        assert cross_ctx.get("available") is False

    def test_question_packet_related_entities_with_investigation_id(self) -> None:
        """Set active_investigation_id in state and provide workspace_ontology with by_investigation index.
        
        Verify related_entities contains the expected entity IDs, capped at 20.
        """
        from agent.investigation_state import build_question_reasoning_packet

        # Create state with active_investigation_id
        state: dict[str, Any] = {
            "active_investigation_id": "session-001",
            "questions": {},
            "claims": {},
            "evidence": {},
            "provenance_nodes": {},
            "entities": {},
            "links": {},
        }

        # Create workspace ontology with by_investigation index
        workspace_ontology = {
            "entities": {
                f"ent_{i:03d}": {"name": f"Entity {i}"} for i in range(25)
            },
            "claims": {},
            "source_sessions": ["session-001"],
            "indexes": {
                "by_investigation": {
                    "session-001": [f"ent_{i:03d}" for i in range(25)],
                }
            },
        }

        packet = build_question_reasoning_packet(state, workspace_ontology=workspace_ontology)

        # Verify related_entities is capped at 20
        related_entities = packet.get("related_entities", [])
        assert len(related_entities) == 20
        # All should be from the session-001 investigation
        for entity_id in related_entities:
            assert entity_id.startswith("ent_")

    def test_question_packet_related_entities_without_investigation_id(self) -> None:
        """No active_investigation_id. Verify related_entities is empty list."""
        from agent.investigation_state import build_question_reasoning_packet

        # Create state WITHOUT active_investigation_id
        state: dict[str, Any] = {
            "questions": {},
            "claims": {},
            "evidence": {},
            "provenance_nodes": {},
            "entities": {},
            "links": {},
        }

        # Create workspace ontology with by_investigation index
        workspace_ontology = {
            "entities": {"ent_001": {"name": "Entity 1"}},
            "claims": {},
            "source_sessions": ["session-001"],
            "indexes": {
                "by_investigation": {
                    "session-001": ["ent_001"],
                }
            },
        }

        packet = build_question_reasoning_packet(state, workspace_ontology=workspace_ontology)

        # Verify related_entities is empty
        related_entities = packet.get("related_entities", [])
        assert related_entities == []


# ---------------------------------------------------------------------------
# Investigation State Schema Tests
# ---------------------------------------------------------------------------


class TestInvestigationStateSchema:
    """Tests for default state schema including active_investigation_id field."""

    def test_active_investigation_id_in_default_state(self) -> None:
        """Import the default state creation and verify active_investigation_id field exists with None default."""
        from agent.investigation_state import default_state

        state = default_state(session_id="test-session")

        # Verify active_investigation_id field exists
        assert "active_investigation_id" in state
        # Verify default is None
        assert state["active_investigation_id"] is None


# ---------------------------------------------------------------------------
# Auto-sync Tests
# ---------------------------------------------------------------------------


class TestAutoSync:
    """Tests for sync_session_to_workspace_ontology function."""

    def test_sync_session_to_workspace_ontology(self, tmp_path: Path) -> None:
        """Create a temp workspace, call sync_session_to_workspace_ontology() 
        with a session state containing entities/claims. Verify ontology.json is created with merged data.
        """
        from agent.defrag import sync_session_to_workspace_ontology

        session_state: dict[str, Any] = {
            "session_id": "session-001",
            "entities": {
                "ent_001": {"name": "Test Entity", "type": "Person"},
            },
            "claims": {
                "cl_001": {"claim_text": "Test claim", "status": "supported"},
            },
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
        }

        sync_session_to_workspace_ontology(
            workspace=tmp_path,
            session_id="session-001",
            session_state=session_state,
        )

        # Verify ontology.json was created
        ontology_path = tmp_path / ".openplanter" / "ontology.json"
        assert ontology_path.exists()

        # Verify content
        ontology = json.loads(ontology_path.read_text(encoding="utf-8"))
        assert "ent_001" in ontology.get("entities", {})
        assert "cl_001" in ontology.get("claims", {})
        assert "session-001" in ontology.get("source_sessions", [])

    def test_sync_creates_ontology_if_missing(self, tmp_path: Path) -> None:
        """Call sync when no ontology.json exists. Verify it creates one."""
        from agent.defrag import sync_session_to_workspace_ontology

        session_state: dict[str, Any] = {
            "session_id": "session-001",
            "entities": {"ent_001": {"name": "Test Entity"}},
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
        }

        # Ensure no ontology.json exists
        ontology_path = tmp_path / ".openplanter" / "ontology.json"
        assert not ontology_path.exists()

        sync_session_to_workspace_ontology(
            workspace=tmp_path,
            session_id="session-001",
            session_state=session_state,
        )

        # Verify ontology.json was created
        assert ontology_path.exists()

        ontology = json.loads(ontology_path.read_text(encoding="utf-8"))
        assert "ent_001" in ontology.get("entities", {})

    def test_sync_deduplicates_entities(self, tmp_path: Path) -> None:
        """Call sync twice with overlapping entities. Verify entities are deduplicated 
        and source_sessions tracks both session IDs.
        """
        from agent.defrag import sync_session_to_workspace_ontology

        # First sync
        session_state_1: dict[str, Any] = {
            "session_id": "session-001",
            "entities": {
                "ent_001": {"name": "Shared Entity", "type": "Person"},
                "ent_002": {"name": "Unique Entity 1", "type": "Person"},
            },
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
        }

        sync_session_to_workspace_ontology(
            workspace=tmp_path,
            session_id="session-001",
            session_state=session_state_1,
        )

        # Second sync with overlapping entity
        session_state_2: dict[str, Any] = {
            "session_id": "session-002",
            "entities": {
                "ent_003": {"name": "Shared Entity", "type": "Person"},  # Same name/type as ent_001
                "ent_004": {"name": "Unique Entity 2", "type": "Person"},
            },
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
        }

        sync_session_to_workspace_ontology(
            workspace=tmp_path,
            session_id="session-002",
            session_state=session_state_2,
        )

        # Verify ontology
        ontology_path = tmp_path / ".openplanter" / "ontology.json"
        ontology = json.loads(ontology_path.read_text(encoding="utf-8"))

        # Should have 3 unique entities (ent_001, ent_002, ent_004)
        # ent_003 should be deduplicated with ent_001
        entities = ontology.get("entities", {})
        assert len(entities) == 3

        # The shared entity should have both session IDs in source_sessions
        # Note: ent_001 is the canonical ID since it was added first
        shared_entity = entities.get("ent_001")
        assert shared_entity is not None
        source_sessions = shared_entity.get("source_sessions", [])
        assert "session-001" in source_sessions
        assert "session-002" in source_sessions

        # Both sessions should be in top-level source_sessions
        assert "session-001" in ontology.get("source_sessions", [])
        assert "session-002" in ontology.get("source_sessions", [])

    def test_sync_never_crashes(self, tmp_path: Path) -> None:
        """Call sync with malformed/empty state dict. Verify it doesn't raise."""
        from agent.defrag import sync_session_to_workspace_ontology

        # Test with empty state
        empty_state: dict[str, Any] = {}

        try:
            sync_session_to_workspace_ontology(
                workspace=tmp_path,
                session_id="session-001",
                session_state=empty_state,
            )
        except Exception as e:
            pytest.fail(f"sync_session_to_workspace_ontology raised an exception with empty state: {e}")

        # Test with malformed state (missing expected keys)
        malformed_state: dict[str, Any] = {
            "session_id": "session-001",
            "entities": "not a dict",  # Wrong type
            "claims": None,
        }

        try:
            sync_session_to_workspace_ontology(
                workspace=tmp_path,
                session_id="session-001",
                session_state=malformed_state,
            )
        except Exception as e:
            pytest.fail(f"sync_session_to_workspace_ontology raised an exception with malformed state: {e}")

        # Verify no crash means we reach here
        assert True


# ---------------------------------------------------------------------------
# Prompt Tests
# ---------------------------------------------------------------------------


class TestPromptOntologySection:
    """Tests for WORKSPACE_ONTOLOGY_SECTION in prompts."""

    def test_prompt_includes_ontology_section(self) -> None:
        """Call build_system_prompt() and verify the output contains "Workspace-Global Ontology" text."""
        from agent.prompts import build_system_prompt

        prompt = build_system_prompt(recursive=False)

        # Verify the ontology section is included
        assert "Workspace-Global Ontology" in prompt
        assert ".openplanter/ontology.json" in prompt
        assert "cross_investigation_context" in prompt
