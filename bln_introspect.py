#!/usr/bin/env python3
"""Introspect BLN GraphQL schema and explore available queries."""
import json
import sys

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc3MzI2MzQ3NywianRpIjoiZjk0ZjYwMDctNTI2YS00MDBjLTljMTctZmU1ZmM0OTEwYTEwIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImZlOTRlNmVhLTMxZGQtNDQ4NS1hMjZlLTEwZWI5ZTU5ODJiZiIsIm5iZiI6MTc3MzI2MzQ3N30.7b_R0d6WD1sVSYC3PCe5mmasX_3XB4WJAuIXsearSmU"

import bln
c = bln.Client(token=TOKEN)

# 1) GraphQL introspection - get available query types
introspect_query = """
{
  __schema {
    queryType {
      fields {
        name
        description
        args {
          name
          type {
            name
            kind
            ofType { name kind }
          }
        }
      }
    }
  }
}
"""

try:
    resp = c.raw(introspect_query, {})
    fields = resp.get("__schema", {}).get("queryType", {}).get("fields", [])
    print("=== Available GraphQL Query Fields ===")
    for f in fields:
        args = ", ".join([
            f"{a['name']}: {a['type'].get('name') or a['type'].get('kind', '?')}"
            for a in f.get("args", [])
        ])
        print(f"  {f['name']}({args})")
        if f.get("description"):
            print(f"    desc: {f['description'][:200]}")
except Exception as e:
    print(f"Introspection error: {e}")

# 2) Also check what search_projects/search_files actually do
import inspect
print("\n=== search_projects source ===")
try:
    src = inspect.getsource(c.search_projects)
    print(src[:1000])
except:
    print("Could not get source")

print("\n=== search_files source ===")
try:
    src = inspect.getsource(c.search_files)
    print(src[:1000])
except:
    print("Could not get source")

# 3) Try the everything() method
print("\n=== everything() ===")
try:
    resp = c.everything()
    if isinstance(resp, list):
        print(f"everything() returned {len(resp)} items")
        if resp:
            print(f"First item keys: {list(resp[0].keys()) if isinstance(resp[0], dict) else type(resp[0])}")
    elif isinstance(resp, dict):
        print(f"everything() returned dict with keys: {list(resp.keys())}")
    else:
        print(f"everything() returned {type(resp)}")
except Exception as e:
    print(f"everything() error: {e}")
