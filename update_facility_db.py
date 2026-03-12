#!/usr/bin/env python3
"""
Update main facility database with ICE detention statistics findings
"""

import json
from datetime import datetime

# Load existing database
with open('ice_facilities_i4_corridor.json', 'r') as f:
    db = json.load(f)

# ICE detention stats findings
# Facilities confirmed in ICE detention statistics FY2020-FY2026
ICE_STATS_CONFIRMED = {
    'PINELLAS COUNTY JAIL': {
        'detention_status': 'Active',
        'stats_type': 'USMS IGA',
        'first_year': 'FY2021',
        'years_active': ['FY21', 'FY22', 'FY23', 'FY24', 'FY25', 'FY26'],
        'notes': 'Most stable I-4 facility. Only facility present in FY2023.'
    },
    'ORANGE COUNTY JAIL': {
        'detention_status': 'Active',
        'stats_type': 'USMS IGA',
        'first_year': 'FY2022',
        'years_active': ['FY22', 'FY24', 'FY25', 'FY26'],
        'notes': 'Gap year in FY2023. Returned in FY2024 with (FL) suffix.'
    },
    'HILLSBOROUGH COUNTY JAIL': {
        'detention_status': 'Active',
        'stats_type': 'IGSA',
        'first_year': 'FY2026',
        'years_active': ['FY26'],
        'notes': 'NEW in FY2026. Orient Road Jail (not Falkenburg).'
    }
}

# Facilities with 287(g) but NOT in ICE detention stats
NOT_IN_STATS = [
    'Hillsborough County Falkenburg Road Jail',
    'Polk County Jail',
    'John E. Polk Correctional Facility',
    'Volusia County Branch Jail',
    'Volusia County Correctional Facility'
]

# Update metadata
db['metadata']['last_updated'] = datetime.now().strftime('%Y-%m-%d')
db['metadata']['data_sources'].append('ICE Detention Statistics FY2020-FY2026')
db['metadata']['ice_stats_analysis_date'] = '2026-02-27'

# Add summary stats
db['metadata']['ice_stats_summary'] = {
    'facilities_in_stats': 3,
    'facilities_with_287g_only': 5,
    'facilities_planned': 1,
    'total_facilities': 9
}

# Update each facility
for facility in db['facilities']:
    name = facility['canonical_name']
    
    # Check if in ICE stats
    in_stats = False
    stats_info = None
    
    for stats_name, info in ICE_STATS_CONFIRMED.items():
        if stats_name.replace(' COUNTY JAIL', '').lower() in name.lower():
            in_stats = True
            stats_info = info
            break
    
    # Add ICE stats fields
    facility['ice_stats'] = {
        'confirmed': in_stats,
        'source': 'ICE Detention Statistics FY2020-FY2026',
        'analysis_date': '2026-02-27'
    }
    
    if in_stats:
        facility['ice_stats']['detention_status'] = stats_info['detention_status']
        facility['ice_stats']['stats_type'] = stats_info['stats_type']
        facility['ice_stats']['first_year'] = stats_info['first_year']
        facility['ice_stats']['years_active'] = stats_info['years_active']
        facility['ice_stats']['notes'] = stats_info['notes']
        
        # Update facility type based on ICE stats
        if 'stats_type' in stats_info:
            facility['ice_stats_facility_type'] = stats_info['stats_type']
    else:
        facility['ice_stats']['detention_status'] = 'Not in statistics'
        facility['ice_stats']['notes'] = 'Has 287(g) agreement but does not appear in ICE detention statistics FY2020-FY2026'
        
        # Flag if it's in the known 287(g)-only list
        if any(non_stat.lower() in name.lower() for non_stat in NOT_IN_STATS):
            facility['ice_stats']['287g_only'] = True
            facility['ice_stats']['hypothesis'] = 'Book-and-release model - brief holding for processing, then transfer'

# Save updated database
with open('ice_facilities_i4_corridor_updated.json', 'w') as f:
    json.dump(db, f, indent=2)

print("Facility database updated successfully!")
print(f"\nUpdated {len(db['facilities'])} facilities")
print(f"\nICE Stats Summary:")
print(f"  Facilities in ICE stats: {db['metadata']['ice_stats_summary']['facilities_in_stats']}")
print(f"  Facilities with 287(g) only: {db['metadata']['ice_stats_summary']['facilities_with_287g_only']}")
print(f"  Planned facilities: {db['metadata']['ice_stats_summary']['facilities_planned']}")
print(f"\nSaved to: ice_facilities_i4_corridor_updated.json")
