"""Conformance tests for session contract v2 compliance.

Verifies that Python writers produce spec-conformant v2 replay and event records.
"""

import json
import tempfile
from pathlib import Path

import pytest

from agent.replay_log import ReplayLogger, TRACE_SCHEMA_VERSION, TRACE_ENVELOPE


class TestReplayV2Conformance:
    """Verify ReplayLogger produces v2-conformant replay entries."""

    def _write_3_turn_session(self, session_dir: Path) -> Path:
        """Write a 3-turn session using ReplayLogger and return the replay path."""
        replay_path = session_dir / "replay.jsonl"
        
        logger = ReplayLogger(
            path=replay_path,
            session_id="test-session-001",
            turn_id="turn-001",
        )
        
        # Write header
        logger.write_header(
            provider="openai",
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            system_prompt="You are a helpful assistant.",
            tool_defs=[],
        )
        
        # Turn 1
        logger.turn_id = "turn-001"
        logger.log_call(
            depth=0,
            step=1,
            messages=[{"role": "user", "content": "Hello"}],
            response={"role": "assistant", "content": "Hi there!"},
            input_tokens=10,
            output_tokens=5,
            elapsed_sec=0.5,
        )
        
        # Turn 2
        logger.turn_id = "turn-002"
        logger.log_call(
            depth=0,
            step=2,
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "Tell me about X"},
            ],
            response={"role": "assistant", "content": "X is..."},
            input_tokens=20,
            output_tokens=15,
            elapsed_sec=1.2,
        )
        
        # Turn 3
        logger.turn_id = "turn-003"
        logger.log_call(
            depth=0,
            step=3,
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "Tell me about X"},
                {"role": "assistant", "content": "X is..."},
                {"role": "user", "content": "Summarize"},
            ],
            response={"role": "assistant", "content": "Summary..."},
            input_tokens=30,
            output_tokens=10,
            elapsed_sec=0.8,
        )
        
        return replay_path

    def test_all_entries_have_schema_version(self, tmp_path):
        """Every replay entry must have schema_version field."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        for i, record in enumerate(records):
            assert "schema_version" in record, f"Record {i} missing schema_version"
            assert record["schema_version"] == TRACE_SCHEMA_VERSION, (
                f"Record {i} has schema_version {record['schema_version']}, expected {TRACE_SCHEMA_VERSION}"
            )

    def test_all_entries_have_envelope(self, tmp_path):
        """Every replay entry must have envelope field."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        for i, record in enumerate(records):
            assert "envelope" in record, f"Record {i} missing envelope"
            assert record["envelope"] == TRACE_ENVELOPE

    def test_all_entries_have_event_id(self, tmp_path):
        """Every replay entry must have a non-empty event_id."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        event_ids = set()
        for i, record in enumerate(records):
            assert "event_id" in record, f"Record {i} missing event_id"
            assert record["event_id"], f"Record {i} has empty event_id"
            event_ids.add(record["event_id"])
        
        # All event_ids should be unique
        assert len(event_ids) == len(records), "Duplicate event_ids found"

    def test_all_entries_have_turn_id(self, tmp_path):
        """Every replay entry must have turn_id."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        for i, record in enumerate(records):
            assert "turn_id" in record, f"Record {i} missing turn_id"

    def test_all_entries_have_channel(self, tmp_path):
        """Every replay entry must have channel field."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        for i, record in enumerate(records):
            assert "channel" in record, f"Record {i} missing channel"
            assert record["channel"] == "replay"

    def test_all_entries_have_provenance(self, tmp_path):
        """Every replay entry must have provenance with source_refs."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        for i, record in enumerate(records):
            assert "provenance" in record, f"Record {i} missing provenance"
            prov = record["provenance"]
            assert "source_refs" in prov, f"Record {i} provenance missing source_refs"
            assert "evidence_refs" in prov, f"Record {i} provenance missing evidence_refs"

    def test_call_entries_have_generated_from_with_provider(self, tmp_path):
        """Call entries' provenance.generated_from must include provider and model."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        call_records = [r for r in records if r.get("type") == "call" or 
                       (r.get("compat", {}).get("legacy_kind") == "call")]
        assert len(call_records) == 3, f"Expected 3 call records, got {len(call_records)}"
        
        for i, record in enumerate(call_records):
            gen = record.get("provenance", {}).get("generated_from", {})
            assert "provider" in gen, f"Call record {i} missing generated_from.provider"
            assert "model" in gen, f"Call record {i} missing generated_from.model"
            assert gen["provider"] == "openai", f"Call record {i} has wrong provider"
            assert gen["model"] == "gpt-4o", f"Call record {i} has wrong model"

    def test_header_has_actor_with_provider(self, tmp_path):
        """Header entry actor must include provider and model."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        header = next((r for r in records if r.get("type") == "header" or 
                       r.get("event_type") == "session.started"), None)
        assert header is not None, "No header record found"
        
        actor = header.get("actor", {})
        assert actor.get("provider") == "openai"
        assert actor.get("model") == "gpt-4o"

    def test_call_entries_have_actor_with_provider(self, tmp_path):
        """Call entries' actor must include provider and model."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        call_records = [r for r in records if r.get("type") == "call"]
        for i, record in enumerate(call_records):
            actor = record.get("actor", {})
            assert "provider" in actor, f"Call record {i} actor missing provider"
            assert "model" in actor, f"Call record {i} actor missing model"

    def test_compat_block_present(self, tmp_path):
        """Every entry must have compat block with legacy_kind."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        for i, record in enumerate(records):
            assert "compat" in record, f"Record {i} missing compat"
            compat = record["compat"]
            assert "legacy_kind" in compat, f"Record {i} compat missing legacy_kind"

    def test_session_id_present(self, tmp_path):
        """Every entry must have session_id."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        for i, record in enumerate(records):
            assert "session_id" in record, f"Record {i} missing session_id"
            assert record["session_id"] == "test-session-001"

    def test_turn_ids_match_assigned_turns(self, tmp_path):
        """Call entries' turn_ids should match the turn assigned at write time."""
        replay_path = self._write_3_turn_session(tmp_path)
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        
        call_records = [r for r in records if r.get("type") == "call"]
        expected_turns = ["turn-001", "turn-002", "turn-003"]
        
        for i, (record, expected_turn) in enumerate(zip(call_records, expected_turns)):
            assert record.get("turn_id") == expected_turn, (
                f"Call record {i} has turn_id {record.get('turn_id')}, expected {expected_turn}"
            )
