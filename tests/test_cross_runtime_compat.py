"""Cross-runtime compatibility tests.

Verifies that session fixtures from different runtimes and schema versions
can be read by the Python replay reader without errors.
"""

import json
from pathlib import Path

import pytest

from agent.replay_log import ReplayLogger, TRACE_SCHEMA_VERSION, TRACE_ENVELOPE

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_replay_records(fixture_path: Path) -> list[dict]:
    """Load all records from a replay fixture file."""
    records = []
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


class TestLegacyPythonReplayCompat:
    """Verify legacy Python v1 replay files can be read."""

    @pytest.fixture
    def records(self):
        return load_replay_records(FIXTURES_DIR / "legacy_python_replay.jsonl")

    def test_records_loadable(self, records):
        assert len(records) == 3  # 1 header + 2 calls

    def test_header_recognized(self, records):
        header = records[0]
        assert header["type"] == "header"
        assert header["provider"] == "openai"

    def test_call_records_have_seq(self, records):
        calls = [r for r in records if r.get("type") == "call"]
        assert len(calls) == 2
        assert calls[0]["seq"] == 0
        assert calls[1]["seq"] == 1

    def test_delta_encoding(self, records):
        calls = [r for r in records if r.get("type") == "call"]
        assert "messages_snapshot" in calls[0]
        assert "messages_delta" in calls[1]


class TestDesktopV1ReplayCompat:
    """Verify desktop v1 bare replay entries can be read."""

    @pytest.fixture
    def records(self):
        return load_replay_records(FIXTURES_DIR / "desktop_v1_replay.jsonl")

    def test_records_loadable(self, records):
        assert len(records) == 2

    def test_step_summary_entry(self, records):
        step = records[0]
        assert step["role"] == "step-summary"
        assert step["step_number"] == 1
        assert step["step_tokens_in"] == 100

    def test_assistant_entry(self, records):
        assistant = records[1]
        assert assistant["role"] == "assistant"
        assert assistant["is_rendered"] is True


class TestPythonV2ReplayCompat:
    """Verify Python v2 envelope replay files can be read."""

    @pytest.fixture
    def records(self):
        return load_replay_records(FIXTURES_DIR / "python_v2_replay.jsonl")

    def test_records_loadable(self, records):
        assert len(records) == 2

    def test_v2_envelope_fields(self, records):
        for record in records:
            assert record["schema_version"] == 2
            assert record["envelope"] == TRACE_ENVELOPE
            assert "event_id" in record
            assert "session_id" in record

    def test_provenance_present(self, records):
        for record in records:
            assert "provenance" in record
            prov = record["provenance"]
            assert "source_refs" in prov
            assert "evidence_refs" in prov

    def test_compat_present(self, records):
        for record in records:
            assert "compat" in record
            assert "legacy_kind" in record["compat"]


class TestDesktopV2ReplayCompat:
    """Verify desktop v2 envelope replay files can be read."""

    @pytest.fixture
    def records(self):
        return load_replay_records(FIXTURES_DIR / "desktop_v2_replay.jsonl")

    def test_records_loadable(self, records):
        assert len(records) == 2

    def test_v2_envelope_fields(self, records):
        for record in records:
            assert record["schema_version"] == 2
            assert record["envelope"] == "openplanter.trace.replay.v2"

    def test_event_ids_present(self, records):
        event_ids = [r["event_id"] for r in records]
        assert len(set(event_ids)) == 2  # unique

    def test_turn_id_present(self, records):
        for record in records:
            assert record.get("turn_id") is not None


class TestCrossFormatCanonical:
    """Verify all fixture formats produce readable records with key fields."""

    FIXTURE_FILES = [
        "legacy_python_replay.jsonl",
        "desktop_v1_replay.jsonl",
        "python_v2_replay.jsonl",
        "desktop_v2_replay.jsonl",
    ]

    @pytest.mark.parametrize("fixture_name", FIXTURE_FILES)
    def test_all_fixtures_parseable(self, fixture_name):
        records = load_replay_records(FIXTURES_DIR / fixture_name)
        assert len(records) >= 2, f"{fixture_name} has fewer than 2 records"

    @pytest.mark.parametrize("fixture_name", FIXTURE_FILES)
    def test_all_records_valid_json(self, fixture_name):
        path = FIXTURES_DIR / fixture_name
        for i, line in enumerate(path.read_text().splitlines()):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"{fixture_name} line {i+1} is not valid JSON")

    @pytest.mark.parametrize("fixture_name", FIXTURE_FILES)
    def test_non_header_records_have_seq(self, fixture_name):
        """All non-header records should have a seq field."""
        records = load_replay_records(FIXTURES_DIR / fixture_name)
        for record in records:
            if record.get("type") == "header" or record.get("event_type") == "session.started":
                continue
            assert "seq" in record, f"Non-header record in {fixture_name} missing seq"


class TestReplayLoggerCanReadOwnOutput:
    """Verify ReplayLogger can hydrate state from its own v2 output."""

    def test_hydrate_from_v2_output(self, tmp_path):
        replay_path = tmp_path / "replay.jsonl"
        
        # Write some entries
        logger1 = ReplayLogger(
            path=replay_path,
            session_id="test-hydrate",
            turn_id="turn-001",
        )
        logger1.write_header(
            provider="openai",
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            system_prompt="Test",
            tool_defs=[],
        )
        logger1.log_call(
            depth=0, step=1,
            messages=[{"role": "user", "content": "Hello"}],
            response={"role": "assistant", "content": "Hi"},
            input_tokens=5, output_tokens=3, elapsed_sec=0.1,
        )
        
        # Create a new logger on the same file — it should hydrate state
        logger2 = ReplayLogger(
            path=replay_path,
            session_id="test-hydrate",
            turn_id="turn-002",
        )
        
        # Should recognize existing header and call
        assert logger2._has_header is True
        assert logger2._has_call is True
        assert logger2._last_msg_count == 1  # 1 message in snapshot
        
        # Second call should use delta encoding
        logger2.log_call(
            depth=0, step=2,
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "More"},
            ],
            response={"role": "assistant", "content": "Response"},
            input_tokens=10, output_tokens=5, elapsed_sec=0.2,
        )
        
        # Verify delta encoding was used
        records = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
        last_call = [r for r in records if r.get("type") == "call"][-1]
        # Should have messages_delta, not messages_snapshot
        payload = last_call.get("payload", last_call)
        assert payload.get("messages_delta") is not None or "messages_delta" in last_call
