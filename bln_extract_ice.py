#!/usr/bin/env python3
"""Extract ICE/DHS Florida contract cancellations from BLN data - optimized."""
import csv
import json
import sys

# Use the limited cols file for convenience (smaller) and close_out for completeness
files_to_search = [
    ("bln_downloads/fed_contracts/convenience--limited_cols.csv", "convenience"),
    ("bln_downloads/fed_contracts/close_out.csv", "close_out"),
    ("bln_downloads/fed_contracts/default.csv", "default"),
    ("bln_downloads/fed_contracts/for_cause.csv", "for_cause"),
    ("bln_downloads/fed_contracts/legal.csv", "legal"),
]

# First, let's see what columns the limited file has
with open("bln_downloads/fed_contracts/convenience--limited_cols.csv") as f:
    reader = csv.DictReader(f)
    print("Limited cols:", list(reader.fieldnames)[:30])

results = {"ice_fl_contracts": [], "dhs_fl_contracts": [], "ice_i4_corridor": []}

I4_COUNTIES = {"ORANGE", "OSCEOLA", "SEMINOLE", "POLK", "HILLSBOROUGH", "PINELLAS", "BREVARD", "VOLUSIA", "LAKE"}
I4_CITIES = {"ORLANDO", "TAMPA", "KISSIMMEE", "SANFORD", "LAKELAND", "CLEARWATER", "ST PETERSBURG", "SAINT PETERSBURG"}

for filepath, label in files_to_search:
    print(f"\nProcessing {filepath}...", file=sys.stderr)
    ice_fl = 0
    dhs_fl = 0
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_upper = {k: (str(v) or "").upper() for k, v in row.items()}
                all_text = " ".join(row_upper.values())
                
                is_ice = "IMMIGRATION AND CUSTOMS" in all_text or "7012" in row_upper.get("awardContractID__agencyID", row_upper.get("contractingOfficeAgencyID", ""))
                is_dhs = "HOMELAND SECURITY" in all_text
                is_fl = row_upper.get("principalPlaceOfPerformance__stateCode", row_upper.get("performance_state", "")) == "FL" or "FLORIDA" in all_text
                
                perf_county = row_upper.get("placeOfPerformanceZIPCode__county", row_upper.get("performance_county", ""))
                perf_city = row_upper.get("placeOfPerformanceZIPCode__city", row_upper.get("", ""))
                is_i4 = any(c in perf_county for c in I4_COUNTIES) or any(c in all_text for c in I4_CITIES)
                
                if is_ice and is_fl:
                    ice_fl += 1
                    entry = {
                        "source_file": label,
                        "contract_id": row.get("awardContractID__PIID", row.get("contract_id", "")),
                        "mod_number": row.get("awardContractID__modNumber", row.get("modification_number", "")),
                        "vendor": row.get("vendor", row.get("UEILegalBusinessName", "")),
                        "vendor_dba": row.get("vendorDoingAsBusinessName", ""),
                        "amount_cancelled": row.get("amount_cancelled", ""),
                        "obligated_amount": row.get("dollarValues__obligatedAmount", ""),
                        "total_obligated": row.get("totalDollarValues__totalObligatedAmount", ""),
                        "total_base_options": row.get("totalDollarValues__totalBaseAndAllOptionsValue", ""),
                        "date_cancelled": row.get("date_cancelled", ""),
                        "signed_date": row.get("relevantContractDates__signedDate", ""),
                        "agency_id": row.get("awardContractID__agencyID", ""),
                        "agency_name": row.get("awardContractID__agencyID__name", ""),
                        "contracting_office": row.get("contractingOfficeID__name", ""),
                        "funding_agency": row.get("fundingRequestingAgencyID__name", ""),
                        "funding_dept": row.get("fundingRequestingAgencyID__departmentName", ""),
                        "description": row.get("contractData__descriptionOfContractRequirement", row.get("product_or_service_description", "")),
                        "product_service": row.get("productOrServiceInformation__productOrServiceCode__description", row.get("product_or_service_description", "")),
                        "naics": row.get("productOrServiceInformation__principalNAICSCode__description", ""),
                        "perf_state": row.get("principalPlaceOfPerformance__stateCode", row.get("performance_state", "")),
                        "perf_county": perf_county,
                        "perf_city": row.get("placeOfPerformanceZIPCode__city", ""),
                        "perf_zip": row.get("placeOfPerformanceZIPCode", ""),
                        "vendor_city": row.get("vendorLocation__city", row.get("vendor_city", "")),
                        "vendor_state": row.get("vendorLocation__state", row.get("vendor_state", "")),
                        "reason": row.get("reason", ""),
                        "reason_code": row.get("reason_code", row.get("contractData__reasonForModification", "")),
                        "title": row.get("title", ""),
                        "fpds_url": row.get("fpds_url", ""),
                        "is_i4_corridor": is_i4,
                        "is_detention_related": any(t in all_text for t in ["DETENTION", "DETAIN", "JAIL", "CORRECT", "INMATE"]),
                    }
                    results["ice_fl_contracts"].append(entry)
                    if is_i4:
                        results["ice_i4_corridor"].append(entry)
                elif is_dhs and is_fl:
                    dhs_fl += 1
                    entry = {
                        "source_file": label,
                        "contract_id": row.get("awardContractID__PIID", row.get("contract_id", "")),
                        "vendor": row.get("vendor", row.get("UEILegalBusinessName", "")),
                        "amount_cancelled": row.get("amount_cancelled", ""),
                        "total_obligated": row.get("totalDollarValues__totalObligatedAmount", ""),
                        "date_cancelled": row.get("date_cancelled", ""),
                        "agency_name": row.get("awardContractID__agencyID__name", ""),
                        "funding_agency": row.get("fundingRequestingAgencyID__name", ""),
                        "description": row.get("contractData__descriptionOfContractRequirement", row.get("product_or_service_description", ""))[:300],
                        "perf_state": row.get("principalPlaceOfPerformance__stateCode", row.get("performance_state", "")),
                        "perf_county": perf_county,
                        "is_i4_corridor": is_i4,
                    }
                    results["dhs_fl_contracts"].append(entry)
        
        print(f"  ICE+FL: {ice_fl}, DHS+FL (non-ICE): {dhs_fl}", file=sys.stderr)
    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()

# Summary
print(f"\n=== SUMMARY ===", file=sys.stderr)
print(f"Total ICE + Florida contracts: {len(results['ice_fl_contracts'])}", file=sys.stderr)
print(f"Total DHS + Florida (non-ICE): {len(results['dhs_fl_contracts'])}", file=sys.stderr)
print(f"ICE + I-4 Corridor: {len(results['ice_i4_corridor'])}", file=sys.stderr)

# Deduplicate by contract ID
seen = set()
unique_ice_fl = []
for c in results["ice_fl_contracts"]:
    key = c["contract_id"]
    if key and key not in seen:
        seen.add(key)
        unique_ice_fl.append(c)
results["unique_ice_fl"] = unique_ice_fl

print(f"Unique ICE+FL contract IDs: {len(unique_ice_fl)}", file=sys.stderr)

# Detention-related
detention = [c for c in results["ice_fl_contracts"] if c.get("is_detention_related")]
results["detention_related"] = detention
print(f"Detention-related: {len(detention)}", file=sys.stderr)

with open("bln_ice_fl_contracts.json", "w") as f:
    json.dump(results, f, indent=2)

# Print I-4 corridor hits and detention hits
print("\n=== ICE CONTRACTS IN I-4 CORRIDOR ===\n")
for c in results["ice_i4_corridor"][:20]:
    print(f"Contract: {c['contract_id']} | {c['source_file']}")
    print(f"  Vendor: {c['vendor']}")
    print(f"  Total Obligated: ${c['total_obligated']}")
    print(f"  Location: {c['perf_city']}, {c['perf_county']}, FL")
    print(f"  Description: {str(c['description'])[:200]}")
    print(f"  Detention-related: {c['is_detention_related']}")
    print()

if detention:
    print("\n=== DETENTION-RELATED ICE FL CONTRACTS ===\n")
    for c in detention[:20]:
        print(f"Contract: {c['contract_id']} | {c['source_file']}")
        print(f"  Vendor: {c['vendor']}")
        print(f"  Total Obligated: ${c['total_obligated']}")
        print(f"  Location: {c['perf_city']}, {c['perf_county']}, FL")
        print(f"  Description: {str(c['description'])[:300]}")
        print()
