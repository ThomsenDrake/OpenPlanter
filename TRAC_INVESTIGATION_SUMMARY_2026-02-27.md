# TRAC Immigration Data Integration - Executive Summary
## I-4 Corridor ICE Detention Investigation

**Generated:** February 27, 2026
**Status:** COMPLETED - Data Integrated
**Source:** TRAC Immigration (Syracuse University)

---

## 🎯 Key Accomplishments

### 1. TRAC Data Successfully Accessed
- ✅ Detention Quick Facts (Feb 2026)
- ✅ Facility Population Data (Feb 5, 2026)
- ✅ ICE Removals Data (through Feb 2024)
- ✅ Historical Detention Snapshots (March 2024)
- ✅ Book-In Statistics (Oct 2018 - Feb 2026)

### 2. Cross-Reference Analysis Completed
- ✅ Compared TRAC data with ICE Stats (FY26)
- ✅ Identified facility classification discrepancies
- ✅ Documented missing facilities in each dataset
- ✅ Created structured JSON data exports

### 3. Critical Discrepancies Identified
- ⚠️ **3 major discrepancies** between TRAC and ICE Stats
- ⚠️ **4 I-4 counties** missing from both datasets
- ⚠️ **Type classification mismatch** for Pinellas County Jail

---

## 📊 Key Findings

### Florida Detention Surge

| Metric | March 2024 | February 2026 | Change |
|--------|------------|---------------|--------|
| State Population | 1,385 | 5,231 | **+278%** |
| National Rank | - | 4th | - |
| I-4 Corridor Pop. | ~200 est. | 303 | +52% |

### Facility Discrepancies

| Facility | TRAC | ICE Stats | Issue |
|----------|------|-----------|-------|
| Pinellas County Jail | IGSA | USMS IGA | Type mismatch |
| Orange County Jail (FL) | Not listed | Listed | Missing from TRAC |
| Orlando ICE Processing Center | Listed | Not listed | Missing from ICE Stats |
| Hillsborough County Jail | IGSA | IGSA | ✓ Match |

### I-4 Corridor Representation

**TRAC Shows (Feb 2026):**
- Hillsborough County Jail: 132 detainees
- Orlando ICE Processing Center: 167 detainees
- Pinellas County Jail: 4 detainees
- **Total: 303 detainees**

**Missing from TRAC:**
- Polk County
- Seminole County
- Volusia County
- Osceola County (confirmed historical activity)

---

## 🔍 Deep Analysis Results

### 1. Contract Structure Insights

**IGSA vs USMS IGA:**
- TRAC shows Pinellas as IGSA (direct ICE-county contract)
- ICE Stats shows Pinellas as USMS IGA (ICE uses US Marshals contract)
- **Implication:** USMS IGA route reduces public transparency

### 2. Population Distribution

**Florida ICE Detention by Facility Type (TRAC):**
- IGSA facilities: 971 detainees (29.6%)
- STATE facilities: 871 detainees (26.5%)
- CDF facilities: 681 detainees (20.7%)
- SPC facilities: 595 detainees (18.1%)
- Other: 170 detainees (5.2%)

### 3. Removal Statistics

**Florida Removals (through Feb 2024):**
- Total: 169,338
- National rank: 6th
- No criminal conviction: 39%
- Average processing time: Data not available

---

## 📁 Files Created

| File | Purpose | Size |
|------|---------|------|
| `trac_florida_analysis.py` | Analysis script | 5.6 KB |
| `trac_florida_analysis.json` | Basic extraction | 1.8 KB |
| `trac_florida_detailed.json` | Detailed JSON data | 3.2 KB |
| `TRAC_ICE_CROSS_REFERENCE_ANALYSIS.md` | Cross-reference report | 8.5 KB |
| `TRAC_REMOVALS_FLORIDA_ANALYSIS.md` | Removals analysis | 4.0 KB |
| `TRAC_INVESTIGATION_SUMMARY_2026-02-27.md` | This summary | 4.1 KB |

---

## 🚨 Issues Requiring Follow-Up

### High Priority

1. **Pinellas County Jail Type Discrepancy**
   - Why does TRAC show IGSA but ICE Stats show USMS IGA?
   - FOIA response expected March 10 should clarify
   - May indicate contract routing for transparency avoidance

2. **Missing Orange County Jail from TRAC**
   - ICE Stats shows it as active USMS IGA facility
   - TRAC snapshot may have missed it
   - Population may be undercounted in TRAC

3. **Orlando ICE Processing Center Missing from ICE Stats**
   - TRAC shows 167 detainees
   - Not in official ICE facility list
   - Possible data collection methodology difference

### Medium Priority

4. **Osceola County Absence**
   - Historical IGA rate ($35/day) confirms activity
   - Not in TRAC or ICE Stats facility lists
   - May indicate underreporting or alternative routing

5. **278% Population Growth**
   - Why did Florida detention surge so dramatically?
   - CBP vs ICE arrest ratios shifting?
   - Processing bottlenecks?

---

## 📈 TRAC Data Value Assessment

### Strengths ✅
- Independent, non-partisan source
- Monthly snapshots available
- Facility-level detail
- Historical trend data
- Free public access

### Limitations ❌
- No contract rate data
- No financial information
- Lag time in updates (Feb 5 snapshot)
- State-level filtering limited
- No IGA terms or conditions

### Best Used For:
- Validating ICE official statistics
- Tracking population trends
- Identifying facility utilization
- Cross-referencing facility types
- Historical comparison baseline

### Not Useful For:
- Contract rate analysis (need FOIA)
- 287(g) program details (need FOIA)
- Per-detainee costs (need financial records)
- County budget impact (need local records)

---

## 🎯 Next Steps

### Immediate (This Week)

1. **Monitor TRAC for updates** - New data expected monthly
2. **Document discrepancies** for FOIA follow-up questions
3. **Prepare comparison questions** for county PRR responses

### When FOIA Responses Arrive (March 10-25)

1. **Validate TRAC findings** against FOIA contract documents
2. **Resolve Pinellas type discrepancy** with actual contract
3. **Confirm Orange County facility** status and type
4. **Cross-reference IGA rates** with TRAC population data

### Future Analysis

1. **Build historical trend** from TRAC monthly data
2. **Compare I-4 corridor** to other Florida regions
3. **Analyze detention-to-removal timeline** when data available
4. **Create predictive model** for capacity utilization

---

## 📚 TRAC Resources Used

| Tool | URL | Data |
|------|-----|------|
| Quick Facts | /immigration/quickfacts/detention.html | Current snapshot |
| Facilities | /immigration/detentionstats/facilities.html | All facilities |
| Removals | /phptools/immigration/remove/ | Deportation records |
| Detention History | /phptools/immigration/newdetention/ | Monthly snapshots |
| Book-Ins | /immigration/detentionstats/book_in_agen_program_table.html | Monthly admissions |

---

## 🔗 Integration with Existing Investigation

This TRAC analysis integrates with:

- **Existing Files:**
  - `FY26_detentionStats_02122026.xlsx` - ICE official stats
  - `i4_facilities_all_years.json` - Historical facility data
  - `IGA_RATE_ANALYSIS_DEEP_DIVE_2026-02-27.md` - Rate comparison

- **Pending FOIA:**
  - Hillsborough County Sheriff (PRR P390162-022326)
  - Seminole County Sheriff (PRR R008264-022326)
  - Volusia County Sheriff (PRR R052454-022226)
  - Orange County Corrections (PRR 1587404)
  - GSA property assessments (FOIA 2026-FOI-01240)

---

## 📝 Conclusion

TRAC data provides valuable independent validation of ICE detention statistics. The identified discrepancies—particularly the Pinellas County Jail type mismatch and missing facilities from both datasets—warrant investigation through our pending FOIA requests.

The 278% growth in Florida's ICE detention population (March 2024 → February 2026) is significant and may indicate policy changes, increased arrivals, or processing bottlenecks that should be monitored.

**Overall Assessment:** TRAC data successfully integrated and provides actionable insights for the I-4 corridor investigation.
