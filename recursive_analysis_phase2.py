#!/usr/bin/env python3
"""
RECURSIVE ANALYSIS PHASE 2: 
- BOA contract number sequence analysis
- Cross-county IGA rate timeline construction
- Vendor-to-facility mapping
- Contract prefix decoder ring
- Entity network across all data sources
"""

import json
import re
from collections import defaultdict, Counter

# Load data
with open('bln_ice_fl_contracts.json') as f:
    ice_data = json.load(f)
with open('bln_dhs_contracts.json') as f:
    dhs_broad = json.load(f)

ice_fl = ice_data['ice_fl_contracts']
detention = ice_data['detention_related']
dhs_fl_broad = dhs_broad['dhs_florida_matches']

print("=" * 80)
print("RECURSIVE ANALYSIS PHASE 2: DEEP PATTERN DISCOVERY")
print("=" * 80)

# ============================================================
# 1. BOA CONTRACT NUMBER SEQUENCE ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("1. BOA CONTRACT NUMBER SEQUENCE ANALYSIS")
print("=" * 80)

# Known BOAs:
# 70CDCR18G00000015 - Sarasota County Sheriff
# 70CDCR18G00000016 - Walton County Sheriff
# Pattern: 70CDCR[FY][G][8-digit sequence]
# G = Grant/Agreement instrument type
# FY18 = executed in FY2018

# The sequential numbers 15 and 16 suggest there are at least 16 BOAs
# in this FY2018 series. If we assume they're Florida BOAs, we can
# identify the likely range.

print("""
KNOWN BOA CONTRACTS:
  70CDCR18G00000015 = Sarasota County Sheriff
  70CDCR18G00000016 = Walton County Sheriff

ANALYSIS:
  Prefix: 70CDCR = ICE Custody/Detention/Care/Release
  FY: 18 = Fiscal Year 2018
  Type: G = Grant/Intergovernmental Agreement
  Sequence: 00000015, 00000016 (sequential)

INFERENCE:
  There are at least 16 BOAs in this series (numbered 00000001-00000016+)
  From PSL-resources, we know 29 FL counties had BOAs as of Feb 2019.
  These were likely executed in FY2018 (Oct 2017 - Sep 2018).
  
  PREDICTED BOA NUMBERS (FL counties, FY2018 series):
  70CDCR18G00000001 through 70CDCR18G00000029+ (at minimum)
  
  Known mapping:
    ...00000015 = Sarasota
    ...00000016 = Walton
    
  From PSL-resources BOA list (29 counties):
    Bay, Brevard, Charlotte, Columbia, De Soto, Flagler, Hernando,
    Highlands, Hillsborough, Indian River, Lake, Lee, Manatee,
    Martin, Monroe, Nassau, Okeechobee, Palm Beach, Pasco, Pinellas,
    Polk, Santa Rosa, Sarasota, Seminole, St. Johns, St. Lucie,
    Suwannee, Walton + Louisiana (St. Charles Parish)
""")

# Search FPDS data for any 70CDCR18G contracts
g_contracts = []
for rec in ice_fl + dhs_fl_broad:
    cid = str(rec.get('contract_id', ''))
    if '18G0' in cid:
        g_contracts.append(rec)

print(f"Found {len(g_contracts)} 70CDCR18G-pattern contracts in FPDS data")
for rec in g_contracts:
    print(f"  {rec.get('contract_id','')} | {rec.get('vendor','')[:40]} | {rec.get('description','')[:60]}")

# ============================================================
# 2. CONTRACT PREFIX DECODER RING
# ============================================================
print("\n" + "=" * 80)
print("2. CONTRACT PREFIX DECODER RING")
print("=" * 80)

# Decode ICE contract numbering system
# 70 = DHS bureau
# Next 4 chars = ICE office code
# Next 2 = fiscal year
# Next chars = instrument type + sequence

prefix_decoder = {
    '70CDCR': 'ICE Custody/Detention Compliance & Removals (ERO)',
    '70CTD0': 'ICE Chief Technology Division / IT',
    '70CMSW': 'ICE Mission Support - Weapons/Tactical (OFTP)',
    '70CMSD': 'ICE Mission Support - Directorate',
    'HSCEMR': 'Legacy DHS/ICE (pre-2018 numbering)',
    '70SBUR': 'USCIS (sister agency under DHS)',
}

instrument_types = {
    'P': 'Purchase Order',
    'FC': 'Firm-Fixed Contract / BPA Call',
    'FR': 'Firm-Fixed Requirements Contract',
    'G': 'Grant/Intergovernmental Agreement',
    'M': 'Modification to existing agreement',
}

print("\nICE Contract Number Decoder:")
for prefix, meaning in prefix_decoder.items():
    print(f"  {prefix} = {meaning}")

print("\nInstrument Type Codes:")
for code, meaning in instrument_types.items():
    print(f"  {code} = {meaning}")

# ============================================================
# 3. CROSS-COUNTY IGA RATE TIMELINE
# ============================================================
print("\n" + "=" * 80)
print("3. CROSS-COUNTY IGA PER-DIEM RATE TIMELINE")
print("=" * 80)

# Build timeline from all IGA transcriptions
rate_history = {
    'Hillsborough County': [
        ('1983-02-01', 33.50, 'Base agreement J-B18-M-038'),
        ('1985-06-01', 40.00, 'Modification 1'),
        ('1987-05-01', 45.00, 'Modification 2'),
        ('1991-09-01', 58.00, 'Modification 3'),
        ('1994-03-01', 62.23, 'Modification 4'),
        ('1995-05-01', 83.46, 'Modification 5'),
        ('1996-09-01', 80.27, 'Modification 6 (overcharge recoupment, then $81.33)'),
        ('2004-01-19', 77.20, 'Modification 8 (temporary decrease)'),
        ('2004-09-01', 87.50, 'Modification 8 (scheduled increase)'),
        ('2005-09-01', 88.50, 'Modification 8 (scheduled increase)'),
    ],
    'Osceola County': [
        ('1986-09-01', 40.00, 'Base agreement J-B18-M-529'),
        ('1994-12-01', 55.00, 'Modification 2'),
        ('2004-03-01', 60.00, 'Modification 4 (temp)'),
        ('2004-09-01', 68.00, 'Modification 4 (scheduled)'),
        ('2005-09-01', 69.00, 'Modification 4 (scheduled)'),
        ('2018-00-00', 80.00, 'IGSA mod 70CDCR18M00000065 (from wiki)'),
    ],
    'Seminole County (John E. Polk)': [
        ('2004-01-01', 56.71, 'Base agreement 18-04-0024'),
    ],
    'Pinellas County': [
        ('2018-00-00', 80.00, 'Agreement 18-91-0041 (newer format)'),
    ],
    'Orange County': [
        ('1983-00-00', None, 'Original IGA 18-04-0023 (rate unknown for base)'),
        ('2022-02-01', 88.00, 'Modification 3 to IGA 18-04-0023'),
        ('2026-03-00', 88.00, 'Current rate (crisis - actual cost $180/day)'),
    ],
}

print("\nPer-Diem Rate Timeline Across I-4 Corridor Counties:")
print("-" * 90)
for county, rates in rate_history.items():
    print(f"\n  {county}:")
    for date, rate, note in rates:
        rate_str = f"${rate:.2f}" if rate else "N/A"
        print(f"    {date}: {rate_str:>10s}  — {note}")

# Calculate rate differences
print("\n\n--- RATE COMPARISON AS OF LATEST KNOWN ---")
print("-" * 70)
latest_rates = {
    'Hillsborough': 88.50,
    'Osceola': 80.00,
    'Seminole': 56.71,
    'Pinellas': 80.00,
    'Orange': 88.00,
}

avg_rate = sum(latest_rates.values()) / len(latest_rates)
print(f"\n  Average I-4 corridor per-diem: ${avg_rate:.2f}")
print(f"  Orange County actual cost:     $180.00")
print(f"  Federal subsidy gap:           ${180.00 - avg_rate:.2f}/day")
print()

for county, rate in sorted(latest_rates.items(), key=lambda x: -x[1]):
    diff = rate - avg_rate
    bar = '▓' * int(rate / 2)
    print(f"  {county:20s}: ${rate:6.2f}  ({'+' if diff >= 0 else ''}{diff:+.2f} vs avg)  {bar}")

# BOA comparison
print(f"\n  BOA rate (48hr hold): $50/hold ($25/day equivalent)")
print(f"  IGSA vs BOA premium:  ${avg_rate - 25:.2f}/day more for IGSA")

# ============================================================
# 4. AGREEMENT NUMBER PATTERNS - IDENTIFYING MISSING AGREEMENTS
# ============================================================
print("\n" + "=" * 80)
print("4. AGREEMENT NUMBER PATTERNS - IDENTIFYING GAPS")
print("=" * 80)

known_agreements = {
    'J-B18-M-038': ('Hillsborough', '1983-02-01', 'Original IGA'),
    'J-B18-M-529': ('Osceola', '1986-09-01', 'Original IGA'),
    '18-04-0023': ('Orange County', '~1983', 'Original IGA (Mod 3 in 2022)'),
    '18-04-0024': ('Seminole/John E. Polk', '2004-01-01', 'IGA'),
    '18-91-0041': ('Pinellas', '~2018', 'Modern format IGA'),
    '15-IGSA-0058': ('Osceola', '~2015', 'IGSA (direct ICE)'),
    '70CDCR18M00000065': ('Osceola', '~2018', 'IGSA modification'),
    '70CDCR18G00000015': ('Sarasota', '~2018', 'BOA'),
    '70CDCR18G00000016': ('Walton', '~2018', 'BOA'),
}

print("\nKnown Agreement Numbers:")
for num, (county, date, atype) in sorted(known_agreements.items()):
    print(f"  {num:25s} | {county:25s} | {date:12s} | {atype}")

# Pattern analysis for old-style J-series
print("\n--- J-Series Agreement Pattern ---")
print("  J-B18-M-038 (Hillsborough, 1983)")
print("  J-B18-M-529 (Osceola, 1986)")
print("  'B18' = judicial district 18 (Middle District of Florida)")
print("  M = Mutual/Main agreement")
print("  Sequential numbering: 038, 529")
print("  INFERENCE: Hundreds of agreements exist in this district alone")

# Pattern for 18-XX-XXXX series
print("\n--- Modern Agreement Pattern ---")
print("  18-04-0023 (Orange County, ~1983 origin, renewed)")
print("  18-04-0024 (Seminole, 2004)")
print("  18-91-0041 (Pinellas, ~2018)")
print("  '18' = district code (Middle FL)")
print("  '04' or '91' = facility/county sequence?")
print("  Sequential within group")

# ============================================================
# 5. FACILITY CODE MAPPING
# ============================================================
print("\n" + "=" * 80)
print("5. USMS FACILITY CODE MAPPING")
print("=" * 80)

facility_codes = {
    '4CM': ('Orange County Correctional Facility', 'Orange'),
    '4CC': ('Hillsborough County Jail', 'Hillsborough'),
    '4CB': ('Hillsborough County Camp', 'Hillsborough'),
    '4ML': ('Hillsborough County Stockade', 'Hillsborough'),
    '4YA': ('John E. Polk Correctional Facility', 'Seminole'),
    '4RI': ('Pinellas County Jail', 'Pinellas'),
}

print("\nKnown USMS Facility Codes (I-4 Corridor):")
for code, (name, county) in sorted(facility_codes.items()):
    print(f"  {code} = {name} ({county} County)")

print("""
PATTERN ANALYSIS:
  All codes start with '4' — this is the USMS district code for Middle FL
  Second/third characters = facility identifier
  
  UNKNOWN CODES (predicted):
    4?? = Osceola County Jail
    4?? = Volusia County Branch Jail  
    4?? = Volusia County Correctional Facility
    4?? = Polk County Jail
    
  These codes would be in the PRR responses from sheriff's offices.
""")

# ============================================================
# 6. VENDOR DEEP DIVE: GEO GROUP CONTRACT CHAIN
# ============================================================
print("\n" + "=" * 80)
print("6. GEO GROUP CONTRACT CHAIN ANALYSIS")
print("=" * 80)

geo_contracts = []
for rec in ice_fl:
    vendor = str(rec.get('vendor', ''))
    if 'GEO GROUP' in vendor.upper():
        geo_contracts.append(rec)

geo_contracts.sort(key=lambda x: x.get('contract_id', ''))

print(f"\nGEO Group: {len(geo_contracts)} ICE FL contracts")
total_geo = 0
for rec in geo_contracts:
    cid = rec.get('contract_id', '')
    total = rec.get('total_obligated', '0')
    desc = str(rec.get('description', ''))[:80]
    county = rec.get('perf_county', 'N/A')
    try:
        total_geo += float(total)
    except:
        pass
    print(f"  {cid} | ${total} | {county} | {desc}")

print(f"\n  TOTAL GEO GROUP OBLIGATED: ${total_geo:,.2f}")

# ============================================================
# 7. G4S CONTRACT CHAIN ANALYSIS  
# ============================================================
print("\n" + "=" * 80)
print("7. G4S SECURE SOLUTIONS CONTRACT CHAIN")
print("=" * 80)

g4s_contracts = []
for rec in ice_fl:
    vendor = str(rec.get('vendor', ''))
    if 'G4S' in vendor.upper():
        g4s_contracts.append(rec)

g4s_contracts.sort(key=lambda x: x.get('contract_id', ''))

print(f"\nG4S Secure Solutions: {len(g4s_contracts)} ICE FL contracts")
total_g4s = 0
for rec in g4s_contracts:
    cid = rec.get('contract_id', '')
    total = rec.get('total_obligated', '0')
    desc = str(rec.get('description', ''))[:80]
    county = rec.get('perf_county', 'N/A')
    try:
        total_g4s += float(total)
    except:
        pass
    print(f"  {cid} | ${total} | {county} | {desc}")

print(f"\n  TOTAL G4S OBLIGATED: ${total_g4s:,.2f}")

# G4S was acquired by Allied Universal in 2021
print("""
  NOTE: G4S Secure Solutions was acquired by Allied Universal in 2021.
  Any future contracts may appear under 'ALLIED UNIVERSAL' branding.
  This is a critical entity resolution issue for ongoing monitoring.
""")

# ============================================================
# 8. OPTIVOR TECHNOLOGIES - ICE TELECOM INFRASTRUCTURE
# ============================================================
print("\n" + "=" * 80)
print("8. OPTIVOR TECHNOLOGIES - ICE TELECOM INFRASTRUCTURE MAP")
print("=" * 80)

optivor = []
for rec in ice_fl:
    if 'OPTIVOR' in str(rec.get('vendor', '')).upper():
        optivor.append(rec)

print(f"\nOptivor Technologies: {len(optivor)} ICE contracts")
print("  (FL-based vendor providing PBX/VoIP to ICE facilities nationwide)")

# Map where Optivor has installed ICE phone systems
optivor_locations = set()
optivor_total = 0
for rec in optivor:
    desc = str(rec.get('description', ''))
    county = rec.get('perf_county', 'N/A')
    try:
        optivor_total += float(rec.get('total_obligated', 0))
    except:
        pass
    optivor_locations.add(county)
    # Extract facility mentions from descriptions
    if 'KROME' in desc.upper():
        print(f"  → KROME SPC reference: {rec.get('contract_id','')} | {desc[:80]}")
    if 'BROAD' in desc.upper():
        print(f"  → BROWARD reference: {rec.get('contract_id','')} | {desc[:80]}")
    if 'ORLANDO' in desc.upper():
        print(f"  → ORLANDO reference: {rec.get('contract_id','')} | {desc[:80]}")

print(f"\n  Total Optivor value: ${optivor_total:,.2f}")
print(f"  Locations served: {', '.join(sorted(optivor_locations))}")
print(f"  Significance: Optivor's installation footprint maps ICE office locations")

# ============================================================
# SAVE PHASE 2 RESULTS
# ============================================================

phase2 = {
    'boa_analysis': {
        'known_boas': {
            '70CDCR18G00000015': 'Sarasota County Sheriff',
            '70CDCR18G00000016': 'Walton County Sheriff',
        },
        'predicted_series_range': '70CDCR18G00000001 through 70CDCR18G00000029+',
        'boa_counties_29': [
            'Bay', 'Brevard', 'Charlotte', 'Columbia', 'De Soto', 'Flagler',
            'Hernando', 'Highlands', 'Hillsborough', 'Indian River', 'Lake',
            'Lee', 'Manatee', 'Martin', 'Monroe', 'Nassau', 'Okeechobee',
            'Palm Beach', 'Pasco', 'Pinellas', 'Polk', 'Santa Rosa', 'Sarasota',
            'Seminole', 'St. Johns', 'St. Lucie', 'Suwannee', 'Walton'
        ]
    },
    'rate_comparison': latest_rates,
    'rate_average': avg_rate,
    'facility_codes': {k: v[0] for k, v in facility_codes.items()},
    'geo_group_total': total_geo,
    'g4s_total': total_g4s,
    'optivor_locations': sorted(list(optivor_locations)),
    'agreement_patterns': {
        'j_series': 'J-B18-M-### (Middle FL, 1980s-era)',
        'modern_series': '18-##-#### (Middle FL, 2000s+ era)',
        'fpds_boa': '70CDCR18G######## (FY2018 BOAs)',
        'fpds_igsa_mod': '70CDCR18M######## (FY2018 IGSA mods)',
    }
}

with open('recursive_phase2_results.json', 'w') as f:
    json.dump(phase2, f, indent=2)

print("\nPhase 2 results saved to recursive_phase2_results.json")
