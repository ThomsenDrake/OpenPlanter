#!/usr/bin/env python3
"""
Deep dive analysis to decode ICE stats column metrics (metric_1 through metric_6)
Based on value patterns and ICE footnotes documentation
"""

import json
from collections import defaultdict

def analyze_metrics():
    """Analyze metric values to infer their meaning"""
    
    print("="*80)
    print("ICE DETENTION STATS COLUMN METRICS DEEP DIVE")
    print("="*80)
    
    # Load facilities data
    with open('FY26_detentionStats_02122026_facilities.json', 'r') as f:
        data = json.load(f)
    
    # Extract metrics for I-4 corridor facilities
    i4_facilities = {
        'Hillsborough County Jail': None,
        'Orange County Jail (FL)': None,
        'Pinellas County Jail': None
    }
    
    print("\n--- I-4 CORRIDOR FACILITY DATA ---\n")
    
    for facility in data['florida_facilities']:
        name = facility[0]
        
        if name in i4_facilities:
            # Extract all available data
            print(f"\n{name}")
            print(f"  Address: {facility[1]}, {facility[2]}, {facility[3]} {facility[4]}")
            print(f"  AOR: {facility[5]}")
            print(f"  Type: {facility[6]}")
            print(f"  Gender: {facility[7]}")
            
            # Extract numeric columns (positions 8-20 based on data structure)
            print(f"\n  Numeric columns:")
            for i in range(8, min(21, len(facility))):
                col_value = facility[i]
                if col_value not in [None, "", " "]:
                    print(f"    Column {i}: {col_value}")
            
            # Store metrics (columns 8-13)
            i4_facilities[name] = {
                'type': facility[6],
                'metrics': facility[8:14],
                'all_data': facility
            }
    
    print("\n" + "="*80)
    print("METRIC COMPARISON ACROSS I-4 FACILITIES")
    print("="*80)
    
    print("\nMetric values (positions 8-13):")
    print(f"{'Facility':<30} {'Metric 8':>10} {'Metric 9':>10} {'Metric 10':>10} {'Metric 11':>10} {'Metric 12':>10} {'Metric 13':>10}")
    print("-" * 90)
    
    for name, data in i4_facilities.items():
        if data:
            metrics = data['metrics']
            print(f"{name:<30} {metrics[0]:>10.2f} {metrics[1]:>10.2f} {metrics[2]:>10.2f} {metrics[3]:>10.2f} {metrics[4]:>10.2f} {metrics[5]:>10.2f}")
    
    # Analyze what these metrics might represent
    print("\n" + "="*80)
    print("METRIC DECODING HYPOTHESES")
    print("="*80)
    
    print("\nBased on ICE footnotes and value patterns:")
    print("\nColumn 8 (smallest values: 1.28-2.60):")
    print("  - Likely: ADP (Average Daily Population) - actual ICE detainee count")
    print("  - Orange highest (2.60), Pinellas moderate (1.84), Hillsborough lowest (1.28)")
    
    print("\nColumn 9 (medium values: 1.65-43.00):")
    print("  - Likely: ALOS (Average Length of Stay) in days")
    print("  - Orange highest (43 days), Pinellas moderate (24 days), Hillsborough lowest (1.65 days)")
    print("  - Pattern suggests Orange holds detainees longer")
    
    print("\nColumn 10 (varied: 1.54-15.31):")
    print("  - Could be: Total capacity or bed count")
    print("  - Orange highest (15.31), suggesting larger facility")
    
    print("\nColumns 11-13 (smaller values):")
    print("  - Could be: Sub-populations (male/female breakdown)")
    print("  - Could be: Different classification levels")
    print("  - Could be: Different ICE threat levels")
    
    # Look at raw data structure
    print("\n" + "="*80)
    print("RAW DATA STRUCTURE ANALYSIS")
    print("="*80)
    
    # Check a sample facility
    print("\nSample facility (Hillsborough County Jail):")
    sample = data['florida_facilities'][1]  # Hillsborough
    for i, val in enumerate(sample):
        print(f"  Position {i}: {val}")
    
    print("\n" + "="*80)
    print("ICE FOOTNOTES REFERENCE")
    print("="*80)
    
    print("""
From FY26_detentionStats_02122026_parsed.json footnotes:

Key terms:
- ADP: Average daily population
- ALOS: Average length of stay
- AOR: Area of Responsibility
- Classification Level: Security levels A/B/C/D
- ICE Threat Level: Criminality levels 1/2/3/None
- Gender: Male/Female breakdowns
- Facility Type: IGSA, USMS IGA, etc.

HYPOTHESIS FOR COLUMN MAPPING:
- Col 8: ADP (Average Daily Population) - ICE detainees
- Col 9: ALOS (Average Length of Stay) - in days
- Col 10: Total ICE-dedicated beds or capacity
- Col 11: Male population/capacity
- Col 12: Female population/capacity
- Col 13: Alternative measure (booked/released?)

NEED TO VERIFY:
- Cross-reference with official ICE data dictionary
- Compare with other years to see if columns shift
- Check if column positions vary by facility type
""")

if __name__ == '__main__':
    try:
        analyze_metrics()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
