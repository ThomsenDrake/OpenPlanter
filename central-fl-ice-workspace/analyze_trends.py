#!/usr/bin/env python3
"""
Clean and analyze population trends for I-4 corridor facilities
Filter out non-Florida facilities and create trends analysis
"""

import json
from pathlib import Path

def is_florida_facility(record):
    """Check if this is a Florida I-4 corridor facility"""
    raw_data = record.get('raw_data', [])
    
    # Check state field (index 3)
    if len(raw_data) > 3:
        state = raw_data[3]
        if state == 'FL':
            return True
    
    return False

def get_facility_info(record):
    """Extract facility information from raw data"""
    raw_data = record.get('raw_data', [])
    
    info = {
        'fiscal_year': record['fiscal_year'],
        'name': raw_data[0] if len(raw_data) > 0 else 'Unknown',
        'address': raw_data[1] if len(raw_data) > 1 else '',
        'city': raw_data[2] if len(raw_data) > 2 else '',
        'state': raw_data[3] if len(raw_data) > 3 else '',
        'zip': raw_data[4] if len(raw_data) > 4 else '',
        'area': raw_data[5] if len(raw_data) > 5 else '',
        'type': raw_data[6] if len(raw_data) > 6 else '',
        'gender': raw_data[7] if len(raw_data) > 7 else '',
        # Numeric columns (indices 8-19 are population/capacity data)
        'metric_1': float(raw_data[8]) if len(raw_data) > 8 and raw_data[8] else None,
        'metric_2': float(raw_data[9]) if len(raw_data) > 9 and raw_data[9] else None,
        'metric_3': float(raw_data[10]) if len(raw_data) > 10 and raw_data[10] else None,
        'metric_4': float(raw_data[11]) if len(raw_data) > 11 and raw_data[11] else None,
        'metric_5': float(raw_data[12]) if len(raw_data) > 12 and raw_data[12] else None,
        'metric_6': float(raw_data[13]) if len(raw_data) > 13 and raw_data[13] else None,
        'metric_7': float(raw_data[14]) if len(raw_data) > 14 and raw_data[14] else None,
        'metric_8': float(raw_data[15]) if len(raw_data) > 15 and raw_data[15] else None,
        'metric_9': float(raw_data[16]) if len(raw_data) > 16 and raw_data[16] else None,
        'metric_10': float(raw_data[17]) if len(raw_data) > 17 and raw_data[17] else None,
        'metric_11': float(raw_data[18]) if len(raw_data) > 18 and raw_data[18] else None,
        'metric_12': float(raw_data[19]) if len(raw_data) > 19 and raw_data[19] else None,
    }
    
    return info

def main():
    # Load raw data
    with open('population_trends_raw.json', 'r') as f:
        raw_data = json.load(f)
    
    print(f"Total records loaded: {len(raw_data)}")
    
    # Filter to Florida facilities only
    fl_records = [r for r in raw_data if is_florida_facility(r)]
    print(f"Florida I-4 corridor records: {len(fl_records)}")
    
    # Extract facility info
    facilities = []
    for record in fl_records:
        info = get_facility_info(record)
        facilities.append(info)
    
    # Group by facility
    facility_groups = {}
    for fac in facilities:
        name = fac['name']
        # Normalize names
        if 'ORANGE COUNTY JAIL' in name:
            name = 'Orange County Jail'
        elif 'PINELLAS' in name:
            name = 'Pinellas County Jail'
        elif 'HILLSBOROUGH' in name:
            name = 'Hillsborough County Jail'
        
        if name not in facility_groups:
            facility_groups[name] = []
        facility_groups[name].append(fac)
    
    # Create trends analysis
    print(f"\n{'='*60}")
    print("I-4 CORRIDOR FACILITY TRENDS (FY2020-FY2026)")
    print(f"{'='*60}")
    
    trends = {
        'metadata': {
            'analysis_date': '2026-02-27',
            'facilities_analyzed': len(facility_groups),
            'years_covered': ['FY20', 'FY21', 'FY22', 'FY23', 'FY24', 'FY25', 'FY26'],
            'note': 'Only Florida facilities included (NY filtered out)'
        },
        'facilities': {}
    }
    
    for facility_name in sorted(facility_groups.keys()):
        records = facility_groups[facility_name]
        years_active = [r['fiscal_year'] for r in records]
        
        print(f"\n{facility_name}:")
        print(f"  County: {records[0]['city']}, {records[0]['state']}")
        print(f"  Type: {records[0]['type']}")
        print(f"  Years Active: {', '.join(years_active)}")
        
        # Store in trends
        trends['facilities'][facility_name] = {
            'county': records[0]['city'],
            'state': records[0]['state'],
            'facility_type': records[0]['type'],
            'gender': records[0]['gender'],
            'years_active': sorted(years_active),
            'yearly_data': []
        }
        
        # Add yearly data
        for record in sorted(records, key=lambda x: x['fiscal_year']):
            year_data = {
                'fiscal_year': record['fiscal_year'],
                'population_metrics': {
                    'metric_1': record['metric_1'],
                    'metric_2': record['metric_2'],
                    'metric_3': record['metric_3'],
                    'metric_4': record['metric_4'],
                    'metric_5': record['metric_5'],
                    'metric_6': record['metric_6'],
                }
            }
            trends['facilities'][facility_name]['yearly_data'].append(year_data)
    
    # Save trends analysis
    with open('population_trends_analysis.json', 'w') as f:
        json.dump(trends, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Analysis saved to: population_trends_analysis.json")
    
    # Create summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    for fac_name in sorted(facility_groups.keys()):
        records = facility_groups[fac_name]
        first_year = min([r['fiscal_year'] for r in records])
        last_year = max([r['fiscal_year'] for r in records])
        years_count = len(records)
        
        print(f"\n{fac_name}:")
        print(f"  First appeared: {first_year}")
        print(f"  Most recent: {last_year}")
        print(f"  Total years in data: {years_count}")

if __name__ == '__main__':
    main()
