#!/usr/bin/env python3
"""
Extract population trends from ICE detention statistics Excel files
Focus on I-4 corridor facilities: Pinellas, Orange, Hillsborough
"""

import pandas as pd
import json
from pathlib import Path

# I-4 corridor facilities that appear in ICE stats
I4_FACILITIES = {
    'PINELLAS COUNTY JAIL': {
        'county': 'Pinellas',
        'type': 'USMS IGA',
        'canonical_name': 'Pinellas County Jail'
    },
    'ORANGE COUNTY JAIL': {
        'county': 'Orange',
        'type': 'USMS IGA',
        'canonical_name': 'Orange County Jail'
    },
    'ORANGE COUNTY JAIL (FL)': {
        'county': 'Orange',
        'type': 'USMS IGA',
        'canonical_name': 'Orange County Jail'
    },
    'HILLSBOROUGH COUNTY JAIL': {
        'county': 'Hillsborough',
        'type': 'IGSA',
        'canonical_name': 'Hillsborough County Jail'
    }
}

def extract_facilities_sheet(filepath):
    """Extract the Facilities sheet from an Excel file"""
    try:
        xl = pd.ExcelFile(filepath)
        
        # Find the facilities sheet
        facilities_sheet = None
        for sheet_name in xl.sheet_names:
            if 'facilit' in sheet_name.lower():
                facilities_sheet = sheet_name
                break
        
        if not facilities_sheet:
            print(f"No facilities sheet found in {filepath.name}")
            return None
        
        df = pd.read_excel(filepath, sheet_name=facilities_sheet)
        return df
        
    except Exception as e:
        print(f"Error reading {filepath.name}: {e}")
        return None

def find_i4_facilities(df, year):
    """Find I-4 corridor facilities in the dataframe"""
    results = []
    
    # Get facility name column
    if 'Facility' in df.columns:
        name_col = 'Facility'
    elif 'Name' in df.columns:
        name_col = 'Name'
    else:
        # Use first column
        name_col = df.columns[0]
    
    # Search for each facility
    for facility_pattern, facility_info in I4_FACILITIES.items():
        mask = df[name_col].astype(str).str.contains(facility_pattern.replace('(', r'\(').replace(')', r'\)'), 
                                                      case=False, na=False, regex=True)
        
        if mask.any():
            matching_rows = df[mask]
            for idx, row in matching_rows.iterrows():
                # Extract key data
                record = {
                    'fiscal_year': year,
                    'facility': facility_info['canonical_name'],
                    'county': facility_info['county'],
                    'type': facility_info['type'],
                    'raw_name': row[name_col]
                }
                
                # Try to extract population/capacity data
                for col in df.columns:
                    if any(keyword in str(col).lower() for keyword in ['adp', 'population', 'average', 'daily']):
                        try:
                            val = pd.to_numeric(row[col], errors='coerce')
                            if pd.notna(val):
                                record[col.lower().replace(' ', '_')] = float(val)
                        except:
                            pass
                    
                    if any(keyword in str(col).lower() for keyword in ['alos', 'length', 'stay']):
                        try:
                            val = pd.to_numeric(row[col], errors='coerce')
                            if pd.notna(val):
                                record[col.lower().replace(' ', '_')] = float(val)
                        except:
                            pass
                
                results.append(record)
    
    return results

def main():
    excel_dir = Path('ICE-Detention-Stats')
    all_records = []
    
    # Process each year
    years = ['FY20', 'FY21', 'FY22', 'FY23', 'FY24', 'FY25', 'FY26']
    
    for year in years:
        # Find matching file
        matching_files = list(excel_dir.glob(f'{year}*.xlsx'))
        if not matching_files:
            print(f"No file found for {year}")
            continue
        
        filepath = matching_files[0]
        print(f"\nProcessing {filepath.name}...")
        
        df = extract_facilities_sheet(filepath)
        if df is not None:
            print(f"  Found {len(df.columns)} columns: {list(df.columns[:15])}")
            
            records = find_i4_facilities(df, year)
            if records:
                all_records.extend(records)
                print(f"  Found {len(records)} I-4 corridor facilities")
            else:
                print(f"  No I-4 corridor facilities found")
    
    # Save results
    print(f"\n{'='*60}")
    print(f"Total records extracted: {len(all_records)}")
    
    with open('population_trends.json', 'w') as f:
        json.dump(all_records, f, indent=2)
    
    print(f"Results saved to: population_trends.json")
    
    # Show summary
    if all_records:
        print(f"\nSummary by facility:")
        facilities = {}
        for record in all_records:
            fac = record['facility']
            if fac not in facilities:
                facilities[fac] = []
            facilities[fac].append(record['fiscal_year'])
        
        for fac, years in facilities.items():
            print(f"  {fac}: {', '.join(years)}")

if __name__ == '__main__':
    main()
