Document-Type: deep-dive
Canonical: yes
Derived-From: detention stats extraction outputs
Last-Reviewed: 2026-02-27
Status: active
Contradictions-Tracked-In: I4_CORRIDOR_MASTER_INVESTIGATION.md

# ICE Detention Statistics Analysis Update
**Generated:** February 27, 2026
**Data Source:** ICE Detention Statistics FY2020-FY2026

---

## Executive Summary

Analysis of official ICE detention statistics (FY2020-FY2026) reveals that only **3 I-4 corridor facilities** are currently holding ICE detainees, despite **9 facilities** being documented with 287(g) agreements and IGSA contracts.

### Key Findings

1. **Active ICE Detention Facilities in I-4 Corridor:** 3
   - Pinellas County Jail (Clearwater)
   - Orange County Jail (Orlando)
   - Hillsborough County Jail (Tampa) - NEW in FY2026

2. **Facilities with 287(g) but NOT in ICE Detention Stats:** 6
   - Hillsborough County Falkenburg Road Jail
   - Polk County Jail (Bartow)
   - John E. Polk Correctional Facility (Seminole County)
   - Volusia County Branch Jail
   - Volusia County Correctional Facility
   - Orlando ICE Processing Center (planned)

---

## Detailed Analysis: ICE Detention Statistics (FY2020-FY2026)

### Timeline of I-4 Corridor Facility Usage

| Fiscal Year | Facilities in ICE Detention Stats |
|-------------|-----------------------------------|
| FY2020 | None found |
| FY2021 | Pinellas County Jail |
| FY2022 | Orange County Jail, Pinellas County Jail |
| FY2023 | Pinellas County Jail |
| FY2024 | Orange County Jail (FL), Pinellas County Jail |
| FY2025 | Orange County Jail (FL), Pinellas County Jail |
| FY2026 | **Hillsborough County Jail**, Orange County Jail (FL), Pinellas County Jail |

### Facility Details from ICE Statistics

#### 1. PINELLAS COUNTY JAIL
- **Address:** 14400 49th Street North, Clearwater, FL 33762
- **County:** Pinellas
- **Facility Type:** USMS IGA (U.S. Marshals Service Intergovernmental Agreement)
- **Gender:** Female/Male
- **Years in ICE Stats:** FY2021-FY2026 (6 consecutive years)
- **Status:** Continuously active since at least FY2021
- **Notes:** Longest-running I-4 corridor facility in ICE detention statistics

#### 2. ORANGE COUNTY JAIL (FL)
- **Address:** 3855 South John Young Parkway, Orlando, FL 32839
- **County:** Orange
- **Facility Type:** USMS IGA (U.S. Marshals Service Intergovernmental Agreement)
- **Gender:** Female/Male
- **Years in ICE Stats:** FY2022, FY2024-FY2026 (5 years total)
- **Status:** Active (gap in FY2023 suggests reporting or operational change)
- **Notes:** Address differs from main facility address (3723 Vision Blvd) - this may be booking/intake facility

#### 3. HILLSBOROUGH COUNTY JAIL
- **Address:** 1201 North Orient Road, Tampa, FL 33619
- **County:** Hillsborough
- **Facility Type:** IGSA (Intergovernmental Service Agreement)
- **Gender:** Female/Male
- **Years in ICE Stats:** FY2026 only
- **Status:** NEW - First appearance in FY2026 (which started October 2025)
- **Notes:** 
  - Address confirms this is Orient Road Jail, not Falkenburg Road
  - Appears ONLY as IGSA (not USMS IGA)
  - First year of ICE detention usage despite 287(g) agreement signed February 2025
  - Suggests ICE began placing detainees after 287(g) implementation

---

## Important Findings

### 1. USMS Joint-Use Pattern Confirmed

**Pinellas County Jail** and **Orange County Jail** are classified as **USMS IGA** facilities in ICE statistics, confirming they are **joint-use facilities** that hold:
- U.S. Marshals Service prisoners
- ICE detainees
- County inmates

This aligns with:
- USMS Agreement Documents 2022 showing Orange County Jail (Facility Code: 4CM)
- USMS IGA transcriptions for Pinellas County Sheriff's Office
- News reports about Orange County seeking better reimbursement from both USMS and ICE

### 2. Hillsborough County - Different Arrangement

**Hillsborough County Jail** appears as **IGSA** (not USMS IGA), suggesting:
- Direct agreement with ICE (not through USMS)
- Different funding/operational structure than Pinellas/Orange
- May explain why it only started appearing in FY2026 despite 287(g) agreement signed Feb 2025

### 3. Facilities NOT in ICE Detention Statistics

The following I-4 corridor facilities have 287(g) agreements but **do NOT appear** in ICE detention statistics FY2020-FY2026:

1. **Hillsborough County Falkenburg Road Jail** (3,300 beds)
   - Has 287(g) agreement
   - No ICE detainees in official statistics
   
2. **Polk County Jail** (Bartow)
   - Has 287(g) agreement
   - TRAC reports show 43 ICE detainers, 200+ transfers to ICE
   - Not in ICE detention statistics
   
3. **John E. Polk Correctional Facility** (Seminole County)
   - Has 287(g) agreement since 2019
   - Not in ICE detention statistics
   
4. **Volusia County Branch Jail**
   - Has 287(g) agreement
   - Not in ICE detention statistics
   
5. **Volusia County Correctional Facility**
   - Has 287(g) agreement
   - Not in ICE detention statistics

**Possible Explanations:**
- Facilities may hold ICE detainees for very short periods (book-and-release)
- Detainees transferred quickly to other facilities
- 287(g) used for identification/processing, not long-term detention
- ICE detainees held under different funding arrangements not captured in detention stats
- Data reporting gaps or different statistical methodologies

### 4. Geographic Concentration

**Current ICE detention in I-4 corridor is concentrated in:**
- Tampa Bay Area (Hillsborough, Pinellas)
- Orlando Area (Orange)

**Notable absences:**
- No Polk County facilities in ICE detention stats (despite 287(g))
- No Seminole County facilities in ICE detention stats (despite 287(g))
- No Volusia County facilities in ICE detention stats (despite 287(g))

---

## Address Discrepancy: Orange County Jail

**ICE Statistics Address:**
- 3855 South John Young Parkway, Orlando, FL 32839

**Previously Documented Address:**
- 3723 Vision Blvd, Orlando, FL 32839

**Analysis:**
- John Young Parkway address may be booking/intake facility
- Vision Blvd is main correctional facility
- Both addresses are in Orlando (Orange County)
- Confirms same facility with different operational areas

---

## Capacity and Population Data

ICE detention statistics include columns for:
- Average Daily Population (ADP)
- Average Length of Stay (ALOS)
- Detainee classification levels

**Note:** This analysis focused on facility identification. Detailed population data available in the Excel files for further analysis.

---

## Methodology

1. **Data Sources:** 
   - ICE Detention Statistics Excel files FY2020-FY2026 (7 files)
   - Parsed using Python zipfile module (no external dependencies)
   - Extracted "Facilities" sheet from each file

2. **Geographic Filtering:**
   - Filtered for state = FL
   - Matched against I-4 corridor counties: Hillsborough, Pinellas, Polk, Orange, Seminole, Volusia
   - Used both county names and city names for matching

3. **Cross-Reference:**
   - Compared with existing ice_facilities_i4_corridor.json
   - Verified addresses and facility types
   - Identified timeline patterns

---

## Data Sources

- **FY26_detentionStats_02122026.xlsx** (through Feb 12, 2026)
- **FY25_detentionStats.xlsx**
- **FY24_detentionStats.xlsx**
- **FY23_detentionStats.xlsx**
- **FY22_detentionStats.xlsx**
- **FY21_detentionStats.xlsx**
- **FY20_detentionStats.xlsx**

**Source URL:** https://www.ice.gov/detain/detention-management

---

## Next Steps

1. **Population Analysis:** Extract detailed population data (ADP, ALOS, capacity) for each facility
2. **Trend Analysis:** Analyze year-over-year changes in detention populations
3. **Cross-Reference:** Compare with FOIA responses when received
4. **Verify Non-Appearing Facilities:** Investigate why Polk, Seminole, Volusia facilities don't appear despite 287(g) agreements
5. **Update Main Database:** Integrate this data into ice_facilities_i4_corridor.json

---

## Files Generated

- `i4_facilities_all_years.json` - All facility records by year
- `i4_facilities_grouped.json` - Facilities grouped by name
- Individual Excel parsing outputs for each fiscal year

---

## Confidence Levels

- **Confirmed:** Facilities appearing in ICE detention statistics (3 facilities)
- **Probable:** Facilities with 287(g) agreements but not in detention stats (6 facilities)
- **Requires Investigation:** Why certain facilities with 287(g) don't appear in official ICE detention statistics
