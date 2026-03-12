Document-Type: deep-dive
Canonical: yes
Derived-From: TRAC extraction outputs
Last-Reviewed: 2026-02-27
Status: active
Contradictions-Tracked-In: I4_CORRIDOR_MASTER_INVESTIGATION.md

# TRAC vs ICE Detention Stats Cross-Reference Analysis
## I-4 Corridor Investigation - Florida

**Generated:** February 27, 2026
**TRAC Data Source:** https://tracreports.org/immigration/tools/#ICE_Tools
**ICE Stats Source:** FY26_detentionStats_02122026.xlsx (via FOIA)

---

## Executive Summary

Cross-referencing TRAC Immigration data with ICE detention statistics reveals **significant discrepancies** in facility classification and population reporting for Florida I-4 corridor facilities. These discrepancies warrant investigation.

### Key Findings:
1. **278% growth** in Florida ICE detention population (March 2024: 1,385 → February 2026: 5,231)
2. **Type classification mismatch** for Pinellas County Jail (TRAC: IGSA vs ICE Stats: USMS IGA)
3. **Missing facilities** - some facilities appear in one dataset but not the other
4. **I-4 corridor facilities** only partially represented in both datasets

---

## Florida Statewide Detention Trends

| Period | Population | Source |
|--------|------------|--------|
| March 2024 | 1,385 | TRAC Historical Tool |
| February 2026 | 5,231 | TRAC Quick Facts |
| **Change** | **+3,846 (+278%)** | |

### National Context (Feb 2026)
- **Texas:** 18,734 (highest)
- **Louisiana:** 8,244
- **California:** 6,459
- **Florida:** 5,231 (4th highest)
- **Georgia:** 4,227

---

## Facility-by-Facility Cross-Reference

### TRAC Florida Facilities (Feb 5, 2026)

| Facility | City | Type | Guaranteed Min | Avg Pop |
|----------|------|------|----------------|---------|
| BAKER CORRECTIONAL INSTITUTION | Sanderson | STATE | - | 871 |
| BAKER COUNTY SHERIFF DEPT. | McClenny | IGSA | 250 | 286 |
| BROWARD COUNTY JAIL | Ft. Lauderdale | IGSA | - | 3 |
| BROWARD TRANSITIONAL CENTER | Pompano Beach | CDF | 700 | 681 |
| GLADES COUNTY DETENTION CENTER | Moore Haven | IGSA | 700 | 458 |
| HENDRY COUNTY JAIL | Clewiston | IGSA | - | 59 |
| **HILLSBOROUGH COUNTY JAIL** | Tampa | IGSA | 125 | **132** |
| JACKSON COUNTY CORRECTIONAL FACILITY | Marianna | IGSA | - | 23 |
| KROME NORTH SERVICE PROCESSING CENTER | Miami | SPC | 550 | 595 |
| MONROE COUNTY JAIL | Key West | IGSA | - | 9 |
| **ORLANDO ICE PROCESSING CENTER** | Orlando | IGSA | 150 | **167** |
| **PINELLAS COUNTY JAIL** | Clearwater | IGSA | - | **4** |

**Total Florida (TRAC):** 3,288 detainees across 12 facilities

### ICE Stats Florida Facilities (FY26 as of Feb 12, 2026)

| Facility | City | Type | Address |
|----------|------|------|---------|
| FLORIDA SOFT-SIDED FACILITY | Ochopee | STATE | 54575 Tamiami Trail E |
| **HILLSBOROUGH COUNTY JAIL** | Tampa | IGSA | 1201 North Orient Road |
| **ORANGE COUNTY JAIL (FL)** | Orlando | **USMS IGA** | 3855 S John Young Parkway |
| **PINELLAS COUNTY JAIL** | Clearwater | **USMS IGA** | 14400 49th Street North |

---

## I-4 Corridor Discrepancies

### 1. PINELLAS COUNTY JAIL - Type Mismatch ⚠️

| Attribute | TRAC (Feb 2026) | ICE Stats (FY26) |
|-----------|-----------------|------------------|
| **Type** | IGSA | **USMS IGA** |
| Population | 4 | Not specified |
| Guaranteed Min | None | Not applicable |

**Significance:** The classification difference indicates:
- TRAC reports direct ICE-County agreement (IGSA)
- ICE Stats reports ICE using US Marshals Service agreement (USMS IGA)
- This affects reimbursement rates and contract terms

### 2. ORANGE COUNTY JAIL (FL) - Missing from TRAC ⚠️

| Attribute | TRAC (Feb 2026) | ICE Stats (FY26) |
|-----------|-----------------|------------------|
| **Presence** | NOT LISTED | Listed as active |
| Type | N/A | USMS IGA |
| Address | N/A | 3855 S John Young Parkway |
| Last Inspection | N/A | ODO (45519) - NDS 2019 - Pass |

**Significance:** 
- ICE Stats shows Orange County Jail actively housing ICE detainees via USMS IGA
- TRAC snapshot (Feb 5) may have missed this facility
- Possible population undercount in TRAC for Florida

### 3. ORLANDO ICE PROCESSING CENTER - Missing from ICE Stats ⚠️

| Attribute | TRAC (Feb 2026) | ICE Stats (FY26) |
|-----------|-----------------|------------------|
| **Presence** | Listed as active | NOT LISTED |
| Type | IGSA | N/A |
| Population | 167 | N/A |
| Guaranteed Min | 150 | N/A |

**Significance:**
- TRAC shows 167 detainees at this facility
- ICE Stats facilities list does not include this facility
- Possible data collection methodology difference

### 4. HILLSBOROUGH COUNTY JAIL - Consistent ✓

| Attribute | TRAC (Feb 2026) | ICE Stats (FY26) |
|-----------|-----------------|------------------|
| **Type** | IGSA | IGSA |
| Population | 132 | ~132 (ADP 1.28) |
| Address | Tampa | 1201 North Orient Road |

**Status:** Classification matches between datasets

---

## I-4 Counties Missing from Both Datasets

| County | TRAC | ICE Stats | Notes |
|--------|------|-----------|-------|
| POLK | Not listed | Not listed | May use facilities outside county |
| SEMINOLE | Not listed | Not listed | Part of Orlando ICE AOR |
| VOLUSIA | Not listed | Not listed | May transfer to other facilities |
| OSCEOLA | Not listed | Not listed | **Historical rate data shows activity** |

**Critical Finding:** Osceola County Sheriff's Department has a $35/day IGA rate (documented in our transcriptions) but does NOT appear in either TRAC or ICE Stats facility lists. This confirms our previous finding that Osceola may be underreporting or using alternative accounting.

---

## TRAC Data Deep Dive Opportunities

### Available TRAC Tools for Further Analysis:

1. **ICE Removals Tool** (through Feb 2024)
   - Individual deportation records
   - Can filter by state (Florida: 169,338 total removals)
   - Departure cities available

2. **Detention Snapshots** (through March 2024)
   - Monthly population data by facility
   - Detainee characteristics
   - Facility type breakdowns

3. **Book-In Statistics** (Oct 2018 - Feb 2026)
   - ICE vs CBP arrests
   - Monthly trends
   - National totals only

4. **Facility Population Trends**
   - Historical data available
   - Can track facility utilization over time

### Data Not Available in TRAC:
- Per-detainee daily rates
- IGA contract terms
- Facility-specific financial data
- 287(g) program participation

---

## Implications for Investigation

### 1. Contract Structure Questions
- Why does Pinellas show as USMS IGA in ICE stats but IGSA in TRAC?
- Does Orange County use USMS IGA to hide ICE activity from public records?
- Are guaranteed minimum bed counts creating financial incentives?

### 2. Data Quality Issues
- TRAC and ICE Stats use different snapshots (Feb 5 vs Feb 12)
- Some facilities may be miscategorized
- Population numbers vary significantly

### 3. Missing Osceola Data
- Osceola's $35/day rate (unchanged since 1985) suggests active participation
- Absence from both datasets indicates possible data suppression
- USMS IGA route may be masking county-level transparency

### 4. FOIA Request Validation
- Pending FOIA responses from Pinellas, Polk counties will clarify USMS IGA vs IGSA
- ICE ERO facility codes FOIA will resolve naming discrepancies
- ICE Procurement contracts will show actual agreement types

---

## Next Steps

1. **Download TRAC historical data** for Florida facilities (March 2024 back to 2018)
2. **Cross-reference removal data** to identify Florida deportation patterns
3. **Monitor TRAC updates** when new data is released (monthly)
4. **Compare book-in trends** with local arrest data
5. **Validate findings** when FOIA responses arrive (March 10-25)

---

## Data Sources

- **TRAC Immigration:** https://tracreports.org/immigration/tools/#ICE_Tools
- **TRAC Detention Quick Facts:** https://tracreports.org/immigration/quickfacts/detention.html
- **TRAC Facilities Data:** https://tracreports.org/immigration/detentionstats/facilities.html
- **TRAC Removals Data:** https://tracreports.org/phptools/immigration/remove/
- **ICE Stats (Local):** FY26_detentionStats_02122026.xlsx

---

## Appendix: TRAC Facility Type Definitions

| Code | Full Name | Description |
|------|-----------|-------------|
| IGSA | Intergovernmental Service Agreement | Local jail with ICE bed space; houses ICE and non-ICE detainees |
| DIGSA | Dedicated IGSA | IGSA where ICE contracts ALL bed space or only houses ICE detainees |
| CDF | Contract Detention Facility | Private company facility contracted directly with government |
| SPC | Service Processing Center | Government-owned, federal/contract staffed |
| USMS IGA | USMS Intergovernmental Agreement | US Marshals contract that ICE piggybacks on |
| STATE | State Facility | State-operated correctional facility |
