#!/usr/bin/env python3
"""Direct BLN API search for Central FL ICE investigation."""

import json
import re
import sys

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc3MzI2MzQ3NywianRpIjoiZjk0ZjYwMDctNTI2YS00MDBjLTljMTctZmU1ZmM0OTEwYTEwIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImZlOTRlNmVhLTMxZGQtNDQ4NS1hMjZlLTEwZWI5ZTU5ODJiZiIsIm5iZiI6MTc3MzI2MzQ3N30.7b_R0d6WD1sVSYC3PCe5mmasX_3XB4WJAuIXsearSmU"

import bln

c = bln.Client(token=TOKEN)

# Get all open projects
print("Fetching open projects...", file=sys.stderr)
projects = c.openProjects()
print(f"Found {len(projects)} open projects", file=sys.stderr)

# Search keywords relevant to Central FL ICE investigation
SEARCH_PATTERNS = [
    (r"ICE\b", "ICE"),
    (r"immigration", "immigration"),
    (r"deten(tion|ee|ed)", "detention"),
    (r"IGSA", "IGSA"),
    (r"287.*g", "287g"),
    (r"deportat", "deportation"),
    (r"florida", "florida"),
    (r"orange.county", "orange_county"),
    (r"osceola", "osceola"),
    (r"seminole", "seminole"),
    (r"orlando", "orlando"),
    (r"sheriff", "sheriff"),
    (r"jail\b", "jail"),
    (r"correct(ion|ional)", "corrections"),
    (r"inmate", "inmate"),
    (r"incarcerat", "incarceration"),
    (r"enforcement.*removal|ERO\b", "ERO"),
    (r"customs.enforcement", "customs_enforcement"),
    (r"remov(al|ed)", "removal"),
    (r"campaign.financ", "campaign_finance"),
    (r"lobby", "lobbying"),
    (r"procurement", "procurement"),
    (r"government.contract", "gov_contracts"),
    (r"police", "police"),
    (r"law.enforcement", "law_enforcement"),
]

compiled = [(re.compile(pat, re.IGNORECASE), label) for pat, label in SEARCH_PATTERNS]

results = []
for proj in projects:
    name = proj.get("name", "") or ""
    desc = proj.get("description", "") or ""
    
    # Handle tags - could be strings or dicts
    tags_raw = proj.get("tags", []) or []
    tags_list = []
    for t in tags_raw:
        if isinstance(t, str):
            tags_list.append(t)
        elif isinstance(t, dict):
            tags_list.append(t.get("name", t.get("tag", {}).get("name", "") if isinstance(t.get("tag"), dict) else str(t.get("tag", ""))))
    tags_text = " ".join(tags_list)
    
    # Handle files
    files_raw = proj.get("files", []) or []
    file_names = []
    for f in files_raw:
        if isinstance(f, dict):
            file_names.append(f.get("name", ""))
        elif isinstance(f, str):
            file_names.append(f)
    file_text = " ".join(file_names)
    
    searchable = f"{name} {desc} {tags_text} {file_text}"
    
    matches = []
    for pat, label in compiled:
        if pat.search(searchable):
            matches.append(label)
    
    if matches:
        # Calculate relevance score - higher for ICE/detention + Florida overlap
        ice_related = any(m in matches for m in ["ICE", "immigration", "detention", "IGSA", "287g", "deportation", "ERO", "customs_enforcement", "removal"])
        florida_related = any(m in matches for m in ["florida", "orange_county", "osceola", "seminole", "orlando"])
        corrections_related = any(m in matches for m in ["jail", "corrections", "inmate", "incarceration", "sheriff"])
        
        score = len(matches)
        if ice_related and florida_related:
            score += 10  # Big bonus for ICE + Florida overlap
        if ice_related and corrections_related:
            score += 5
        if florida_related and corrections_related:
            score += 3
        
        results.append({
            "id": proj.get("id", ""),
            "name": name,
            "description": desc[:500] if desc else "",
            "tags": tags_list,
            "file_count": len(files_raw),
            "files": [f.get("name", "") if isinstance(f, dict) else str(f) for f in files_raw[:20]],
            "matches": matches,
            "score": score,
            "updatedAt": proj.get("updatedAt", ""),
        })

# Sort by score descending
results.sort(key=lambda x: x["score"], reverse=True)

print(f"\nFound {len(results)} matching projects", file=sys.stderr)
print(f"Top 5 scores: {[r['score'] for r in results[:5]]}", file=sys.stderr)

# Output
output = {
    "total_open_projects": len(projects),
    "matching_projects": len(results),
    "results": results,
}

with open("bln_search_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

# Also print top results
print("\n=== TOP MATCHING PROJECTS ===\n")
for r in results[:30]:
    print(f"[Score: {r['score']}] {r['name']}")
    print(f"  Matches: {', '.join(r['matches'])}")
    if r['description']:
        print(f"  Desc: {r['description'][:200]}")
    if r['files']:
        print(f"  Files ({r['file_count']}): {', '.join(r['files'][:5])}")
    print(f"  Updated: {r['updatedAt']}")
    print(f"  ID: {r['id']}")
    print()
