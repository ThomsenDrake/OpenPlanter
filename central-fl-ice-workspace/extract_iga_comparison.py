#!/usr/bin/env python3
"""
Extract and compare IGA rates and terms across counties in the I-4 corridor
"""

import json
import re
from datetime import datetime

# Extracted data from IGA transcriptions
iga_data = {
    "Hillsborough County": {
        "agreement_number": "J-B18-M-038",
        "facility_codes": ["4CC", "4CB", "4ML"],
        "base_effective_date": "1983-02-01",
        "facilities": [
            "Hillsborough County Jail",
            "Hillsborough County Stockade", 
            "Hillsborough County Camp"
        ],
        "rate_history": [
            {
                "date": "1983-02-01",
                "modification": "Base",
                "per_diem_rate": 33.50,
                "guard_rate": 10.00,
                "estimated_annual_payment": 469000.00,
                "notes": "Base agreement"
            },
            {
                "date": "1985-06-01",
                "modification": "Mod 1",
                "per_diem_rate": 40.00,
                "guard_rate": 10.00,
                "notes": "Incorporated Prompt Payment Act"
            },
            {
                "date": "1987-05-01",
                "modification": "Mod 2",
                "per_diem_rate": 45.00,
                "guard_rate": 10.00,
                "notes": "Rate increase"
            },
            {
                "date": "1991-09-01",
                "modification": "Mod 3",
                "per_diem_rate": 58.00,
                "guard_rate": 10.00,
                "notes": "Rate increase"
            },
            {
                "date": "1994-03-01",
                "modification": "Mod 4",
                "per_diem_rate": 62.23,
                "guard_rate": 10.00,
                "notes": "Added medical support language"
            },
            {
                "date": "1995-05-01",
                "modification": "Mod 5",
                "per_diem_rate": 83.46,
                "guard_rate": 10.00,
                "notes": "Rate increase, medical services parity"
            },
            {
                "date": "1996-09-01",
                "modification": "Mod 6",
                "per_diem_rate": 81.33,
                "guard_rate": 10.00,
                "notes": "Recouped overcharges, reduced rate"
            },
            {
                "date": "1997-01-01",
                "modification": "Mod 7",
                "per_diem_rate": 81.33,
                "guard_rate": 20.94,
                "notes": "Guard rate increase"
            },
            {
                "date": "2005-09-01",
                "modification": "Mod 15",
                "per_diem_rate": 101.06,
                "guard_rate": 20.94,
                "notes": "Final rate in document"
            }
        ],
        "current_rate": {
            "per_diem": 101.06,
            "guard": 20.94,
            "as_of": "2005-09-01"
        },
        "source": "IGA-Florida-Hillsborough-County_Manual-Visual-Transcription.md"
    },
    
    "John E. Polk (Seminole County)": {
        "agreement_number": "18-04-0024",
        "facility_codes": ["4YA"],
        "base_effective_date": "2004-01-01",
        "facilities": [
            "John E. Polk Correctional Facility, 211 Bush Boulevard, Sanford, FL 32773"
        ],
        "rate_history": [
            {
                "date": "2004-01-01",
                "modification": "Base",
                "per_diem_rate": 56.71,
                "guard_rate": 24.72,
                "estimated_prisoner_days": 36500,
                "estimated_annual_payment": 2069915.00,
                "notes": "Base agreement"
            }
        ],
        "current_rate": {
            "per_diem": 56.71,
            "guard": 24.72,
            "as_of": "2004-01-01"
        },
        "source": "IGA-Florida-John-E-Polk-Correctional-Facility_Manual-Visual-Transcription.md"
    },
    
    "Osceola County": {
        "agreement_number": "J-B18-M-529",
        "facility_codes": [],
        "base_effective_date": "1986-09-01",
        "facilities": [
            "Osceola County Jail"
        ],
        "rate_history": [
            {
                "date": "1986-09-01",
                "modification": "Base",
                "per_diem_rate": 40.00,
                "guard_rate": 12.00,
                "estimated_prisoner_days": 11680,
                "estimated_annual_payment": 467200.00,
                "notes": "Base agreement signed by Sheriff Randy Sheive"
            }
        ],
        "current_rate": {
            "per_diem": 40.00,
            "guard": 12.00,
            "as_of": "1986-09-01"
        },
        "source": "IGA-Florida-Osceola-County-Sheriffs-Department_Manual-Visual-Transcription.md"
    },
    
    "Pinellas County": {
        "agreement_number": "18-91-0041",
        "facility_codes": ["4RI"],
        "base_effective_date": "Unknown",
        "facilities": [
            "Pinellas County Sheriff's Office, 10750 Ulmerton Road, Largo, FL 33778"
        ],
        "rate_history": [
            {
                "date": "Unknown",
                "modification": "Base",
                "per_diem_rate": 80.00,
                "guard_rate": 27.57,
                "male_beds": 300,
                "female_beds": 100,
                "total_beds": 400,
                "notes": "Agreement includes PREA and Service Contract Act"
            }
        ],
        "current_rate": {
            "per_diem": 80.00,
            "guard": 27.57,
            "as_of": "Unknown"
        },
        "source": "IGA-Florida-Pinellas-County-Sheriffs-Office_Manual-Visual-Transcription.md"
    },
    
    "Orange County": {
        "agreement_number": "18-04-0023",
        "facility_codes": ["4CM"],
        "base_effective_date": "1983",
        "facilities": [
            "Orange County Correctional Facility, 3723 Vision Boulevard, Orlando, FL 32839"
        ],
        "rate_history": [
            {
                "date": "2011-03-15",
                "modification": "Mod 6",
                "per_diem_rate": 88.00,
                "guard_rate": 31.75,
                "male_beds": 94,
                "female_beds": 20,
                "total_beds": 114,
                "notes": "Current rate from USMS documents"
            }
        ],
        "current_rate": {
            "per_diem": 88.00,
            "guard": 31.75,
            "as_of": "2011-03-15"
        },
        "source": "USMS-Agreement-Documents-2022_OCR.md"
    }
}

# Analysis
print("="*80)
print("IGA RATE COMPARISON ACROSS I-4 CORRIDOR COUNTIES")
print("="*80)
print()

# Sort by per-diem rate
sorted_counties = sorted(
    iga_data.items(),
    key=lambda x: x[1]["current_rate"]["per_diem"],
    reverse=True
)

print("CURRENT PER-DIEM RATES (Highest to Lowest):")
print("-"*80)
for county, data in sorted_counties:
    rate = data["current_rate"]["per_diem"]
    as_of = data["current_rate"]["as_of"]
    agreement = data["agreement_number"]
    codes = ", ".join(data["facility_codes"]) if data["facility_codes"] else "Not specified"
    print(f"{county:30} ${rate:>7.2f}/day  (as of {as_of})")
    print(f"  Agreement: {agreement}")
    print(f"  Facility Codes: {codes}")
    print()

print("\n" + "="*80)
print("GUARD/TRANSPORTATION HOURLY RATES (Highest to Lowest):")
print("-"*80)
sorted_by_guard = sorted(
    iga_data.items(),
    key=lambda x: x[1]["current_rate"]["guard"],
    reverse=True
)

for county, data in sorted_by_guard:
    rate = data["current_rate"]["guard"]
    as_of = data["current_rate"]["as_of"]
    print(f"{county:30} ${rate:>6.2f}/hour  (as of {as_of})")

print("\n" + "="*80)
print("RATE DISPARITY ANALYSIS:")
print("-"*80)

per_diem_rates = [data["current_rate"]["per_diem"] for data in iga_data.values()]
max_per_diem = max(per_diem_rates)
min_per_diem = min(per_diem_rates)
avg_per_diem = sum(per_diem_rates) / len(per_diem_rates)

print(f"Per-Diem Rate Range:    ${min_per_diem:.2f} - ${max_per_diem:.2f}")
print(f"Average Per-Diem Rate:  ${avg_per_diem:.2f}")
print(f"Maximum Disparity:      ${max_per_diem - min_per_diem:.2f} ({((max_per_diem/min_per_diem - 1) * 100):.1f}% difference)")
print()

guard_rates = [data["current_rate"]["guard"] for data in iga_data.values()]
max_guard = max(guard_rates)
min_guard = min(guard_rates)
avg_guard = sum(guard_rates) / len(guard_rates)

print(f"Guard Rate Range:       ${min_guard:.2f} - ${max_guard:.2f}")
print(f"Average Guard Rate:     ${avg_guard:.2f}")
print(f"Maximum Disparity:      ${max_guard - min_guard:.2f} ({((max_guard/min_guard - 1) * 100):.1f}% difference)")

# Save to JSON
output = {
    "analysis_date": datetime.now().isoformat(),
    "counties": iga_data,
    "summary": {
        "per_diem_rates": {
            "max": max_per_diem,
            "min": min_per_diem,
            "average": avg_per_diem,
            "disparity_percentage": ((max_per_diem/min_per_diem - 1) * 100)
        },
        "guard_rates": {
            "max": max_guard,
            "min": min_guard,
            "average": avg_guard,
            "disparity_percentage": ((max_guard/min_guard - 1) * 100)
        },
        "ranking_per_diem": [
            {"county": county, "rate": data["current_rate"]["per_diem"]}
            for county, data in sorted_counties
        ]
    }
}

with open("iga_rate_comparison.json", "w") as f:
    json.dump(output, f, indent=2)

print("\n" + "="*80)
print("Data saved to: iga_rate_comparison.json")
print("="*80)
