#!/usr/bin/env python3
"""
BigLocalNews (BLN) API Query Script
====================================
Queries the BigLocalNews open-data platform for projects and files
relevant to our I-4 corridor ICE detention and Seminole County investigations.

Usage:
    # Set your API token (get one at https://biglocalnews.org)
    export BLN_API_TOKEN="your-token-here"

    # Run the full scan
    python3 bln_query.py

    # Run with a specific search term
    python3 bln_query.py --search "ICE detention"

    # List all open projects (no keyword filter)
    python3 bln_query.py --list-all

    # Download files from a specific project
    python3 bln_query.py --download PROJECT_ID --output-dir ./bln_downloads/

Requires: pip install bln   (package version 2.3.x+)

Output: bln_results.json — structured results with matched projects and files
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration: search terms relevant to our investigations
# ---------------------------------------------------------------------------

# ICE / immigration enforcement investigation
ICE_KEYWORDS = [
    r"ICE\b",
    r"immigration\s+(and\s+customs\s+)?enforcement",
    r"deten(tion|ee|tion\s+facility)",
    r"IGSA",
    r"287\s*\(?g\)?",
    r"deportat",
    r"remov(al|ed)\s+(flight|operation)",
    r"immigra(tion|nt)",
    r"customs\s+enforcement",
    r"border\s+patrol",
    r"ERO\b",            # Enforcement and Removal Operations
]

# Florida / I-4 corridor specifics
FLORIDA_KEYWORDS = [
    r"florida",
    r"orange\s+county",
    r"osceola",
    r"seminole\s+county",
    r"polk\s+county",
    r"hillsborough",
    r"pinellas",
    r"orlando",
    r"tampa",
    r"i-?4\s+corridor",
]

# Detention / jail / corrections data
CORRECTIONS_KEYWORDS = [
    r"jail\b",
    r"correct(ion|ional)",
    r"inmate",
    r"incarcerat",
    r"prison\b",
    r"sheriff.*contract",
    r"booking",
    r"detain",
]

# Public transit / microtransit (Scout program)
TRANSIT_KEYWORDS = [
    r"microtransit",
    r"on-demand\s+transit",
    r"freebee",
    r"befree",
    r"scout\s+(program|transit|shuttle)",
    r"ride[-\s]?share.*public",
]

# Campaign finance / lobbying / procurement
MONEY_KEYWORDS = [
    r"campaign\s+financ",
    r"lobby(ing|ist)",
    r"procurement",
    r"government\s+contract",
    r"vendor\s+payment",
    r"expenditure",
]

ALL_KEYWORD_GROUPS = {
    "ice_immigration": ICE_KEYWORDS,
    "florida_i4": FLORIDA_KEYWORDS,
    "corrections_jail": CORRECTIONS_KEYWORDS,
    "transit_microtransit": TRANSIT_KEYWORDS,
    "money_politics": MONEY_KEYWORDS,
}


def compile_patterns(keyword_list):
    """Compile a list of regex patterns (case-insensitive)."""
    return [re.compile(kw, re.IGNORECASE) for kw in keyword_list]


def match_text(text, compiled_patterns):
    """Return list of pattern strings that match anywhere in text."""
    if not text:
        return []
    return [p.pattern for p in compiled_patterns if p.search(text)]


def score_project(project, all_compiled):
    """Score a project against all keyword groups. Returns (score, matches_dict)."""
    name = project.get("name", "")
    desc = project.get("description", "") or ""
    searchable = f"{name} {desc}"

    # Also search file names
    file_names = " ".join(f.get("name", "") for f in project.get("files", []))
    searchable_with_files = f"{searchable} {file_names}"

    # Also search tags
    tags_text = " ".join(
        t.get("tag", {}).get("name", "")
        for t in project.get("tags", [])
    )
    searchable_full = f"{searchable_with_files} {tags_text}"

    matches = {}
    total_score = 0
    for group_name, patterns in all_compiled.items():
        hits = match_text(searchable_full, patterns)
        if hits:
            matches[group_name] = hits
            total_score += len(hits)

    return total_score, matches


def flatten_graphql_edges(obj):
    """Recursively flatten GraphQL edges/node structures."""
    if isinstance(obj, dict):
        if "edges" in obj and isinstance(obj["edges"], list):
            return [flatten_graphql_edges(edge.get("node", edge)) for edge in obj["edges"]]
        return {k: flatten_graphql_edges(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [flatten_graphql_edges(item) for item in obj]
    return obj


def format_project_summary(project, score, matches):
    """Create a human-readable summary dict for a scored project."""
    files = project.get("files", [])
    if isinstance(files, list):
        file_list = []
        for f in files:
            if isinstance(f, dict):
                file_list.append({
                    "name": f.get("name", ""),
                    "size": f.get("size"),
                    "updated": f.get("updatedAt", ""),
                })
    else:
        file_list = []

    tags = project.get("tags", [])
    if isinstance(tags, list):
        tag_names = []
        for t in tags:
            if isinstance(t, dict):
                tag_obj = t.get("tag", t)
                tag_names.append(tag_obj.get("name", str(t)))
            else:
                tag_names.append(str(t))
    else:
        tag_names = []

    return {
        "id": project.get("id", ""),
        "name": project.get("name", ""),
        "description": (project.get("description") or "")[:500],
        "is_open": project.get("isOpen"),
        "updated_at": project.get("updatedAt", ""),
        "relevance_score": score,
        "keyword_matches": matches,
        "file_count": len(file_list),
        "files": file_list[:50],  # cap at 50 files in summary
        "tags": tag_names,
        "contact": project.get("contact", ""),
        "contact_method": project.get("contactMethod", ""),
    }


def run_query(token, search_term=None, list_all=False, download_project=None, output_dir=None):
    """Main query logic."""
    try:
        from bln import Client
    except ImportError:
        print("ERROR: 'bln' package not installed. Run: pip install bln", file=sys.stderr)
        sys.exit(1)

    client = Client(token=token)
    results = {
        "query_timestamp": datetime.now(timezone.utc).isoformat(),
        "api_endpoint": client.endpoint,
        "mode": None,
        "projects": [],
        "errors": [],
    }

    # ------------------------------------------------------------------
    # Mode: Download files from a specific project
    # ------------------------------------------------------------------
    if download_project:
        results["mode"] = "download"
        out = output_dir or "./bln_downloads"
        os.makedirs(out, exist_ok=True)
        print(f"Fetching project {download_project}...")
        try:
            proj = client.get_project_by_id(download_project)
            proj = flatten_graphql_edges(proj)
            files = proj.get("files", [])
            print(f"  Project: {proj.get('name', '?')}")
            print(f"  Files: {len(files)}")
            downloaded = []
            for f in files:
                fname = f.get("name", "")
                print(f"  Downloading {fname}...")
                try:
                    path = client.download_file(download_project, fname, out)
                    downloaded.append({"name": fname, "path": str(path)})
                except Exception as e:
                    results["errors"].append(f"Download {fname}: {e}")
            results["downloaded"] = downloaded
            results["projects"] = [format_project_summary(proj, 0, {})]
        except Exception as e:
            results["errors"].append(f"Project fetch: {e}")
        return results

    # ------------------------------------------------------------------
    # Mode: Query open projects
    # ------------------------------------------------------------------
    print("Fetching open projects from BigLocalNews...")
    try:
        raw_projects = client.openProjects()
    except Exception as e:
        results["errors"].append(f"openProjects failed: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        return results

    # Flatten GraphQL edge/node structures
    projects = flatten_graphql_edges(raw_projects)
    if isinstance(projects, dict):
        # Sometimes returns a dict with a key containing the list
        for k, v in projects.items():
            if isinstance(v, list):
                projects = v
                break
    if not isinstance(projects, list):
        projects = [projects] if projects else []

    print(f"Found {len(projects)} open projects on the platform.")

    # ------------------------------------------------------------------
    # Compile keyword patterns
    # ------------------------------------------------------------------
    all_compiled = {
        group: compile_patterns(kws) for group, kws in ALL_KEYWORD_GROUPS.items()
    }

    # If user supplied a custom search term, add it
    if search_term:
        results["mode"] = "custom_search"
        results["search_term"] = search_term
        custom = compile_patterns([re.escape(search_term)])
        all_compiled["custom_search"] = custom
    elif list_all:
        results["mode"] = "list_all"
    else:
        results["mode"] = "investigation_scan"

    # ------------------------------------------------------------------
    # Score and filter projects
    # ------------------------------------------------------------------
    scored = []
    for proj in projects:
        if not isinstance(proj, dict):
            continue
        score, matches = score_project(proj, all_compiled)
        if list_all or score > 0:
            scored.append((score, matches, proj))

    # Sort by relevance score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    for score, matches, proj in scored:
        summary = format_project_summary(proj, score, matches)
        results["projects"].append(summary)

    results["total_open_projects"] = len(projects)
    results["matched_projects"] = len(results["projects"])

    return results


def print_results(results):
    """Print a human-readable summary to stdout."""
    mode = results.get("mode", "?")
    print(f"\n{'='*70}")
    print(f"BigLocalNews Query Results  —  {results.get('query_timestamp', '')}")
    print(f"Mode: {mode}")
    print(f"API Endpoint: {results.get('api_endpoint', '')}")
    print(f"{'='*70}")

    if results.get("errors"):
        print(f"\n⚠  ERRORS ({len(results['errors'])}):")
        for err in results["errors"]:
            print(f"   • {err}")

    projects = results.get("projects", [])
    total = results.get("total_open_projects", "?")
    matched = results.get("matched_projects", len(projects))
    print(f"\nOpen projects on platform: {total}")
    print(f"Projects matching our keywords: {matched}")

    if not projects:
        print("\nNo matching projects found.")
        return

    print(f"\n{'─'*70}")
    for i, p in enumerate(projects[:30], 1):  # show top 30
        score = p.get("relevance_score", 0)
        name = p.get("name", "?")
        pid = p.get("id", "?")
        desc = p.get("description", "")[:200]
        files = p.get("file_count", 0)
        matches = p.get("keyword_matches", {})
        tags = p.get("tags", [])

        print(f"\n  [{i}] {name}")
        print(f"      ID: {pid}")
        print(f"      Score: {score}  |  Files: {files}  |  Updated: {p.get('updated_at', '?')}")
        if tags:
            print(f"      Tags: {', '.join(tags[:10])}")
        if desc:
            print(f"      Desc: {desc}")
        if matches:
            for group, kws in matches.items():
                print(f"      ✓ {group}: {', '.join(kws)}")
        if p.get("files"):
            print(f"      Files:")
            for f in p["files"][:10]:
                print(f"        • {f['name']}  ({f.get('size', '?')} bytes)")
            if len(p["files"]) > 10:
                print(f"        ... and {len(p['files'])-10} more")

    print(f"\n{'─'*70}")
    if len(projects) > 30:
        print(f"  ... {len(projects)-30} more projects in bln_results.json")

    print(f"\nFull results saved to bln_results.json")
    print(f"\nTo download files from a project:")
    print(f"  python3 bln_query.py --download PROJECT_ID --output-dir ./bln_downloads/")


def main():
    parser = argparse.ArgumentParser(
        description="Query BigLocalNews for investigation-relevant datasets"
    )
    parser.add_argument(
        "--search", "-s",
        help="Custom search term (added to default investigation keywords)"
    )
    parser.add_argument(
        "--list-all", "-a",
        action="store_true",
        help="List all open projects (no keyword filtering)"
    )
    parser.add_argument(
        "--download", "-d",
        metavar="PROJECT_ID",
        help="Download all files from a specific project"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./bln_downloads",
        help="Directory for downloaded files (default: ./bln_downloads/)"
    )
    parser.add_argument(
        "--output", "-O",
        default="bln_results.json",
        help="Output JSON file (default: bln_results.json)"
    )
    parser.add_argument(
        "--token", "-t",
        help="BLN API token (or set BLN_API_TOKEN env var)"
    )
    args = parser.parse_args()

    # Resolve token
    token = args.token or os.environ.get("BLN_API_TOKEN")
    if not token:
        print("=" * 70)
        print("BigLocalNews API Token Required")
        print("=" * 70)
        print()
        print("To use this script, you need a BigLocalNews API token.")
        print()
        print("Steps to get a token:")
        print("  1. Create an account at https://biglocalnews.org")
        print("  2. Log in and go to your profile/settings")
        print("  3. Generate a Personal API Token")
        print("  4. Set it as an environment variable:")
        print()
        print('     export BLN_API_TOKEN="your-token-here"')
        print()
        print("  Or pass it directly:")
        print()
        print('     python3 bln_query.py --token "your-token-here"')
        print()
        print("BigLocalNews is a Stanford-affiliated open data platform")
        print("hosting journalism datasets. It's free for journalists")
        print("and researchers.")
        print("=" * 70)

        # Write a stub results file so there's something on disk
        stub = {
            "query_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "token_required",
            "instructions": "Set BLN_API_TOKEN env var or use --token flag. "
                            "Register at https://biglocalnews.org to get a token.",
            "projects": [],
        }
        with open(args.output, "w") as f:
            json.dump(stub, f, indent=2)
        sys.exit(1)

    # Run the query
    results = run_query(
        token=token,
        search_term=args.search,
        list_all=args.list_all,
        download_project=args.download,
        output_dir=args.output_dir,
    )

    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Print summary
    print_results(results)


if __name__ == "__main__":
    main()
