#!/usr/bin/env python3
"""Deep BLN search using multiple API methods for Central FL ICE investigation."""

import json
import re
import sys

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc3MzI2MzQ3NywianRpIjoiZjk0ZjYwMDctNTI2YS00MDBjLTljMTctZmU1ZmM0OTEwYTEwIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImZlOTRlNmVhLTMxZGQtNDQ4NS1hMjZlLTEwZWI5ZTU5ODJiZiIsIm5iZiI6MTc3MzI2MzQ3N30.7b_R0d6WD1sVSYC3PCe5mmasX_3XB4WJAuIXsearSmU"

import bln

c = bln.Client(token=TOKEN)

results = {}

# 1) search_projects with various predicates
search_terms = [
    "detention", "ICE detention", "IGSA", "287g", "immigration enforcement",
    "jail", "Florida jail", "Orange County", "Orlando", "sheriff contract",
    "deportation", "inmate", "correctional facility", "Seminole County",
    "Osceola", "intergovernmental agreement", "federal detention",
]

print("=== search_projects ===", file=sys.stderr)
for term in search_terms:
    term_lower = term.lower()
    try:
        matches = c.search_projects(
            lambda p, t=term_lower: (
                t in (p.get("name", "") or "").lower() or
                t in (p.get("description", "") or "").lower()
            )
        )
        if matches:
            print(f"  '{term}': {len(matches)} results", file=sys.stderr)
            results[f"search_projects_{term}"] = []
            for m in matches:
                results[f"search_projects_{term}"].append({
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "description": (m.get("description") or "")[:300],
                    "files": [f.get("name", "") if isinstance(f, dict) else str(f) for f in (m.get("files") or [])[:10]],
                })
    except Exception as e:
        print(f"  '{term}': ERROR - {e}", file=sys.stderr)

# 2) search_files for specific file types/names
print("\n=== search_files ===", file=sys.stderr)
file_terms = [
    "detention", "ice", "igsa", "287g", "jail", "inmate",
    "immigration", "florida", "orange_county", "sheriff",
    "deportation", "correctional",
]

for term in file_terms:
    term_lower = term.lower()
    try:
        matches = c.search_files(
            lambda f, t=term_lower: t in (f.get("name", "") or "").lower()
        )
        if matches:
            print(f"  '{term}' in filename: {len(matches)} results", file=sys.stderr)
            results[f"search_files_{term}"] = []
            for m in matches[:20]:
                results[f"search_files_{term}"].append({
                    "name": m.get("name"),
                    "size": m.get("size"),
                    "updatedAt": m.get("updatedAt"),
                    "project": m.get("project", {}).get("name") if isinstance(m.get("project"), dict) else None,
                })
    except Exception as e:
        print(f"  '{term}': ERROR - {e}", file=sys.stderr)

# 3) Raw GraphQL for more flexibility
print("\n=== Raw GraphQL searches ===", file=sys.stderr)

# Try to get project details for top hits
top_project_ids = [
    "UHJvamVjdDpkOGI3NjExZi04NWYzLTQ0NmMtYmUzMC0yN2Y3MGQ3M2VjNTY=",  # Lee County Sheriff
    "UHJvamVjdDpjZjgyZTRkYS0xNTQ4LTQ4NGUtOTk2MC1mNzk4ZTg4NmY5ODM=",  # Federal contract cancellations
]

for pid in top_project_ids:
    try:
        proj = c.get_project_by_id(pid)
        if proj:
            name = proj.get("name", "unknown")
            print(f"  Project '{name}': {len(proj.get('files', []))} files", file=sys.stderr)
            results[f"project_detail_{name}"] = {
                "id": proj.get("id"),
                "name": name,
                "description": (proj.get("description") or "")[:1000],
                "files": [{
                    "name": f.get("name", ""),
                    "size": f.get("size"),
                    "updatedAt": f.get("updatedAt", ""),
                } if isinstance(f, dict) else str(f) for f in (proj.get("files") or [])[:30]],
            }
    except Exception as e:
        print(f"  Project {pid}: ERROR - {e}", file=sys.stderr)

# 4) Try raw GraphQL search query
print("\n=== Raw GraphQL keyword search ===", file=sys.stderr)
gql_searches = [
    "ICE detention Florida",
    "immigration enforcement jail",
    "IGSA intergovernmental",
    "287g sheriff Florida",
    "Orange County Florida detention",
    "Orlando ICE",
    "Seminole County Florida",
]

for query_term in gql_searches:
    try:
        gql = """
        query SearchProjects($search: String!) {
            searchProjects(search: $search) {
                edges {
                    node {
                        id
                        name
                        description
                        isOpen
                        files {
                            edges {
                                node {
                                    name
                                    size
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        resp = c.raw(gql, {"search": query_term})
        if resp and "searchProjects" in resp:
            edges = resp["searchProjects"].get("edges", [])
            if edges:
                print(f"  GraphQL '{query_term}': {len(edges)} results", file=sys.stderr)
                results[f"graphql_{query_term}"] = []
                for e in edges[:10]:
                    node = e.get("node", {})
                    files = []
                    if isinstance(node.get("files"), dict):
                        for fe in node["files"].get("edges", []):
                            fn = fe.get("node", {})
                            files.append(fn.get("name", ""))
                    results[f"graphql_{query_term}"].append({
                        "id": node.get("id"),
                        "name": node.get("name"),
                        "description": (node.get("description") or "")[:300],
                        "isOpen": node.get("isOpen"),
                        "files": files[:10],
                    })
            else:
                print(f"  GraphQL '{query_term}': 0 results", file=sys.stderr)
        else:
            print(f"  GraphQL '{query_term}': no searchProjects in response", file=sys.stderr)
    except Exception as e:
        print(f"  GraphQL '{query_term}': ERROR - {e}", file=sys.stderr)

with open("bln_deep_search.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nDone. Total result keys: {len(results)}", file=sys.stderr)
print(f"Saved to bln_deep_search.json", file=sys.stderr)
