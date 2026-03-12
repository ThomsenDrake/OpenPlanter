# Next Steps: Work to Complete While Awaiting FOIA Results

**Generated:** February 27, 2026
**FOIA Response Window:** March 10 - March 25, 2026 (first wave)
**Investigation Status:** Analysis Phase - Awaiting External Data

---

## Executive Summary

While 5 FOIA/PRR requests are pending (responses expected March 10-25), substantial work can proceed:

- **11 pending FOIA requests** should be submitted now
- **Public records research** can fill gaps without FOIA
- **Deep analysis** of existing documents can yield new insights
- **Data preparation** can accelerate FOIA response processing
- **External research** can expand context and sources

---

## PRIORITY 1: Submit Remaining FOIA Requests (Week of Feb 27)

### State Law PRR (2 counties not yet submitted)

| Agency | Contact | Request | Expected Time |
|--------|---------|---------|---------------|
| Pinellas County Sheriff's Office | (727) 582-6200 | IGSA + 287(g) + financial + capacity | 10-30 days |
| Polk County Sheriff's Office | (863) 298-6200 | IGSA + 287(g) + financial + capacity | 10-30 days |

**Action Required:** Draft and submit these PRRs immediately. They will return data in the same timeframe as the already-submitted requests.

### Federal FOIA Requests (5 TIER 1 not yet submitted)

| Agency | Target Data | Expected Time | Success Likelihood |
|--------|-------------|---------------|-------------------|
| ICE ERO | Facility codes for I-4 corridor | 20-30 days | 95% |
| ICE 287(g) Program | MOA amendments + compliance reports | 30-45 days | 85% |
| ICE ODO | Inspection reports 2020-2026 | 30-45 days | 80% |
| ICE Procurement | IGSA contracts + amendments + rates | 30-45 days | HIGH (backup) |
| ICE ERO | Population data aggregate 2019-2026 | 30-60 days | 70% |

**Action Required:** Draft and submit these federal FOIA requests. Use standard ICE FOIA portal.

---

## PRIORITY 2: Public Records Research (No FOIA Required)

### A. County Budget Documents

**What to Search:**
- County commission meeting minutes for ICE-related budget items
- Sheriff's office annual reports
- Budget line items for "federal reimbursement" or "detention services"
- Capital improvement plans for jail expansions

**Target Counties:**
- Hillsborough County (budgets, BCC minutes)
- Pinellas County (budgets, BCC minutes)
- Orange County (budgets, BCC minutes)
- Polk County (budgets, BCC minutes)
- Seminole County (budgets, BCC minutes)
- Volusia County (budgets, BCC minutes)

**Expected Findings:**
- Reimbursement revenue from ICE
- Bed allocation decisions
- Facility expansion/improvement related to ICE

### B. News Archive Research

**Search Terms:**
- "ICE detention" + [county name] + 2020-2026
- "287(g)" + [county name] + 2020-2026
- "immigration detention" + "I-4" + Florida
- "Orlando ICE Processing Center"
- "Hillsborough County Jail ICE" + Orient Road

**News Sources to Check:**
- Tampa Bay Times
- Orlando Sentinel
- Daytona Beach News-Journal
- Lakeland Ledger
- Florida Phoenix
- Miami Herald (state political coverage)

### C. Florida Legislature & State Agency Records

**What to Check:**
- Florida Senate/House committee hearings on immigration
- Florida Department of Corrections reports
- Florida Sheriff's Association statements
- Governor's office press releases on 287(g)

### D. Federal Government Public Sources

**Already Available:**
- TRAC Immigration database (Syracuse University)
- ICE detention statistics (already analyzed)
- ICE 287(g) program participant list (public)
- USMS detention facility directory (partial)

**Additional to Research:**
- GSA procurement forecasts
- Federal Register notices for ICE facility awards
- Congressional testimony about ICE capacity

---

## PRIORITY 3: Deep Analysis of Existing Documents

### A. USMS Agreement Documents 2022 (Already OCR'd)

**File:** `USMS-Agreement-Documents-2022_OCR.md` (91KB)

**Analysis Tasks:**
1. Extract all financial terms (rates, billing procedures, cost allocations)
2. Map facility codes and cross-reference with ICE stats
3. Identify amendments and their dates
4. Document PREA compliance requirements
5. Note COVID-19 protocols (may explain FY2023 gaps)
6. Extract ICE ORSA MOU details (pages 67-73)

### B. IGA Transcription Documents

**Files Available:**
- `IGA-Florida-Hillsborough-County_Manual-Visual-Transcription.md`
- `IGA-Florida-John-E-Polk-Correctional-Facility_Manual-Visual-Transcription.md`
- `IGA-Florida-Osceola-County-Sheriffs-Department_Manual-Visual-Transcription.md`
- `IGA-Florida-Pinellas-County-Sheriffs-Office_Manual-Visual-Transcription.md`

**Analysis Tasks:**
1. Cross-reference terms across all four IGA documents
2. Identify standard clauses vs. county-specific variations
3. Extract all financial terms and compare rates
4. Document capacity allocations by county
5. Note any termination clauses or renewal terms

### C. ICE Detention Statistics (FY2020-FY2026)

**COMPLETED:** Deep dive analysis of column metrics (see `ICE_METRICS_DECODE_DEEP_DIVE_2026-02-27.md`)

**Status:** PARTIAL - Official definitions required
- **Completed:** Pattern analysis and hypothesis generation
- **Result:** High confidence that Metric 1 = population/utilization, Metric 2 = time/cumulative count
- **Missing:** Official ICE data dictionary with column definitions

**Remaining Tasks:**
1. ~~Decode the column metrics (metric_1 through metric_6)~~ ✅ PARTIAL
2. Submit FOIA request for ICE data dictionary (ADDED TO HIGH PRIORITY)
3. Calculate year-over-year growth rates (blocked without official definitions)
4. Correlate with national ICE detention trends
5. Identify capacity utilization patterns

**Action Required:** Submit FOIA request #1 (see `foia_summary.md` - added as URGENT priority)
3. Correlate with national ICE detention trends
4. Identify seasonal patterns

---

## PRIORITY 4: Data Preparation for FOIA Response Processing

### A. Build Processing Scripts

**Create:**
1. `process_igsa_response.py` - Parse IGSA contract PDFs
2. `process_287g_response.py` - Extract MOA details
3. `process_financial_response.py` - Analyze reimbursement data
4. `process_inspection_response.py` - Extract ODO findings

### B. Create Analysis Templates

**Prepare:**
1. Contract comparison matrix (rates, terms, capacity)
2. Financial analysis worksheet (revenue by year by county)
3. Compliance tracking spreadsheet (ODO findings by facility)
4. Entity linkage database schema

### C. Build Entity Map

**Map Relationships:**
- Sheriffs → Facilities → Contracts
- ICE officials → Facilities → Inspections
- Counties → Budget items → Reimbursements
- Facilities → Population data → Trends

---

## PRIORITY 5: External Research Expansion

### A. Academic & NGO Sources

**Organizations with Relevant Research:**
- TRAC Immigration (Syracuse University) - already referenced
- Detention Watch Network
- National Immigrant Justice Center
- Southern Poverty Law Center
- Florida Immigrant Coalition

**Search for:**
- Published reports on Florida ICE detention
- Facility conditions reports
- Legal filings mentioning I-4 corridor facilities

### B. Legal Research

**Check:**
- Court filings in Pacer (for lawsuits involving these facilities)
- ACLU litigation database
- Florida court dockets for immigration-related cases
- Federal court cases challenging 287(g) agreements

### C. Social Media & Public Statements

**Monitor:**
- Sheriff's office social media accounts
- County commission meeting videos
- ICE press releases
- Elected official statements on immigration

---

## PRIORITY 6: Investigate Specific Anomalies

### A. Orange County Jail FY2023 Gap

**Known:** Orange disappeared from ICE stats in FY2023, returned FY2024 with "(FL)" suffix

**Research Tasks:**
1. Search Orange County news archives for 2022-2023
2. Check Orange County Commission meeting minutes
3. Look for contract disputes or operational pauses
4. Research what "(FL)" suffix designation means

### B. Hillsborough New Facility Timing

**Known:** Orient Road Jail began ICE detention FY2026, 7 months after 287(g) signing

**Research Tasks:**
1. Check Hillsborough County Commission records for IGSA approval
2. Search Tampa Bay Times for coverage
3. Identify facility preparation timeline
4. Compare to other facilities' startup timelines

### C. Missing 287(g) Facilities in ICE Stats

**Known:** 5 facilities have 287(g) but no ICE detention stats

**Hypothesis:** Book-and-release model, transfer to other facilities

**Research Tasks:**
1. Search for transfer documentation
2. Check TRAC data for transfer patterns
3. Research book-and-release standard practices
4. Identify destination facilities

### D. Orlando ICE Processing Center

**Known:** Planned 1,500-bed facility at Transport Drive

**Research Tasks:**
1. Identify property owner/developer
2. Check Orange County zoning records
3. Search for permit applications
4. Track opposition efforts and statements
5. Monitor ICE facility tour reports

---

## PRIORITY 7: Follow-Up on Submitted Requests

### Week of March 3-9, 2026

- [ ] Check status of GSA FOIA (2026-FOI-01240)
- [ ] Check status of Hillsborough PRR (P390162-022326)
- [ ] Check status of Seminole PRR (R008264-022326)
- [ ] Check status of Volusia PRR (R052454-022226)
- [ ] Check status of Orange PRR (1587404)

### Week of March 10-16, 2026

- **EXPECTED:** First wave of county PRR responses
- [ ] Process returned documents immediately
- [ ] Update investigation database
- [ ] Identify any follow-up requests needed

---

## Summary: Immediate Action Items

| Priority | Action | Time Required | Deadline |
|----------|--------|---------------|----------|
| 1 | Submit Pinellas & Polk PRRs | 2 hours | Feb 28 |
| 2 | Submit 5 federal FOIA requests | 3 hours | Mar 1 |
| 3 | County budget research | 4 hours | Mar 5 |
| 4 | Deep analysis of IGA documents | 4 hours | Mar 7 |
| 5 | News archive research | 4 hours | Mar 10 |
| 6 | Build FOIA response processing scripts | 3 hours | Mar 10 |

**Total Estimated Effort:** ~20 hours of work that can proceed without FOIA responses

---

## Expected Deliverables by March 10

1. **Updated FOIA Tracking:** All 16 requests submitted and tracked
2. **Budget Analysis:** County-level ICE-related revenue identified
3. **IGA Comparative Analysis:** Side-by-side contract terms
4. **News Timeline:** Historical coverage compiled
5. **Processing Scripts:** Ready for incoming FOIA data
6. **Anomaly Investigations:** Preliminary findings on gaps and patterns

---

*This document will be updated as tasks are completed and new opportunities identified.*
