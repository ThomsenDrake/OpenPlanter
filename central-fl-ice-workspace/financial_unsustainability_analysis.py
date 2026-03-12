#!/usr/bin/env python3
"""
Financial Unsustainability Analysis - I-4 Corridor ICE Detentions
Analysis Date: February 27, 2026
"""

import json

# Load the data
with open('iga_rate_comparison.json', 'r') as f:
    iga_data = json.load(f)

# Current populations from TRAC data (Feb 2026)
populations = {
    'Hillsborough County Jail': 132,
    'Orange County Jail': 100,  # Estimated from TRAC
    'Pinellas County Jail': 4,
    'Orlando ICE Processing Center': 167,
    'Osceola County': 0,  # Not in current stats but has 287(g)
    'Seminole County (John E. Polk)': 0  # Not in current stats
}

# Per-diem rates from IGA data
rates = {
    'Hillsborough County': 101.06,
    'Orange County': 88.00,
    'Pinellas County': 80.00,
    'Osceola County': 40.00,
    'Seminole County (John E. Polk)': 56.71
}

# Estimated actual costs (based on Orange County data)
estimated_costs = {
    'Hillsborough County': 180,  # Similar to Orange
    'Orange County': 180,  # Confirmed
    'Pinellas County': 160,  # Slightly lower estimate
    'Osceola County': 180,  # Similar to Orange
    'Seminole County (John E. Polk)': 160  # Slightly lower estimate
}

# Calculate current losses
current_losses = {}
for facility, pop in populations.items():
    if pop > 0:
        county = facility.replace(' Jail', '').replace(' County', ' County')
        if 'John E. Polk' in facility:
            county = 'Seminole County (John E. Polk)'
        
        rate = rates.get(county, 0)
        cost = estimated_costs.get(county, 0)
        
        if rate and cost:
            daily_loss = (cost - rate) * pop
            annual_loss = daily_loss * 365
            current_losses[facility] = {
                'population': pop,
                'rate': rate,
                'estimated_cost': cost,
                'loss_per_detainee': cost - rate,
                'daily_loss': daily_loss,
                'annual_loss': annual_loss
            }

# Historical losses
historical_losses = {
    'Osceola County': {
        'rate': 40.00,
        'estimated_cost': 180,
        'years_stagnant': 40,
        'avg_population_estimate': 20,
        'annual_loss': (180 - 40) * 20 * 365
    },
    'Seminole County': {
        'rate': 56.71,
        'estimated_cost': 160,
        'years_stagnant': 22,
        'avg_population_estimate': 15,
        'annual_loss': (160 - 56.71) * 15 * 365
    }
}

# Output results
print("=" * 80)
print("FINANCIAL UNSUSTAINABILITY ANALYSIS - I-4 CORRIDOR ICE DETENTIONS")
print("=" * 80)
print()

print("CURRENT ACTIVE DETENTION LOSSES (February 2026)")
print("-" * 80)
for facility, data in current_losses.items():
    print(f"\n{facility}:")
    print(f"  Current Population: {data['population']} detainees")
    print(f"  Per-Diem Rate: ${data['rate']:.2f}/day")
    print(f"  Estimated Cost: ${data['estimated_cost']:.2f}/day")
    print(f"  Loss Per Detainee: ${data['loss_per_detainee']:.2f}/day")
    print(f"  Daily Loss: ${data['daily_loss']:,.2f}")
    print(f"  ANNUAL LOSS: ${data['annual_loss']:,.2f}")

print("\n" + "=" * 80)
print("TOTAL CURRENT ANNUAL LOSSES (Active Facilities)")
print("=" * 80)
total_annual = sum(d['annual_loss'] for d in current_losses.values())
print(f"${total_annual:,.2f}")
print()

print("=" * 80)
print("HISTORICAL CUMULATIVE LOSSES")
print("=" * 80)

print("\nOsceola County - 40-Year Rate Stagnation:")
osc_data = historical_losses['Osceola County']
print(f"  Rate: ${osc_data['rate']:.2f}/day since 1986 (40 years)")
print(f"  Estimated Cost: ${osc_data['estimated_cost']}/day")
print(f"  Loss Per Day: ${osc_data['estimated_cost'] - osc_data['rate']:.2f}")
print(f"  Estimated Average Population: {osc_data['avg_population_estimate']} detainees/year")
print(f"  ESTIMATED 40-YEAR SUBSIDY: ${osc_data['annual_loss'] * 40:,.2f}")

print("\nSeminole County - 22-Year Rate Stagnation:")
sem_data = historical_losses['Seminole County']
print(f"  Rate: ${sem_data['rate']:.2f}/day since 2004 (22 years)")
print(f"  Estimated Cost: ${sem_data['estimated_cost']}/day")
print(f"  Loss Per Day: ${sem_data['estimated_cost'] - sem_data['rate']:.2f}")
print(f"  Estimated Average Population: {sem_data['avg_population_estimate']} detainees/year")
print(f"  ESTIMATED 22-YEAR SUBSIDY: ${sem_data['annual_loss'] * 22:,.2f}")

print("\n" + "=" * 80)
print("TRUMP ADMINISTRATION IMPACT (Jan 2025 - Feb 2026)")
print("=" * 80)
print()
print("Florida Population Growth:")
print("  March 2024: 1,385 detainees")
print("  February 2026: 5,231 detainees")
print("  INCREASE: +278% (+3,846 detainees)")
print()
print("I-4 Corridor Current Population: 303 detainees")
print()
print("Federal Funding:")
print("  ICE Budget (through 2029): $75 billion")
print("  This represents +837% increase from ~$8B annually")
print()
print("Rate Adjustments: NONE")
print("  Despite 278% population increase, per-diem rates unchanged")
print("  Counties absorbing massive cost increases")
print()

print("=" * 80)
print("CRITICAL FINDINGS")
print("=" * 80)
print()
print("1. IMMEDIATE CRISIS - Orange County:")
print("   - Deadline: March 13, 2026 (2 weeks)")
print("   - Annual Loss: $3,358,000")
print("   - Mayor Demings demanding rate increase")
print("   - May cancel agreement if unresolved")
print()
print("2. CHRONIC UNDERFUNDING:")
print(f"   - Osceola: 40 years at ${osc_data['rate']}/day")
print(f"   - Seminole: 22 years at ${sem_data['rate']}/day")
print("   - Rate variance: 152.7% across corridor")
print()
print("3. STRUCTURAL WEAK POINT:")
print("   - System depends on county subsidies")
print("   - No mechanism for automatic rate adjustments")
print("   - Population growth +278% with $0 rate increase")
print()
