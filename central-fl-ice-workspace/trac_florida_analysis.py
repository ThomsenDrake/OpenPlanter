#!/usr/bin/env python3
"""
TRAC Immigration Data Analysis - Florida I-4 Corridor
Cross-references TRAC data with existing ICE detention statistics
"""

import json
import re
from datetime import datetime

# TRAC Florida facility data from Feb 2026 snapshot
# Extracted from https://tracreports.org/immigration/detentionstats/facilities.html
TRAC_FL_FACILITIES = [
    {"name": "BAKER CORRECTIONAL INSTITUTION", "city": "SANDERSON", "type": "STATE", "guaranteed_min": None, "avg_pop": 871, "date": "02/05/2026"},
    {"name": "BAKER COUNTY SHERIFF DEPT.", "city": "MACCLENNY", "type": "IGSA", "guaranteed_min": 250, "avg_pop": 286, "date": "02/05/2026"},
    {"name": "BROWARD COUNTY JAIL", "city": "FT. LAUDERDALE", "type": "IGSA", "guaranteed_min": None, "avg_pop": 3, "date": "02/05/2026"},
    {"name": "BROWARD TRANSITIONAL CENTER", "city": "POMPANO BEACH", "type": "CDF", "guaranteed_min": 700, "avg_pop": 681, "date": "02/05/2026"},
    {"name": "GLADES COUNTY DETENTION CENTER", "city": "MOORE HAVEN", "type": "IGSA", "guaranteed_min": 700, "avg_pop": 458, "date": "02/05/2026"},
    {"name": "HENDRY COUNTY JAIL", "city": "CLEWISTON", "type": "IGSA", "guaranteed_min": None, "avg_pop": 59, "date": "02/05/2026"},
    {"name": "HILLSBOROUGH COUNTY JAIL", "city": "TAMPA", "type": "IGSA", "guaranteed_min": 125, "avg_pop": 132, "date": "02/05/2026"},
    {"name": "JACKSON COUNTY CORRECTIONAL FACILITY", "city": "MARIANNA", "type": "IGSA", "guaranteed_min": None, "avg_pop": 23, "date": "02/05/2026"},
    {"name": "KROME NORTH SERVICE PROCESSING CENTER", "city": "MIAMI", "type": "SPC", "guaranteed_min": 550, "avg_pop": 595, "date": "02/05/2026"},
    {"name": "MONROE COUNTY JAIL", "city": "KEY WEST", "type": "IGSA", "guaranteed_min": None, "avg_pop": 9, "date": "02/05/2026"},
    {"name": "ORLANDO ICE PROCESSING CENTER", "city": "ORLANDO", "type": "IGSA", "guaranteed_min": 150, "avg_pop": 167, "date": "02/05/2026"},  # I-4 CORRIDOR
    {"name": "PINELLAS COUNTY JAIL", "city": "CLEARWATER", "type": "IGSA", "guaranteed_min": None, "avg_pop": 4, "date": "02/05/2026"},  # I-4 CORRIDOR
]

# I-4 Corridor counties for cross-reference
I4_COUNTIES = {
    "HILLSBOROUGH": {"city": "TAMPA", "key_facilities": ["HILLSBOROUGH COUNTY JAIL"]},
    "PINELLAS": {"city": "CLEARWATER/ST. PETERSBURG", "key_facilities": ["PINELLAS COUNTY JAIL"]},
    "POLK": {"city": "BARTOW/LAKELAND", "key_facilities": []},  # Not in TRAC Feb 2026
    "ORANGE": {"city": "ORLANDO", "key_facilities": ["ORLANDO ICE PROCESSING CENTER"]},
    "SEMINOLE": {"city": "SANFORD", "key_facilities": []},  # Not in TRAC
    "VOLUSIA": {"city": "DAYTONA BEACH", "key_facilities": []},  # Not in TRAC
    "OSCEOLA": {"city": "KISSIMMEE", "key_facilities": []},  # Not in TRAC directly
}

# Historical Florida detention from TRAC (March 2024)
FL_DETENTION_MARCH_2024 = 1385
FL_DETENTION_FEB_2026 = 5231  # From Quick Facts

# Book-in data for Florida (extracted from TRAC)
# Note: TRAC doesn't break down book-ins by state, only national totals

def analyze_trac_vs_local():
    """Compare TRAC data with local ICE stats"""
    
    print("=" * 70)
    print("TRAC FLORIDA ANALYSIS - I-4 CORRIDOR")
    print("=" * 70)
    print()
    
    # Summary statistics
    print("## FLORIDA DETENTION OVERVIEW (TRAC Data)")
    print("-" * 50)
    print(f"March 2024 Population: {FL_DETENTION_MARCH_2024:,}")
    print(f"February 2026 Population: {FL_DETENTION_FEB_2026:,}")
    print(f"Growth: {FL_DETENTION_FEB_2026 - FL_DETENTION_MARCH_2024:,} (+{((FL_DETENTION_FEB_2026/FL_DETENTION_MARCH_2024)-1)*100:.1f}%)")
    print()
    
    # Florida facilities in TRAC
    print("## FLORIDA FACILITIES IN TRAC (Feb 2026)")
    print("-" * 50)
    total_beds = 0
    total_pop = 0
    for fac in TRAC_FL_FACILITIES:
        guaranteed = fac['guaranteed_min'] if fac['guaranteed_min'] else 0
        total_beds += guaranteed
        total_pop += fac['avg_pop']
        marker = " <-- I-4 CORRIDOR" if any(c in fac['name'] for c in ["HILLSBOROUGH", "PINELLAS", "ORLANDO"]) else ""
        print(f"  {fac['name']:<45} {fac['type']:<8} Min:{guaranteed:>4} Pop:{fac['avg_pop']:>4}{marker}")
    
    print(f"\n  TOTAL Guaranteed Minimum Beds: {total_beds:,}")
    print(f"  TOTAL Average Population: {total_pop:,}")
    print()
    
    # I-4 Corridor specific
    print("## I-4 CORRIDOR FACILITIES (TRAC)")
    print("-" * 50)
    i4_facilities = [f for f in TRAC_FL_FACILITIES if any(c in f['name'] for c in ["HILLSBOROUGH", "PINELLAS", "ORLANDO"])]
    i4_pop = sum(f['avg_pop'] for f in i4_facilities)
    for fac in i4_facilities:
        print(f"  {fac['name']}: {fac['avg_pop']} detainees")
    print(f"  I-4 Corridor Total (in TRAC): {i4_pop}")
    print()
    
    # Missing facilities analysis
    print("## I-4 COUNTIES MISSING FROM TRAC (Feb 2026)")
    print("-" * 50)
    for county, info in I4_COUNTIES.items():
        if not info['key_facilities'] or all(f not in [x['name'] for x in TRAC_FL_FACILITIES] for f in info['key_facilities']):
            print(f"  {county} County ({info['city']}) - NOT in TRAC current snapshot")
    
    print()
    
    return {
        "fl_march_2024": FL_DETENTION_MARCH_2024,
        "fl_feb_2026": FL_DETENTION_FEB_2026,
        "facilities": TRAC_FL_FACILITIES,
        "i4_facilities": i4_facilities,
        "i4_total_pop": i4_pop
    }

if __name__ == "__main__":
    results = analyze_trac_vs_local()
    
    # Save to JSON
    with open("trac_florida_analysis.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\nResults saved to trac_florida_analysis.json")
