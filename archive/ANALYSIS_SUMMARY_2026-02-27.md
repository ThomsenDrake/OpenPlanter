# Analysis Summary: ICE Detention Statistics & I-4 Corridor Facilities
**Date:** February 27, 2026
**Analyst:** OpenPlanter Investigation System

---

## 📌 EXECUTIVE SUMMARY

Analysis of ICE detention statistics (FY2020-FY2026) combined with USMS IGA documents reveals:

**3 I-4 corridor facilities currently holding ICE detainees:**
1. Pinellas County Jail (Clearwater) - USMS IGA - Active since FY2021
2. Orange County Jail (Orlando) - USMS IGA - Active since FY2022
3. Hillsborough County Jail (Tampa) - IGSA - NEW in FY2026

**Key Discovery:** Only 3 of 9 documented I-4 corridor facilities appear in official ICE detention statistics, despite 8 facilities having active 287(g) agreements.

---

## 📊 DATA ANALYZED

### ICE Detention Statistics (7 files)
- FY2020-FY2026 detention statistics (through Feb 12, 2026)
- Source: https://www.ice.gov/detain/detention-management
- Extracted "Facilities" sheets from each Excel file
- Total: 11 I-4 corridor facility records across all years

### USMS IGA Documents
- Pinellas County Sheriff's Office IGA
  - Agreement: 18-91-0041
  - Facility Code: 4RI
  - Federal Capacity: 400 beds (300 male / 100 female)
  - Per-Diem: $80.00
- Hillsborough County IGA (reviewed)
- John E. Polk Correctional Facility IGA (reviewed)
- Osceola County Sheriff's Department IGA (reviewed)

---

## 🔍 KEY FINDINGS

### Finding 1: Three-Tier System Identified

**Tier 1: Active ICE Detention (Confirmed in Statistics)**
- Facilities actively holding ICE detainees
- Appear in official ICE detention statistics
- Regular population reporting to ICE

| Facility | County | Type | Period Active |
|----------|--------|------|---------------|
| Pinellas County Jail | Pinellas | USMS IGA | FY2021-FY2026 |
| Orange County Jail | Orange | USMS IGA | FY2022, FY2024-FY2026 |
| Hillsborough County Jail | Hillsborough | IGSA | FY2026 only |

**Tier 2: 287(g) Authority but No Detention Statistics**
- Have 287(g) agreements and detention authority
- Do NOT appear in ICE detention statistics FY2020-FY2026
- May hold detainees for very short periods or under different arrangements

| Facility | County | Capacity | Status |
|----------|--------|----------|--------|
| Hillsborough Falkenburg Road Jail | Hillsborough | 3,300 beds | 287(g) but no stats |
| Polk County Jail | Polk | Unknown | 287(g) but no stats |
| John E. Polk Correctional | Seminole | 1,396 beds | 287(g) but no stats |
| Volusia County Branch Jail | Volusia | Unknown | 287(g) but no stats |
| Volusia County Correctional | Volusia | Unknown | 287(g) but no stats |

**Tier 3: Planned/Proposed**
- Orlando ICE Processing Center (1,500 beds planned)

### Finding 2: USMS Joint-Use Pattern

**Pinellas & Orange Counties:**
- Both classified as USMS IGA in ICE statistics
- Hold USMS prisoners + ICE detainees + county inmates
- Joint-use funding model
- Confirmed by USMS Agreement Documents 2022 (Orange: Facility Code 4CM)

**Hillsborough County:**
- Classified as IGSA (not USMS IGA) in ICE statistics
- Direct ICE agreement, different operational model
- Only started FY2026 (after 287(g) signed Feb 2025)

### Finding 3: Timeline Patterns

```
FY2020: No I-4 corridor facilities in stats
   ↓
FY2021: Pinellas appears (first I-4 facility)
   ↓
FY2022: Orange added (2 facilities total)
   ↓
FY2023: Only Pinellas (Orange disappears - gap year)
   ↓
FY2024: Orange returns with "(FL)" suffix designation
   ↓
FY2025: Same 2 facilities continue
   ↓
FY2026: Hillsborough added (3 facilities - NEW)
```

**Notable:** Hillsborough County Jail only appears in FY2026, despite:
- 287(g) agreement signed February 26, 2025
- Both Orient Road and Falkenburg Road facilities documented
- Suggests ICE began placing detainees ~7 months after 287(g) implementation

### Finding 4: Address Verification

**Orange County Jail Address Discrepancy:**
- ICE Stats: 3855 South John Young Parkway, Orlando
- Previous Docs: 3723 Vision Blvd, Orlando
- Explanation: John Young = intake/booking; Vision Blvd = main facility

**Pinellas County Address:**
- ICE Stats: 14400 49th Street North, Clearwater
- USMS IGA: 10750 Ulmerton Road, Largo
- Explanation: Administrative vs physical location, or different parts of same complex

---

## 📈 CAPACITY & OPERATIONAL DATA

### From USMS IGA - Pinellas County
- **Federal Beds:** 400 (300 male / 100 female)
- **Per-Diem Rate:** $80.00
- **Guard Rate:** $27.57/hour
- **Billing:** Monthly invoices to USMS Tampa, BOP Orlando, ICE Burlington
- **Services:** Housing, medical, courthouse transport

### From ICE Statistics
- All three facilities classified as Female/Male
- Average Daily Population (ADP) data available in Excel files
- Average Length of Stay (ALOS) data available
- Classification level breakdowns available

---

## ⚠️ CRITICAL QUESTIONS

### 1. Why do 6 facilities with 287(g) not appear in ICE detention stats?

**Possible Explanations:**
- **Book-and-Release Model:** Hold detainees briefly for processing, then transfer
- **Identification Only:** 287(g) used for immigration status checks, not detention
- **Different Reporting:** Held under funding arrangements not captured in detention stats
- **Short-Term Holding:** Detainees moved quickly to other facilities
- **Capacity Issues:** Facilities may not have available beds for ICE

### 2. Why did Orange County disappear from FY2023 stats?

**Possible Explanations:**
- Operational change or contract modification
- Data reporting gap
- Temporary suspension of ICE housing
- Change in statistical methodology

### 3. Why different facility types (IGSA vs USMS IGA)?

**Hillsborough (IGSA):**
- Direct agreement with ICE
- No USMS prisoners
- Simpler administrative structure

**Pinellas/Orange (USMS IGA):**
- Joint-use with US Marshals
- Shared infrastructure and costs
- More complex funding but potentially more stable

---

## 📁 FILES GENERATED

### Analysis Documents
1. **ICE_STATS_ANALYSIS_2026-02-27.md** - Full analysis report
2. **ICE_STATS_KEY_FINDINGS.md** - Quick reference summary
3. **THIS DOCUMENT** - Comprehensive summary

### Data Files
1. **i4_facilities_all_years.json** - All facility records by fiscal year
2. **i4_facilities_grouped.json** - Facilities grouped by name
3. **FY##_detentionStats_facilities.json** - Individual year extractions

### Analysis Scripts
1. **extract_i4_facilities.py** - Main extraction script
2. **parse_facilities_sheet.py** - Excel parsing utilities
3. **analyze_all_facilities.py** - Multi-year analysis

---

## ✅ CONFIDENCE LEVELS

### Confirmed (High Confidence)
- 3 facilities currently holding ICE detainees (ICE statistics)
- USMS joint-use pattern for Pinellas/Orange (USMS IGA documents)
- Facility types and classifications (ICE statistics)
- Timeline of facility usage FY2020-FY2026 (ICE statistics)

### Probable (Medium Confidence)
- 6 additional facilities with 287(g) authority (ICE MOA documents, TRAC reports)
- Reasons for non-appearance in statistics (inferred from patterns)
- Address discrepancies explained (operational differences)

### Requires Investigation (Unknown)
- Why specific facilities don't appear despite 287(g)
- Orange County FY2023 gap
- Population counts and trends
- Transfer patterns between facilities

---

## 🎯 RECOMMENDATIONS

### Immediate Actions
1. ✅ COMPLETED: Extract and analyze ICE detention statistics
2. ✅ COMPLETED: Cross-reference with existing documentation
3. ⏳ NEXT: Extract detailed population data (ADP, ALOS) from Excel files
4. ⏳ NEXT: Analyze year-over-year population trends

### Future Investigation
1. **FOIA Requests:** Request detailed data on 287(g) facilities not in detention stats
2. **Interviews:** Contact county officials about ICE housing arrangements
3. **Transfer Analysis:** Map where detainees go after initial booking at 287(g) facilities
4. **Funding Analysis:** Investigate funding streams for IGSA vs USMS IGA facilities

---

## 📊 METHODOLOGY

### Data Extraction
- Parsed Excel files using Python zipfile module (no external dependencies)
- Extracted "Facilities" sheet from each fiscal year file
- Filtered for Florida state and I-4 corridor counties
- Matched facilities by name, city, and county

### Cross-Reference
- Compared with existing ice_facilities_i4_corridor.json
- Verified against USMS IGA documents
- Checked addresses and facility types
- Analyzed timeline patterns

### Quality Assurance
- Manual verification of address discrepancies
- Cross-check with multiple data sources
- Documented confidence levels
- Flagged anomalies for further investigation

---

## 📞 CONTACT & RESOURCES

**Data Sources:**
- ICE Detention Statistics: https://www.ice.gov/detain/detention-management
- USMS IGA Documents: Manually downloaded from usmarshals.gov
- Previous Investigation: ice_facilities_i4_corridor.json

**Related Documents:**
- findings.md (previous comprehensive report)
- USMS-Agreement-Documents-2022_OCR.md
- FOIA-Strategy-Summary.md

---

**Analysis Completed:** February 27, 2026
**Next Update:** Upon receipt of FOIA responses or new data
