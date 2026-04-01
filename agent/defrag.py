"""Workspace defragmentation module.

Consolidates duplicate files, syncs wiki ingestion, and merges session ontologies
into a workspace-global ontology.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Exclusion patterns (mirrored from retrieval.py)
# ---------------------------------------------------------------------------

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

_TEXT_EXTENSIONS = {".md", ".json", ".csv", ".txt", ".yaml", ".yml"}

# Date patterns to strip from filenames for dedup grouping
_DATE_PATTERN = re.compile(r"[-_]?\d{4}[-_]?\d{2}[-_]?\d{2}")
_VERSION_SUFFIX = re.compile(r"[-_]?\d+$")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DuplicateGroup:
    """A group of duplicate files with classification."""

    classification: str  # "exact_duplicate", "near_duplicate", "versioned"
    canonical: Path  # Best/most complete version to keep
    duplicates: list[Path]  # Files to remove
    keep: list[Path]  # For "versioned": additional files worth keeping
    size_bytes: int  # Total reclaimable bytes
    confidence: float  # LLM confidence 0.0-1.0
    rationale: str  # One-line LLM explanation


@dataclass
class UnIngestedFile:
    """A file found in workspace but not in wiki."""

    path: Path
    suggested_category: str
    suggested_title: str
    size_bytes: int
    ingested: bool = False


@dataclass
class FileManifest:
    """Metadata for a single scanned file."""

    path: Path
    size: int
    hash: str
    extension: str
    modified_at: str
    is_text: bool


@dataclass
class DefragReport:
    """Complete report from a defrag operation."""

    workspace_path: Path
    timestamp: str
    dry_run: bool
    files_scanned: int
    total_size_bytes: int
    duplicates_found: int
    duplicate_groups: list[DuplicateGroup]
    space_reclaimable_bytes: int
    files_deleted: int
    space_reclaimed_bytes: int
    un_ingested_files: list[UnIngestedFile]
    files_ingested: int
    wiki_entries_added: int
    entities_merged: int
    indexes_rebuilt: bool
    errors: list[str]

    def to_summary(self) -> str:
        """Return a human-readable summary string."""
        lines = [
            "=== Workspace Defrag Report ===",
            f"Timestamp: {self.timestamp}",
            f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}",
            "",
            "--- Scan Results ---",
            f"Files scanned: {self.files_scanned}",
            f"Total size: {self._format_bytes(self.total_size_bytes)}",
            "",
            "--- Duplicates ---",
            f"Duplicate groups found: {self.duplicates_found}",
            f"Space reclaimable: {self._format_bytes(self.space_reclaimable_bytes)}",
        ]

        if not self.dry_run:
            lines.extend([
                f"Files deleted: {self.files_deleted}",
                f"Space reclaimed: {self._format_bytes(self.space_reclaimed_bytes)}",
            ])

        lines.extend([
            "",
            "--- Wiki Ingestion ---",
            f"Un-ingested files found: {len(self.un_ingested_files)}",
            f"Files ingested: {self.files_ingested}",
            f"Wiki entries added: {self.wiki_entries_added}",
            "",
            "--- Ontology Sync ---",
            f"Entities merged: {self.entities_merged}",
            f"Indexes rebuilt: {self.indexes_rebuilt}",
        ])

        if self.errors:
            lines.extend([
                "",
                f"--- Errors ({len(self.errors)}) ---",
            ])
            for err in self.errors[:10]:
                lines.append(f"  - {err}")
            if len(self.errors) > 10:
                lines.append(f"  ... and {len(self.errors) - 10} more errors")

        return "\n".join(lines)

    def _format_bytes(self, size: int) -> str:
        """Format byte count for human readability."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _fingerprint_file(path: Path) -> str:
    """Compute SHA256 hash of file contents."""
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except OSError:
        return ""


def _fingerprint_text(text: str) -> str:
    """Compute SHA256 hash of text content."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _is_junk_name(name: str) -> bool:
    """Check if a filename is junk (should be ignored)."""
    return name in _IGNORED_FILE_NAMES or any(
        name.startswith(prefix) for prefix in _IGNORED_FILE_PREFIXES
    )


def _should_skip_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped during scan."""
    return dir_name in _EXCLUDED_DIR_NAMES


def _strip_date_from_filename(filename: str) -> str:
    """Strip date patterns from filename for dedup grouping."""
    stem = Path(filename).stem
    stem = _DATE_PATTERN.sub("", stem)
    stem = _VERSION_SUFFIX.sub("", stem)
    return stem.strip("-_ ").lower()


def _extract_title_from_md(content: str) -> str:
    """Extract title from first # heading in markdown."""
    for line in content.splitlines()[:20]:
        if line.startswith("# ") and not line.startswith("##"):
            return line[2:].strip()
    return ""


def _classify_by_filename(filename: str) -> str:
    """Classify file by filename heuristics."""
    lower = filename.lower()
    if any(kw in lower for kw in ["investigation", "analysis", "summary", "findings"]):
        return "investigation-artifacts"
    if any(kw in lower for kw in ["foia", "prr", "request"]):
        return "government-records"
    if lower.endswith(".json"):
        return "data-artifacts"
    return "general-notes"


def _read_file_ends(path: Path, first_chars: int = 500, last_chars: int = 200) -> str:
    """Read first and last portion of a text file."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        total = len(content)
        if total <= first_chars + last_chars:
            return content
        return content[:first_chars] + "\n...[TRUNCATED]...\n" + content[-last_chars:]
    except OSError:
        return ""


def _build_duplicate_prompt(file_samples: list[tuple[Path, str]]) -> str:
    """Build LLM prompt for duplicate classification."""
    lines = [
        "You are analyzing files to detect duplicates. For each file, you are given",
        "the path and a preview of its content (first ~500 chars + last ~200 chars).",
        "",
        "Classify the relationship between these files as one of:",
        "  - exact_duplicate: Identical content, minor formatting differences only",
        "  - near_duplicate: Same content with timestamp/whitespace/minor wording changes",
        "  - versioned: Same topic but meaningfully different versions",
        "  - unrelated: False positive from pre-filtering",
        "",
        "For each classification, provide:",
        "  - canonical: The best/most complete version to keep (file path)",
        "  - duplicates: Files that should be removed (list of paths)",
        "  - keep: Additional files worth keeping for 'versioned' (list of paths)",
        "  - confidence: Your confidence in this classification (0.0-1.0)",
        "  - rationale: One-line explanation",
        "",
        "Respond in JSON format:",
        "{",
        '  "classification": "...",',
        '  "canonical": "...",',
        '  "duplicates": [...],',
        '  "keep": [...],',
        '  "confidence": 0.0,',
        '  "rationale": "..."',
        "}",
        "",
        "Files to analyze:",
    ]
    for path, sample in file_samples:
        lines.append(f"\n--- {path} ---")
        lines.append(sample)
    return "\n".join(lines)


def _parse_llm_duplicate_response(response: str, file_paths: list[Path]) -> DuplicateGroup | None:
    """Parse LLM response into DuplicateGroup, with validation."""
    try:
        # Extract JSON from response
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start == -1 or json_end == 0:
            return None
        data = json.loads(response[json_start:json_end])
    except json.JSONDecodeError:
        return None

    classification = str(data.get("classification", "")).lower()
    if classification not in {"exact_duplicate", "near_duplicate", "versioned", "unrelated"}:
        return None

    if classification == "unrelated":
        return None

    # Resolve canonical path
    canonical_str = str(data.get("canonical", ""))
    canonical = None
    for p in file_paths:
        if str(p) == canonical_str or p.name == canonical_str:
            canonical = p
            break
    if canonical is None:
        canonical = file_paths[0]

    # Resolve duplicates and keep lists
    duplicates: list[Path] = []
    keep: list[Path] = []

    for p in file_paths:
        if p == canonical:
            continue
        dup_paths = data.get("duplicates", [])
        keep_paths = data.get("keep", [])
        if str(p) in dup_paths or p.name in dup_paths:
            duplicates.append(p)
        elif str(p) in keep_paths or p.name in keep_paths:
            keep.append(p)
        elif classification in {"exact_duplicate", "near_duplicate"}:
            duplicates.append(p)

    # Calculate total size
    total_size = 0
    try:
        total_size = sum(p.stat().st_size for p in duplicates if p.exists())
    except OSError:
        pass

    return DuplicateGroup(
        classification=classification,
        canonical=canonical,
        duplicates=duplicates,
        keep=keep,
        size_bytes=total_size,
        confidence=float(data.get("confidence", 0.5)),
        rationale=str(data.get("rationale", "")),
    )


# ---------------------------------------------------------------------------
# WorkspaceDefrag class
# ---------------------------------------------------------------------------


class WorkspaceDefrag:
    """Workspace defragmentation manager.

    Consolidates duplicate files, syncs wiki ingestion, and merges session
    ontologies into a workspace-global ontology.
    """

    def __init__(
        self,
        workspace: Path,
        wiki_dir: Path | None = None,
        sessions_dir: Path | None = None,
        llm_classify: Callable[[str], str] | None = None,
    ) -> None:
        """Initialize the defrag manager.

        Args:
            workspace: Root workspace directory
            wiki_dir: Wiki directory (default: workspace/.openplanter/wiki)
            sessions_dir: Sessions directory (default: workspace/.openplanter/sessions)
            llm_classify: Optional callable that takes a prompt and returns LLM response.
                          If None, only hash-based exact dedup is performed.
        """
        self.workspace = Path(workspace).resolve()
        self.wiki_dir = (
            Path(wiki_dir).resolve()
            if wiki_dir
            else self.workspace / ".openplanter" / "wiki"
        )
        self.sessions_dir = (
            Path(sessions_dir).resolve()
            if sessions_dir
            else self.workspace / ".openplanter" / "sessions"
        )
        self.llm_classify = llm_classify

        # Internal state
        self._file_manifests: dict[Path, FileManifest] = {}
        self._hash_groups: dict[str, list[Path]] = {}
        self._candidate_clusters: list[list[Path]] = []

    def run(self, mode: str = "full", dry_run: bool = False) -> DefragReport:
        """Run defrag operation.

        Args:
            mode: Operation mode - one of:
                - "scan_only": Phase 1 only, report stats
                - "dedup": Phase 1 + 2 + 6 (cleanup duplicates only)
                - "ingest": Phase 1 + 3 + 4 (wiki ingestion only)
                - "cleanup": Phase 1 + 2 + 5 + 6 (dedup + ontology + cleanup, no wiki ingest)
                - "full": All phases
            dry_run: If True, don't make any changes, just report what would be done

        Returns:
            DefragReport with complete operation results
        """
        timestamp = _utc_now_iso()
        errors: list[str] = []

        # Phase 1: Scan
        try:
            self._phase_scan()
        except Exception as e:
            errors.append(f"Scan phase failed: {e}")

        # Initialize report components
        duplicate_groups: list[DuplicateGroup] = []
        un_ingested_files: list[UnIngestedFile] = []
        files_deleted = 0
        space_reclaimed = 0
        files_ingested = 0
        wiki_entries_added = 0
        entities_merged = 0
        indexes_rebuilt = False

        # Phase 2: Duplicate Detection (for dedup, cleanup, full modes)
        if mode in {"dedup", "cleanup", "full"}:
            try:
                duplicate_groups = self._phase_duplicates()
            except Exception as e:
                errors.append(f"Duplicate detection failed: {e}")

        # Phase 3: Un-ingested Data Detection (for ingest, full modes)
        if mode in {"ingest", "full"}:
            try:
                un_ingested_files = self._phase_un_ingested()
            except Exception as e:
                errors.append(f"Un-ingested detection failed: {e}")

        # Phase 4: Wiki Ingestion (for ingest, full modes)
        if mode in {"ingest", "full"} and not dry_run:
            try:
                files_ingested, wiki_entries_added = self._phase_ingest(un_ingested_files)
            except Exception as e:
                errors.append(f"Wiki ingestion failed: {e}")

        # Phase 5: Ontology Sync (for cleanup, full modes)
        if mode in {"cleanup", "full"}:
            try:
                entities_merged, indexes_rebuilt = self._phase_ontology(dry_run)
            except Exception as e:
                errors.append(f"Ontology sync failed: {e}")

        # Phase 6: Cleanup (for dedup, cleanup, full modes)
        if mode in {"dedup", "cleanup", "full"} and not dry_run:
            try:
                files_deleted, space_reclaimed = self._phase_cleanup(duplicate_groups, timestamp)
            except Exception as e:
                errors.append(f"Cleanup phase failed: {e}")

        # Calculate totals
        files_scanned = len(self._file_manifests)
        total_size = sum(m.size for m in self._file_manifests.values())
        space_reclaimable = sum(g.size_bytes for g in duplicate_groups)
        duplicates_found = len(duplicate_groups)

        return DefragReport(
            workspace_path=self.workspace,
            timestamp=timestamp,
            dry_run=dry_run,
            files_scanned=files_scanned,
            total_size_bytes=total_size,
            duplicates_found=duplicates_found,
            duplicate_groups=duplicate_groups,
            space_reclaimable_bytes=space_reclaimable,
            files_deleted=files_deleted,
            space_reclaimed_bytes=space_reclaimed,
            un_ingested_files=un_ingested_files,
            files_ingested=files_ingested,
            wiki_entries_added=wiki_entries_added,
            entities_merged=entities_merged,
            indexes_rebuilt=indexes_rebuilt,
            errors=errors,
        )

    # -----------------------------------------------------------------------
    # Phase 1: Scan
    # -----------------------------------------------------------------------

    def _phase_scan(self) -> None:
        """Scan workspace and build file manifest."""
        self._file_manifests.clear()
        self._hash_groups.clear()
        self._candidate_clusters.clear()

        if not self.workspace.is_dir():
            return

        for root, dirs, files in os.walk(self.workspace):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

            # Skip sessions directory (except wiki within it)
            rel_parts = Path(root).relative_to(self.workspace).parts
            if rel_parts and rel_parts[0] == ".openplanter":
                if "sessions" in rel_parts:
                    continue

            for fname in files:
                if _is_junk_name(fname):
                    continue

                path = Path(root) / fname
                try:
                    stat = path.stat()
                    ext = path.suffix.lower()
                    is_text = ext in _TEXT_EXTENSIONS

                    file_hash = _fingerprint_file(path)

                    manifest = FileManifest(
                        path=path,
                        size=stat.st_size,
                        hash=file_hash,
                        extension=ext,
                        modified_at=datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                        is_text=is_text,
                    )
                    self._file_manifests[path] = manifest

                    # Group by hash for exact duplicate detection
                    if file_hash:
                        self._hash_groups.setdefault(file_hash, []).append(path)

                except OSError:
                    # Skip files we can't read, but don't fail the scan
                    continue

        # Build candidate clusters for LLM-based dedup
        self._build_candidate_clusters()

    def _build_candidate_clusters(self) -> None:
        """Build candidate clusters for LLM-based duplicate detection."""
        # Group by extension + similar filename stem
        stem_groups: dict[str, list[Path]] = {}
        for path, manifest in self._file_manifests.items():
            if not manifest.is_text:
                continue
            stem = _strip_date_from_filename(path.name)
            key = f"{manifest.extension}:{stem}"
            stem_groups.setdefault(key, []).append(path)

        # Group by similar size in same or sibling directories
        size_groups: dict[str, list[Path]] = {}
        for path, manifest in self._file_manifests.items():
            if not manifest.is_text:
                continue
            # Round size to nearest 1KB for grouping
            size_bucket = manifest.size // 1024
            parent = str(path.parent.relative_to(self.workspace))
            key = f"{parent}:{size_bucket}"
            size_groups.setdefault(key, []).append(path)

        # Combine groups, excluding exact hash matches (already handled)
        seen_paths: set[Path] = set()
        for paths in stem_groups.values():
            if len(paths) < 2:
                continue
            # Skip if all paths have same hash (exact duplicates)
            hashes = {self._file_manifests[p].hash for p in paths if p in self._file_manifests}
            if len(hashes) == 1:
                continue
            if any(p not in seen_paths for p in paths):
                self._candidate_clusters.append(paths)
                seen_paths.update(paths)

        for paths in size_groups.values():
            if len(paths) < 2:
                continue
            hashes = {self._file_manifests[p].hash for p in paths if p in self._file_manifests}
            if len(hashes) == 1:
                continue
            new_paths = [p for p in paths if p not in seen_paths]
            if len(new_paths) >= 2:
                self._candidate_clusters.append(new_paths)
                seen_paths.update(new_paths)

    # -----------------------------------------------------------------------
    # Phase 2: Duplicate Detection
    # -----------------------------------------------------------------------

    def _phase_duplicates(self) -> list[DuplicateGroup]:
        """Detect duplicate files using hash and LLM classification."""
        groups: list[DuplicateGroup] = []

        # Exact hash-based duplicates
        for file_hash, paths in self._hash_groups.items():
            if len(paths) < 2:
                continue

            # Choose canonical: largest file, then most recent
            canonical = max(
                paths,
                key=lambda p: (
                    self._file_manifests[p].size,
                    self._file_manifests[p].modified_at,
                ),
            )
            duplicates = [p for p in paths if p != canonical]
            total_size = sum(self._file_manifests[p].size for p in duplicates)

            groups.append(
                DuplicateGroup(
                    classification="exact_duplicate",
                    canonical=canonical,
                    duplicates=duplicates,
                    keep=[],
                    size_bytes=total_size,
                    confidence=1.0,
                    rationale="Identical SHA256 hash",
                )
            )

        # LLM-based near-duplicate detection
        if self.llm_classify is None:
            return groups

        for cluster in self._candidate_clusters:
            if len(cluster) < 2:
                continue

            # Read samples from each file
            samples: list[tuple[Path, str]] = []
            for path in cluster:
                if path not in self._file_manifests:
                    continue
                sample = _read_file_ends(path)
                if sample:
                    samples.append((path, sample))

            if len(samples) < 2:
                continue

            # Build prompt and call LLM
            prompt = _build_duplicate_prompt(samples)
            try:
                response = self.llm_classify(prompt)
                group = _parse_llm_duplicate_response(response, [p for p, _ in samples])
                if group is not None:
                    groups.append(group)
            except Exception:
                # LLM call failed, skip this cluster
                continue

        return groups

    # -----------------------------------------------------------------------
    # Phase 3: Un-ingested Data Detection
    # -----------------------------------------------------------------------

    def _phase_un_ingested(self) -> list[UnIngestedFile]:
        """Find files not in wiki and suggest categories."""
        un_ingested: list[UnIngestedFile] = []

        # Get set of known wiki source paths
        wiki_paths = self._get_wiki_paths()

        for path, manifest in self._file_manifests.items():
            # Only consider .md and .json files
            if manifest.extension not in {".md", ".json"}:
                continue

            # Skip files already in wiki
            try:
                path.relative_to(self.wiki_dir)
                continue  # File is in wiki
            except ValueError:
                pass

            # Skip files in sessions directory
            try:
                path.relative_to(self.sessions_dir)
                continue
            except ValueError:
                pass

            # Check if file path is referenced in wiki index
            rel_to_workspace = path.relative_to(self.workspace)
            if str(rel_to_workspace) in wiki_paths:
                continue

            # Classify by filename
            category = _classify_by_filename(path.name)

            # Extract title
            title = ""
            if manifest.extension == ".md":
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    title = _extract_title_from_md(content)
                except OSError:
                    pass
            if not title:
                title = Path(path).stem

            un_ingested.append(
                UnIngestedFile(
                    path=path,
                    suggested_category=category,
                    suggested_title=title,
                    size_bytes=manifest.size,
                    ingested=False,
                )
            )

        return un_ingested

    def _get_wiki_paths(self) -> set[str]:
        """Get set of file paths referenced in wiki index."""
        wiki_paths: set[str] = set()

        if not self.wiki_dir.is_dir():
            return wiki_paths

        # Parse wiki index if it exists
        index_path = self.wiki_dir / "index.md"
        if index_path.is_file():
            try:
                content = index_path.read_text(encoding="utf-8")
                # Look for markdown links: [text](path)
                for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", content):
                    wiki_paths.add(match.group(1))
            except OSError:
                pass

        # Also scan wiki directory for actual files
        for root, _dirs, files in os.walk(self.wiki_dir):
            for fname in files:
                if fname.endswith((".md", ".json")):
                    full_path = Path(root) / fname
                    try:
                        rel = full_path.relative_to(self.wiki_dir)
                        wiki_paths.add(str(rel))
                        wiki_paths.add(str(full_path))
                    except ValueError:
                        pass

        return wiki_paths

    # -----------------------------------------------------------------------
    # Phase 4: Wiki Ingestion
    # -----------------------------------------------------------------------

    def _phase_ingest(
        self, un_ingested: list[UnIngestedFile]
    ) -> tuple[int, int]:
        """Ingest un-ingested files into wiki.

        Returns:
            Tuple of (files_ingested, wiki_entries_added)
        """
        files_ingested = 0
        wiki_entries_added = 0

        if not self.wiki_dir.is_dir():
            try:
                self.wiki_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                return files_ingested, wiki_entries_added

        for item in un_ingested:
            try:
                # Create category directory if needed
                category_dir = self.wiki_dir / item.suggested_category
                category_dir.mkdir(parents=True, exist_ok=True)

                # Copy file into wiki
                dest_path = category_dir / item.path.name
                if dest_path.exists():
                    # Skip if already exists
                    continue

                shutil.copy2(item.path, dest_path)
                files_ingested += 1

                # Append entry to index.md
                index_path = self.wiki_dir / "index.md"
                self._append_to_index(index_path, item)
                wiki_entries_added += 1

                item.ingested = True

            except OSError:
                continue

        # Rebuild wiki graph if available
        if wiki_entries_added > 0:
            self._rebuild_wiki_graph()

        return files_ingested, wiki_entries_added

    def _append_to_index(self, index_path: Path, item: UnIngestedFile) -> None:
        """Append entry to wiki index.md."""
        # Determine category heading
        category_heading = f"### {item.suggested_category.replace('-', ' ').title()}"

        # Build entry line
        rel_path = f"{item.suggested_category}/{item.path.name}"
        entry_line = f"| {item.suggested_title} | | [{item.path.name}]({rel_path}) |"

        try:
            if index_path.exists():
                content = index_path.read_text(encoding="utf-8")
                lines = content.splitlines()

                # Find or add category heading
                cat_line_idx = -1
                for i, line in enumerate(lines):
                    if line.strip() == category_heading:
                        cat_line_idx = i
                        break

                if cat_line_idx == -1:
                    # Add new category at end
                    lines.append("")
                    lines.append(category_heading)
                    lines.append("")
                    lines.append("| Name | Jurisdiction | Source |")
                    lines.append("|------|--------------|--------|")
                    lines.append(entry_line)
                else:
                    # Insert after existing entries in this category
                    insert_idx = cat_line_idx + 1
                    # Skip header rows
                    while insert_idx < len(lines) and (
                        lines[insert_idx].strip().startswith("|--")
                        or lines[insert_idx].strip().startswith("| Name")
                        or lines[insert_idx].strip() == ""
                    ):
                        insert_idx += 1
                    lines.insert(insert_idx, entry_line)

                index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            else:
                # Create new index
                content = "\n".join([
                    "# Wiki Index",
                    "",
                    category_heading,
                    "",
                    "| Name | Jurisdiction | Source |",
                    "|------|--------------|--------|",
                    entry_line,
                    "",
                ])
                index_path.write_text(content, encoding="utf-8")
        except OSError:
            pass

    def _rebuild_wiki_graph(self) -> None:
        """Rebuild wiki graph if WikiGraphModel is available."""
        try:
            # Lazy import
            from .wiki_graph import WikiGraphModel

            model = WikiGraphModel(self.wiki_dir)
            model.rebuild()
        except ImportError:
            pass
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Phase 5: Ontology Sync
    # -----------------------------------------------------------------------

    def _phase_ontology(self, dry_run: bool) -> tuple[int, bool]:
        """Sync workspace-global ontology from all sessions.

        Returns:
            Tuple of (entities_merged, indexes_rebuilt)
        """
        entities_merged = 0
        indexes_rebuilt = False

        # Load all session states
        session_states: list[dict[str, Any]] = []
        if self.sessions_dir.is_dir():
            for session_dir in self.sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                state_path = session_dir / "state.json"
                if not state_path.exists():
                    continue
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                    if isinstance(state, dict):
                        session_states.append(state)
                except (json.JSONDecodeError, OSError):
                    continue

        if not session_states:
            return entities_merged, indexes_rebuilt

        # Load or create workspace ontology
        ontology_path = self.workspace / ".openplanter" / "ontology.json"
        ontology: dict[str, Any] = {
            "namespace": "openplanter.workspace",
            "version": "2026-04",
            "entities": {},
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
            "indexes": {
                "by_external_ref": {},
                "by_tag": {},
                "by_investigation": {},
            },
            "source_sessions": [],
        }

        if ontology_path.exists():
            try:
                existing = json.loads(ontology_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    ontology.update(existing)
            except (json.JSONDecodeError, OSError):
                pass

        # Merge entities from all sessions
        entity_index: dict[tuple[str, str], str] = {}  # (name, type) -> canonical_id

        # Seed the dedup index from existing ontology content so repeated defrag
        # runs keep reusing the canonical entity IDs already written to disk.
        for entity_id, entity in ontology.get("entities", {}).items():
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name") or entity.get("label") or "")
            etype = str(entity.get("type") or "Entity")
            key = (name.lower(), etype.lower())
            entity_index[key] = entity_id

        for state in session_states:
            session_id = str(state.get("session_id", "unknown"))

            # Merge entities
            entities = state.get("entities", {})
            if isinstance(entities, dict):
                for entity_id, entity in entities.items():
                    if not isinstance(entity, dict):
                        continue

                    name = str(entity.get("name") or entity.get("label") or "")
                    etype = str(entity.get("type") or "Entity")
                    key = (name.lower(), etype.lower())

                    if key in entity_index:
                        # Entity already exists - merge and track source
                        canonical_id = entity_index[key]
                        if canonical_id in ontology["entities"]:
                            sources = ontology["entities"][canonical_id].setdefault(
                                "source_sessions", []
                            )
                            if session_id not in sources:
                                sources.append(session_id)
                            entities_merged += 1
                    else:
                        # New entity
                        entity_copy = dict(entity)
                        entity_copy["source_sessions"] = [session_id]
                        ontology["entities"][entity_id] = entity_copy
                        entity_index[key] = entity_id

            # Merge claims with provenance tracking
            self._merge_ontology_objects(
                ontology["claims"],
                state.get("claims", {}),
                session_id,
                "claim",
            )

            # Merge evidence
            self._merge_ontology_objects(
                ontology["evidence"],
                state.get("evidence", {}),
                session_id,
                "evidence",
            )

            # Merge questions
            self._merge_ontology_objects(
                ontology["questions"],
                state.get("questions", {}),
                session_id,
                "question",
            )

            # Merge hypotheses
            self._merge_ontology_objects(
                ontology["hypotheses"],
                state.get("hypotheses", {}),
                session_id,
                "hypothesis",
            )

            # Merge links
            self._merge_ontology_objects(
                ontology["links"],
                state.get("links", {}),
                session_id,
                "link",
            )

            # Merge provenance nodes
            self._merge_ontology_objects(
                ontology["provenance_nodes"],
                state.get("provenance_nodes", {}),
                session_id,
                "provenance",
            )

            # Track session
            if session_id not in ontology["source_sessions"]:
                ontology["source_sessions"].append(session_id)

        # Rebuild indexes
        self._rebuild_ontology_indexes(ontology)
        indexes_rebuilt = True

        # Write ontology
        if not dry_run:
            try:
                ontology_path.parent.mkdir(parents=True, exist_ok=True)
                ontology_path.write_text(
                    json.dumps(ontology, indent=2), encoding="utf-8"
                )
            except OSError:
                indexes_rebuilt = False

        # Project to wiki graph if available
        if not dry_run:
            self._project_ontology_to_wiki(ontology)

        return entities_merged, indexes_rebuilt

    def _merge_ontology_objects(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
        session_id: str,
        object_type: str,
    ) -> None:
        """Merge ontology objects from source into target."""
        if not isinstance(source, dict):
            return

        for obj_id, obj in source.items():
            if not isinstance(obj, dict):
                continue

            if obj_id in target:
                # Object exists - merge source_sessions
                existing = target[obj_id]
                if isinstance(existing, dict):
                    sources = existing.setdefault("source_sessions", [])
                    if session_id not in sources:
                        sources.append(session_id)

                    # Check for conflicting claims
                    if object_type == "claim":
                        existing_confidence = existing.get("confidence")
                        new_confidence = obj.get("confidence")
                        if (
                            existing_confidence is not None
                            and new_confidence is not None
                            and existing_confidence != new_confidence
                        ):
                            existing["contradicts"] = True
            else:
                # New object
                obj_copy = dict(obj)
                obj_copy["source_sessions"] = [session_id]
                target[obj_id] = obj_copy

    def _rebuild_ontology_indexes(self, ontology: dict[str, Any]) -> None:
        """Rebuild ontology indexes: by_external_ref, by_tag, by_investigation."""
        indexes = ontology.setdefault("indexes", {})

        # by_external_ref: maps external references to object IDs
        by_external_ref: dict[str, list[str]] = {}
        indexes["by_external_ref"] = by_external_ref

        # by_tag: maps tags to object IDs
        by_tag: dict[str, list[str]] = {}
        indexes["by_tag"] = by_tag

        # by_investigation: maps investigation/session IDs to object IDs
        by_investigation: dict[str, list[str]] = {}
        indexes["by_investigation"] = by_investigation

        # Index entities
        for entity_id, entity in ontology.get("entities", {}).items():
            if not isinstance(entity, dict):
                continue
            self._index_object(entity_id, entity, "entity", by_external_ref, by_tag, by_investigation)

        # Index claims
        for claim_id, claim in ontology.get("claims", {}).items():
            if not isinstance(claim, dict):
                continue
            self._index_object(claim_id, claim, "claim", by_external_ref, by_tag, by_investigation)

        # Index evidence
        for evidence_id, evidence in ontology.get("evidence", {}).items():
            if not isinstance(evidence, dict):
                continue
            self._index_object(evidence_id, evidence, "evidence", by_external_ref, by_tag, by_investigation)
            # Also index by source_uri
            source_uri = evidence.get("source_uri")
            if source_uri:
                key = f"evidence:{source_uri}"
                by_external_ref.setdefault(key, []).append(evidence_id)

        # Index questions
        for question_id, question in ontology.get("questions", {}).items():
            if not isinstance(question, dict):
                continue
            self._index_object(question_id, question, "question", by_external_ref, by_tag, by_investigation)

        # Index hypotheses
        for hypothesis_id, hypothesis in ontology.get("hypotheses", {}).items():
            if not isinstance(hypothesis, dict):
                continue
            self._index_object(hypothesis_id, hypothesis, "hypothesis", by_external_ref, by_tag, by_investigation)

    def _index_object(
        self,
        obj_id: str,
        obj: dict[str, Any],
        obj_type: str,
        by_external_ref: dict[str, list[str]],
        by_tag: dict[str, list[str]],
        by_investigation: dict[str, list[str]],
    ) -> None:
        """Index a single ontology object."""
        # Index by external references
        for key in ("external_id", "external_ref", "source_uri", "url"):
            val = obj.get(key)
            if val:
                ref_key = f"{obj_type}:{val}"
                by_external_ref.setdefault(ref_key, []).append(obj_id)

        # Index by tags
        tags = obj.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                tag = str(tag)
                by_tag.setdefault(tag, []).append(obj_id)

        # Index by investigation/session
        source_sessions = obj.get("source_sessions", [])
        if isinstance(source_sessions, list):
            for session_id in source_sessions:
                by_investigation.setdefault(str(session_id), []).append(obj_id)

    def _project_ontology_to_wiki(self, ontology: dict[str, Any]) -> None:
        """Project ontology to wiki graph using project_to_wiki_graph."""
        try:
            # Lazy import
            from .investigation_state import project_to_wiki_graph

            # Create a synthetic state for projection
            synthetic_state = {
                "session_id": "workspace-ontology",
                "entities": ontology.get("entities", {}),
                "claims": ontology.get("claims", {}),
                "evidence": ontology.get("evidence", {}),
                "questions": ontology.get("questions", {}),
                "hypotheses": ontology.get("hypotheses", {}),
                "links": ontology.get("links", {}),
                "provenance_nodes": ontology.get("provenance_nodes", {}),
            }
            # Project to wiki graph (result stored in wiki_graph module)
            project_to_wiki_graph(synthetic_state)

            # Write projection to wiki (optional - could create special file)
            # For now, just ensure wiki graph is rebuilt
            self._rebuild_wiki_graph()

        except ImportError:
            pass
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Phase 6: Cleanup
    # -----------------------------------------------------------------------

    def _phase_cleanup(
        self,
        duplicate_groups: list[DuplicateGroup],
        timestamp: str,
    ) -> tuple[int, int]:
        """Delete duplicate files and clean up empty directories.

        Returns:
            Tuple of (files_deleted, space_reclaimed)
        """
        files_deleted = 0
        space_reclaimed = 0

        # Write backup manifest
        manifest_path = (
            self.workspace
            / ".openplanter"
            / f"defrag-manifest-{timestamp.replace(':', '-')}.json"
        )

        manifest_data: dict[str, Any] = {
            "timestamp": timestamp,
            "deleted_files": [],
            "errors": [],
        }

        # Collect all files to delete
        files_to_delete: list[tuple[Path, int]] = []
        for group in duplicate_groups:
            for dup_path in group.duplicates:
                if dup_path.exists():
                    try:
                        size = dup_path.stat().st_size
                        files_to_delete.append((dup_path, size))
                    except OSError:
                        continue

        # Delete files
        deleted_dirs: set[Path] = set()
        for dup_path, size in files_to_delete:
            try:
                manifest_data["deleted_files"].append({
                    "path": str(dup_path),
                    "size": size,
                })
                dup_path.unlink()
                files_deleted += 1
                space_reclaimed += size
                deleted_dirs.add(dup_path.parent)
            except OSError as e:
                manifest_data["errors"].append(f"Failed to delete {dup_path}: {e}")

        # Remove empty directories
        for parent in deleted_dirs:
            try:
                # Walk up and remove empty parent directories
                current = parent
                while current != self.workspace:
                    if current.exists() and current.is_dir():
                        contents = list(current.iterdir())
                        if not contents:
                            current.rmdir()
                        else:
                            break
                    current = current.parent
            except OSError:
                continue

        # Write manifest
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest_data, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

        return files_deleted, space_reclaimed


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def sync_session_to_workspace_ontology(
    workspace: Path,
    session_id: str,
    session_state: dict,
) -> None:
    """Lightweight incremental merge of a single session's state into workspace ontology.

    This function is designed to be called during session finalization to ensure
    session ontology contributions are automatically merged into the workspace-global
    ontology. It never raises exceptions - all errors are silently caught to prevent
    crashing session finalization.

    Args:
        workspace: Path to the workspace root directory.
        session_id: The session identifier being synced.
        session_state: The typed session state containing ontology objects.
    """
    try:
        workspace = Path(workspace).resolve()
        ontology_path = workspace / ".openplanter" / "ontology.json"

        # Step 1: Load existing ontology or create new empty one with standard schema
        ontology: dict[str, Any] = {
            "namespace": "openplanter.workspace",
            "version": "2026-04",
            "entities": {},
            "claims": {},
            "evidence": {},
            "questions": {},
            "hypotheses": {},
            "links": {},
            "provenance_nodes": {},
            "indexes": {
                "by_external_ref": {},
                "by_tag": {},
                "by_investigation": {},
            },
            "source_sessions": [],
        }

        if ontology_path.exists():
            try:
                existing = json.loads(ontology_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    ontology.update(existing)
            except (json.JSONDecodeError, OSError):
                pass

        # Step 2: Merge entities with dedup by (name.lower(), type.lower())
        entity_index: dict[tuple[str, str], str] = {}  # (name, type) -> canonical_id

        # Build existing entity index
        for entity_id, entity in ontology.get("entities", {}).items():
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name") or entity.get("label") or "")
            etype = str(entity.get("type") or "Entity")
            key = (name.lower(), etype.lower())
            entity_index[key] = entity_id

        # Merge entities from session state
        entities = session_state.get("entities", {})
        if isinstance(entities, dict):
            for entity_id, entity in entities.items():
                if not isinstance(entity, dict):
                    continue

                name = str(entity.get("name") or entity.get("label") or "")
                etype = str(entity.get("type") or "Entity")
                key = (name.lower(), etype.lower())

                if key in entity_index:
                    # Entity already exists - add session_id to source_sessions
                    canonical_id = entity_index[key]
                    if canonical_id in ontology["entities"]:
                        sources = ontology["entities"][canonical_id].setdefault(
                            "source_sessions", []
                        )
                        if session_id not in sources:
                            sources.append(session_id)
                else:
                    # New entity - add with source_sessions
                    entity_copy = dict(entity)
                    entity_copy["source_sessions"] = [session_id]
                    ontology["entities"][entity_id] = entity_copy
                    entity_index[key] = entity_id

        # Step 3: Merge other ontology objects (claims, evidence, questions, etc.)
        object_types = [
            ("claims", "claim"),
            ("evidence", "evidence"),
            ("questions", "question"),
            ("hypotheses", "hypothesis"),
            ("links", "link"),
            ("provenance_nodes", "provenance"),
        ]

        for collection_key, object_type in object_types:
            target = ontology.setdefault(collection_key, {})
            source = session_state.get(collection_key, {})
            if not isinstance(source, dict):
                continue

            for obj_id, obj in source.items():
                if not isinstance(obj, dict):
                    continue

                if obj_id in target:
                    # Object exists - append session_id to source_sessions
                    existing = target[obj_id]
                    if isinstance(existing, dict):
                        sources = existing.setdefault("source_sessions", [])
                        if session_id not in sources:
                            sources.append(session_id)
                else:
                    # New object - add with source_sessions
                    obj_copy = dict(obj)
                    obj_copy["source_sessions"] = [session_id]
                    target[obj_id] = obj_copy

        # Step 4: Add session_id to top-level source_sessions
        if session_id not in ontology["source_sessions"]:
            ontology["source_sessions"].append(session_id)

        # Step 5: Rebuild indexes (inline implementation)
        indexes = ontology.setdefault("indexes", {})

        # by_external_ref: maps external_ref fields to object IDs
        by_external_ref: dict[str, list[str]] = {}
        indexes["by_external_ref"] = by_external_ref

        # by_tag: maps tags to object IDs
        by_tag: dict[str, list[str]] = {}
        indexes["by_tag"] = by_tag

        # by_investigation: maps session IDs from source_sessions to object IDs
        by_investigation: dict[str, list[str]] = {}
        indexes["by_investigation"] = by_investigation

        def _index_object(obj_id: str, obj: dict, obj_type: str) -> None:
            """Index a single ontology object."""
            # Index by external references
            for key in ("external_id", "external_ref", "source_uri", "url"):
                val = obj.get(key)
                if val:
                    ref_key = f"{obj_type}:{val}"
                    by_external_ref.setdefault(ref_key, []).append(obj_id)

            # Index by tags
            tags = obj.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    tag = str(tag)
                    by_tag.setdefault(tag, []).append(obj_id)

            # Index by investigation/session
            source_sessions = obj.get("source_sessions", [])
            if isinstance(source_sessions, list):
                for sid in source_sessions:
                    by_investigation.setdefault(str(sid), []).append(obj_id)

        # Index all object types
        for entity_id, entity in ontology.get("entities", {}).items():
            if isinstance(entity, dict):
                _index_object(entity_id, entity, "entity")

        for claim_id, claim in ontology.get("claims", {}).items():
            if isinstance(claim, dict):
                _index_object(claim_id, claim, "claim")

        for evidence_id, evidence in ontology.get("evidence", {}).items():
            if isinstance(evidence, dict):
                _index_object(evidence_id, evidence, "evidence")
                # Also index by source_uri
                source_uri = evidence.get("source_uri")
                if source_uri:
                    key = f"evidence:{source_uri}"
                    by_external_ref.setdefault(key, []).append(evidence_id)

        for question_id, question in ontology.get("questions", {}).items():
            if isinstance(question, dict):
                _index_object(question_id, question, "question")

        for hypothesis_id, hypothesis in ontology.get("hypotheses", {}).items():
            if isinstance(hypothesis, dict):
                _index_object(hypothesis_id, hypothesis, "hypothesis")

        # Step 6: Write ontology back to file
        try:
            ontology_path.parent.mkdir(parents=True, exist_ok=True)
            ontology_path.write_text(
                json.dumps(ontology, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # Silently ignore write errors

    except Exception:
        pass  # Never crash session finalization for ontology sync
