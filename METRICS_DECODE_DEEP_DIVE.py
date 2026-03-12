#!/usr/bin/env python3
"""
Deep dive to decode ICE stats column metrics
Analyzes value patterns and cross-references with ICE documentation
"""

import json

def decode_metrics():
    with open('FY26_detentionStats_02122026_facilities.json', 'r') as f:
        data = json.load(f)
    
    print("="*100)
    print("ICE DETENTION STATS COLUMN METRICS DEEP DIVE")
    print("="*100)
    
    # Get I-4 corridor facilities
    i4_names = ['HILLSBOROUGH COUNTY JAIL', 'ORANGE COUNTY JAIL (FL)', 'PINELLAS COUNTY JAIL']
    
    i4_facilities = []
    print("\n--- EXTRACTING I-4 CORRIDOR FACILITIES ---\n")
    
    for facility in data['florida_facilities']:
        name = facility[0]
        if name in i4_names:
            i4_facilities.append(facility)
            print(f"Found: {name}")
            print(f"  Type: {facility[6]}")
            print(f"  Gender: {facility[7]}")
            
            # Print all numeric columns
            print(f"\n  All numeric columns (positions 8-20):")
            for i in range(8, min(21, len(facility))):
                val = facility[i]
                if val is not None and val != "":
                    print(f"    Col {i}: {val}")
            print()
    
    # Now analyze the pattern
    print("\n" + "="*100)
    print("METRIC PATTERN ANALYSIS")
    print("="*100)
    
    print("\nComparing metrics across I-4 facilities:")
    print(f"\n{'Facility':<35} {'Col 8':>10} {'Col 9':>10} {'Col 10':>10} {'Col 11':>10} {'Col 12':>10} {'Col 13':>10}")
    print("-" * 105)
    
    for facility in i4_facilities:
        name = facility[0]
        values = [facility[i] if i < len(facility) else None for i in range(8, 14)]
        vals_str = [f"{float(v):10.2f}" if v not in [None, "", " "] else "      N/A" for v in values]
        print(f"{name:<35} {' '.join(vals_str)}")
    
    # Deep dive into what these might mean
    print("\n" + "="*100)
    print("HYPOTHESIS GENERATION")
    print("="*100)
    
    print("""
BASED ON VALUE PATTERNS AND ICE DOCUMENTATION:

Column 8 (values: 1.28 - 2.60):
  • Range: Small single digits
  • Hypothesis 1: ADP (Average Daily Population) - ICE detainees
  • Hypothesis 2: Utilization rate (percentage)
  • Pattern: Orange (2.60) > Pinellas (1.84) > Hillsborough (1.28)
  • Interpretation: Orange has highest average daily population

Column 9 (values: 1.65 - 43.00):
  • Range: 1-43, wide spread
  • Hypothesis 1: ALOS (Average Length of Stay) in days
  • Hypothesis 2: Total book-ins this period
  • Pattern: Orange (43) >> Pinellas (24) >> Hillsborough (1.65)
  • Interpretation: Orange holds detainees much longer (43 days avg)
  • Hillsborough's low value (1.65 days) suggests:
    - Short-term holding facility
    - Book-and-release operation
    - Just started operations (FY2026 only)

Column 10 (values: 1.54 - 15.31):
  • Range: Moderate values
  • Hypothesis: Total ICE-dedicated beds or capacity metric
  • Pattern: Orange (15.31) > Pinellas (6.43) > Hillsborough (1.54)
  • Interpretation: Orange has largest ICE capacity

Columns 11-13 (smaller values, 0.29 - 12.71):
  • These could be sub-populations:
    - Male/female breakdowns
    - Security classification levels (A/B/C/D)
    - ICE threat levels (1/2/3/None)
    - Criminal vs. non-criminal detainees
    
  • Pattern shows Orange highest across all columns

Column 14+ (values like 3.42, 1.57, etc.):
  • Additional breakdown metrics
  • Could be turnover rates, transfer counts, or other operational metrics
""")
    
    # Look at a larger facility for comparison
    print("\n" + "="*100)
    print("COMPARISON WITH LARGE FACILITY (Florida Soft-Sided)")
    print("="*100)
    
    large_facility = data['florida_facilities'][0]  # Florida Soft-Sided
    print(f"\nFacility: {large_facility[0]}")
    print(f"Type: {large_facility[6]}")
    print(f"\nNumeric columns:")
    for i in range(8, min(21, len(large_facility))):
        val = large_facility[i]
        if val not in [None, "", " "]:
            print(f"  Col {i}: {val}")
    
    print("""
OBSERVATION: Florida Soft-Sided Facility has MUCH larger values (633, 225, 179, etc.)
This suggests columns 9-13 are NOT simple bed counts.

REVISED HYPOTHESES:
- Column 8: Likely ADP or similar population measure (all facilities have small values)
- Columns 9-13: May be in different units or represent different metrics entirely
- Large facility values (hundreds) suggest these could be:
  * Total detainee-days (population × days)
  * Book-ins/Book-outs over period
  * Cumulative metrics rather than snapshot
""")
    
    # Create summary
    print("\n" + "="*100)
    print("CONFIDENCE LEVELS AND NEXT STEPS")
    print("="*100)
    
    print("""
CONFIDENCE IN INTERPRETATIONS:

HIGH CONFIDENCE:
✓ Column 8 represents a population or utilization metric
✓ Orange County has highest values across all metrics
✓ Hillsborough has lowest values (new facility, just started FY2026)

MEDIUM CONFIDENCE:
~ Column 9 likely represents ALOS or cumulative book-in count
~ Columns 10-13 are related sub-populations or capacity measures

LOW CONFIDENCE:
✗ Exact column definitions (need official ICE data dictionary)
✗ Unit of measurement (people? bed-days? percentages?)
✗ Whether columns are snapshots or cumulative

REQUIRED ACTIONS:
1. Obtain official ICE data dictionary or schema documentation
2. Cross-reference with ICE performance reports
3. Compare column positions across multiple fiscal years
4. Look for ICE technical documentation on detention statistics
5. Submit FOIA request for data schema/definitions

IMMEDIATE ACTIONS TO DOCUMENT:
→ Create TODO note to circle back on metric definitions
→ Add to FOIA request list: "Data dictionary for ICE detention statistics"
→ Search ICE.gov for technical documentation
→ Contact TRAC Immigration for data definitions
""")

if __name__ == '__main__':
    decode_metrics()
