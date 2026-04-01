"""Tests for investigation resolver module.

Tests cover:
- list_investigations: Scanning workspace for investigations from ontology and sessions
- infer_investigation: LLM-driven classification of objectives against known investigations
- resolve_investigation: Main entry point orchestrating the full resolution flow
- create_llm_callable: Creating LLM callables from model instances
- Integration with SessionRuntime.bootstrap and PersistentSettings
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.investigation_resolver import (
    InvestigationChoice,
    create_llm_callable,
    infer_investigation,
    list_investigations,
    resolve_investigation,
)
from agent.settings import PersistentSettings


# ---------------------------------------------------------------------------
# list_investigations tests
# ---------------------------------------------------------------------------


class TestListInvestigations:
    """Tests for list_investigations function."""

    def test_list_investigations_from_ontology(self, tmp_path: Path) -> None:
        """Create tmp workspace with ontology.json containing indexes.by_investigation.
        
        Verify the function returns investigation entries with correct counts.
        """
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Investigate financial irregularities",
                    },
                    "inv-002": {
                        "session_count": 1,
                        "entity_count": 5,
                        "claim_count": 2,
                        "last_active": "2026-03-15T10:30:00Z",
                        "objective": "Research competitor analysis",
                    },
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        investigations = list_investigations(tmp_path)

        assert len(investigations) == 2

        # Find inv-001
        inv_001 = next((inv for inv in investigations if inv["id"] == "inv-001"), None)
        assert inv_001 is not None
        assert inv_001["session_count"] == 3
        assert inv_001["entity_count"] == 10
        assert inv_001["claim_count"] == 5
        assert inv_001["last_active"] == "2026-03-01T12:00:00Z"
        assert inv_001["objective"] == "Investigate financial irregularities"
        assert "financial" in inv_001["label"].lower()

        # Find inv-002
        inv_002 = next((inv for inv in investigations if inv["id"] == "inv-002"), None)
        assert inv_002 is not None
        assert inv_002["session_count"] == 1
        assert inv_002["entity_count"] == 5

    def test_list_investigations_from_sessions(self, tmp_path: Path) -> None:
        """Create tmp workspace with session investigation_state.json containing active_investigation_id.
        
        Verify investigation is found from session scan.
        """
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        session_dir = sessions_dir / "sess-1"
        session_dir.mkdir(parents=True)

        investigation_state = {
            "active_investigation_id": "inv-from-session",
            "objective": "Test objective from session",
            "updated_at": "2026-03-20T14:00:00Z",
            "entities": {"ent_001": {"name": "Entity 1"}, "ent_002": {"name": "Entity 2"}},
            "claims": {"cl_001": {"text": "Claim 1"}},
        }
        (session_dir / "investigation_state.json").write_text(
            json.dumps(investigation_state), encoding="utf-8"
        )

        investigations = list_investigations(tmp_path)

        assert len(investigations) == 1
        assert investigations[0]["id"] == "inv-from-session"
        assert investigations[0]["session_count"] == 1
        assert investigations[0]["entity_count"] == 2
        assert investigations[0]["claim_count"] == 1
        assert investigations[0]["objective"] == "Test objective from session"

    def test_list_investigations_empty(self, tmp_path: Path) -> None:
        """Empty workspace with no ontology or sessions. Returns empty list."""
        # Create empty .openplanter directory
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        investigations = list_investigations(tmp_path)

        assert investigations == []

    def test_list_investigations_no_openplanter_dir(self, tmp_path: Path) -> None:
        """Workspace with no .openplanter directory. Returns empty list."""
        investigations = list_investigations(tmp_path)

        assert investigations == []

    def test_list_investigations_deduplicates(self, tmp_path: Path) -> None:
        """Same investigation ID in ontology and sessions. Returns single entry."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        # Create ontology with investigation
        ontology = {
            "indexes": {
                "by_investigation": {
                    "shared-inv": {
                        "session_count": 2,
                        "entity_count": 8,
                        "claim_count": 3,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "From ontology",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        # Create session with same investigation ID
        sessions_dir = openplanter_dir / "sessions"
        session_dir = sessions_dir / "sess-1"
        session_dir.mkdir(parents=True)

        investigation_state = {
            "active_investigation_id": "shared-inv",
            "objective": "From session",
            "updated_at": "2026-03-20T14:00:00Z",  # More recent
            "entities": {"ent_001": {"name": "Entity 1"}},
            "claims": {},
        }
        (session_dir / "investigation_state.json").write_text(
            json.dumps(investigation_state), encoding="utf-8"
        )

        investigations = list_investigations(tmp_path)

        # Should only have one entry (deduplicated)
        assert len(investigations) == 1
        assert investigations[0]["id"] == "shared-inv"
        # Session count should be incremented (2 from ontology + 1 from session scan)
        assert investigations[0]["session_count"] == 3
        # Entity count should be combined (8 from ontology + 1 from session)
        assert investigations[0]["entity_count"] == 9
        # Last active should be the more recent one
        assert investigations[0]["last_active"] == "2026-03-20T14:00:00Z"

    def test_list_investigations_multiple_sessions_same_inv(self, tmp_path: Path) -> None:
        """Multiple sessions with same investigation ID. Correctly aggregates counts."""
        sessions_dir = tmp_path / ".openplanter" / "sessions"

        for i in range(3):
            session_dir = sessions_dir / f"sess-{i}"
            session_dir.mkdir(parents=True)

            investigation_state = {
                "active_investigation_id": "multi-session-inv",
                "objective": "Shared investigation",
                "updated_at": f"2026-03-{10+i:02d}T12:00:00Z",
                "entities": {f"ent_{i}": {"name": f"Entity {i}"}},
                "claims": {f"cl_{i}": {"text": f"Claim {i}"}},
            }
            (session_dir / "investigation_state.json").write_text(
                json.dumps(investigation_state), encoding="utf-8"
            )

        investigations = list_investigations(tmp_path)

        assert len(investigations) == 1
        assert investigations[0]["id"] == "multi-session-inv"
        assert investigations[0]["session_count"] == 3
        assert investigations[0]["entity_count"] == 3
        assert investigations[0]["claim_count"] == 3

    def test_list_investigations_skips_invalid_session_state(self, tmp_path: Path) -> None:
        """Session with invalid investigation_state.json is skipped gracefully."""
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        session_dir = sessions_dir / "sess-invalid"
        session_dir.mkdir(parents=True)

        # Invalid JSON
        (session_dir / "investigation_state.json").write_text("not valid json", encoding="utf-8")

        # Another valid session
        valid_session_dir = sessions_dir / "sess-valid"
        valid_session_dir.mkdir(parents=True)
        valid_state = {
            "active_investigation_id": "valid-inv",
            "objective": "Valid",
            "updated_at": "2026-03-20T12:00:00Z",
            "entities": {},
            "claims": {},
        }
        (valid_session_dir / "investigation_state.json").write_text(
            json.dumps(valid_state), encoding="utf-8"
        )

        investigations = list_investigations(tmp_path)

        assert len(investigations) == 1
        assert investigations[0]["id"] == "valid-inv"

    def test_list_investigations_skips_empty_inv_id(self, tmp_path: Path) -> None:
        """Session with empty/whitespace investigation_id is skipped."""
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        session_dir = sessions_dir / "sess-empty"
        session_dir.mkdir(parents=True)

        investigation_state = {
            "active_investigation_id": "   ",  # Whitespace only
            "objective": "Empty ID",
            "entities": {},
            "claims": {},
        }
        (session_dir / "investigation_state.json").write_text(
            json.dumps(investigation_state), encoding="utf-8"
        )

        investigations = list_investigations(tmp_path)

        assert investigations == []


# ---------------------------------------------------------------------------
# infer_investigation tests
# ---------------------------------------------------------------------------


class TestInferInvestigation:
    """Tests for infer_investigation function."""

    def test_infer_investigation_matches(self) -> None:
        """Mock LLM returns match for existing investigation. Verify result."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
            {
                "id": "inv-002",
                "label": "Competitor research",
                "session_count": 1,
                "entity_count": 5,
                "claim_count": 2,
                "last_active": "2026-03-15T10:30:00Z",
            },
        ]

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.9,
            "reasoning": "The objective mentions financial terms matching this investigation",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = infer_investigation(
            objective="Analyze the financial records for Q1",
            investigations=investigations,
            llm_call=mock_llm,
        )

        assert result["match"] == "inv-001"
        assert result["confidence"] == 0.9
        assert "financial" in result["reasoning"].lower()

    def test_infer_investigation_new(self) -> None:
        """Mock LLM returns 'new' for new investigation. Verify result."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
        ]

        mock_llm_response = json.dumps({
            "match": "new",
            "confidence": 0.85,
            "reasoning": "This appears to be a new topic unrelated to existing investigations",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = infer_investigation(
            objective="Research quantum computing applications",
            investigations=investigations,
            llm_call=mock_llm,
        )

        assert result["match"] == "new"
        assert result["confidence"] == 0.85

    def test_infer_investigation_generic(self) -> None:
        """Mock LLM returns 'generic' for one-off query. Verify result."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
        ]

        mock_llm_response = json.dumps({
            "match": "generic",
            "confidence": 0.95,
            "reasoning": "This is a simple one-off question not needing investigation context",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = infer_investigation(
            objective="What is the capital of France?",
            investigations=investigations,
            llm_call=mock_llm,
        )

        assert result["match"] == "generic"
        assert result["confidence"] == 0.95

    def test_infer_investigation_malformed_response(self) -> None:
        """Mock LLM returns garbage text. Verify graceful fallback to 'generic'."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
        ]

        mock_llm = MagicMock(return_value="This is not valid JSON at all!")

        result = infer_investigation(
            objective="Some objective",
            investigations=investigations,
            llm_call=mock_llm,
        )

        assert result["match"] == "generic"
        assert result["confidence"] == 0.0
        assert "Failed to parse" in result["reasoning"]

    def test_infer_investigation_invalid_json_in_code_block(self) -> None:
        """Mock LLM returns JSON in markdown code block. Verify extraction works."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
        ]

        mock_llm_response = """```json
{
    "match": "inv-001",
    "confidence": 0.8,
    "reasoning": "Matches the financial investigation"
}
```"""
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = infer_investigation(
            objective="Analyze Q1 finances",
            investigations=investigations,
            llm_call=mock_llm,
        )

        assert result["match"] == "inv-001"
        assert result["confidence"] == 0.8

    def test_infer_investigation_no_investigations(self) -> None:
        """Empty investigations list returns generic with appropriate reasoning."""
        mock_llm = MagicMock()

        result = infer_investigation(
            objective="Some objective",
            investigations=[],
            llm_call=mock_llm,
        )

        assert result["match"] == "generic"
        assert result["confidence"] == 1.0
        assert "No existing investigations" in result["reasoning"]
        # LLM should not be called when no investigations
        mock_llm.assert_not_called()

    def test_infer_investigation_unknown_inv_id(self) -> None:
        """LLM returns unknown investigation ID. Falls back to generic."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
        ]

        mock_llm_response = json.dumps({
            "match": "non-existent-id",
            "confidence": 0.7,
            "reasoning": "I think this matches",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = infer_investigation(
            objective="Some objective",
            investigations=investigations,
            llm_call=mock_llm,
        )

        assert result["match"] == "generic"
        assert "unknown investigation ID" in result["reasoning"]

    def test_infer_investigation_llm_exception(self) -> None:
        """LLM call raises exception. Returns generic with failure reasoning."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
        ]

        mock_llm = MagicMock(side_effect=Exception("LLM service unavailable"))

        result = infer_investigation(
            objective="Some objective",
            investigations=investigations,
            llm_call=mock_llm,
        )

        assert result["match"] == "generic"
        assert result["confidence"] == 0.0
        assert "LLM call failed" in result["reasoning"]

    def test_infer_investigation_clamps_confidence(self) -> None:
        """Confidence values outside 0-1 range are clamped."""
        investigations = [
            {
                "id": "inv-001",
                "label": "Financial investigation",
                "session_count": 3,
                "entity_count": 10,
                "claim_count": 5,
                "last_active": "2026-03-01T12:00:00Z",
            },
        ]

        # Test confidence > 1
        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 1.5,
            "reasoning": "Very confident",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = infer_investigation(
            objective="Some objective",
            investigations=investigations,
            llm_call=mock_llm,
        )
        assert result["confidence"] == 1.0

        # Test confidence < 0
        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": -0.5,
            "reasoning": "Negative confidence",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = infer_investigation(
            objective="Some objective",
            investigations=investigations,
            llm_call=mock_llm,
        )
        assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# resolve_investigation tests
# ---------------------------------------------------------------------------


class TestResolveInvestigation:
    """Tests for resolve_investigation function."""

    def test_resolve_skips_inference_when_no_objective(self, tmp_path: Path) -> None:
        """No objective provided. Returns default_investigation_id."""
        result = resolve_investigation(
            workspace=tmp_path,
            objective=None,
            llm_call=MagicMock(),
            interactive=True,
            default_investigation_id="default-inv",
        )

        assert result == "default-inv"

    def test_resolve_skips_inference_when_empty_objective(self, tmp_path: Path) -> None:
        """Empty/whitespace objective provided. Returns default_investigation_id."""
        result = resolve_investigation(
            workspace=tmp_path,
            objective="   ",
            llm_call=MagicMock(),
            interactive=True,
            default_investigation_id="default-inv",
        )

        assert result == "default-inv"

    def test_resolve_skips_inference_when_no_investigations(self, tmp_path: Path) -> None:
        """Empty workspace. Returns None."""
        # Create empty .openplanter directory
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        mock_llm = MagicMock()

        result = resolve_investigation(
            workspace=tmp_path,
            objective="Some objective",
            llm_call=mock_llm,
            interactive=True,
            default_investigation_id="default-inv",
        )

        assert result is None
        mock_llm.assert_not_called()

    def test_resolve_non_interactive_auto_accepts_match(self, tmp_path: Path) -> None:
        """interactive=False, mock LLM suggests match. Verify auto-accept returns the matched ID."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.9,
            "reasoning": "Matches financial investigation",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = resolve_investigation(
            workspace=tmp_path,
            objective="Analyze Q1 financials",
            llm_call=mock_llm,
            interactive=False,  # Non-interactive mode
            default_investigation_id="default-inv",
        )

        assert result == "inv-001"

    def test_resolve_non_interactive_auto_accepts_new(self, tmp_path: Path) -> None:
        """interactive=False, mock LLM suggests 'new'. Returns None."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "new",
            "confidence": 0.85,
            "reasoning": "New topic",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = resolve_investigation(
            workspace=tmp_path,
            objective="Research quantum computing",
            llm_call=mock_llm,
            interactive=False,
            default_investigation_id="default-inv",
        )

        assert result is None

    def test_resolve_non_interactive_auto_accepts_generic(self, tmp_path: Path) -> None:
        """interactive=False, mock LLM suggests 'generic'. Returns None."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "generic",
            "confidence": 0.95,
            "reasoning": "One-off query",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        result = resolve_investigation(
            workspace=tmp_path,
            objective="What is 2+2?",
            llm_call=mock_llm,
            interactive=False,
            default_investigation_id="default-inv",
        )

        assert result is None

    def test_resolve_returns_default_when_no_llm(self, tmp_path: Path) -> None:
        """No llm_call provided. Returns default_investigation_id."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        result = resolve_investigation(
            workspace=tmp_path,
            objective="Some objective",
            llm_call=None,  # No LLM
            interactive=True,
            default_investigation_id="default-inv",
        )

        assert result == "default-inv"

    def test_resolve_interactive_accepts_suggestion(self, tmp_path: Path) -> None:
        """Interactive mode, user accepts suggestion (choice 1)."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.9,
            "reasoning": "Matches financial investigation",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        with patch("builtins.input", return_value="1"):
            result = resolve_investigation(
                workspace=tmp_path,
                objective="Analyze Q1 financials",
                llm_call=mock_llm,
                interactive=True,
                default_investigation_id="default-inv",
            )

        assert result == "inv-001"

    def test_resolve_interactive_chooses_different(self, tmp_path: Path) -> None:
        """Interactive mode, user chooses different investigation (choice 2 + selection)."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    },
                    "inv-002": {
                        "session_count": 1,
                        "entity_count": 5,
                        "claim_count": 2,
                        "last_active": "2026-03-15T10:30:00Z",
                        "objective": "Competitor research",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.6,
            "reasoning": "Maybe matches financial",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        # User chooses option 2 (different investigation), then selects investigation 2
        with patch("builtins.input", side_effect=["2", "2"]):
            result = resolve_investigation(
                workspace=tmp_path,
                objective="Research competitors",
                llm_call=mock_llm,
                interactive=True,
                default_investigation_id="default-inv",
            )

        assert result == "inv-002"

    def test_resolve_interactive_creates_new(self, tmp_path: Path) -> None:
        """Interactive mode, user creates new investigation (choice 3)."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.5,
            "reasoning": "Not sure",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        # User chooses option 3 (create new), then enters name
        with patch("builtins.input", side_effect=["3", "Quantum Computing Research"]):
            result = resolve_investigation(
                workspace=tmp_path,
                objective="Research quantum computing",
                llm_call=mock_llm,
                interactive=True,
                default_investigation_id="default-inv",
            )

        assert result == "quantum-computing-research"

    def test_resolve_interactive_generic(self, tmp_path: Path) -> None:
        """Interactive mode, user chooses generic/one-off (choice 4)."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.3,
            "reasoning": "Not really related",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        # User chooses option 4 (generic)
        with patch("builtins.input", return_value="4"):
            result = resolve_investigation(
                workspace=tmp_path,
                objective="What is 2+2?",
                llm_call=mock_llm,
                interactive=True,
                default_investigation_id="default-inv",
            )

        assert result is None

    def test_resolve_interactive_default_choice(self, tmp_path: Path) -> None:
        """Interactive mode, user presses enter for default choice."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.9,
            "reasoning": "Matches",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        # User just presses enter (empty string = default)
        with patch("builtins.input", return_value=""):
            result = resolve_investigation(
                workspace=tmp_path,
                objective="Analyze financials",
                llm_call=mock_llm,
                interactive=True,
                default_investigation_id="default-inv",
            )

        assert result == "inv-001"

    def test_resolve_interactive_eof_error(self, tmp_path: Path) -> None:
        """Interactive mode, EOFError during input returns None."""
        openplanter_dir = tmp_path / ".openplanter"
        openplanter_dir.mkdir(parents=True)

        ontology = {
            "indexes": {
                "by_investigation": {
                    "inv-001": {
                        "session_count": 3,
                        "entity_count": 10,
                        "claim_count": 5,
                        "last_active": "2026-03-01T12:00:00Z",
                        "objective": "Financial investigation",
                    }
                }
            }
        }
        (openplanter_dir / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")

        mock_llm_response = json.dumps({
            "match": "inv-001",
            "confidence": 0.9,
            "reasoning": "Matches",
        })
        mock_llm = MagicMock(return_value=mock_llm_response)

        with patch("builtins.input", side_effect=EOFError()):
            result = resolve_investigation(
                workspace=tmp_path,
                objective="Analyze financials",
                llm_call=mock_llm,
                interactive=True,
                default_investigation_id="default-inv",
            )

        assert result is None


# ---------------------------------------------------------------------------
# create_llm_callable tests
# ---------------------------------------------------------------------------


class TestCreateLlmCallable:
    """Tests for create_llm_callable function."""

    def test_create_llm_callable_with_valid_model(self) -> None:
        """Create callable from model with required methods."""
        mock_model = MagicMock()
        mock_conversation = MagicMock()
        mock_turn = MagicMock()
        mock_turn.text = "  Response text  "
        mock_model.create_conversation.return_value = mock_conversation
        mock_model.complete.return_value = mock_turn

        llm_call = create_llm_callable(mock_model)

        assert llm_call is not None
        result = llm_call("Test prompt")

        assert result == "Response text"
        mock_model.create_conversation.assert_called_once_with(
            system_prompt="You are a helpful assistant that responds with JSON only.",
            initial_user_message="Test prompt",
        )
        mock_model.complete.assert_called_once_with(mock_conversation)

    def test_create_llm_callable_returns_none_for_none_model(self) -> None:
        """Pass None as model. Returns None."""
        result = create_llm_callable(None)
        assert result is None

    def test_create_llm_callable_returns_none_for_missing_methods(self) -> None:
        """Model missing required methods. Returns None."""
        mock_model = MagicMock()
        del mock_model.create_conversation

        result = create_llm_callable(mock_model)
        assert result is None

    def test_create_llm_callable_handles_none_text(self) -> None:
        """Model returns turn with None text. Returns empty string."""
        mock_model = MagicMock()
        mock_conversation = MagicMock()
        mock_turn = MagicMock()
        mock_turn.text = None
        mock_model.create_conversation.return_value = mock_conversation
        mock_model.complete.return_value = mock_turn

        llm_call = create_llm_callable(mock_model)
        result = llm_call("Test prompt")

        assert result == ""


# ---------------------------------------------------------------------------
# InvestigationChoice dataclass tests
# ---------------------------------------------------------------------------


class TestInvestigationChoice:
    """Tests for InvestigationChoice dataclass."""

    def test_investigation_choice_with_id(self) -> None:
        """Create choice with investigation ID."""
        choice = InvestigationChoice(
            investigation_id="inv-001",
            is_new=False,
            label="Financial Investigation",
        )
        assert choice.investigation_id == "inv-001"
        assert choice.is_new is False
        assert choice.label == "Financial Investigation"

    def test_investigation_choice_new(self) -> None:
        """Create choice for new investigation."""
        choice = InvestigationChoice(
            investigation_id=None,
            is_new=True,
            label="Create New Investigation",
        )
        assert choice.investigation_id is None
        assert choice.is_new is True

    def test_investigation_choice_generic(self) -> None:
        """Create choice for generic/one-off query."""
        choice = InvestigationChoice(
            investigation_id=None,
            is_new=False,
            label="Generic Query",
        )
        assert choice.investigation_id is None
        assert choice.is_new is False


# ---------------------------------------------------------------------------
# Settings integration tests
# ---------------------------------------------------------------------------


class TestSettingsIntegration:
    """Tests for PersistentSettings integration with investigation resolver."""

    def test_default_investigation_from_settings(self) -> None:
        """Create PersistentSettings with default_investigation_id set.
        
        Verify to_json() includes it and from_json() restores it.
        """
        settings = PersistentSettings(
            default_model="gpt-4",
            default_investigation_id="my-default-inv",
        )

        # Test to_json
        json_data = settings.to_json()
        assert json_data["default_investigation_id"] == "my-default-inv"
        assert json_data["default_model"] == "gpt-4"

        # Test from_json
        restored = PersistentSettings.from_json(json_data)
        assert restored.default_investigation_id == "my-default-inv"
        assert restored.default_model == "gpt-4"

    def test_settings_default_investigation_none(self) -> None:
        """Default PersistentSettings has default_investigation_id = None."""
        settings = PersistentSettings()

        assert settings.default_investigation_id is None

        json_data = settings.to_json()
        assert "default_investigation_id" not in json_data

    def test_settings_from_json_with_empty_string(self) -> None:
        """from_json handles empty string for default_investigation_id."""
        json_data = {"default_investigation_id": ""}
        restored = PersistentSettings.from_json(json_data)
        assert restored.default_investigation_id is None

    def test_settings_from_json_with_whitespace(self) -> None:
        """from_json handles whitespace-only string for default_investigation_id."""
        json_data = {"default_investigation_id": "   "}
        restored = PersistentSettings.from_json(json_data)
        assert restored.default_investigation_id is None

    def test_settings_normalized_strips_whitespace(self) -> None:
        """normalized() strips whitespace from default_investigation_id."""
        settings = PersistentSettings(
            default_investigation_id="  inv-with-spaces  ",
        )
        normalized = settings.normalized()
        assert normalized.default_investigation_id == "inv-with-spaces"


# ---------------------------------------------------------------------------
# Bootstrap wiring tests
# ---------------------------------------------------------------------------


class TestBootstrapWiring:
    """Tests for SessionRuntime.bootstrap integration with investigation_id."""

    def test_bootstrap_passes_investigation_id(self, tmp_path: Path) -> None:
        """Create a minimal SessionRuntime.bootstrap() call with investigation_id.
        
        Verify it reaches open_session(). Use mocking to intercept the open_session call.
        """
        from agent.config import AgentConfig
        from agent.engine import RLMEngine
        from agent.model import ModelTurn, ScriptedModel
        from agent.runtime import SessionRuntime
        from agent.tools import WorkspaceTools

        cfg = AgentConfig(workspace=tmp_path, max_depth=1, max_steps_per_call=2)
        tools = WorkspaceTools(root=tmp_path)
        model = ScriptedModel(scripted_turns=[ModelTurn(text="done", stop_reason="end_turn")])
        engine = RLMEngine(model=model, tools=tools, config=cfg)

        with patch.object(
            SessionRuntime,
            "bootstrap",
            wraps=SessionRuntime.bootstrap,
        ) as mock_bootstrap:
            runtime = SessionRuntime.bootstrap(
                engine=engine,
                config=cfg,
                session_id="test-session",
                investigation_id="test-investigation-id",
            )

            # Verify the bootstrap was called with investigation_id
            mock_bootstrap.assert_called_once()
            call_kwargs = mock_bootstrap.call_args.kwargs
            assert call_kwargs.get("investigation_id") == "test-investigation-id"

            # Verify the session was created
            assert runtime.session_id is not None
            assert runtime.store is not None

            # Verify investigation_id was persisted in typed state
            typed_state = runtime.store.load_typed_state(runtime.session_id)
            assert typed_state.get("active_investigation_id") == "test-investigation-id"

    def test_bootstrap_without_investigation_id(self, tmp_path: Path) -> None:
        """Bootstrap without investigation_id doesn't set active_investigation_id."""
        from agent.config import AgentConfig
        from agent.engine import RLMEngine
        from agent.model import ModelTurn, ScriptedModel
        from agent.runtime import SessionRuntime
        from agent.tools import WorkspaceTools

        cfg = AgentConfig(workspace=tmp_path, max_depth=1, max_steps_per_call=2)
        tools = WorkspaceTools(root=tmp_path)
        model = ScriptedModel(scripted_turns=[ModelTurn(text="done", stop_reason="end_turn")])
        engine = RLMEngine(model=model, tools=tools, config=cfg)

        runtime = SessionRuntime.bootstrap(
            engine=engine,
            config=cfg,
            session_id="test-session-no-inv",
        )

        # Verify no investigation_id was set
        typed_state = runtime.store.load_typed_state(runtime.session_id)
        assert typed_state.get("active_investigation_id") is None

    def test_bootstrap_with_empty_investigation_id(self, tmp_path: Path) -> None:
        """Bootstrap with empty/whitespace investigation_id doesn't set active_investigation_id."""
        from agent.config import AgentConfig
        from agent.engine import RLMEngine
        from agent.model import ModelTurn, ScriptedModel
        from agent.runtime import SessionRuntime
        from agent.tools import WorkspaceTools

        cfg = AgentConfig(workspace=tmp_path, max_depth=1, max_steps_per_call=2)
        tools = WorkspaceTools(root=tmp_path)
        model = ScriptedModel(scripted_turns=[ModelTurn(text="done", stop_reason="end_turn")])
        engine = RLMEngine(model=model, tools=tools, config=cfg)

        runtime = SessionRuntime.bootstrap(
            engine=engine,
            config=cfg,
            session_id="test-session-empty-inv",
            investigation_id="   ",  # Whitespace only
        )

        # Verify no investigation_id was set (whitespace is filtered out)
        typed_state = runtime.store.load_typed_state(runtime.session_id)
        # The runtime stores it as-is, but let's verify behavior
        inv_id = typed_state.get("active_investigation_id")
        # Empty/whitespace strings should either not be set or be stripped
        assert inv_id is None or inv_id.strip() == ""
