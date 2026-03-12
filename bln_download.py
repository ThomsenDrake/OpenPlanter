#!/usr/bin/env python3
"""Get details on Federal contract cancellations and download relevant files."""
import json
import os
import sys

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc3MzI2MzQ3NywianRpIjoiZjk0ZjYwMDctNTI2YS00MDBjLTljMTctZmU1ZmM0OTEwYTEwIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImZlOTRlNmVhLTMxZGQtNDQ4NS1hMjZlLTEwZWI5ZTU5ODJiZiIsIm5iZiI6MTc3MzI2MzQ3N30.7b_R0d6WD1sVSYC3PCe5mmasX_3XB4WJAuIXsearSmU"

import bln
c = bln.Client(token=TOKEN)

# Federal contract cancellations project
FED_CONTRACTS_ID = "UHJvamVjdDpjZjgyZTRkYS0xNTQ4LTQ4NGUtOTk2MC1mNzk4ZTg4NmY5ODM="

proj = c.get_project_by_id(FED_CONTRACTS_ID)
print("=== Federal Contract Cancellations ===")
print(f"Name: {proj.get('name')}")
print(f"Description: {proj.get('description', '')[:500]}")
print(f"Updated: {proj.get('updatedAt')}")

files = proj.get("files", [])
print(f"\nFiles ({len(files)}):")
for f in files:
    if isinstance(f, dict):
        print(f"  {f.get('name', '?')} - {f.get('size', '?')} bytes - updated {f.get('updatedAt', '?')}")
    else:
        print(f"  {f}")

# Download files
os.makedirs("bln_downloads/fed_contracts", exist_ok=True)

for f in files:
    fname = f.get("name", "") if isinstance(f, dict) else str(f)
    if not fname:
        continue
    print(f"\nDownloading: {fname}")
    try:
        c.download_file(FED_CONTRACTS_ID, fname, "bln_downloads/fed_contracts")
        fpath = os.path.join("bln_downloads/fed_contracts", fname)
        if os.path.exists(fpath):
            size = os.path.getsize(fpath)
            print(f"  Downloaded: {size} bytes")
        else:
            print(f"  File not found after download")
    except Exception as e:
        print(f"  Error: {e}")

# Also get details on Lee County Sheriff project
LEE_COUNTY_ID = "UHJvamVjdDpkOGI3NjExZi04NWYzLTQ0NmMtYmUzMC0yN2Y3MGQ3M2VjNTY="
print("\n\n=== Lee County Florida Sheriff Carmine Marceno ===")
proj2 = c.get_project_by_id(LEE_COUNTY_ID)
print(f"Name: {proj2.get('name')}")
print(f"Description:\n{proj2.get('description', '')[:2000]}")
print(f"Updated: {proj2.get('updatedAt')}")
files2 = proj2.get("files", [])
print(f"Files: {len(files2)}")
for f in files2:
    if isinstance(f, dict):
        print(f"  {f.get('name', '?')}")

# Also get Marceno Files project
MARCENO_ID = "UHJvamVjdDpmNjMwMTYzNC0xOTI0LTQwODUtYmJlYS1iMzMwZjNiMjIzNTg="
print("\n\n=== Marceno Files ===")
proj3 = c.get_project_by_id(MARCENO_ID)
print(f"Name: {proj3.get('name')}")
print(f"Description:\n{proj3.get('description', '')[:2000]}")
files3 = proj3.get("files", [])
print(f"Files: {len(files3)}")
for f in files3:
    if isinstance(f, dict):
        print(f"  {f.get('name', '?')} ({f.get('size', '?')} bytes)")
