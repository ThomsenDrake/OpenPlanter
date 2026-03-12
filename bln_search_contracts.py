#!/usr/bin/env python3
"""Search BLN federal contract cancellation data for ICE/DHS Florida contracts."""
import csv
import json
import sys

# Files to search
files = [
    "bln_downloads/fed_contracts/default.csv",
    "bln_downloads/fed_contracts/for_cause.csv",
    "bln_downloads/fed_contracts/legal.csv",
    "bln_downloads/fed_contracts/close_out.csv",
    "bln_downloads/fed_contracts/convenience.csv",
]

# Search criteria
DHS_TERMS = ["HOMELAND SECURITY", "IMMIGRATION AND CUSTOMS", "ICE ", "CUSTOMS ENFORCEMENT"]
FL_TERMS = ["FLORIDA", ", FL", "FL "]
DETENTION_TERMS = ["DETENTION", "DETAIN", "IGSA", "JAIL", "CORRECT", "INMATE"]
I4_COUNTIES = ["ORANGE", "OSCEOLA", "SEMINOLE", "POLK", "HILLSBOROUGH", "PINELLAS"]
I4_CITIES = ["ORLANDO", "TAMPA", "KISSIMMEE", "SANFORD"]

results = []
for filepath in files:
    print(f"Scanning {filepath}...", file=sys.stderr)
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                count += 1
                # Check if DHS/ICE related
                row_text = " ".join(str(v) for v in row.values()).upper()
                
                is_dhs = any(t in row_text for t in DHS_TERMS)
                is_fl = any(t in row_text for t in FL_TERMS)
                is_detention = any(t in row_text for t in DETENTION_TERMS)
                is_i4 = any(t in row_text for t in I4_COUNTIES + I4_CITIES)
                
                # Criteria: DHS/ICE AND (Florida OR I-4 corridor)
                if is_dhs and (is_fl or is_i4):
                    results.append({
                        "file": filepath.split("/")[-1],
                        "contract_id": row.get("contract_id", row.get("awardContractID__PIID", "")),
                        "vendor": row.get("vendor", row.get("UEILegalBusinessName", "")),
                        "amount_cancelled": row.get("amount_cancelled", ""),
                        "date_cancelled": row.get("date_cancelled", ""),
                        "admin_agency": row.get("admin_agency", ""),
                        "contracting_dept": row.get("contracting_agency_department", ""),
                        "funding_agency": row.get("funding_agency", ""),
                        "funding_dept": row.get("funding_agency_department", ""),
                        "description": row.get("product_or_service_description", ""),
                        "requirement": row.get("contract_requirement", row.get("contractData__descriptionOfContractRequirement", "")),
                        "performance_state": row.get("performance_state", ""),
                        "performance_county": row.get("performance_county", ""),
                        "vendor_state": row.get("vendor_state", ""),
                        "vendor_city": row.get("vendor_city", ""),
                        "reason": row.get("reason", ""),
                        "title": row.get("title", ""),
                        "is_detention": is_detention,
                        "is_i4_corridor": is_i4,
                        "total_obligated": row.get("totalDollarValues__totalObligatedAmount", ""),
                        "total_base_options": row.get("totalDollarValues__totalBaseAndAllOptionsValue", ""),
                    })
                
                # Also check: Florida + detention (regardless of agency)
                elif is_fl and is_detention and is_i4:
                    results.append({
                        "file": filepath.split("/")[-1],
                        "contract_id": row.get("contract_id", row.get("awardContractID__PIID", "")),
                        "vendor": row.get("vendor", row.get("UEILegalBusinessName", "")),
                        "amount_cancelled": row.get("amount_cancelled", ""),
                        "date_cancelled": row.get("date_cancelled", ""),
                        "admin_agency": row.get("admin_agency", ""),
                        "contracting_dept": row.get("contracting_agency_department", ""),
                        "funding_agency": row.get("funding_agency", ""),
                        "funding_dept": row.get("funding_agency_department", ""),
                        "description": row.get("product_or_service_description", ""),
                        "requirement": row.get("contract_requirement", row.get("contractData__descriptionOfContractRequirement", "")),
                        "performance_state": row.get("performance_state", ""),
                        "performance_county": row.get("performance_county", ""),
                        "vendor_state": row.get("vendor_state", ""),
                        "vendor_city": row.get("vendor_city", ""),
                        "reason": row.get("reason", ""),
                        "title": row.get("title", ""),
                        "is_detention": is_detention,
                        "is_i4_corridor": is_i4,
                        "total_obligated": row.get("totalDollarValues__totalObligatedAmount", ""),
                        "total_base_options": row.get("totalDollarValues__totalBaseAndAllOptionsValue", ""),
                    })
            
            print(f"  Scanned {count} rows", file=sys.stderr)
    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)

print(f"\nTotal DHS+FL matches: {len(results)}", file=sys.stderr)

# Also do a broader DHS search
dhs_all = []
for filepath in files[:3]:  # Just the smaller files
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_text = " ".join(str(v) for v in row.values()).upper()
                if any(t in row_text for t in DHS_TERMS):
                    dhs_all.append({
                        "file": filepath.split("/")[-1],
                        "vendor": row.get("vendor", ""),
                        "state": row.get("performance_state", ""),
                        "amount": row.get("amount_cancelled", ""),
                        "description": row.get("product_or_service_description", "")[:100],
                    })
    except:
        pass

print(f"Total DHS contracts (all states, smaller files): {len(dhs_all)}", file=sys.stderr)

output = {
    "dhs_florida_matches": results,
    "dhs_all_count": len(dhs_all),
    "dhs_all_sample": dhs_all[:50],
}

with open("bln_dhs_contracts.json", "w") as f:
    json.dump(output, f, indent=2)

# Print results
if results:
    print("\n=== DHS/ICE + Florida Contract Cancellations ===\n")
    for r in results:
        print(f"File: {r['file']}")
        print(f"  Contract: {r['contract_id']}")
        print(f"  Vendor: {r['vendor']}")
        print(f"  Amount Cancelled: {r['amount_cancelled']}")
        print(f"  Date: {r['date_cancelled']}")
        print(f"  Agency: {r['admin_agency']} / {r['funding_dept']}")
        print(f"  Description: {r['description'][:100]}")
        print(f"  Requirement: {r['requirement'][:200]}")
        print(f"  Performance: {r['performance_state']}, {r['performance_county']}")
        print(f"  Vendor Location: {r['vendor_city']}, {r['vendor_state']}")
        print(f"  I-4 Corridor: {r['is_i4_corridor']}")
        print(f"  Detention-related: {r['is_detention']}")
        print()
else:
    print("\nNo DHS/ICE + Florida matches found in contract cancellation data.")
    if dhs_all:
        print(f"\nDHS contracts found but not in FL ({len(dhs_all)} total). Sample states:")
        states = {}
        for d in dhs_all:
            s = d.get("state", "unknown")
            states[s] = states.get(s, 0) + 1
        for s, cnt in sorted(states.items(), key=lambda x: -x[1])[:15]:
            print(f"  {s}: {cnt}")
