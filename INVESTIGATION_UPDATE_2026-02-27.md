# Investigation Update: ICE Detention Statistics Analysis
**Date:** February 27, 2026
**Session:** 20260226-210523-84c1ba
**Status:** Analysis Complete - FOIA Pending

---

## 📊 Work Completed

### 1. ICE Detention Statistics Analysis (FY2020-FY2026)
**Status:** ✅ COMPLETE

**Files Generated:**
- `POPULATION_TRENDS_2026-02-27.md` - Comprehensive trends analysis
- `population_trends_raw.json` - Raw extracted data from Excel files
- `population_trends_analysis.json` - Cleaned and analyzed trends data
- `ice_facilities_i4_corridor_updated.json` - Updated facility database with ICE stats

**Key Findings:**
- **3 facilities** currently holding ICE detainees (confirmed in official statistics)
- **6 facilities** with 287(g) agreements but NOT in ICE detention stats
- **Expansion pattern** from 0 to 3 facilities over 6 years
- **Notable gap** in Orange County Jail FY2023 data
- **NEW facility** in FY2026: Hillsborough County Jail (Orient Road)

---

### 2. Population Trends Extraction
**Status:** ✅ COMPLETE

**Method:** XML-based parsing of ICE detention statistics Excel files (FY20-FY26)

**Results:**
- 11 Florida I-4 corridor records extracted (filtered from 18 total records)
- 3 facilities tracked across 6 fiscal years
- Year-over-year patterns identified
- Orange County FY2023 gap documented

**Data Quality:**
- Column headers not fully identified (numeric metrics only)
- Population/capacity data captured but requires column mapping
- Sufficient for trend analysis and facility tracking

---

### 3. Facility Database Update
**Status:** ✅ COMPLETE

**Updated:** `ice_facilities_i4_corridor_updated.json`

**New Fields Added:**
- `ice_stats.confirmed` - Boolean confirming facility in ICE stats
- `ice_stats.detention_status` - Active/Not in statistics
- `ice_stats.stats_type` - USMS IGA vs. IGSA
- `ice_stats.first_year` - First year in ICE stats
- `ice_stats.years_active` - List of active fiscal years
- `ice_stats.notes` - Analysis notes
- `ice_stats_facility_type` - Type confirmed by ICE stats

**Metadata Updates:**
- Added ICE Detention Statistics FY2020-FY2026 to data sources
- Added ice_stats_summary with breakdown by facility type
- Updated last_updated date

---

## 🎯 Critical Findings

### Finding 1: Three-Tier System Confirmed

**Tier 1: Active ICE Detention (3 facilities)**
- Pinellas County Jail (USMS IGA) - FY2021-FY2026
- Orange County Jail (USMS IGA) - FY2022, FY2024-FY2026
- Hillsborough County Jail (IGSA) - FY2026 NEW

**Tier 2: 287(g) Authority Only (5 facilities)**
- Hillsborough Falkenburg Road Jail
- Polk County Jail
- John E. Polk Correctional Facility
- Volusia County Branch Jail
- Volusia County Correctional Facility

**Tier 3: Planned (1 facility)**
- Orlando ICE Processing Center (1,500 beds)

---

### Finding 2: Orange County Jail FY2023 Gap
**Discovery:** Orange County Jail disappeared from ICE detention statistics in FY2023, then returned in FY2024 with "(FL)" suffix designation.

**Questions:**
- Why did Orange disappear in FY2023?
- Was this a reporting issue, operational pause, or contract gap?
- What does the "(FL)" suffix designation mean?

**Action:** Flagged for FOIA investigation

---

### Finding 3: Hillsborough County Timing
**Discovery:** Hillsborough County Jail began holding ICE detainees in FY2026 (Oct 2025), approximately 7 months after 287(g) agreement signing (Feb 2025).

**Pattern:**
- Feb 26, 2025: 287(g) agreement signed
- Oct 2025: First ICE detainees placed
- Only Orient Road Jail appears in stats (not Falkenburg)

**Hypothesis:** IGSA contract negotiation + facility preparation = 7-month delay

---

### Finding 4: Missing 287(g) Facilities
**Discovery:** 5 facilities have 287(g) agreements but do NOT appear in ICE detention statistics FY2020-FY2026.

**Hypothesis:** Book-and-release model
- Hold detainees briefly for processing/identification
- Transfer to active detention facilities (Pinellas, Orange, Hillsborough)
- Or transfer to facilities outside I-4 corridor

**Required Data:** Transfer records from 287(g) facilities

---

## 📋 Outstanding Questions (FOIA Phase)

### HIGH PRIORITY

#### 1. Orange County FY2023 Gap
**Question:** Why did Orange County Jail disappear from ICE detention statistics in FY2023?

**FOIA Request:** ICE ERO facility records for Orange County Jail FY2023
**Status:** Pending (expected March 2026)

---

#### 2. 287(g) Facility Transfer Patterns
**Question:** What happens to detainees at facilities with 287(g) but no ICE detention stats?

**FOIA Request:** ICE ERO transfer records for I-4 corridor counties
**Status:** Pending (expected March 2026)

---

#### 3. Hillsborough IGSA Details
**Question:** What are the terms of Hillsborough's IGSA contract?

**FOIA Request:** Hillsborough County Sheriff PRR - IGSA contract
**Status:** Acknowledged, response expected March 10, 2026

---

### MODERATE PRIORITY

#### 4. Facility Codes
**Question:** What are the ICE facility codes for all I-4 corridor facilities?

**FOIA Request:** ICE ERO facility codes for Florida
**Status:** Pending submission

---

#### 5. Capacity Allocations
**Question:** How many ICE-dedicated beds at each facility?

**FOIA Request:** ICE capacity allocation records
**Status:** Pending submission

---

## 📈 Next Steps

### Immediate (This Week)
- [x] Extract population trends from ICE stats
- [x] Update facility database with ICE stats findings
- [x] Create comprehensive trends analysis document
- [ ] Backup updated facility database to original filename
- [ ] Create executive summary for stakeholder review

### Short-term (March 2026)
- [ ] Process FOIA/PRR responses (expected March 10-25)
  - Hillsborough County Sheriff (IGSA contract)
  - Seminole County Sheriff (John E. Polk records)
  - Volusia County Sheriff (Volusia facilities)
  - Orange County Corrections (Orange Jail records)
- [ ] Analyze FOIA data and cross-reference with ICE stats
- [ ] Investigate Orange County FY2023 gap
- [ ] Map transfer patterns from 287(g) facilities

### Medium-term (April-May 2026)
- [ ] Submit remaining FOIA requests (ICE ERO facility codes, capacity data)
- [ ] Build capacity vs. utilization model
- [ ] Analyze book-and-release patterns at 287(g) facilities
- [ ] Create final comprehensive investigation report

---

## 📊 Investigation Status Summary

| Component | Status | Completion |
|-----------|--------|------------|
| ICE Detention Stats Analysis | ✅ Complete | 100% |
| USMS IGA Document Analysis | ✅ Complete | 100% |
| Population Trends Extraction | ✅ Complete | 100% |
| Facility Database Update | ✅ Complete | 100% |
| FOIA Request Submission | 🔄 In Progress | 31% (5 of 16) |
| FOIA Response Processing | ⏳ Pending | 0% |
| Transfer Pattern Analysis | ⏳ Pending | 0% |
| Final Report | ⏳ Pending | 0% |

**Overall Investigation Progress:** 40% complete

---

## 📁 Files Generated This Session

1. `extract_trends_xml.py` - XML parser for ICE stats Excel files
2. `analyze_trends.py` - Trends analysis script
3. `update_facility_db.py` - Database update script
4. `population_trends_raw.json` - Raw extracted data
5. `population_trends_analysis.json` - Cleaned trends data
6. `POPULATION_TRENDS_2026-02-27.md` - Trends analysis document
7. `ice_facilities_i4_corridor_updated.json` - Updated facility database
8. `INVESTIGATION_UPDATE_2026-02-27.md` - This update document

---

## 🔗 Related Documents

- `ANALYSIS_SUMMARY_2026-02-27.md` - Previous analysis summary
- `ICE_STATS_KEY_FINDINGS.md` - Key findings from ICE stats
- `FOIA_Status_Summary_2026-02-26.md` - FOIA tracking
- `foia_gap_analysis.md` - FOIA strategy document

---

**Investigation Lead:** OpenPlanter Investigation System
**Last Updated:** February 27, 2026
**Next Milestone:** FOIA response processing (March 10-25, 2026)
