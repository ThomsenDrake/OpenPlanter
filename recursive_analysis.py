#!/usr/bin/env python3
"""
RECURSIVE INVESTIGATION: Deep cross-reference analysis of all ICE/DHS
contract data, IGA documents, and entity networks.

Threads:
1. Contract number pattern analysis (identify series, predecessors, modifications)
2. Vendor network mapping (who works for ICE in FL, what else do they do)
3. DHS broader contract ecosystem (7934 FL records)
4. BOA contract number decoding
5. Temporal analysis
6. Geographic clustering
"""

import json
import re
from collections import defaultdict, Counter
from datetime import datetime

# ============================================================
# LOAD ALL DATA
# ============================================================

print("=" * 80)
print("RECURSIVE INVESTIGATION: DEEP CROSS-REFERENCE ANALYSIS")
print("=" * 80)

# Load ICE FL contracts
with open('bln_ice_fl_contracts.json') as f:
    ice_data = json.load(f)

ice_fl = ice_data['ice_fl_contracts']  # 197
dhs_fl = ice_data['dhs_fl_contracts']  # 506
ice_i4 = ice_data['ice_i4_corridor']  # 101
detention = ice_data['detention_related']  # 83

print(f"\nDatasets loaded:")
print(f"  ICE FL contracts: {len(ice_fl)}")
print(f"  DHS FL contracts: {len(dhs_fl)}")
print(f"  ICE I-4 corridor: {len(ice_i4)}")
print(f"  Detention-related: {len(detention)}")

# Load broader DHS data
with open('bln_dhs_contracts.json') as f:
    dhs_broad = json.load(f)

dhs_fl_broad = dhs_broad['dhs_florida_matches']  # 7934
print(f"  DHS FL broad matches: {len(dhs_fl_broad)}")

# ============================================================
# THREAD 1: CONTRACT NUMBER PATTERN ANALYSIS
# ============================================================

print("\n" + "=" * 80)
print("THREAD 1: CONTRACT NUMBER PATTERN ANALYSIS")
print("=" * 80)

# Decode ICE contract number patterns
# Format: 70CDCR[YY][TYPE][SEQUENCE]
# 70 = DHS, CDCR = ICE Custody/Detention/Care/Release?
# Alternative: 70CTD0 = ICE CTD (Counter-Terrorism Division? or Technical?)
# 70CMSW = ICE CMSW (?)

contract_prefixes = Counter()
contract_series = defaultdict(list)

for rec in ice_fl:
    cid = rec.get('contract_id', '')
    if cid:
        # Extract prefix pattern
        match = re.match(r'^(\d{2}[A-Z]+\d{2})([A-Z]+)(\d+)$', cid)
        if match:
            prefix = match.group(1)
            ctype = match.group(2)
            seq = match.group(3)
            contract_prefixes[f"{prefix}{ctype}"] += 1
            # Group by base (prefix + type + first 7 digits to capture series)
            base = cid[:len(cid)-2] if len(cid) > 2 else cid
            contract_series[f"{prefix}{ctype}"].append({
                'contract_id': cid,
                'vendor': rec.get('vendor', ''),
                'total_obligated': rec.get('total_obligated', ''),
                'description': rec.get('description', '')[:100]
            })

print("\nContract Prefix Patterns:")
for prefix, count in contract_prefixes.most_common(20):
    print(f"  {prefix}: {count} contracts")

# Identify contract families (same base, different mods/years)
print("\n--- Contract Families (grouped by prefix pattern) ---")
for prefix, contracts in sorted(contract_series.items(), key=lambda x: -len(x[1])):
    if len(contracts) >= 3:
        print(f"\n  Family: {prefix} ({len(contracts)} contracts)")
        for c in contracts[:5]:
            print(f"    {c['contract_id']} | {c['vendor'][:35]:35s} | ${c['total_obligated']}")

# ============================================================
# BOA CONTRACT NUMBER ANALYSIS
# ============================================================

print("\n\n--- BOA Contract Number Pattern ---")
# Known BOA numbers: 70CDCR18G00000015 (Sarasota), 70CDCR18G00000016 (Walton)
# G = Grant/Agreement type
# 18 = FY2018
# Sequential numbering suggests we can identify other BOAs in the series

boa_pattern = re.compile(r'70CDCR\d{2}G\d+')

# Search all contracts for BOA-pattern numbers
boa_contracts = []
for rec in dhs_fl_broad:
    cid = rec.get('contract_id', '') or ''
    if boa_pattern.match(cid):
        boa_contracts.append(rec)

print(f"BOA-pattern contracts in DHS FL broad data: {len(boa_contracts)}")
for rec in boa_contracts[:20]:
    print(f"  {rec.get('contract_id','')} | {rec.get('vendor','')[:40]} | {rec.get('description','')[:60]}")

# Also search ICE FL for G-type contracts
for rec in ice_fl:
    cid = rec.get('contract_id', '') or ''
    if 'G0' in cid:
        print(f"  [ICE FL] {cid} | {rec.get('vendor','')[:40]} | {rec.get('description','')[:60]}")

# ============================================================
# THREAD 2: VENDOR NETWORK MAPPING
# ============================================================

print("\n" + "=" * 80)
print("THREAD 2: VENDOR NETWORK MAPPING")
print("=" * 80)

# Build comprehensive vendor profile for each vendor
vendor_profiles = defaultdict(lambda: {
    'contracts': [],
    'total_obligated': 0,
    'counties': set(),
    'contract_types': set(),
    'date_range': [],
    'descriptions': set()
})

for rec in ice_fl:
    vendor = rec.get('vendor', 'UNKNOWN')
    profile = vendor_profiles[vendor]
    profile['contracts'].append(rec.get('contract_id', ''))
    try:
        profile['total_obligated'] += float(rec.get('total_obligated', 0))
    except (ValueError, TypeError):
        pass
    county = rec.get('perf_county', '')
    if county:
        profile['counties'].add(county)
    desc = rec.get('description', '')
    if desc:
        profile['descriptions'].add(desc[:80])
    date = rec.get('date_cancelled', '') or rec.get('date_signed', '')
    if date:
        profile['date_range'].append(date)

print("\n--- Top 20 ICE FL Vendors by Total Obligated ---")
sorted_vendors = sorted(vendor_profiles.items(), 
                        key=lambda x: -x[1]['total_obligated'])

for vendor, profile in sorted_vendors[:20]:
    counties = ', '.join(sorted(profile['counties'])) or 'N/A'
    print(f"\n  {vendor}")
    print(f"    Contracts: {len(profile['contracts'])}")
    print(f"    Total Obligated: ${profile['total_obligated']:,.2f}")
    print(f"    Counties: {counties}")
    descs = list(profile['descriptions'])[:3]
    for d in descs:
        print(f"    Desc: {d}")

# ============================================================
# THREAD 2b: VENDOR CROSS-AGENCY CHECK
# ============================================================

print("\n\n--- Vendors Working for Multiple DHS Agencies ---")

# Check if ICE vendors also have contracts with other DHS components
ice_vendors = set(v for v in vendor_profiles.keys() if v != 'UNKNOWN')

vendor_agencies = defaultdict(set)
vendor_dhs_contracts = defaultdict(list)

for rec in dhs_fl_broad:
    vendor = rec.get('vendor', '')
    agency = rec.get('agency_name', '') or rec.get('funding_agency', '')
    if vendor in ice_vendors and agency:
        vendor_agencies[vendor].add(agency)
        vendor_dhs_contracts[vendor].append(rec)

multi_agency = {v: a for v, a in vendor_agencies.items() if len(a) > 1}
print(f"\nVendors with contracts across multiple DHS agencies: {len(multi_agency)}")
for vendor, agencies in sorted(multi_agency.items(), key=lambda x: -len(x[1])):
    print(f"\n  {vendor}")
    print(f"    Agencies: {', '.join(sorted(agencies))}")
    print(f"    Total DHS contracts: {len(vendor_dhs_contracts[vendor])}")

# ============================================================
# THREAD 3: GEOGRAPHIC CLUSTERING ANALYSIS
# ============================================================

print("\n" + "=" * 80)
print("THREAD 3: GEOGRAPHIC CLUSTERING")
print("=" * 80)

# Map all ICE contract activity by county
county_activity = defaultdict(lambda: {
    'contracts': [],
    'vendors': set(),
    'total_value': 0,
    'descriptions': []
})

for rec in ice_fl:
    county = rec.get('perf_county', 'UNKNOWN')
    county_activity[county]['contracts'].append(rec.get('contract_id', ''))
    county_activity[county]['vendors'].add(rec.get('vendor', ''))
    try:
        county_activity[county]['total_value'] += float(rec.get('total_obligated', 0))
    except (ValueError, TypeError):
        pass
    desc = rec.get('description', '')
    if desc and len(county_activity[county]['descriptions']) < 5:
        county_activity[county]['descriptions'].append(desc[:80])

print("\nICE Contract Activity by County:")
for county, data in sorted(county_activity.items(), key=lambda x: -x[1]['total_value']):
    print(f"\n  {county}")
    print(f"    Contracts: {len(data['contracts'])}")
    print(f"    Unique Vendors: {len(data['vendors'])}")
    print(f"    Total Value: ${data['total_value']:,.2f}")
    for v in sorted(data['vendors']):
        print(f"      Vendor: {v}")

# ============================================================
# THREAD 4: DHS BROAD ECOSYSTEM - HIDDEN ICE CONNECTIONS
# ============================================================

print("\n" + "=" * 80)
print("THREAD 4: DHS BROAD ECOSYSTEM - HIDDEN ICE CONNECTIONS")
print("=" * 80)

# Search the 7934 broader DHS FL records for detention/immigration keywords
detention_keywords = [
    'detention', 'detain', 'immigrant', 'immigration', 'ice ', 'i.c.e.',
    'removal', 'deportat', 'custody', 'incarcerat', 'jail', 'correctional',
    'igsa', 'intergovernmental', 'marshal', 'processing center',
    'enforcement and removal', 'ero ', 'border', 'alien'
]

hidden_ice = []
for rec in dhs_fl_broad:
    desc = str(rec.get('description', '')).lower()
    vendor = str(rec.get('vendor', '')).lower()
    agency = str(rec.get('agency_name', '')).lower()
    
    # Skip if already in our ICE FL dataset
    cid = rec.get('contract_id', '')
    
    for kw in detention_keywords:
        if kw in desc or kw in vendor:
            hidden_ice.append(rec)
            break

print(f"\nDetention/Immigration-related contracts in broader DHS FL data: {len(hidden_ice)}")

# Deduplicate by contract_id and group by agency
hidden_by_agency = defaultdict(list)
seen_cids = set()
for rec in hidden_ice:
    cid = rec.get('contract_id', '')
    if cid not in seen_cids:
        seen_cids.add(cid)
        agency = rec.get('agency_name', '') or rec.get('funding_agency', '') or 'Unknown'
        hidden_by_agency[agency].append(rec)

for agency, recs in sorted(hidden_by_agency.items(), key=lambda x: -len(x[1])):
    print(f"\n  Agency: {agency} ({len(recs)} contracts)")
    for rec in recs[:5]:
        print(f"    {rec.get('contract_id','')} | {rec.get('vendor','')[:35]} | {rec.get('description','')[:60]}")
    if len(recs) > 5:
        print(f"    ... and {len(recs)-5} more")

# ============================================================
# THREAD 5: TEMPORAL ANALYSIS - CONTRACT TIMELINE
# ============================================================

print("\n" + "=" * 80)
print("THREAD 5: TEMPORAL ANALYSIS")
print("=" * 80)

# Extract date patterns from contract IDs
year_pattern = re.compile(r'70[A-Z]+(\d{2})')
contract_years = Counter()

for rec in ice_fl:
    cid = rec.get('contract_id', '')
    match = year_pattern.match(cid)
    if match:
        yr = int(match.group(1))
        fy = 2000 + yr if yr < 50 else 1900 + yr
        contract_years[fy] += 1

print("\nICE FL Contract Volume by Fiscal Year (from contract IDs):")
for yr in sorted(contract_years.keys()):
    bar = '█' * contract_years[yr]
    print(f"  FY{yr}: {contract_years[yr]:3d} {bar}")

# Check for acceleration/deceleration patterns
if contract_years:
    recent = sum(v for k, v in contract_years.items() if k >= 2023)
    older = sum(v for k, v in contract_years.items() if k < 2023)
    print(f"\n  Pre-FY2023: {older} contracts")
    print(f"  FY2023+:    {recent} contracts")

# ============================================================
# THREAD 6: I-4 CORRIDOR DEEP DIVE - EVERY CONTRACT
# ============================================================

print("\n" + "=" * 80)
print("THREAD 6: I-4 CORRIDOR - COMPLETE CONTRACT INVENTORY")
print("=" * 80)

i4_counties = {'ORANGE', 'SEMINOLE', 'VOLUSIA', 'HILLSBOROUGH', 'PINELLAS', 'POLK',
               'OSCEOLA', 'LAKE'}

print(f"\nAll {len(ice_i4)} I-4 corridor ICE contracts:")
for rec in sorted(ice_i4, key=lambda x: x.get('perf_county', '')):
    county = rec.get('perf_county', 'N/A')
    cid = rec.get('contract_id', 'N/A')
    vendor = rec.get('vendor', 'N/A')
    total = rec.get('total_obligated', 'N/A')
    desc = str(rec.get('description', ''))[:70]
    print(f"  [{county:15s}] {cid} | {vendor[:30]:30s} | ${total} | {desc}")

# ============================================================
# THREAD 7: ENTITY CROSS-REFERENCE
# ============================================================

print("\n" + "=" * 80)
print("THREAD 7: ENTITY CROSS-REFERENCE - CONNECTING DOTS")
print("=" * 80)

# Cross-reference FPDS vendors with IGA documents
print("\n--- Cross-referencing FPDS vendors with IGA document entities ---")

# Known entities from IGA transcriptions
iga_entities = {
    'orange_county': {
        'name': 'Orange County Board of County Commissioners',
        'iga_number': '18-04-0023',
        'rate': '$88/day',
        'facility': 'Orange County Correctional Facility',
        'usms_code': '4CM'
    },
    'seminole_county': {
        'name': 'Seminole County Sheriff',
        'iga_number': '18-04-0024',
        'rate': '$56.71/day',
        'facility': 'John E. Polk Correctional Facility',
        'usms_code': None
    },
    'hillsborough': {
        'name': 'Hillsborough County',
        'iga_number': None,
        'rate': None,
        'facility': 'Orient Road Jail / Falkenburg Road Jail',
        'usms_code': None
    },
    'pinellas': {
        'name': 'Pinellas County Sheriff',
        'iga_number': None,
        'rate': None,
        'facility': 'Pinellas County Jail',
        'usms_code': None
    },
    'osceola': {
        'name': 'Osceola County Sheriff',
        'iga_number': '15-IGSA-0058 / mod 70CDCR18M00000065',
        'rate': '$60/day (original) → $80/day (mod)',
        'facility': 'Osceola County Dept of Corrections',
        'usms_code': None
    }
}

# Check if any IGA entities appear as FPDS vendors
for county, info in iga_entities.items():
    name_parts = info['name'].lower().split()
    matches = []
    for rec in dhs_fl_broad:
        vendor = str(rec.get('vendor', '')).lower()
        desc = str(rec.get('description', '')).lower()
        # Check if county name appears in vendor or description
        if county.replace('_', ' ') in vendor or county.replace('_', ' ') in desc:
            matches.append(rec)
    
    if matches:
        print(f"\n  {info['name']}: {len(matches)} DHS contract references")
        for m in matches[:3]:
            print(f"    {m.get('contract_id','')} | {m.get('vendor','')[:40]} | {m.get('description','')[:50]}")

# ============================================================
# THREAD 8: OSCEOLA IGSA CONTRACT NUMBER RECURSION
# ============================================================

print("\n" + "=" * 80)
print("THREAD 8: OSCEOLA IGSA DEEP DIVE")
print("=" * 80)

# Known: Osceola IGSA mod number is 70CDCR18M00000065
# This gives us a specific contract in FPDS to trace
osceola_pattern = '70CDCR18M'

print(f"\nSearching for contracts in Osceola IGSA series ({osceola_pattern}*)...")
osceola_matches = []
for rec in dhs_fl_broad:
    cid = str(rec.get('contract_id', ''))
    if cid.startswith(osceola_pattern):
        osceola_matches.append(rec)

for rec in ice_fl:
    cid = str(rec.get('contract_id', ''))
    if cid.startswith(osceola_pattern):
        osceola_matches.append(rec)

if osceola_matches:
    print(f"Found {len(osceola_matches)} contracts in series:")
    for rec in osceola_matches:
        print(f"  {rec.get('contract_id','')} | {rec.get('vendor','')[:40]} | {rec.get('total_obligated','')} | {rec.get('description','')[:60]}")
else:
    print("  No matches in FPDS data (IGSA may be tracked differently)")

# Search broader for 70CDCR18M pattern (M = Modification? or different type)
m_contracts = []
for rec in dhs_fl_broad:
    cid = str(rec.get('contract_id', ''))
    if re.match(r'70CDCR\d{2}M', cid):
        m_contracts.append(rec)

print(f"\nAll '70CDCR##M' type contracts in DHS FL: {len(m_contracts)}")
for rec in m_contracts[:10]:
    print(f"  {rec.get('contract_id','')} | {rec.get('vendor','')[:40]} | {rec.get('description','')[:60]}")

# ============================================================
# SUMMARY STATISTICS
# ============================================================

print("\n" + "=" * 80)
print("SUMMARY OF RECURSIVE FINDINGS")
print("=" * 80)

print(f"""
Total data points analyzed:
  ICE FL contracts: {len(ice_fl)}
  DHS FL contracts: {len(dhs_fl)}
  DHS FL broad: {len(dhs_fl_broad)}
  ICE I-4 corridor: {len(ice_i4)}
  Detention-related: {len(detention)}
  
Key recursive discoveries:
  Contract families identified: {len([p for p, c in contract_series.items() if len(c) >= 3])}
  Unique ICE FL vendors: {len(vendor_profiles)}
  Multi-agency vendors: {len(multi_agency)}
  Hidden detention contracts: {len(hidden_ice)}
  Counties with ICE activity: {len(county_activity)}
""")

# ============================================================
# SAVE STRUCTURED RESULTS
# ============================================================

results = {
    'metadata': {
        'analysis_date': '2026-03-11',
        'description': 'Recursive cross-reference analysis of ICE/DHS FL contract data',
        'data_sources': [
            'bln_ice_fl_contracts.json (197 ICE FL, 506 DHS FL, 101 I-4, 83 detention)',
            'bln_dhs_contracts.json (7934 FL matches)',
            'IGA transcriptions (Orange, Seminole, Hillsborough, Pinellas, Osceola)'
        ]
    },
    'vendor_network': {
        vendor: {
            'contracts': len(profile['contracts']),
            'total_obligated': profile['total_obligated'],
            'counties': sorted(list(profile['counties'])),
            'descriptions': list(profile['descriptions'])[:5]
        }
        for vendor, profile in sorted_vendors[:30]
    },
    'multi_agency_vendors': {
        v: sorted(list(a)) for v, a in multi_agency.items()
    },
    'contract_years': dict(sorted(contract_years.items())),
    'county_activity': {
        county: {
            'contract_count': len(data['contracts']),
            'vendor_count': len(data['vendors']),
            'total_value': data['total_value'],
            'vendors': sorted(list(data['vendors'])),
            'sample_descriptions': data['descriptions'][:3]
        }
        for county, data in county_activity.items()
    },
    'hidden_detention_count': len(hidden_ice),
    'hidden_by_agency': {
        agency: len(recs) for agency, recs in hidden_by_agency.items()
    }
}

with open('recursive_analysis_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)

print("\nResults saved to recursive_analysis_results.json")
