#!/usr/bin/env python3
"""
Phase 3 Recursive Analysis: Deep Cross-Reference Mining
Builds on Phase 1 & 2 findings from the prior session.
"""
import json
from collections import defaultdict
from datetime import datetime

# Load all datasets
with open('bln_ice_fl_contracts.json') as f:
    bln = json.load(f)

with open('recursive_analysis_results.json') as f:
    phase1 = json.load(f)

with open('entity_map.json') as f:
    entity_map = json.load(f)

# ====================================================================
# ANALYSIS 1: FL Performance Location Mapping → "ICE Footprint Atlas"
# ====================================================================
print("=" * 70)
print("ANALYSIS 1: ICE FLORIDA FOOTPRINT ATLAS")
print("=" * 70)

fl_contracts = [c for c in bln['ice_fl_contracts'] 
                if c.get('perf_state','') == 'FL' or 'FLORIDA' in c.get('perf_state','').upper()]

# Group by county
county_map = defaultdict(list)
for c in fl_contracts:
    county = c.get('perf_county', 'UNKNOWN').upper().strip()
    county_map[county].append(c)

print(f"\nTotal FL-performed contracts: {len(fl_contracts)}")
print(f"Counties with ICE spending: {len(county_map)}")
print()

# Known detention/IGA counties
known_detention_counties = {
    'ORANGE', 'OSCEOLA', 'HILLSBOROUGH', 'SEMINOLE', 'PINELLAS', 'POLK',
    'SARASOTA', 'WALTON', 'MIAMI-DADE', 'BROWARD'
}

# Known 287g counties  
known_287g_counties = {
    'ORANGE', 'OSCEOLA', 'HILLSBOROUGH', 'SEMINOLE', 'VOLUSIA',
    'BREVARD', 'FLAGLER', 'LAKE', 'POLK'
}

atlas = {}
for county in sorted(county_map.keys()):
    contracts = county_map[county]
    total = sum(float(c.get('total_obligated','0') or '0') for c in contracts)
    vendors = set(c.get('vendor','') for c in contracts)
    cities = set(c.get('perf_city','') for c in contracts)
    prefixes = set(c.get('contract_id','')[:6] for c in contracts if c.get('contract_id',''))
    
    # Determine facility type from contract prefixes
    has_detention = any(p.startswith('70CDCR') for p in prefixes)
    has_tactical = any(p.startswith('70CMSW') for p in prefixes)
    has_investigations = any(p.startswith('70CMSD') for p in prefixes)
    has_it = any(p.startswith('70CTD0') for p in prefixes)
    
    status = []
    if county in known_detention_counties:
        status.append('KNOWN_DETENTION')
    if county in known_287g_counties:
        status.append('287g')
    if has_detention and county not in known_detention_counties:
        status.append('⚠️ PHANTOM_DETENTION')
    if has_tactical:
        status.append('TACTICAL')
    if has_investigations:
        status.append('HSI')
    if has_it:
        status.append('IT_INFRA')
    
    atlas[county] = {
        'contracts': len(contracts),
        'total_obligated': total,
        'vendors': list(vendors),
        'cities': list(cities),
        'prefixes': list(prefixes),
        'status': status,
        'has_detention_contracts': has_detention,
        'has_tactical': has_tactical,
        'has_investigations': has_investigations,
        'has_it': has_it
    }
    
    print(f"\n{county} ({', '.join(cities)})")
    print(f"  Contracts: {len(contracts)} | Total: ${total:,.2f}")
    print(f"  Status: {' | '.join(status)}")
    print(f"  Prefixes: {', '.join(sorted(prefixes))}")
    print(f"  Vendors: {', '.join(sorted(vendors))[:120]}")

# Identify phantom counties - spending but no known agreements
print("\n" + "=" * 70)
print("PHANTOM COUNTIES: ICE spending with no known detention agreement")
print("=" * 70)
for county, info in sorted(atlas.items(), key=lambda x: -x[1]['total_obligated']):
    if county not in known_detention_counties and county not in known_287g_counties:
        if county != 'UNKNOWN':
            print(f"  ⚠️ {county}: {info['contracts']} contracts, ${info['total_obligated']:,.2f}")
            print(f"     Cities: {', '.join(info['cities'])}")
            print(f"     Vendors: {', '.join(info['vendors'])[:100]}")

# ====================================================================
# ANALYSIS 2: G4S → Allied Universal Transition Timeline
# ====================================================================
print("\n" + "=" * 70)
print("ANALYSIS 2: G4S → ALLIED UNIVERSAL TRANSITION TIMELINE")
print("=" * 70)

g4s_contracts = [c for c in bln['ice_fl_contracts'] if 'G4S' in c.get('vendor','')]
g4s_contracts.sort(key=lambda x: x.get('contract_id',''))

# Extract fiscal years from contract IDs
fy_analysis = defaultdict(list)
for c in g4s_contracts:
    cid = c.get('contract_id','')
    if len(cid) >= 8:
        fy = cid[6:8]  # Two digits after prefix
        fy_analysis[f'FY20{fy}'].append(c)

print("\nG4S contracts by fiscal year:")
for fy in sorted(fy_analysis.keys()):
    cs = fy_analysis[fy]
    total = sum(float(c.get('total_obligated','0') or '0') for c in cs)
    print(f"  {fy}: {len(cs)} contracts, ${total:,.2f}")
    for c in cs:
        print(f"    {c.get('contract_id','')} | {c.get('perf_city','')}, {c.get('perf_county','')}")

# Key finding: Last G4S contract year vs Allied Universal appearance
print("\nNOTE: G4S Secure Solutions was acquired by Allied Universal in 2021.")
print("All G4S contracts are pre-acquisition legacy contracts being closed out.")
print("Look for 'ALLIED UNIVERSAL' in newer contracts for the continuation.")

allied = [c for c in bln['ice_fl_contracts'] if 'ALLIED' in c.get('vendor','').upper()]
print(f"\nAllied Universal contracts found: {len(allied)}")
for c in allied:
    print(f"  {c.get('contract_id','')} | {c.get('vendor','')} | ${float(c.get('total_obligated','0') or '0'):,.2f}")

# ====================================================================
# ANALYSIS 3: Contract Acceleration Timeline
# ====================================================================
print("\n" + "=" * 70)
print("ANALYSIS 3: CONTRACT ACCELERATION TIMELINE")
print("=" * 70)

# Group ALL contracts by fiscal year
all_by_fy = defaultdict(list)
for c in bln['ice_fl_contracts']:
    cid = c.get('contract_id','')
    if len(cid) >= 8 and cid[:2] == '70':
        fy = f'FY20{cid[6:8]}'
        all_by_fy[fy].append(c)
    elif cid.startswith('HSCE'):
        # Legacy contracts - extract year differently
        all_by_fy['Legacy'].append(c)

print("\nICE FL contract origination by fiscal year:")
for fy in sorted(all_by_fy.keys()):
    cs = all_by_fy[fy]
    total = sum(float(c.get('total_obligated','0') or '0') for c in cs)
    vendors = len(set(c.get('vendor','') for c in cs))
    det = len([c for c in cs if c.get('contract_id','').startswith('70CDCR')])
    tac = len([c for c in cs if c.get('contract_id','').startswith('70CMSW')])
    inv = len([c for c in cs if c.get('contract_id','').startswith('70CMSD')])
    it_ = len([c for c in cs if c.get('contract_id','').startswith('70CTD0')])
    print(f"  {fy}: {len(cs):3d} contracts | ${total:>15,.2f} | {vendors} vendors | DET:{det} TAC:{tac} INV:{inv} IT:{it_}")

# ====================================================================
# ANALYSIS 4: IGA CROSS-REFERENCE MATRIX
# ====================================================================
print("\n" + "=" * 70)
print("ANALYSIS 4: IGA CROSS-REFERENCE MATRIX")
print("=" * 70)

# Known IGA/IGSA details from transcriptions
iga_matrix = {
    'Hillsborough': {
        'type': 'IGSA',
        'initial_date': '1983',
        'initial_rate': '$40/day',
        'current_rate': '$88/day (2025)',
        'rate_history': [
            ('1983', '$40/day', 'Original'),
            ('Amendment 1', '$50/day', 'Undated'),
            ('Amendment 2', '$55/day', 'Undated'),
            ('2014 renewal', '$70/day', '5-year term'),
            ('2019 renewal', '$80/day', '5-year term'),
            ('2024 amendment', '$88/day', 'Current'),
        ],
        'bed_cap': 'No explicit cap in agreement',
        'facility': 'Orient Road Jail, 1201 E. Orient Road, Tampa',
        'detainee_types': 'Male/Female adults',
        'special_notes': 'Oldest continuous IGSA in I-4 corridor; 40+ year relationship',
        'medical': 'County provides, ICE reimburses at cost',
        'transport': 'County provides to/from ICE offices and airports',
        'source': 'IGA-Florida-Hillsborough-County_Manual-Visual-Transcription.md'
    },
    'Osceola': {
        'type': 'IGSA',
        'initial_date': '2004',
        'initial_rate': '$56.71/day (in-house) / $56.71/day (overflow)',
        'current_rate': '$56.71/day (never renegotiated)',
        'rate_history': [
            ('2004', '$56.71/day', 'Original - NEVER CHANGED'),
        ],
        'bed_cap': 'Not specified in available agreement',
        'facility': 'Osceola County Correctional Facility',
        'detainee_types': 'Male/Female adults',
        'special_notes': '22 years at same rate - massive county subsidy; IGA references USMS pass-through',
        'medical': 'County provides basic, ICE covers extraordinary',
        'transport': 'County provides local transport',
        'source': 'IGA-Florida-Osceola-County-Sheriffs-Department_Manual-Visual-Transcription.md'
    },
    'Seminole (John E. Polk)': {
        'type': 'USMS IGA → ICE pass-through',
        'initial_date': '2004',
        'initial_rate': '$56.71/day',
        'current_rate': '$56.71/day (stagnant since 2004)',
        'rate_history': [
            ('2004', '$56.71/day', 'Original USMS rate'),
        ],
        'bed_cap': 'Not specified',
        'facility': 'John E. Polk Correctional Facility, 211 Eslinger Way, Sanford',
        'detainee_types': 'Federal prisoners (USMS + ICE)',
        'special_notes': 'USMS IGA 18-04-0023/0024 structure; ICE detainees held under USMS authority; 287(g) active since 2010',
        'medical': 'Facility provides, federal agency reimburses',
        'transport': 'USMS/ICE provide transport to court',
        'source': 'IGA-Florida-John-E-Polk-Correctional-Facility_Manual-Visual-Transcription.md'
    },
    'Pinellas': {
        'type': 'IGSA',
        'initial_date': 'Unknown (pre-2019)',
        'initial_rate': 'Unknown',
        'current_rate': '$85/day (2024)',
        'rate_history': [
            ('Pre-2019', 'Unknown', 'Original'),
            ('2024', '$85/day', 'Current per ICE stats'),
        ],
        'bed_cap': 'Unknown',
        'facility': 'Pinellas County Jail',
        'detainee_types': 'Male/Female adults',
        'special_notes': 'Also major OFTP weapons/tactical hub (22 contracts); dual detention + tactical role unique in corridor',
        'medical': 'County provides',
        'transport': 'County provides',
        'source': 'IGA-Florida-Pinellas-County-Sheriffs-Office_Manual-Visual-Transcription.md'
    },
    'Orange': {
        'type': 'IGSA',
        'initial_date': '1997',
        'initial_rate': 'Unknown',
        'current_rate': '$88/day (2024-2025)',
        'rate_history': [
            ('1997', 'Unknown', 'Original IGSA'),
            ('Multiple amendments', 'Escalating', 'Over 27 years'),
            ('2024', '$88/day', 'Current - CRISIS: actual cost $180/day'),
        ],
        'bed_cap': '130 (current cap per Demings letters)',
        'facility': 'Orange County Jail, 3723 Vision Blvd, Orlando',
        'detainee_types': 'Male/Female adults',
        'special_notes': 'CRISIS: March 13, 2026 IGSA deadline; county subsidizing $92/day per detainee; ended rebooking March 1, 2026; Demings ultimatum letters',
        'medical': 'County provides at significant loss',
        'transport': 'County provides',
        'source': 'PSL-Resources/IGSA Analysis.md + PRR-158704 (pending)'
    },
    'Polk': {
        'type': 'BOA + MOA + MOU (layered)',
        'initial_date': '2007 (earliest MOU)',
        'initial_rate': '$25/day (BOA standard)',
        'current_rate': '$25/day (BOA) + possible supplements',
        'rate_history': [
            ('2007', 'Unknown', 'Original MOU'),
            ('2014', 'Updated', 'MOU renewal'),
            ('2018', '$25/day', 'BOA (70CDCR18G series)'),
            ('2019', 'MOA supplement', 'Immigration enforcement cooperation'),
        ],
        'bed_cap': 'As available - no fixed cap',
        'facility': 'Polk County Jail',
        'detainee_types': 'ICE detainees on BOA holds',
        'special_notes': '7 different agreements found in MuckRock FOIA; layered structure = BOA ($25/day base) + MOA (cooperation terms) + MOU (operational procedures)',
        'medical': 'County provides basic',
        'transport': 'ICE ERO handles',
        'source': 'muckrock_documents/polk_county_ice/ (7 PDFs from FOIA #75988)'
    },
    'Sarasota': {
        'type': 'BOA + IGSA + MOA',
        'initial_date': '2003 (IGSA)',
        'initial_rate': 'Unknown (2003 IGSA)',
        'current_rate': '$25/day (BOA) / Unknown (IGSA)',
        'rate_history': [
            ('2003', 'Unknown', 'Original IGSA'),
            ('2018', '$25/day', 'BOA 70CDCR18G00000015'),
            ('2019', 'MOA supplement', 'Cooperation terms'),
        ],
        'bed_cap': 'As available',
        'facility': 'Sarasota County Jail',
        'detainee_types': 'ICE detainees',
        'special_notes': 'BOA contract number 15 in FY2018 series - confirms sequential numbering',
        'medical': 'County provides',
        'transport': 'ICE ERO handles',
        'source': 'muckrock_documents/sarasota_ice/ (3 PDFs from opclaudia FOIA)'
    },
    'Walton': {
        'type': 'BOA + MOA',
        'initial_date': '2018 (BOA)',
        'initial_rate': '$25/day',
        'current_rate': '$25/day (BOA)',
        'rate_history': [
            ('2018', '$25/day', 'BOA 70CDCR18G00000016'),
        ],
        'bed_cap': 'As available',
        'facility': 'Walton County Jail',
        'detainee_types': 'ICE detainees on BOA holds',
        'special_notes': 'BOA contract number 16 - sequential after Sarasota (15)',
        'medical': 'County provides',
        'transport': 'ICE ERO handles',
        'source': 'muckrock_documents/walton_county_ice/ (2 PDFs from opclaudia FOIA)'
    },
    'Broward': {
        'type': 'USMS Agreement + GEO Group private',
        'initial_date': 'Unknown',
        'initial_rate': 'Unknown',
        'current_rate': 'Unknown (GEO contract: $96.5M+)',
        'rate_history': [],
        'bed_cap': 'Unknown',
        'facility': 'Broward Transitional Center (GEO Group)',
        'detainee_types': 'ICE detainees (GEO-operated)',
        'special_notes': 'GEO Group operates Broward Transitional Center; USMS agreement found in MuckRock; unique private facility model',
        'medical': 'GEO Group provides per contract',
        'transport': 'GEO Group provides per contract',
        'source': 'muckrock_documents/broward_usms/ + FPDS contract 70CDCR24FR0000053'
    }
}

print("\nIGA/IGSA COMPARISON MATRIX")
print("-" * 120)
print(f"{'County':<20} {'Type':<15} {'Rate':<25} {'Since':<8} {'Years@Rate':<12} {'Annual Subsidy Est.':<20}")
print("-" * 120)

for county, info in sorted(iga_matrix.items()):
    rate = info['current_rate'].split('(')[0].strip()
    since = info['initial_date']
    
    # Calculate years at current rate
    try:
        if 'never' in info['current_rate'].lower() or 'stagnant' in info.get('special_notes','').lower():
            years_stagnant = 2026 - int(since[:4]) if since[:4].isdigit() else '?'
        else:
            years_stagnant = '?'
    except:
        years_stagnant = '?'
    
    # Estimate annual subsidy (if known)
    if '$88' in rate and county == 'Orange':
        subsidy = '$92/day × 130 beds × 365 = ~$4.4M/yr'
    elif '$56.71' in rate:
        subsidy = '$123+/day subsidy × beds × 365'  
    elif '$25' in rate:
        subsidy = '$155/day subsidy × beds × 365'
    elif '$85' in rate:
        subsidy = 'Moderate subsidy likely'
    else:
        subsidy = 'Unknown'
    
    print(f"{county:<20} {info['type']:<15} {rate:<25} {since:<8} {str(years_stagnant):<12} {subsidy:<20}")

# ====================================================================
# ANALYSIS 5: HIDDEN CONNECTIONS - Vendor Overlap Across Divisions
# ====================================================================
print("\n" + "=" * 70)
print("ANALYSIS 5: VENDOR CROSS-DIVISION OVERLAP")
print("=" * 70)

vendor_divisions = defaultdict(lambda: defaultdict(list))
for c in bln['ice_fl_contracts']:
    v = c.get('vendor','')
    cid = c.get('contract_id','')
    if len(cid) >= 6:
        prefix = cid[:6]
        vendor_divisions[v][prefix].append(cid)

print("\nVendors operating across multiple ICE divisions:")
for v in sorted(vendor_divisions.keys()):
    divs = vendor_divisions[v]
    if len(divs) > 1:
        div_summary = []
        for d, contracts in sorted(divs.items()):
            div_summary.append(f"{d}({len(contracts)})")
        print(f"  {v}: {' | '.join(div_summary)}")

# ====================================================================
# ANALYSIS 6: BOA SEQUENCE RECONSTRUCTION
# ====================================================================
print("\n" + "=" * 70)
print("ANALYSIS 6: BOA SEQUENCE RECONSTRUCTION (70CDCR18G series)")
print("=" * 70)

# Known BOAs
known_boas = {
    15: 'Sarasota County Sheriff',
    16: 'Walton County Sheriff',
}

# 29 counties with BOAs per PSL-Resources
boa_counties = [
    'Bay', 'Brevard', 'Charlotte', 'Columbia', 'DeSoto', 'Flagler',
    'Hernando', 'Highlands', 'Hillsborough', 'Indian River', 'Lake',
    'Lee', 'Manatee', 'Martin', 'Monroe', 'Nassau', 'Okaloosa',
    'Orange', 'Osceola', 'Palm Beach', 'Pasco', 'Pinellas', 'Polk',
    'Sarasota', 'Seminole', 'St. Johns', 'St. Lucie', 'Volusia', 'Walton'
]

print(f"\n29 BOA counties from PSL-Resources:")
print(f"Known mappings: #15=Sarasota, #16=Walton")
print(f"\nSequence analysis:")
print(f"  Numbers 1-14: Unknown counties (14 unmapped)")
print(f"  Number 15: Sarasota (CONFIRMED)")
print(f"  Number 16: Walton (CONFIRMED)")
print(f"  Numbers 17-29+: Unknown counties (13+ unmapped)")
print(f"\n  Total BOA pool: {len(boa_counties)} counties")
print(f"  Mapped: 2 ({2/len(boa_counties)*100:.1f}%)")
print(f"  Unmapped: {len(boa_counties)-2} ({(len(boa_counties)-2)/len(boa_counties)*100:.1f}%)")

# Cross-reference: which of the 29 BOA counties also appear in FPDS?
print("\n  BOA counties also in FPDS performance locations:")
for county in sorted(boa_counties):
    county_upper = county.upper().replace('ST.', 'ST').replace('DESOTO', 'DE SOTO')
    if county_upper in atlas or county.upper() in atlas:
        fpds_info = atlas.get(county_upper) or atlas.get(county.upper())
        if fpds_info:
            print(f"    ✓ {county}: {fpds_info['contracts']} FPDS contracts, ${fpds_info['total_obligated']:,.2f}")
    else:
        # Try fuzzy match
        matched = False
        for ac in atlas.keys():
            if county.upper()[:5] in ac:
                print(f"    ~ {county} → {ac}: {atlas[ac]['contracts']} FPDS contracts, ${atlas[ac]['total_obligated']:,.2f}")
                matched = True
                break
        if not matched:
            print(f"    ✗ {county}: No FPDS contracts found")

# ====================================================================
# ANALYSIS 7: KROME DETENTION CENTER DEEP DIVE
# ====================================================================
print("\n" + "=" * 70)
print("ANALYSIS 7: KROME SERVICE PROCESSING CENTER (SPC) DEEP DIVE")
print("=" * 70)

krome_contracts = []
for c in bln['ice_fl_contracts']:
    desc = c.get('description','').upper()
    vendor = c.get('vendor','').upper()
    city = c.get('perf_city','').upper()
    if 'KROME' in desc or ('MIAMI' in city and '70CDCR' in c.get('contract_id','')):
        krome_contracts.append(c)

print(f"\nKrome-related contracts: {len(krome_contracts)}")
for c in krome_contracts:
    print(f"  {c.get('contract_id','')} | {c.get('vendor','')[:40]} | ${float(c.get('total_obligated','0') or '0'):,.2f}")
    print(f"    {c.get('description','')[:100]}")

# ====================================================================
# ANALYSIS 8: TIMELINE OF ICE FL OPERATIONS (Chronological)
# ====================================================================
print("\n" + "=" * 70)
print("ANALYSIS 8: MASTER TIMELINE OF ICE FL OPERATIONS")
print("=" * 70)

events = []

# IGA dates
events.append(('1983', 'Hillsborough IGSA signed', 'Original agreement at $40/day', 'IGA transcription'))
events.append(('1997', 'Orange County IGSA signed', 'Original agreement', 'PSL-Resources'))
events.append(('2003', 'Sarasota IGSA signed', 'Original agreement', 'MuckRock FOIA'))
events.append(('2004', 'Osceola IGSA signed', '$56.71/day rate set', 'IGA transcription'))
events.append(('2004', 'Seminole/Polk USMS IGA signed', '$56.71/day rate set', 'IGA transcription'))
events.append(('2007', 'Polk County MOU with ICE', 'First known agreement', 'MuckRock FOIA #75988'))
events.append(('2010', 'Seminole County 287(g) activated', '287(g) Task Force Model', 'TRAC data'))
events.append(('2014', 'Hillsborough rate increase to $70/day', '5-year renewal', 'IGA transcription'))
events.append(('2014', 'Polk County MOU renewed', 'Updated terms', 'MuckRock FOIA'))
events.append(('2018', '29 FL counties sign BOAs', '70CDCR18G series issued', 'PSL-Resources + MuckRock'))
events.append(('2019', 'Hillsborough rate increase to $80/day', '5-year renewal', 'IGA transcription'))
events.append(('2019', 'Polk County MOA signed', 'Immigration enforcement cooperation', 'MuckRock'))
events.append(('2019', 'Sarasota MOA signed', 'Cooperation terms', 'MuckRock'))
events.append(('2021', 'G4S acquired by Allied Universal', 'Transport contractor transition', 'Public records'))
events.append(('2021', 'Akima Global: $50M Krome contract', '70CDCR21FR0000025', 'FPDS'))
events.append(('2023', 'Contract acceleration begins', '72 new contracts FY23-25 vs 115 all prior', 'FPDS analysis'))
events.append(('2024', 'Hillsborough rate increase to $88/day', 'Latest amendment', 'IGA transcription'))
events.append(('2024', 'Orange County rate at $88/day', 'Actual cost: $180/day', 'PSL-Resources'))
events.append(('2024-10', 'GEO Group Broward: $96.5M contract', '70CDCR24FR0000053', 'FPDS'))
events.append(('2025-02', 'DOGE contract cancellations begin', 'FPDS close-outs accelerate', 'BLN data'))
events.append(('2025-12', 'Massive OFTP weapons purchases', 'ADS Pinellas contracts', 'FPDS'))
events.append(('2026-01', 'Orange County ends rebooking', 'Effective March 1, 2026', 'PSL-Resources'))
events.append(('2026-02', 'Demings ultimatum letters', 'IGSA deadline set March 13', 'PSL-Resources'))
events.append(('2026-03-01', 'Orange County rebooking ends', 'ICE detainees no longer rebooked', 'PRR-158704'))
events.append(('2026-03-09', 'PRR requests acknowledged', '4 county sheriffs offices', 'foia_prr_tracking.csv'))
events.append(('2026-03-13', 'Orange County IGSA DEADLINE', 'County may terminate agreement', 'Demings letters'))

print("\nChronological timeline:")
for date, event, detail, source in sorted(events, key=lambda x: x[0]):
    print(f"  {date:<12} | {event}")
    print(f"               | Detail: {detail}")
    print(f"               | Source: {source}")
    print()

# ====================================================================
# SAVE STRUCTURED OUTPUTS
# ====================================================================

phase3_results = {
    'metadata': {
        'analysis_date': datetime.now().isoformat(),
        'description': 'Phase 3 Recursive Deep Analysis',
        'analyses': [
            'ICE Florida Footprint Atlas',
            'G4S → Allied Universal Timeline',
            'Contract Acceleration',
            'IGA Cross-Reference Matrix',
            'Vendor Cross-Division Overlap',
            'BOA Sequence Reconstruction',
            'Krome SPC Deep Dive',
            'Master Timeline'
        ]
    },
    'footprint_atlas': atlas,
    'iga_matrix': iga_matrix,
    'timeline': [{'date': d, 'event': e, 'detail': det, 'source': s} for d, e, det, s in events],
    'boa_reconstruction': {
        'confirmed': known_boas,
        'pool_counties': boa_counties,
        'total_predicted': len(boa_counties),
        'mapped': 2,
        'unmapped': len(boa_counties) - 2
    }
}

with open('recursive_phase3_results.json', 'w') as f:
    json.dump(phase3_results, f, indent=2, default=str)

print("\n✅ Phase 3 results saved to recursive_phase3_results.json")
