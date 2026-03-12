#!/usr/bin/env python3
"""Check user's accessible projects and get details on high-priority targets."""
import json
import sys

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc3MzI2MzQ3NywianRpIjoiZjk0ZjYwMDctNTI2YS00MDBjLTljMTctZmU1ZmM0OTEwYTEwIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImZlOTRlNmVhLTMxZGQtNDQ4NS1hMjZlLTEwZWI5ZTU5ODJiZiIsIm5iZiI6MTc3MzI2MzQ3N30.7b_R0d6WD1sVSYC3PCe5mmasX_3XB4WJAuIXsearSmU"

import bln
c = bln.Client(token=TOKEN)

# 1) Check what projects user has roles on
print("=== User's Effective Project Roles ===")
try:
    roles = c.effectiveProjectRoles()
    print(f"User has access to {len(roles)} projects via effectiveProjectRoles")
    for r in roles:
        p = r.get("project", {})
        role = r.get("role", "?")
        print(f"  [{role}] {p.get('name', '?')} (id: {p.get('id', '?')[:30]}...)")
        if p.get("description"):
            print(f"        desc: {(p.get('description') or '')[:150]}")
        files = p.get("files", [])
        print(f"        files: {len(files)}")
        for f in files[:5]:
            if isinstance(f, dict):
                print(f"          - {f.get('name', '?')} ({f.get('size', '?')} bytes)")
except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()

# 2) Get full details of all open projects and dump names/descriptions
print("\n=== All 107 Open Projects (full list) ===")
projects = c.openProjects()
for i, p in enumerate(projects):
    name = p.get("name", "")
    desc = (p.get("description") or "")[:100]
    nfiles = len(p.get("files", []))
    print(f"{i+1:3d}. {name} ({nfiles} files) -- {desc}")
