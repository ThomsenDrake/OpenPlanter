#!/usr/bin/env python3
"""
Analyze historical rate progression trends in IGA agreements
"""

import json
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

# Load data
with open('iga_rate_comparison.json', 'r') as f:
    data = json.load(f)

# Extract Hillsborough rate progression (only county with multiple modifications)
hillsborough = data['counties']['Hillsborough County']
dates = []
per_diem_rates = []
guard_rates = []

for entry in hillsborough['rate_history']:
    dates.append(datetime.strptime(entry['date'], '%Y-%m-%d'))
    per_diem_rates.append(entry['per_diem_rate'])
    guard_rates.append(entry['guard_rate'])

# Calculate inflation-adjusted rates (using approximate CPI data)
# Base year 1983 CPI = ~100, 2005 CPI = ~195 (approximate)
cpi_adjustments = {
    1983: 1.0,
    1985: 1.08,
    1987: 1.14,
    1991: 1.36,
    1994: 1.48,
    1995: 1.52,
    1996: 1.57,
    1997: 1.60,
    2005: 1.95
}

inflation_adjusted = []
for i, date in enumerate(dates):
    year = date.year
    cpi_factor = cpi_adjustments.get(year, 1.5)  # Default factor if not in dict
    adjusted_rate = per_diem_rates[i] / cpi_factor
    inflation_adjusted.append(adjusted_rate)

# Create visualization
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))

# Plot 1: Nominal Per-Diem Rates Over Time
ax1.plot(dates, per_diem_rates, 'b-o', linewidth=2, markersize=8)
ax1.set_xlabel('Year', fontsize=12)
ax1.set_ylabel('Per-Diem Rate ($)', fontsize=12)
ax1.set_title('Hillsborough County: Nominal Per-Diem Rate Progression (1983-2005)', fontsize=14, fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.set_ylim(0, 120)

# Annotate key points
for i, (date, rate) in enumerate(zip(dates, per_diem_rates)):
    if i % 2 == 0 or rate in [101.06, 83.46, 81.33]:  # Key rates
        ax1.annotate(f'${rate:.2f}', (date, rate), textcoords="offset points", 
                     xytext=(0,10), ha='center', fontsize=9)

# Plot 2: Inflation-Adjusted Per-Diem Rates
ax2.plot(dates, inflation_adjusted, 'r-s', linewidth=2, markersize=8)
ax2.set_xlabel('Year', fontsize=12)
ax2.set_ylabel('Inflation-Adjusted Rate (1983 $)', fontsize=12)
ax2.set_title('Hillsborough County: Inflation-Adjusted Per-Diem Rates', fontsize=14, fontweight='bold')
ax2.grid(True, alpha=0.3)
ax2.set_ylim(0, 60)

# Plot 3: Guard Rate Progression
ax3.plot(dates, guard_rates, 'g-^', linewidth=2, markersize=8)
ax3.set_xlabel('Year', fontsize=12)
ax3.set_ylabel('Guard Hourly Rate ($)', fontsize=12)
ax3.set_title('Hillsborough County: Guard/Transportation Rate Progression', fontsize=14, fontweight='bold')
ax3.grid(True, alpha=0.3)
ax3.set_ylim(0, 35)

plt.tight_layout()
plt.savefig('iga_rate_trends_hillsborough.png', dpi=150, bbox_inches='tight')
print("Saved: iga_rate_trends_hillsborough.png")

# Calculate key statistics
print("\n" + "="*80)
print("HILLSBOROUGH COUNTY RATE TREND ANALYSIS")
print("="*80)

print("\nPer-Diem Rate Changes:")
for i in range(1, len(dates)):
    change = per_diem_rates[i] - per_diem_rates[i-1]
    pct_change = (change / per_diem_rates[i-1]) * 100
    print(f"  {dates[i-1].strftime('%Y')} → {dates[i].strftime('%Y')}: "
          f"${per_diem_rates[i-1]:.2f} → ${per_diem_rates[i]:.2f} "
          f"({pct_change:+.1f}%, ${change:+.2f})")

print(f"\n22-Year Total Change: ${per_diem_rates[0]:.2f} → ${per_diem_rates[-1]:.2f} "
      f"({((per_diem_rates[-1]/per_diem_rates[0])-1)*100:.1f}% increase)")

print(f"\nInflation-Adjusted Analysis:")
print(f"  1983 Rate (1983 $): ${inflation_adjusted[0]:.2f}")
print(f"  2005 Rate (1983 $): ${inflation_adjusted[-1]:.2f}")
print(f"  Real Increase: ${inflation_adjusted[-1] - inflation_adjusted[0]:.2f} "
      f"({((inflation_adjusted[-1]/inflation_adjusted[0])-1)*100:.1f}%)")

# Compare to other counties
print("\n" + "="*80)
print("CURRENT RATE COMPARISON (ALL COUNTIES)")
print("="*80)

current_rates = []
for county, info in data['counties'].items():
    rate = info['current_rate']['per_diem']
    as_of = info['current_rate']['as_of']
    current_rates.append((county, rate, as_of))
    print(f"{county:30} ${rate:>7.2f}  (as of {as_of})")

# Calculate if Osceola's 1986 rate was inflation-adjusted to 2026
cpi_1986 = 1.10
cpi_2026_estimate = 2.85  # Approximate
osceola_adjusted = 40.00 / cpi_1986 * cpi_2026_estimate

print("\n" + "="*80)
print("OSCEOLA COUNTY RATE ANOMALY")
print("="*80)
print(f"1986 Rate: $40.00/day")
print(f"If adjusted for inflation to 2026: ~${osceola_adjusted:.2f}/day")
print(f"Current disparity from inflation-adjusted value: ${osceola_adjusted - 40.00:.2f}/day")
print(f"\nThis suggests Osceola County is effectively subsidizing federal detention")
print(f"by ~${osceola_adjusted - 40.00:.2f} per detainee per day.")

# Create comparative visualization
fig, ax = plt.subplots(figsize=(12, 6))

counties = [r[0] for r in current_rates]
rates = [r[1] for r in current_rates]
colors = ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd']

bars = ax.bar(range(len(counties)), rates, color=colors, alpha=0.7, edgecolor='black', linewidth=2)

# Add value labels on bars
for i, (bar, rate) in enumerate(zip(bars, rates)):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height,
            f'${rate:.2f}',
            ha='center', va='bottom', fontsize=11, fontweight='bold')

ax.set_xlabel('County/Facility', fontsize=12)
ax.set_ylabel('Per-Diem Rate ($)', fontsize=12)
ax.set_title('I-4 Corridor: Current Federal Detention Per-Diem Rates by County', fontsize=14, fontweight='bold')
ax.set_xticks(range(len(counties)))
ax.set_xticklabels(counties, rotation=15, ha='right', fontsize=10)
ax.set_ylim(0, 120)
ax.grid(axis='y', alpha=0.3)

# Add average line
avg_rate = sum(rates) / len(rates)
ax.axhline(y=avg_rate, color='red', linestyle='--', linewidth=2, label=f'Average: ${avg_rate:.2f}')
ax.legend(fontsize=11)

plt.tight_layout()
plt.savefig('iga_rate_comparison_all_counties.png', dpi=150, bbox_inches='tight')
print("\nSaved: iga_rate_comparison_all_counties.png")

print("\n" + "="*80)
print("ANALYSIS COMPLETE")
print("="*80)
