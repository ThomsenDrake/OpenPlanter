#!/usr/bin/env python3
"""
Analyze ICE Detention Statistics Excel Files for I-4 Corridor Facilities
"""

import pandas as pd
import json
import os
from pathlib import Path

# I-4 Corridor counties
I4_COUNTIES = [
    'Hillsborough', 'Pinellas', 'Polk', 'Orange', 'Seminole', 'Volusia'
]

def read_excel_sheets(filepath):
    """Read all sheets from an Excel file"""
    try:
        xl = pd.ExcelFile(filepath)
        print(f"\n{os.path.basename(filepath)}:")
        print(f"  Sheets: {xl.sheet_names}")
        return xl
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None

def analyze_sheet(df, sheet_name, filename):
    """Analyze a single sheet for I-4 corridor facilities"""
    facilities_found = []
    
    # Convert to string for searching
    df_str = df.astype(str)
    
    # Search for county names in all columns
    for county in I4_COUNTIES:
        # Create mask for rows containing the county name
        mask = df_str.apply(lambda row: row.str.contains(county, case=False, na=False).any(), axis=1)
        
        if mask.any():
            matching_rows = df[mask]
            for idx, row in matching_rows.iterrows():
                facilities_found.append({
                    'county': county,
                    'sheet': sheet_name,
                    'file': filename,
                    'row_data': row.to_dict()
                })
    
    return facilities_found

def main():
    excel_dir = Path('ICE-Detention-Stats')
    all_facilities = []
    
    # Process each Excel file
    for excel_file in sorted(excel_dir.glob('*.xlsx')):
        xl = read_excel_sheets(excel_file)
        if not xl:
            continue
        
        # Analyze each sheet
        for sheet_name in xl.sheet_names:
            try:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                print(f"\n  Sheet '{sheet_name}': {df.shape[0]} rows, {df.shape[1]} columns")
                print(f"    Columns: {list(df.columns[:10])}")  # Show first 10 columns
                
                facilities = analyze_sheet(df, sheet_name, excel_file.name)
                if facilities:
                    all_facilities.extend(facilities)
                    print(f"    Found {len(facilities)} I-4 corridor references")
                    
            except Exception as e:
                print(f"    Error reading sheet {sheet_name}: {e}")
    
    print(f"\n{'='*60}")
    print(f"Total I-4 corridor facility references found: {len(all_facilities)}")
    
    # Save results
    with open('ice_stats_analysis.json', 'w') as f:
        json.dump(all_facilities, f, indent=2, default=str)
    
    print(f"\nResults saved to: ice_stats_analysis.json")
    
    # Show sample
    if all_facilities:
        print(f"\nSample findings:")
        for fac in all_facilities[:5]:
            print(f"  - {fac['county']} County in {fac['file']} / {fac['sheet']}")

if __name__ == '__main__':
    main()
