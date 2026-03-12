#!/usr/bin/env python3
"""
Phase 5: Master Recursion - Deepest Cross-Reference Pass
=========================================================
This is the terminal recursion: every dataset cross-referenced against every other,
every entity traced through every chain, every gap quantified.
"""

import json
import re
from collections import defaultdict, Counter
from datetime import datetime

# Load all prior phase results
p1 = json.load(open('recursive_analysis_results.json'))
p2 = json.load(open('recursive_phase2_results.json'))
p3 = json.load(open('recursive_phase3_results.json'))
p4 = json.load(open('recursive_phase4_results.json'))
entity_map = json.load(open('ice_entity_map.json'))
vendor_net = json.load(open('vendor_network_map.json'))
contract_chains = json.load(open('contract_chain_analysis.json'))
prop_chain = json.load(open('property_ownership_chain.json'))

# Load raw contract data
bln_ice_raw = json.load(open('bln_ice_fl_contracts.json'))
bln_dhs_raw = json.load(open('bln_dhs_contracts.json'))
bln_ice = bln_ice_raw['ice_fl_contracts']  # list of 197 dicts
bln_dhs = bln_dhs_raw.get('dhs_florida_matches', [])  # DHS FL matches

# Load IGA rate comparison
iga_rates = json.load(open('iga_rate_comparison.json'))

print("=" * 80)
print("PHASE 5: MASTER RECURSION — TERMINAL DEPTH")
print("=" * 80)

###############################################################################
# RECURSION 5.1: BOA NUMBER SEQUENCE RECONSTRUCTION
###############################################################################
print("\n" + "=" * 60)
print("5.1: BOA CONTRACT NUMBER SEQUENCE RECONSTRUCTION")
print("=" * 60)

# Known: 15 = Sarasota, 16 = Walton
# Pool: 29 counties from PSL-Resources
# Contract format: 70CDCR18G000000XX where XX = 01-29

boa_pool = [
    'Bay', 'Brevard', 'Charlotte', 'Columbia', 'DeSoto', 'Flagler',
    'Hernando', 'Highlands', 'Hillsborough', 'Indian River', 'Lake',
    'Lee', 'Manatee', 'Martin', 'Monroe', 'Nassau', 'Okaloosa',
    'Orange', 'Osceola', 'Palm Beach', 'Pasco', 'Pinellas', 'Polk',
    'Sarasota', 'Seminole', 'St. Johns', 'St. Lucie', 'Volusia', 'Walton'
]

# Hypothesis: alphabetical assignment
boa_pool_sorted = sorted(boa_pool)
print(f"\nBOA Pool sorted alphabetically ({len(boa_pool_sorted)} counties):")
for i, county in enumerate(boa_pool_sorted, 1):
    number_str = f"70CDCR18G{i:09d}"
    marker = ""
    if county == "Sarasota":
        marker = " ← CONFIRMED (#15)"
    elif county == "Walton":
        marker = " ← CONFIRMED (#16)"
    print(f"  #{i:02d}: {county:20s} → {number_str}{marker}")

# Check if alphabetical hypothesis holds
alpha_check = {i+1: c for i, c in enumerate(boa_pool_sorted)}
print(f"\nAlphabetical hypothesis check:")
print(f"  Sarasota alphabetical position: #{boa_pool_sorted.index('Sarasota')+1}")
print(f"  Walton alphabetical position: #{boa_pool_sorted.index('Walton')+1}")
print(f"  Confirmed #15 = Sarasota? Alphabetical #{boa_pool_sorted.index('Sarasota')+1}")
print(f"  Confirmed #16 = Walton? Alphabetical #{boa_pool_sorted.index('Walton')+1}")

# Sarasota = alphabetical #21, but actual = #15 → NOT alphabetical
# Let's try other orderings
print(f"\n  RESULT: Alphabetical hypothesis FAILS (Sarasota would be #{boa_pool_sorted.index('Sarasota')+1}, not #15)")

# Try: geographic (north to south), signing order, or some other system
# With only 2 data points, we can't determine the sequence definitively
# But we can note that 15 and 16 are consecutive, and S-counties are together
print(f"\n  Alternative hypotheses:")
print(f"  - Signing order (chronological): Plausible but unverifiable")
print(f"  - Geographic (north to south): Would separate Sarasota/Walton")  
print(f"  - Batch processing order: ICE processed applications in received order")
print(f"  - Sarasota(15) + Walton(16) consecutive → possible shared batch submission")

###############################################################################
# RECURSION 5.2: VENDOR CROSS-AGENCY DEEP DIVE
###############################################################################
print("\n" + "=" * 60)
print("5.2: MULTI-AGENCY VENDOR NETWORK ANALYSIS")
print("=" * 60)

# Extract vendor details from BLN contracts
vendor_agencies = defaultdict(lambda: defaultdict(list))
vendor_values = defaultdict(float)
vendor_locations = defaultdict(set)

for contract in bln_ice:
    vendor = contract.get('vendor', 'UNKNOWN')
    agency = contract.get('agency_name', contract.get('contracting_agency', 'UNKNOWN'))
    value = contract.get('total_obligated', 0)
    try:
        value = float(str(value).replace('$', '').replace(',', ''))
    except:
        value = 0
    location = contract.get('perf_county', '')
    
    vendor_agencies[vendor][agency].append(contract.get('contract_id', 'UNK'))
    vendor_values[vendor] += value
    if location:
        vendor_locations[vendor].add(location)

# Also scan DHS broad
for contract in bln_dhs:
    if not isinstance(contract, dict):
        continue
    vendor = contract.get('vendor', 'UNKNOWN')
    agency = contract.get('agency_name', contract.get('contracting_agency', 'UNKNOWN'))
    value = contract.get('total_obligated', 0)
    try:
        value = float(str(value).replace('$', '').replace(',', ''))
    except:
        value = 0
    location = contract.get('perf_county', '')
    
    vendor_agencies[vendor][agency].append(contract.get('contract_id', 'UNK'))
    vendor_values[vendor] += value
    if location:
        vendor_locations[vendor].add(location)

# Find vendors serving both ICE and other DHS agencies in FL
cross_agency_vendors = {v: dict(a) for v, a in vendor_agencies.items() if len(a) > 1}
print(f"\nVendors serving multiple DHS agencies in Florida: {len(cross_agency_vendors)}")
for vendor, agencies in sorted(cross_agency_vendors.items(), key=lambda x: vendor_values[x[0]], reverse=True)[:20]:
    total = vendor_values[vendor]
    print(f"\n  {vendor} (${total:,.2f})")
    for agency, contracts in agencies.items():
        print(f"    {agency}: {len(contracts)} contracts")

###############################################################################
# RECURSION 5.3: CONTRACT PREFIX PATTERN ANALYSIS
###############################################################################
print("\n" + "=" * 60)
print("5.3: CONTRACT PREFIX PATTERN DEEP ANALYSIS")
print("=" * 60)

prefix_patterns = defaultdict(lambda: {'count': 0, 'value': 0, 'vendors': set(), 'years': set()})

for contract in bln_ice:
    cn = contract.get('contract_id', '')
    vendor = contract.get('vendor', '')
    value = contract.get('total_obligated', 0)
    try:
        value = float(str(value).replace('$', '').replace(',', ''))
    except:
        value = 0
    
    # Extract prefix (first 7 chars)
    prefix = cn[:7] if len(cn) >= 7 else cn
    # Extract year
    year_match = re.search(r'(\d{2})[A-Z]', cn[5:] if len(cn) > 5 else '')
    year = '20' + year_match.group(1) if year_match else 'UNK'
    
    prefix_patterns[prefix]['count'] += 1
    prefix_patterns[prefix]['value'] += value
    prefix_patterns[prefix]['vendors'].add(vendor)
    prefix_patterns[prefix]['years'].add(year)

print(f"\nContract prefix analysis ({len(prefix_patterns)} unique prefixes):")
for prefix, data in sorted(prefix_patterns.items(), key=lambda x: x[1]['value'], reverse=True):
    vendors_str = ', '.join(list(data['vendors'])[:3])
    if len(data['vendors']) > 3:
        vendors_str += f" +{len(data['vendors'])-3} more"
    years = sorted(data['years'])
    print(f"  {prefix}: {data['count']} contracts, ${data['value']:,.2f}, years: {','.join(years[:3])}, vendors: {vendors_str[:60]}")

###############################################################################
# RECURSION 5.4: RATE DISPARITY FORENSIC ANALYSIS
###############################################################################
print("\n" + "=" * 60)
print("5.4: RATE DISPARITY FORENSIC ANALYSIS")
print("=" * 60)

fm = p4['financial_model']
corridor = fm['corridor_per_diem_model']

print("\nCounty Rate vs Cost Analysis (annualized at 365 days):")
total_revenue = 0
total_cost = 0
for county, data in corridor.items():
    rate = data['rate']
    beds = data['beds']
    actual = data['actual_cost']
    annual_rev = rate * beds * 365
    annual_cost = actual * beds * 365
    subsidy = annual_cost - annual_rev
    pct_covered = (rate / actual) * 100
    total_revenue += annual_rev
    total_cost += annual_cost
    
    print(f"\n  {county}:")
    print(f"    Agreement: {data['agreement']}")
    print(f"    Per diem: ${rate}/day, Est. actual cost: ${actual}/day")
    print(f"    Beds: {beds}")
    print(f"    Annual ICE revenue: ${annual_rev:,.2f}")
    print(f"    Annual county cost: ${annual_cost:,.2f}")
    print(f"    Annual county SUBSIDY: ${subsidy:,.2f}")
    print(f"    Cost recovery rate: {pct_covered:.1f}%")
    
    # Rate stagnation analysis
    if county == 'Osceola' or county == 'Seminole':
        years_stagnant = 2026 - 2004
        cpi_estimate = 1.51  # ~51% CPI increase 2004-2026
        inflation_adjusted = rate / cpi_estimate
        print(f"    *** STAGNANT {years_stagnant} YEARS ***")
        print(f"    Inflation-adjusted 2004 value: ${inflation_adjusted:.2f}/day")
        print(f"    Real purchasing power lost: {(1 - inflation_adjusted/rate)*100:.1f}%")
    elif county == 'Polk':
        print(f"    *** WORST SUBSIDY: County covers ${actual-rate}/day per detainee ***")
        print(f"    *** BOA rate is STANDARDIZED at $25/day nationally ***")

print(f"\n  CORRIDOR TOTALS:")
print(f"    Total annual ICE revenue: ${total_revenue:,.2f}")
print(f"    Total annual county cost: ${total_cost:,.2f}")
print(f"    Total annual county SUBSIDY: ${total_cost - total_revenue:,.2f}")
print(f"    Weighted average cost recovery: {(total_revenue/total_cost)*100:.1f}%")

###############################################################################
# RECURSION 5.5: CORPORATE RELATIONSHIP GRAPH
###############################################################################
print("\n" + "=" * 60)
print("5.5: CORPORATE RELATIONSHIP GRAPH")
print("=" * 60)

# Build comprehensive entity graph
entities = []
relationships = []

# County entities
counties = {
    'Orange': {'type': 'county', 'agreement': 'IGSA', 'rate': 88, 'status': 'CRISIS - March 13 deadline'},
    'Hillsborough': {'type': 'county', 'agreement': 'IGSA', 'rate': 88, 'status': 'Active'},
    'Osceola': {'type': 'county', 'agreement': 'IGSA', 'rate': 56.71, 'status': 'Active - stagnant rate'},
    'Seminole': {'type': 'county', 'agreement': 'USMS IGA', 'rate': 56.71, 'status': 'Active - stagnant rate'},
    'Pinellas': {'type': 'county', 'agreement': 'IGSA', 'rate': 85, 'status': 'Active + OFTP hub'},
    'Polk': {'type': 'county', 'agreement': 'BOA+MOA+MOU', 'rate': 25, 'status': 'Active - worst subsidy'},
    'Broward': {'type': 'county', 'agreement': 'GEO CDF', 'rate': 'Private', 'status': 'Private operation'},
    'Sarasota': {'type': 'county', 'agreement': 'BOA+IGSA+MOA', 'rate': 25, 'status': 'Active'},
    'Walton': {'type': 'county', 'agreement': 'BOA+MOA', 'rate': 25, 'status': 'Active'},
}

for county, data in counties.items():
    entities.append({
        'id': f'county_{county.lower()}',
        'name': f'{county} County',
        'type': 'county_government',
        'properties': data
    })

# Federal entities
fed_entities = [
    {'id': 'ice_ero', 'name': 'ICE Enforcement and Removal Operations', 'type': 'federal_agency', 'properties': {'role': 'detention authority', 'budget_area': 'IGSA/BOA/CDF payments'}},
    {'id': 'usms', 'name': 'U.S. Marshals Service', 'type': 'federal_agency', 'properties': {'role': 'IGA pass-through', 'i4_presence': 'Seminole, Orange'}},
    {'id': 'ice_hsi', 'name': 'ICE Homeland Security Investigations', 'type': 'federal_agency', 'properties': {'role': 'investigations', 'i4_presence': 'multiple counties'}},
    {'id': 'ice_oftp', 'name': 'ICE Office of Firearms and Tactical Programs', 'type': 'federal_agency', 'properties': {'role': 'tactical/weapons', 'hub': 'Pinellas County'}},
    {'id': 'doge', 'name': 'DOGE (Government Efficiency)', 'type': 'oversight_body', 'properties': {'role': 'contract cancellations', 'impact': 'FY2025 cancellation wave'}},
]
entities.extend(fed_entities)

# Major vendors
vendor_entities = [
    {'id': 'geo_group', 'name': 'GEO Group Inc', 'type': 'private_contractor', 'properties': {'hq': 'Boca Raton, FL', 'total_ice_fl': 713376426.71, 'contracts': 17, 'facilities': ['Broward Transitional Center', 'Denver/Aurora CDF', 'Mesa Verde IPC'], 'note': 'HQ in FL inflates FL contract counts'}},
    {'id': 'g4s_allied', 'name': 'G4S Secure Solutions / Allied Universal', 'type': 'private_contractor', 'properties': {'total_ice_fl': 157346238.65, 'contracts': 20, 'service': 'Detainee transportation', 'note': 'G4S acquired by Allied Universal 2021; FPDS still shows G4S name'}},
    {'id': 'akima', 'name': 'Akima Global Services', 'type': 'private_contractor', 'properties': {'total_ice': 50049270, 'service': 'Krome SPC detention operations', 'note': 'Alaska Native Corporation subsidiary'}},
    {'id': 'optivor', 'name': 'Optivor Technologies', 'type': 'vendor', 'properties': {'service': 'VoIP/Telecom for detention facilities', 'contracts': 3, 'locations': ['Krome SPC', 'other FL facilities']}},
    {'id': 'leidos', 'name': 'Leidos Security Detection & Automation', 'type': 'vendor', 'properties': {'service': 'X-ray security equipment maintenance', 'contracts': 2, 'locations': ['Krome SPC']}},
    {'id': 'eola_power', 'name': 'EOLA Power LLC', 'type': 'vendor', 'properties': {'service': 'UPS power maintenance', 'contracts': 1, 'locations': ['Krome SPC']}},
    {'id': 'price_modern', 'name': 'Price Modern LLC', 'type': 'vendor', 'properties': {'service': 'Furniture/systems', 'contracts': 1, 'locations': ['Orlando OPLA office'], 'note': 'Multi-agency vendor (DHS + others)'}},
    {'id': 'action_target', 'name': 'Action Target Inc', 'type': 'vendor', 'properties': {'service': 'Firing range maintenance', 'contracts': 2, 'locations': ['Krome SPC']}},
]
entities.extend(vendor_entities)

# Facilities
facility_entities = [
    {'id': 'fac_orange', 'name': 'Orange County Jail', 'type': 'facility', 'properties': {'address': '3723 Vision Blvd, Orlando', 'beds': 130, 'agreement': 'IGSA', 'status': 'CRISIS'}},
    {'id': 'fac_hillsborough', 'name': 'Orient Road Jail', 'type': 'facility', 'properties': {'address': '1201 E. Orient Road, Tampa', 'beds': 200, 'agreement': 'IGSA'}},
    {'id': 'fac_osceola', 'name': 'Osceola County Correctional Facility', 'type': 'facility', 'properties': {'agreement': 'IGSA', 'rate_stagnant_since': 2004}},
    {'id': 'fac_seminole', 'name': 'John E. Polk Correctional Facility', 'type': 'facility', 'properties': {'address': '211 Eslinger Way, Sanford', 'agreement': 'USMS IGA'}},
    {'id': 'fac_pinellas', 'name': 'Pinellas County Jail', 'type': 'facility', 'properties': {'agreement': 'IGSA', 'dual_role': 'detention + OFTP tactical hub'}},
    {'id': 'fac_polk', 'name': 'Polk County Jail', 'type': 'facility', 'properties': {'agreement': 'BOA+MOA+MOU', 'worst_subsidy': True}},
    {'id': 'fac_broward', 'name': 'Broward Transitional Center', 'type': 'facility', 'properties': {'operator': 'GEO Group', 'type': 'CDF'}},
    {'id': 'fac_krome', 'name': 'Krome Service Processing Center', 'type': 'facility', 'properties': {'operator': 'Akima Global Services', 'location': 'Miami-Dade', 'supply_chain_size': 9}},
    {'id': 'fac_orlando_ipc', 'name': 'Orlando ICE Processing Center (Planned)', 'type': 'facility', 'properties': {'address': '8660 Transport Drive, Orlando', 'status': 'Planned/Under Development', 'transparency': 'OPAQUE'}},
]
entities.extend(facility_entities)

# Build relationships
rels = [
    # County → Facility
    {'source': 'county_orange', 'target': 'fac_orange', 'type': 'operates', 'properties': {'rate': '$88/day', 'since': 1997}},
    {'source': 'county_hillsborough', 'target': 'fac_hillsborough', 'type': 'operates', 'properties': {'rate': '$88/day', 'since': 1983}},
    {'source': 'county_osceola', 'target': 'fac_osceola', 'type': 'operates', 'properties': {'rate': '$56.71/day', 'since': 2004}},
    {'source': 'county_seminole', 'target': 'fac_seminole', 'type': 'operates', 'properties': {'rate': '$56.71/day', 'since': 2004}},
    {'source': 'county_pinellas', 'target': 'fac_pinellas', 'type': 'operates', 'properties': {'rate': '$85/day'}},
    {'source': 'county_polk', 'target': 'fac_polk', 'type': 'operates', 'properties': {'rate': '$25/day', 'since': 2007}},
    
    # Federal → County/Facility
    {'source': 'ice_ero', 'target': 'county_orange', 'type': 'IGSA', 'properties': {'crisis': True, 'deadline': '2026-03-13'}},
    {'source': 'ice_ero', 'target': 'county_hillsborough', 'type': 'IGSA', 'properties': {'rate_history': '$40→$50→$55→$70→$80→$88'}},
    {'source': 'ice_ero', 'target': 'county_osceola', 'type': 'IGSA', 'properties': {'stagnant_22_years': True}},
    {'source': 'usms', 'target': 'county_seminole', 'type': 'USMS_IGA', 'properties': {'iga_number': '18-04-0023/0024'}},
    {'source': 'ice_ero', 'target': 'county_pinellas', 'type': 'IGSA', 'properties': {}},
    {'source': 'ice_ero', 'target': 'county_polk', 'type': 'BOA', 'properties': {'standard_rate': '$25/day', 'also': 'MOA + MOU'}},
    {'source': 'ice_ero', 'target': 'county_broward', 'type': 'CDF', 'properties': {'operator': 'GEO Group'}},
    {'source': 'ice_ero', 'target': 'county_sarasota', 'type': 'BOA', 'properties': {'number': '70CDCR18G00000015'}},
    {'source': 'ice_ero', 'target': 'county_walton', 'type': 'BOA', 'properties': {'number': '70CDCR18G00000016'}},
    
    # Vendor → Facility
    {'source': 'geo_group', 'target': 'fac_broward', 'type': 'operates_private', 'properties': {'contract': '70CDCR24FR0000053', 'value': '$96.5M'}},
    {'source': 'akima', 'target': 'fac_krome', 'type': 'operates_private', 'properties': {'contract': '70CDCR21FR0000025', 'value': '$50M'}},
    {'source': 'optivor', 'target': 'fac_krome', 'type': 'telecom_provider', 'properties': {'contracts': 3}},
    {'source': 'leidos', 'target': 'fac_krome', 'type': 'security_equipment', 'properties': {'service': 'X-ray maintenance'}},
    {'source': 'eola_power', 'target': 'fac_krome', 'type': 'power_maintenance', 'properties': {'service': 'UPS systems'}},
    {'source': 'action_target', 'target': 'fac_krome', 'type': 'range_maintenance', 'properties': {'service': 'Firing range'}},
    
    # ICE divisions → Facility/County
    {'source': 'ice_oftp', 'target': 'county_pinellas', 'type': 'tactical_hub', 'properties': {'contracts': 22, 'value': '$5.2M'}},
    
    # DOGE impact
    {'source': 'doge', 'target': 'ice_ero', 'type': 'contract_cancellations', 'properties': {'year': 2025, 'impact': 'Active review of ICE detention contracts'}},
    
    # Corporate relationship
    {'source': 'g4s_allied', 'target': 'geo_group', 'type': 'competitor', 'properties': {'note': 'Both serve ICE detention; G4S = transport, GEO = facility operations'}},
]
relationships = rels

###############################################################################
# RECURSION 5.6: ACCELERATION ANALYSIS (FY2023-FY2025)
###############################################################################
print("\n" + "=" * 60)
print("5.6: CONTRACT ACCELERATION FORENSICS (FY2023-2025)")
print("=" * 60)

fy_data = defaultdict(lambda: {'count': 0, 'value': 0, 'vendors': set(), 'categories': Counter()})

for contract in bln_ice:
    cn = contract.get('contract_id', '')
    value = contract.get('total_obligated', 0)
    vendor = contract.get('vendor', '')
    try:
        value = float(str(value).replace('$', '').replace(',', ''))
    except:
        value = 0
    
    # Extract FY from contract number
    year_match = re.search(r'70\w{3}(\d{2})', cn)
    if year_match:
        fy = '20' + year_match.group(1)
        fy_data[fy]['count'] += 1
        fy_data[fy]['value'] += value
        fy_data[fy]['vendors'].add(vendor)
        
        # Category from prefix
        if 'CDCR' in cn[:7]:
            fy_data[fy]['categories']['Detention'] += 1
        elif 'CMSW' in cn[:7]:
            fy_data[fy]['categories']['Tactical'] += 1
        elif 'CMSD' in cn[:7]:
            fy_data[fy]['categories']['Investigations'] += 1
        elif 'CTD0' in cn[:7]:
            fy_data[fy]['categories']['IT'] += 1

print(f"\nFiscal Year Contract Analysis:")
for fy in sorted(fy_data.keys()):
    data = fy_data[fy]
    print(f"\n  FY{fy}:")
    print(f"    Contracts: {data['count']}")
    print(f"    Value: ${data['value']:,.2f}")
    print(f"    Unique vendors: {len(data['vendors'])}")
    print(f"    Categories: {dict(data['categories'])}")

# Acceleration metrics
if 'FY2023' in [f'FY{y}' for y in fy_data.keys()] or '2023' in fy_data:
    pre = fy_data.get('2022', fy_data.get('2021', {'value': 0}))
    fy23 = fy_data.get('2023', {'value': 0})
    fy24 = fy_data.get('2024', {'value': 0})
    fy25 = fy_data.get('2025', {'value': 0})
    
    print(f"\n  ACCELERATION METRICS:")
    if pre['value'] > 0:
        print(f"    FY2023 vs prior: {(fy23['value']/pre['value'] - 1)*100:.1f}% change")
    if fy23['value'] > 0:
        print(f"    FY2024 vs FY2023: {(fy24['value']/fy23['value'] - 1)*100:.1f}% change")
    if fy24['value'] > 0 and fy25['value'] > 0:
        print(f"    FY2025 vs FY2024: {(fy25['value']/fy24['value'] - 1)*100:.1f}% change")

###############################################################################
# RECURSION 5.7: EVIDENCE CHAIN STRENGTH SCORING
###############################################################################
print("\n" + "=" * 60)
print("5.7: EVIDENCE CHAIN STRENGTH SCORING")
print("=" * 60)

evidence_audit = p4['evidence_audit']

# Score each evidence chain
chain_scores = {}
for county, audit in evidence_audit.items():
    confirmed = sum(1 for v in audit.values() if isinstance(v, str) and v.startswith('✅'))
    pending = sum(1 for v in audit.values() if isinstance(v, str) and v.startswith('⚠️'))
    missing = sum(1 for v in audit.values() if isinstance(v, str) and v.startswith('❌'))
    total = confirmed + pending + missing
    
    score = (confirmed * 1.0 + pending * 0.5) / total if total > 0 else 0
    chain_scores[county] = {
        'confirmed': confirmed,
        'pending': pending,
        'missing': missing,
        'total': total,
        'score': score,
        'grade': 'A' if score >= 0.8 else 'B' if score >= 0.6 else 'C' if score >= 0.4 else 'D'
    }
    
    print(f"\n  {county}:")
    print(f"    ✅ Confirmed: {confirmed}")
    print(f"    ⚠️  Pending: {pending}")
    print(f"    ❌ Missing: {missing}")
    print(f"    Score: {score:.2f} (Grade: {chain_scores[county]['grade']})")

###############################################################################
# RECURSION 5.8: STORY THREAD SCORING
###############################################################################
print("\n" + "=" * 60)
print("5.8: STORY THREAD SCORING (JOURNALISTIC VALUE)")
print("=" * 60)

story_threads = [
    {
        'thread': 'County Subsidy Crisis',
        'description': 'I-4 corridor counties subsidize $18.9M/year for ICE detention; Orange County facing March 13 IGSA deadline',
        'evidence_strength': 'HIGH',
        'public_interest': 'VERY HIGH',
        'novelty': 'HIGH',
        'actionability': 'IMMEDIATE',
        'data_points': [
            'Orange County IGSA crisis + Demings ultimatum letters',
            'Osceola/Seminole 22-year rate stagnation ($56.71 unchanged since 2004)',
            'Polk County $25/day BOA vs $140/day actual cost',
            'Financial model: 53.3% of costs borne by counties'
        ],
        'score': 95
    },
    {
        'thread': 'Invisible Contract Acceleration',
        'description': 'FY2024 ICE FL contracts doubled to $384M; 72 new contracts in FY2023-25 vs 115 total all prior years',
        'evidence_strength': 'HIGH',
        'public_interest': 'HIGH',
        'novelty': 'VERY HIGH',
        'actionability': 'HIGH',
        'data_points': [
            'FPDS analysis: FY2024 = $384M (double FY2023)',
            'Contract acceleration began FY2023, accelerated under Trump admin',
            '48 unique vendors activated for FL ICE work',
            'GEO Group: $713M total, largest single contractor'
        ],
        'score': 88
    },
    {
        'thread': 'BOA Stealth Network',
        'description': '29 FL counties signed BOAs at $25/day in FY2018 batch; creates massive latent detention capacity',
        'evidence_strength': 'MEDIUM-HIGH',
        'public_interest': 'VERY HIGH',
        'novelty': 'VERY HIGH',
        'actionability': 'HIGH',
        'data_points': [
            '29 counties in BOA pool (PSL-Resources)',
            'Only 2 of 29 BOA numbers mapped (Sarasota #15, Walton #16)',
            'BOA = standardized $25/day, no volume commitment',
            'Many BOA counties ALSO have higher-rate IGSA/IGA',
            'Dual-agreement structure creates flexible detention surge capacity'
        ],
        'score': 92
    },
    {
        'thread': 'Phantom County / Vendor HQ Artifact',
        'description': 'GEO Group Palm Beach $56M is Colorado facility; FL vendor state inflates state contract totals',
        'evidence_strength': 'HIGH',
        'public_interest': 'MEDIUM',
        'novelty': 'HIGH',
        'actionability': 'MEDIUM',
        'data_points': [
            'Palm Beach $56M = Denver/Aurora facility (GEO HQ artifact)',
            '17 of 57 FL contracts have vendor HQ = performance location',
            'Methodological finding for all FPDS FL analyses'
        ],
        'score': 72
    },
    {
        'thread': 'Pinellas Dual-Role Hub',
        'description': 'Pinellas County = both detention facility and OFTP tactical equipment hub (22 weapons/tactical contracts)',
        'evidence_strength': 'HIGH',
        'public_interest': 'HIGH',
        'novelty': 'HIGH',
        'actionability': 'MEDIUM',
        'data_points': [
            '22 OFTP contracts, $5.2M in Pinellas County',
            'Unique dual role: detention + tactical',
            'Weapons/ammunition purchases accelerated in FY2025'
        ],
        'score': 78
    },
    {
        'thread': 'G4S → Allied Universal Invisibility',
        'description': 'G4S acquired by Allied Universal in 2021 but 0 Allied contracts in FPDS; $157M in transport contracts under legacy name',
        'evidence_strength': 'HIGH',
        'public_interest': 'MEDIUM',
        'novelty': 'MEDIUM',
        'actionability': 'LOW',
        'data_points': [
            '20 G4S contracts still in FPDS through FY2024',
            '0 Allied Universal contracts found',
            'Transport service continuity unclear post-acquisition'
        ],
        'score': 62
    },
    {
        'thread': 'Krome SPC Supply Chain Mapping',
        'description': 'Complete supply chain for Krome SPC mapped: 9 contracts, $50.2M, 6 vendors',
        'evidence_strength': 'VERY HIGH',
        'public_interest': 'MEDIUM',
        'novelty': 'HIGH',
        'actionability': 'MEDIUM',
        'data_points': [
            'Akima Global Services: $50M operations contract',
            'Optivor: 3 telecom contracts',
            'Leidos: X-ray maintenance',
            'EOLA Power: UPS maintenance',
            'Action Target: Range maintenance'
        ],
        'score': 70
    },
    {
        'thread': 'Orlando Processing Center Opacity',
        'description': '8660 Transport Dr planned ICE Processing Center; ownership, permitting, and contract chain still opaque',
        'evidence_strength': 'LOW',
        'public_interest': 'VERY HIGH',
        'novelty': 'HIGH',
        'actionability': 'VERY HIGH',
        'data_points': [
            'Address identified from PRR-158704 correspondence',
            'Property ownership chain: requires Property Appraiser lookup',
            'Building permits: requires county records access',
            'FPDS: no contracts mentioning this address found'
        ],
        'score': 85
    }
]

# Sort by score
story_threads.sort(key=lambda x: x['score'], reverse=True)
print(f"\nStory threads ranked by composite score:")
for i, thread in enumerate(story_threads, 1):
    print(f"\n  #{i}: {thread['thread']} (Score: {thread['score']}/100)")
    print(f"      Evidence: {thread['evidence_strength']}, Public Interest: {thread['public_interest']}")
    print(f"      Novelty: {thread['novelty']}, Actionability: {thread['actionability']}")
    print(f"      Data points: {len(thread['data_points'])}")

###############################################################################
# RECURSION 5.9: RECURSIVE CROSS-REFERENCE MATRIX
###############################################################################
print("\n" + "=" * 60)
print("5.9: RECURSIVE CROSS-REFERENCE MATRIX")
print("=" * 60)

# Which datasets have been cross-referenced against which?
datasets = [
    'FPDS/BLN (197 ICE FL)',
    'FPDS/BLN (506 DHS FL)',
    'FPDS/BLN (7934 DHS FL broad)',
    'IGA Transcriptions (5)',
    'MuckRock FOIAs (14 PDFs)',
    'PSL-Resources (7 docs)',
    'ICE Detention Stats (FY20-26)',
    'TRAC 287(g)',
    'TRAC Detainer Time Series',
    'PRR-158704 (pending)',
    'Sheriff PRRs (4 pending)',
    'Property Records (not accessed)',
    'Sunbiz Corporate (not accessed)',
    'ICE FOIA Reading Room (not accessed)'
]

# Cross-reference completeness matrix
cross_ref = {
    'FPDS↔IGA': {'status': '✅ Complete', 'findings': 'Rate vs contract value comparison; vendor identification'},
    'FPDS↔MuckRock': {'status': '✅ Complete', 'findings': 'BOA numbers confirmed; Polk agreement layers verified'},
    'FPDS↔PSL': {'status': '✅ Complete', 'findings': '29-county BOA pool mapped; IGSA crisis confirmed'},
    'FPDS↔ICE Stats': {'status': '✅ Complete', 'findings': 'Population trends vs contract values; facility activation timing'},
    'FPDS↔TRAC': {'status': '✅ Complete', 'findings': '287(g) facilities vs FPDS presence; Seminole anomaly identified'},
    'IGA↔MuckRock': {'status': '✅ Complete', 'findings': 'Rate confirmation across sources; Polk layering identified'},
    'IGA↔PSL': {'status': '✅ Complete', 'findings': 'Rate stagnation analysis; rebooking practice documentation'},
    'IGA↔ICE Stats': {'status': '✅ Complete', 'findings': 'Population data vs agreement terms; bed utilization modeling'},
    'MuckRock↔PSL': {'status': '✅ Complete', 'findings': 'BOA pool verification; 287(g) cross-reference'},
    'FPDS↔Property': {'status': '❌ Not accessed', 'findings': 'Web services unavailable'},
    'FPDS↔Sunbiz': {'status': '❌ Not accessed', 'findings': 'Web services unavailable'},
    'FPDS↔FOIA Room': {'status': '❌ Not accessed', 'findings': 'Web services unavailable'},
    'PRR↔All': {'status': '⏳ Pending', 'findings': 'PRR responses will unlock new cross-references'},
}

print(f"\nCross-reference matrix ({len(cross_ref)} pairings):")
complete = sum(1 for v in cross_ref.values() if v['status'].startswith('✅'))
pending = sum(1 for v in cross_ref.values() if v['status'].startswith('⏳'))
blocked = sum(1 for v in cross_ref.values() if v['status'].startswith('❌'))
print(f"  ✅ Complete: {complete}")
print(f"  ⏳ Pending: {pending}")
print(f"  ❌ Blocked: {blocked}")
print(f"  Coverage: {complete}/{len(cross_ref)} ({complete/len(cross_ref)*100:.0f}%)")

for pair, data in cross_ref.items():
    print(f"\n  {pair}: {data['status']}")
    print(f"    Findings: {data['findings']}")

###############################################################################
# RECURSION 5.10: META-RECURSION — What Each Finding Tells Us To Look For Next
###############################################################################
print("\n" + "=" * 60)
print("5.10: META-RECURSION — FINDING→NEXT QUERY CHAINS")
print("=" * 60)

recursion_chains = [
    {
        'finding': 'Orange County $88/day rate, $180 actual cost → $92/day subsidy × 130 beds × 365 days = $4.37M/year county loss',
        'next_queries': [
            'VERIFY: Orange County budget line item for jail operations (PRR needed)',
            'VERIFY: How does Orange compare to other large FL counties (Miami-Dade, Duval)?',
            'QUERY: Has Orange County ever attempted IGSA rate renegotiation? (PRR-158704)',
            'QUERY: What happens after March 13, 2026 deadline? Does ICE relocate detainees?',
        ],
        'depth': 3,
        'resolved': ['Rate confirmed', 'Cost estimate from PSL-Resources', 'Deadline confirmed']
    },
    {
        'finding': '22-year rate stagnation at Osceola/Seminole ($56.71 since 2004)',
        'next_queries': [
            'QUERY: CPI adjustment 2004-2026: rate should be ~$85.63 in 2026 dollars',
            'QUERY: Has either county attempted rate renegotiation? (no PRR filed yet)',
            'QUERY: Are detainee volumes increasing despite stagnant rate?',
            'QUERY: Is $56.71 the USMS standard rate, or was it negotiated?',
        ],
        'depth': 2,
        'resolved': ['Rate confirmed from IGA transcription', 'USMS IGA structure identified']
    },
    {
        'finding': '29-county BOA pool at $25/day creates latent detention surge capacity',
        'next_queries': [
            'QUERY: Which of the 29 BOAs are actively being used? (requires ICE data)',
            'QUERY: Can BOA counties be activated without public notice?',
            'QUERY: Were any BOA counties activated during recent enforcement surges?',
            'QUERY: Total potential bed count across all 29 BOA counties?',
        ],
        'depth': 2,
        'resolved': ['Pool identified from PSL-Resources', 'Two numbers confirmed from MuckRock']
    },
    {
        'finding': 'FY2024 contract acceleration to $384M (double FY2023)',
        'next_queries': [
            'QUERY: Is this a national pattern or Florida-specific?',
            'QUERY: Which vendors received the largest new contracts?',
            'QUERY: Does acceleration correlate with Trump admin policy changes?',
            'QUERY: Are DOGE cancellations targeting any of these new contracts?',
        ],
        'depth': 2,
        'resolved': ['FL-specific data confirmed', 'Vendor distribution mapped']
    },
    {
        'finding': 'Pinellas = dual detention + OFTP tactical hub',
        'next_queries': [
            'QUERY: Why Pinellas specifically for OFTP? Geographic proximity to what?',
            'QUERY: What tactical equipment was purchased in FY2025 surge?',
            'QUERY: Is OFTP activity related to enforcement operation staging?',
            'QUERY: Are there other dual-role facilities nationally?',
        ],
        'depth': 1,
        'resolved': ['22 contracts confirmed', '$5.2M value confirmed']
    },
    {
        'finding': 'Orlando ICE Processing Center at 8660 Transport Dr',
        'next_queries': [
            'QUERY: Property appraiser records → owner → developer',
            'QUERY: Building permits → scope of construction → capacity',
            'QUERY: Zoning board records → when was detention use approved?',
            'QUERY: Any FPDS contracts referencing this address?',
            'QUERY: How does this relate to the existing Orange County IGSA?',
        ],
        'depth': 1,
        'resolved': ['Address identified', 'No FPDS match found']
    },
]

for chain in recursion_chains:
    resolved = len(chain['resolved'])
    total = len(chain['next_queries']) + resolved
    print(f"\n  Finding: {chain['finding'][:80]}...")
    print(f"  Recursion depth: {chain['depth']}")
    print(f"  Resolved: {resolved}/{total}")
    print(f"  Open queries:")
    for q in chain['next_queries']:
        print(f"    → {q}")

###############################################################################
# SAVE ALL PHASE 5 RESULTS
###############################################################################

phase5_results = {
    'metadata': {
        'analysis_date': datetime.now().isoformat(),
        'description': 'Phase 5: Master Recursion - Terminal Depth',
        'datasets_cross_referenced': len(datasets),
        'cross_ref_complete': complete,
        'cross_ref_total': len(cross_ref),
    },
    'boa_reconstruction': {
        'confirmed': {'15': 'Sarasota', '16': 'Walton'},
        'hypothesis': 'Non-alphabetical; possibly signing/batch order',
        'pool_size': 29,
        'mapped': 2,
        'unmapped': 27,
    },
    'evidence_chain_scores': chain_scores,
    'story_threads': story_threads,
    'cross_reference_matrix': cross_ref,
    'recursion_chains': recursion_chains,
    'entity_graph': {
        'entities': len(entities),
        'relationships': len(relationships),
    }
}

with open('recursive_phase5_results.json', 'w') as f:
    json.dump(phase5_results, f, indent=2, default=str)

# Save expanded entity map
expanded_entity_map = {
    'metadata': {
        'generated': datetime.now().isoformat(),
        'description': 'Complete I-4 Corridor ICE Entity Relationship Map (Phase 5)',
        'entity_count': len(entities),
        'relationship_count': len(relationships),
    },
    'entities': entities,
    'relationships': relationships,
}

with open('ice_entity_map_v2.json', 'w') as f:
    json.dump(expanded_entity_map, f, indent=2, default=str)

print(f"\n\n{'=' * 60}")
print(f"PHASE 5 COMPLETE")
print(f"{'=' * 60}")
print(f"Entities mapped: {len(entities)}")
print(f"Relationships mapped: {len(relationships)}")
print(f"Cross-references complete: {complete}/{len(cross_ref)}")
print(f"Story threads scored: {len(story_threads)}")
print(f"Recursion chains documented: {len(recursion_chains)}")
print(f"Results saved to: recursive_phase5_results.json")
print(f"Entity map saved to: ice_entity_map_v2.json")
