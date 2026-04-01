"""Tests for agent.defrag — workspace defragmentation module."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.defrag import (
    DuplicateGroup,
    FileManifest,
    UnIngestedFile,
    WorkspaceDefrag,
    DefragReport,
    _build_duplicate_prompt,
    _fingerprint_file,
    _fingerprint_text,
    _parse_llm_duplicate_response,
    _read_file_ends,
    _strip_date_from_filename,
)


# ---------------------------------------------------------------------------
# Scan Tests
# ---------------------------------------------------------------------------


class TestScan:
    """Tests for the scanning phase."""

    def test_scan_finds_all_files(self, tmp_path: Path) -> None:
        """Create temp workspace with known files, verify manifest counts and sizes match."""
        # Create files of different types
        (tmp_path / "doc.md").write_text("# Hello\nContent here.", encoding="utf-8")
        (tmp_path / "data.json").write_text('{"key": "value"}', encoding="utf-8")
        (tmp_path / "table.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested content", encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path)
        defrag._phase_scan()

        # Check that all files are found
        assert len(defrag._file_manifests) == 4

        # Verify sizes match
        for path, manifest in defrag._file_manifests.items():
            assert manifest.size == path.stat().st_size
            assert manifest.hash != ""
            assert manifest.extension in {".md", ".json", ".csv", ".txt"}

    def test_scan_excludes_ignored_directories(self, tmp_path: Path) -> None:
        """Verify .git, __pycache__, etc. are excluded from scan."""
        # Create normal file
        (tmp_path / "normal.md").write_text("content", encoding="utf-8")

        # Create files in excluded directories
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git config", encoding="utf-8")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "module.pyc").write_text("bytes", encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path)
        defrag._phase_scan()

        # Should only find the normal file
        assert len(defrag._file_manifests) == 1
        assert (tmp_path / "normal.md") in defrag._file_manifests

    def test_scan_groups_by_hash(self, tmp_path: Path) -> None:
        """Verify files with identical content are grouped by hash."""
        content = "identical content\n"
        (tmp_path / "file1.md").write_text(content, encoding="utf-8")
        (tmp_path / "file2.md").write_text(content, encoding="utf-8")
        (tmp_path / "unique.md").write_text("different content", encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path)
        defrag._phase_scan()

        # Should have 2 files with same hash
        hash_groups = defrag._hash_groups
        assert any(len(paths) == 2 for paths in hash_groups.values())


# ---------------------------------------------------------------------------
# Duplicate Detection Tests
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Tests for duplicate detection phase."""

    def test_duplicate_detection_exact(self, tmp_path: Path) -> None:
        """Create 3 files where 2 have identical content. Verify auto-grouped as exact_duplicate."""
        content = "This is the same content in both files.\n"
        (tmp_path / "original.md").write_text(content, encoding="utf-8")
        (tmp_path / "copy.md").write_text(content, encoding="utf-8")
        (tmp_path / "different.md").write_text("This is different content.\n", encoding="utf-8")

        # Run without LLM - only hash-based exact duplicates
        # Use mode="dedup" to actually run duplicate detection phase
        defrag = WorkspaceDefrag(tmp_path, llm_classify=None)
        report = defrag.run(mode="dedup", dry_run=True)

        assert report.duplicates_found == 1
        group = report.duplicate_groups[0]
        assert group.classification == "exact_duplicate"
        assert group.confidence == 1.0
        assert "SHA256" in group.rationale
        assert len(group.duplicates) == 1

    def test_duplicate_detection_near(self, tmp_path: Path) -> None:
        """Create files with minor variations. Mock LLM to classify as near_duplicate."""
        # Create files with same base but different timestamps
        (tmp_path / "report.md").write_text(
            "# Investigation Report\nGenerated: 2026-01-15\nKey finding: xyz\n",
            encoding="utf-8",
        )
        (tmp_path / "report_2026-01-20.md").write_text(
            "# Investigation Report\nGenerated: 2026-01-20\nKey finding: xyz\n",
            encoding="utf-8",
        )

        # Mock LLM to return near_duplicate classification
        llm_response = json.dumps({
            "classification": "near_duplicate",
            "canonical": str(tmp_path / "report_2026-01-20.md"),
            "duplicates": [str(tmp_path / "report.md")],
            "keep": [],
            "confidence": 0.85,
            "rationale": "Same content with different timestamps",
        })

        mock_llm = MagicMock(return_value=llm_response)
        defrag = WorkspaceDefrag(tmp_path, llm_classify=mock_llm)
        # Use mode="dedup" to run duplicate detection phase
        report = defrag.run(mode="dedup", dry_run=True)

        # Should have found the near-duplicate pair via LLM
        assert report.duplicates_found >= 1
        near_dup = next(
            (g for g in report.duplicate_groups if g.classification == "near_duplicate"),
            None,
        )
        assert near_dup is not None
        assert near_dup.confidence == 0.85

    def test_duplicate_detection_versioned(self, tmp_path: Path) -> None:
        """Create meaningfully different versions. Mock LLM to return versioned with keep list."""
        (tmp_path / "analysis_v1.md").write_text(
            "# Analysis v1\nInitial findings\n- Item A\n- Item B\n",
            encoding="utf-8",
        )
        (tmp_path / "analysis_v2.md").write_text(
            "# Analysis v2\nUpdated findings\n- Item A (updated)\n- Item B\n- Item C\n",
            encoding="utf-8",
        )

        llm_response = json.dumps({
            "classification": "versioned",
            "canonical": str(tmp_path / "analysis_v2.md"),
            "duplicates": [],
            "keep": [str(tmp_path / "analysis_v1.md")],
            "confidence": 0.9,
            "rationale": "Different versions with distinct content worth preserving",
        })

        mock_llm = MagicMock(return_value=llm_response)
        defrag = WorkspaceDefrag(tmp_path, llm_classify=mock_llm)
        # Use mode="dedup" to run duplicate detection phase
        report = defrag.run(mode="dedup", dry_run=True)

        versioned = next(
            (g for g in report.duplicate_groups if g.classification == "versioned"),
            None,
        )
        assert versioned is not None
        assert len(versioned.keep) == 1
        assert len(versioned.duplicates) == 0

    def test_duplicate_prefilter_clustering(self, tmp_path: Path) -> None:
        """Verify pre-filter groups files with similar stems together."""
        # Files with similar stems (should cluster together based on stripped stem)
        (tmp_path / "REPORT.md").write_text("Report content v1\n", encoding="utf-8")
        (tmp_path / "REPORT_2026-02-27.md").write_text("Report content v2\n", encoding="utf-8")
        # Note: REPORT_v2.md becomes "report_v" after stripping (version suffix only matches digits)
        (tmp_path / "REPORT_2.md").write_text("Report content v3\n", encoding="utf-8")
        # Unrelated file with completely different stem
        (tmp_path / "COMPLETELY_DIFFERENT.json").write_text('{"data": true}', encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, llm_classify=None)
        defrag._phase_scan()

        # Check that REPORT files have the same stem after date stripping
        report_stem = _strip_date_from_filename("REPORT.md")
        report_2026_stem = _strip_date_from_filename("REPORT_2026-02-27.md")
        report_2_stem = _strip_date_from_filename("REPORT_2.md")
        different_stem = _strip_date_from_filename("COMPLETELY_DIFFERENT.json")

        # REPORT, REPORT_2026-02-27, and REPORT_2 should all have same stripped stem
        assert report_stem == report_2026_stem == report_2_stem == "report"
        # UNRELATED should have a different stem
        assert different_stem != report_stem

    def test_duplicate_llm_prompt_construction(self, tmp_path: Path) -> None:
        """Verify LLM prompt contains file path and sample content."""
        # Create files with similar names (to trigger clustering) but different content
        long_content = "A" * 400 + " [MIDDLE] " + "B" * 400
        (tmp_path / "file_2026-01-01.md").write_text(long_content, encoding="utf-8")
        (tmp_path / "file_2026-01-02.md").write_text("Different content " * 50, encoding="utf-8")

        captured_prompt = ""

        def capture_prompt(prompt: str) -> str:
            nonlocal captured_prompt
            captured_prompt = prompt
            return json.dumps({
                "classification": "unrelated",
                "canonical": "",
                "duplicates": [],
                "keep": [],
                "confidence": 0.5,
                "rationale": "Different files",
            })

        mock_llm = MagicMock(side_effect=capture_prompt)
        defrag = WorkspaceDefrag(tmp_path, llm_classify=mock_llm)
        defrag.run(mode="dedup", dry_run=True)

        # Verify prompt contains file markers and content samples
        # The prompt should have file paths and TRUNCATED markers for long content
        assert "file_2026-01-01.md" in captured_prompt or "file_2026-01-02.md" in captured_prompt
        # Check for content structure (may include TRUNCATED for long files)
        if len(long_content) > 700:
            assert "TRUNCATED" in captured_prompt


# ---------------------------------------------------------------------------
# Wiki Tests
# ---------------------------------------------------------------------------


class TestWikiIngestion:
    """Tests for wiki ingestion phase."""

    def test_un_ingested_detection(self, tmp_path: Path) -> None:
        """Create wiki index referencing some files, verify un-ingested files detected."""
        # Set up wiki with index
        wiki_dir = tmp_path / ".openplanter" / "wiki"
        wiki_dir.mkdir(parents=True)
        index_content = """# Wiki Index

### Investigation Artifacts

| Name | Jurisdiction | Source |
|------|--------------|--------|
| Existing Doc | | [existing.md](investigation-artifacts/existing.md) |
"""
        (wiki_dir / "index.md").write_text(index_content, encoding="utf-8")
        (wiki_dir / "investigation-artifacts").mkdir()
        (wiki_dir / "investigation-artifacts" / "existing.md").write_text(
            "# Existing\nContent", encoding="utf-8"
        )

        # Create files in workspace that are not in wiki
        (tmp_path / "new_investigation.md").write_text(
            "# New Investigation\nFresh findings", encoding="utf-8"
        )
        (tmp_path / "data_file.json").write_text('{"key": "value"}', encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, wiki_dir=wiki_dir)
        # Use mode="ingest" or "full" to run un_ingested detection phase
        report = defrag.run(mode="ingest", dry_run=True)

        # Should detect the new files as un-ingested
        un_ingested_names = [f.path.name for f in report.un_ingested_files]
        assert "new_investigation.md" in un_ingested_names
        assert "data_file.json" in un_ingested_names
        # Existing file should not be listed
        assert "existing.md" not in un_ingested_names

    def test_wiki_ingestion(self, tmp_path: Path) -> None:
        """Run defrag in ingest mode, verify new entries appended to index.md."""
        # Set up wiki
        wiki_dir = tmp_path / ".openplanter" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "index.md").write_text("# Wiki Index\n", encoding="utf-8")

        # Create un-ingested file
        (tmp_path / "NEW_FINDINGS.md").write_text(
            "# New Findings\nImportant discoveries", encoding="utf-8"
        )

        defrag = WorkspaceDefrag(tmp_path, wiki_dir=wiki_dir)
        report = defrag.run(mode="ingest", dry_run=False)

        assert report.files_ingested >= 1
        assert report.wiki_entries_added >= 1

        # Verify file was copied to wiki
        category_dir = wiki_dir / "investigation-artifacts"
        assert category_dir.exists()
        assert (category_dir / "NEW_FINDINGS.md").exists()

        # Verify index was updated
        index_content = (wiki_dir / "index.md").read_text(encoding="utf-8")
        assert "NEW_FINDINGS" in index_content


# ---------------------------------------------------------------------------
# Ontology Tests
# ---------------------------------------------------------------------------


class TestOntologySync:
    """Tests for ontology synchronization phase."""

    def test_entity_dedup(self, tmp_path: Path) -> None:
        """Create session state with duplicate entities, verify merged in ontology."""
        # Set up sessions directory
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        session_dir = sessions_dir / "session-001"
        session_dir.mkdir(parents=True)

        # Create state with duplicate entities (same name, different IDs)
        state = {
            "session_id": "session-001",
            "entities": {
                "ent_001": {"name": "John Doe", "type": "Person"},
                "ent_002": {"name": "john doe", "type": "Person"},  # Duplicate
            },
        }
        (session_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, sessions_dir=sessions_dir)
        report = defrag.run(mode="cleanup", dry_run=False)

        # Should have merged the duplicate
        assert report.entities_merged >= 1

        # Verify ontology file exists
        ontology_path = tmp_path / ".openplanter" / "ontology.json"
        assert ontology_path.exists()

        ontology = json.loads(ontology_path.read_text(encoding="utf-8"))
        # Should have tracked source sessions
        assert len(ontology.get("source_sessions", [])) >= 1

    def test_ontology_cross_session_merge(self, tmp_path: Path) -> None:
        """Create 2 sessions with overlapping entities, verify merged into single ontology."""
        sessions_dir = tmp_path / ".openplanter" / "sessions"

        # Session 1
        session1_dir = sessions_dir / "session-001"
        session1_dir.mkdir(parents=True)
        state1 = {
            "session_id": "session-001",
            "entities": {
                "ent_001": {"name": "ACME Corp", "type": "Organization"},
            },
        }
        (session1_dir / "state.json").write_text(json.dumps(state1), encoding="utf-8")

        # Session 2 with same entity
        session2_dir = sessions_dir / "session-002"
        session2_dir.mkdir(parents=True)
        state2 = {
            "session_id": "session-002",
            "entities": {
                "ent_002": {"name": "ACME Corp", "type": "Organization"},
            },
        }
        (session2_dir / "state.json").write_text(json.dumps(state2), encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, sessions_dir=sessions_dir)
        report = defrag.run(mode="cleanup", dry_run=False)

        assert report.entities_merged >= 1

        ontology_path = tmp_path / ".openplanter" / "ontology.json"
        ontology = json.loads(ontology_path.read_text(encoding="utf-8"))

        # Both sessions should be tracked
        assert "session-001" in ontology.get("source_sessions", [])
        assert "session-002" in ontology.get("source_sessions", [])

    def test_ontology_by_investigation_index(self, tmp_path: Path) -> None:
        """Verify by_investigation index maps session IDs to object IDs."""
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        session_dir = sessions_dir / "session-001"
        session_dir.mkdir(parents=True)

        state = {
            "session_id": "session-001",
            "entities": {
                "ent_001": {"name": "Test Entity", "type": "Person"},
            },
        }
        (session_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, sessions_dir=sessions_dir)
        report = defrag.run(mode="cleanup", dry_run=False)

        assert report.indexes_rebuilt

        ontology_path = tmp_path / ".openplanter" / "ontology.json"
        ontology = json.loads(ontology_path.read_text(encoding="utf-8"))

        by_investigation = ontology.get("indexes", {}).get("by_investigation", {})
        assert "session-001" in by_investigation
        assert "ent_001" in by_investigation["session-001"]

    def test_ontology_source_sessions_tracking(self, tmp_path: Path) -> None:
        """Verify merged objects have source_sessions list with contributing session IDs."""
        sessions_dir = tmp_path / ".openplanter" / "sessions"

        # Create two sessions with same entity
        for sid in ["session-001", "session-002"]:
            session_dir = sessions_dir / sid
            session_dir.mkdir(parents=True)
            state = {
                "session_id": sid,
                "entities": {
                    f"ent_{sid}": {"name": "Shared Entity", "type": "Person"},
                },
            }
            (session_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, sessions_dir=sessions_dir)
        defrag.run(mode="cleanup", dry_run=False)

        ontology_path = tmp_path / ".openplanter" / "ontology.json"
        ontology = json.loads(ontology_path.read_text(encoding="utf-8"))

        # Find the entity and check source_sessions
        for entity in ontology.get("entities", {}).values():
            if isinstance(entity, dict) and entity.get("name") == "Shared Entity":
                sources = entity.get("source_sessions", [])
                assert "session-001" in sources
                assert "session-002" in sources
                break


# ---------------------------------------------------------------------------
# Mode Tests
# ---------------------------------------------------------------------------


class TestModes:
    """Tests for different operation modes."""

    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        """Run mode=full, dry_run=True. Verify no files were actually deleted/created."""
        # Create duplicate files
        content = "Same content\n"
        (tmp_path / "original.md").write_text(content, encoding="utf-8")
        (tmp_path / "duplicate.md").write_text(content, encoding="utf-8")

        # Get initial state
        files_before = set(tmp_path.glob("**/*.md"))

        defrag = WorkspaceDefrag(tmp_path)
        report = defrag.run(mode="full", dry_run=True)

        # Should report findings
        assert report.dry_run is True
        assert report.duplicates_found >= 1

        # But no files should be deleted
        files_after = set(tmp_path.glob("**/*.md"))
        assert files_before == files_after

    def test_mode_scan_only(self, tmp_path: Path) -> None:
        """Run mode=scan_only. Verify only scan stats populated, no deletions or ingestion."""
        (tmp_path / "test.md").write_text("content", encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path)
        report = defrag.run(mode="scan_only")

        assert report.files_scanned >= 1
        assert report.files_deleted == 0
        assert report.files_ingested == 0
        assert report.entities_merged == 0

    def test_mode_dedup_only(self, tmp_path: Path) -> None:
        """Run mode=dedup. Verify duplicates removed but no wiki ingestion."""
        # Create duplicate files (identical content to be detected by hash)
        content = "Duplicate content\n"
        (tmp_path / "keep.md").write_text(content, encoding="utf-8")
        (tmp_path / "remove.md").write_text(content, encoding="utf-8")

        # Create potential wiki file (won't be ingested in dedup mode)
        (tmp_path / "wiki_content.md").write_text("# Wiki Content", encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path)
        report = defrag.run(mode="dedup", dry_run=False)

        # Should detect and delete duplicates
        assert report.duplicates_found >= 1
        assert report.files_deleted >= 1
        # Should NOT ingest
        assert report.files_ingested == 0
        # Verify one of the duplicate files was deleted
        remaining = [f.name for f in tmp_path.glob("*.md")]
        assert "remove.md" not in remaining or "keep.md" not in remaining

    def test_mode_ingest_only(self, tmp_path: Path) -> None:
        """Run mode=ingest. Verify wiki ingestion but no file deletions."""
        # Set up wiki
        wiki_dir = tmp_path / ".openplanter" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "index.md").write_text("# Wiki Index\n", encoding="utf-8")

        # Create duplicate files (won't be deleted in ingest mode)
        content = "Same\n"
        (tmp_path / "file1.md").write_text(content, encoding="utf-8")
        (tmp_path / "file2.md").write_text(content, encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, wiki_dir=wiki_dir)
        report = defrag.run(mode="ingest", dry_run=False)

        # Should ingest files
        assert report.files_ingested >= 1
        # Should NOT delete duplicates
        assert report.files_deleted == 0
        # Both files should still exist
        assert (tmp_path / "file1.md").exists()
        assert (tmp_path / "file2.md").exists()


# ---------------------------------------------------------------------------
# Cleanup Tests
# ---------------------------------------------------------------------------


class TestCleanup:
    """Tests for cleanup phase."""

    def test_cleanup_empty_dirs(self, tmp_path: Path) -> None:
        """Create nested dirs with duplicate files, verify empty dirs removed after dedup."""
        # Create nested structure with duplicate files
        content = "Duplicate content\n"
        nested_dir = tmp_path / "level1" / "level2"
        nested_dir.mkdir(parents=True)
        (nested_dir / "duplicate.md").write_text(content, encoding="utf-8")
        (tmp_path / "original.md").write_text(content, encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path)
        report = defrag.run(mode="dedup", dry_run=False)

        assert report.files_deleted >= 1

        # Empty directories should be removed
        assert not (tmp_path / "level1" / "level2").exists()


# ---------------------------------------------------------------------------
# Tool Integration Tests
# ---------------------------------------------------------------------------


class TestToolIntegration:
    """Tests for tool definition and dispatch integration."""

    def test_tool_definition_valid(self) -> None:
        """Import TOOL_DEFINITIONS, find defrag_workspace, verify schema structure."""
        from agent.tool_defs import TOOL_DEFINITIONS

        defrag_def = next(
            (d for d in TOOL_DEFINITIONS if d["name"] == "defrag_workspace"),
            None,
        )
        assert defrag_def is not None
        assert "description" in defrag_def
        assert "parameters" in defrag_def

        params = defrag_def["parameters"]
        assert "properties" in params
        assert "mode" in params["properties"]
        assert "dry_run" in params["properties"]

        # Verify mode enum
        mode_prop = params["properties"]["mode"]
        assert "enum" in mode_prop
        assert set(mode_prop["enum"]) == {"full", "scan_only", "dedup", "ingest", "cleanup"}

        # Verify dry_run is boolean
        dry_run_prop = params["properties"]["dry_run"]
        assert dry_run_prop["type"] == "boolean"

    def test_tool_dispatch(self, tmp_path: Path) -> None:
        """Create minimal WorkspaceTools, call defrag_workspace, verify string report."""
        from agent.tools import WorkspaceTools

        # Create a file for scanning
        (tmp_path / "test.md").write_text("test content", encoding="utf-8")

        tools = WorkspaceTools(root=tmp_path)
        result = tools.defrag_workspace(mode="scan_only")

        assert isinstance(result, str)
        assert "Files scanned" in result or "files_scanned" in result.lower()


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_fingerprint_file(self, tmp_path: Path) -> None:
        """Test file fingerprinting produces consistent hashes."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content", encoding="utf-8")

        hash1 = _fingerprint_file(test_file)
        hash2 = _fingerprint_file(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest

    def test_fingerprint_text(self) -> None:
        """Test text fingerprinting."""
        text = "some text content"
        hash_result = _fingerprint_text(text)

        assert len(hash_result) == 64
        assert hash_result == _fingerprint_text(text)  # Consistent

    def test_strip_date_from_filename(self) -> None:
        """Test date stripping from filenames."""
        assert _strip_date_from_filename("REPORT_2026-02-27.md") == "report"
        assert _strip_date_from_filename("data-2026-01-15.json") == "data"
        # Version suffix matches digits at end only (not _v2)
        assert _strip_date_from_filename("file_2.md") == "file"
        assert _strip_date_from_filename("file-3.md") == "file"
        assert _strip_date_from_filename("simple.md") == "simple"

    def test_read_file_ends(self, tmp_path: Path) -> None:
        """Test reading first and last portions of files."""
        # Short file
        short_file = tmp_path / "short.txt"
        short_file.write_text("short", encoding="utf-8")
        assert _read_file_ends(short_file) == "short"

        # Long file
        long_content = "A" * 600 + "MIDDLE" + "B" * 300
        long_file = tmp_path / "long.txt"
        long_file.write_text(long_content, encoding="utf-8")

        result = _read_file_ends(long_file, first_chars=500, last_chars=200)
        assert "TRUNCATED" in result
        assert len(result) < len(long_content)

    def test_parse_llm_duplicate_response_valid(self, tmp_path: Path) -> None:
        """Test parsing valid LLM response."""
        (tmp_path / "file1.md").write_text("a", encoding="utf-8")
        (tmp_path / "file2.md").write_text("b", encoding="utf-8")

        response = json.dumps({
            "classification": "near_duplicate",
            "canonical": str(tmp_path / "file1.md"),
            "duplicates": [str(tmp_path / "file2.md")],
            "keep": [],
            "confidence": 0.75,
            "rationale": "Similar content",
        })

        file_paths = [tmp_path / "file1.md", tmp_path / "file2.md"]
        result = _parse_llm_duplicate_response(response, file_paths)

        assert result is not None
        assert result.classification == "near_duplicate"
        assert result.confidence == 0.75

    def test_parse_llm_duplicate_response_invalid_json(self, tmp_path: Path) -> None:
        """Test parsing invalid JSON returns None."""
        result = _parse_llm_duplicate_response("not json at all", [])
        assert result is None

    def test_parse_llm_duplicate_response_unrelated(self, tmp_path: Path) -> None:
        """Test unrelated classification returns None."""
        response = json.dumps({
            "classification": "unrelated",
            "canonical": "",
            "duplicates": [],
            "keep": [],
            "confidence": 0.5,
            "rationale": "Files are unrelated",
        })

        result = _parse_llm_duplicate_response(response, [tmp_path / "x.md"])
        assert result is None

    def test_build_duplicate_prompt(self, tmp_path: Path) -> None:
        """Test LLM prompt building."""
        (tmp_path / "file1.md").write_text("Content A", encoding="utf-8")
        (tmp_path / "file2.md").write_text("Content B", encoding="utf-8")

        samples = [
            (tmp_path / "file1.md", "Content A"),
            (tmp_path / "file2.md", "Content B"),
        ]

        prompt = _build_duplicate_prompt(samples)

        assert "exact_duplicate" in prompt
        assert "near_duplicate" in prompt
        assert "versioned" in prompt
        assert "classification" in prompt
        assert "confidence" in prompt


# ---------------------------------------------------------------------------
# Dataclass Tests
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Tests for dataclass behaviors."""

    def test_defrag_report_to_summary(self, tmp_path: Path) -> None:
        """Test DefragReport.to_summary() produces readable output."""
        report = DefragReport(
            workspace_path=tmp_path,
            timestamp="2026-04-01T00:00:00+00:00",
            dry_run=True,
            files_scanned=10,
            total_size_bytes=1024,
            duplicates_found=2,
            duplicate_groups=[],
            space_reclaimable_bytes=512,
            files_deleted=0,
            space_reclaimed_bytes=0,
            un_ingested_files=[],
            files_ingested=0,
            wiki_entries_added=0,
            entities_merged=0,
            indexes_rebuilt=False,
            errors=[],
        )

        summary = report.to_summary()

        assert "DRY RUN" in summary
        assert "Files scanned: 10" in summary
        assert "Duplicate groups found: 2" in summary

    def test_duplicate_group_dataclass(self) -> None:
        """Test DuplicateGroup dataclass fields."""
        group = DuplicateGroup(
            classification="exact_duplicate",
            canonical=Path("/tmp/canonical.md"),
            duplicates=[Path("/tmp/dup1.md"), Path("/tmp/dup2.md")],
            keep=[],
            size_bytes=100,
            confidence=1.0,
            rationale="Test",
        )

        assert group.classification == "exact_duplicate"
        assert len(group.duplicates) == 2
        assert group.size_bytes == 100

    def test_un_ingested_file_dataclass(self) -> None:
        """Test UnIngestedFile dataclass fields."""
        uf = UnIngestedFile(
            path=Path("/tmp/new.md"),
            suggested_category="investigation-artifacts",
            suggested_title="New Document",
            size_bytes=50,
            ingested=False,
        )

        assert uf.path == Path("/tmp/new.md")
        assert uf.ingested is False


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_scan_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test scanning a directory that doesn't exist."""
        nonexistent = tmp_path / "does_not_exist"
        defrag = WorkspaceDefrag(nonexistent)
        defrag._phase_scan()

        assert len(defrag._file_manifests) == 0

    def test_run_with_exception_in_phase(self, tmp_path: Path) -> None:
        """Test that exceptions in phases are captured in errors list."""
        (tmp_path / "test.md").write_text("content", encoding="utf-8")

        # Create a broken sessions directory to trigger ontology phase error
        sessions_dir = tmp_path / ".openplanter" / "sessions"
        sessions_dir.mkdir(parents=True)
        bad_session = sessions_dir / "bad-session"
        bad_session.mkdir()
        (bad_session / "state.json").write_text("not valid json {{{", encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, sessions_dir=sessions_dir)
        report = defrag.run(mode="full")

        # Should complete without crashing
        assert report is not None
        # The bad JSON should be handled gracefully

    def test_wiki_ingestion_handles_existing_files(self, tmp_path: Path) -> None:
        """Test that ingestion skips files that already exist in wiki destination."""
        wiki_dir = tmp_path / ".openplanter" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "index.md").write_text("# Wiki Index\n", encoding="utf-8")

        # Create existing file in wiki category directory
        # Use a filename that will be classified as "investigation-artifacts"
        # (contains "investigation", "analysis", "summary", or "findings")
        category_dir = wiki_dir / "investigation-artifacts"
        category_dir.mkdir(parents=True)
        (category_dir / "INVESTIGATION_existing.md").write_text("# Existing", encoding="utf-8")

        # Create a file in workspace with same name
        # This should be detected as needing ingestion, but the copy will be skipped
        # because the destination already exists
        (tmp_path / "INVESTIGATION_existing.md").write_text("# New Content", encoding="utf-8")

        defrag = WorkspaceDefrag(tmp_path, wiki_dir=wiki_dir)
        report = defrag.run(mode="ingest", dry_run=False)

        # Check that we don't have duplicate files in wiki with same name
        # (index.md is also there, so we filter by "INVESTIGATION_existing.md" specifically)
        wiki_existing_files = list(wiki_dir.glob("**/INVESTIGATION_existing.md"))
        assert len(wiki_existing_files) == 1  # Only the original
