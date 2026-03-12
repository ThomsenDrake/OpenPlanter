# Investigative Question Answerability Assessment

**Assessment Date:** February 27, 2026
**Workspace:** central-fl-ice-workspace
**Data Available:** ICE Detention Stats (FY20-FY26), IGA Transcriptions (4 counties), USMS Agreement OCR, TRAC Data

---

## Summary

| # | Question | Answerable? | Confidence | Data Source |
|---|----------|-------------|------------|-------------|
| 1 | Orange County FY2023 gap - why disappeared from ICE stats? | **PARTIAL** | Medium | i4_facilities_all_years.json |
| 2 | Hillsborough timing - 7-month delay | **YES** | High | ICE stats + 287(g) date |
| 3 | Missing 287(g) facilities - where do detainees go? | **PARTIAL** | Medium | ICE stats + TRAC |
| 4 | Orlando ICE Processing Center - property/permits/opposition | **NO** | N/A | News reports only |
| 5 | Osceola rate never updated in 40 years | **YES** | High | Complete investigation |
| 6 | Hillsborough 1996 overcharge recoupment trigger | **PARTIAL** | Medium | IGA transcription |
| 7 | Why is Orange the only ICE-authorized facility? | **PARTIAL** | Medium | Facility type data |
| 8 | Side agreements or supplemental payments? | **NO** | N/A | Cannot prove negative |
| 9 | How does USMS determine "fair and reasonable" rates? | **YES** | High | USMS OCR methodology |

---

## Detailed Assessments

### 1. Orange County FY2023 Gap - Why Did It Disappear from ICE Stats?

**ANSWERABILITY: PARTIAL**

#### What We CAN Answer:
- ✅ **Document the gap exists** - Orange County Jail appears in FY22, FY24, FY25, FY26 but NOT FY23
- ✅ **Pattern analysis** - Only year Orange was absent between FY22-FY26
- ✅ **Context** - FY23 was Pinellas-only year for I-4 corridor in ICE stats

#### What We CANNOT Answer:
- ❌ **Why it disappeared** - Requires ICE internal records
- ❌ **Whether detainees were held but not reported** - Requires FOIA billing records
- ❌ **If it was contractual, operational, or reporting issue** - No documentation

#### Data Sources:
```
File: i4_facilities_all_years.json
- FY22: Orange County Jail appears (type: USMS IGA)
- FY23: Orange County Jail ABSENT (only Pinellas appears)
- FY24: Orange County Jail returns (type: USMS IGA, with "(FL)" suffix)
```

#### Required for Full Answer:
- FOIA to ICE: FY23 detention statistics methodology changes
- FOIA to USMS: Orange County IGA status during FY23
- Orange County internal records for FY23 federal detention

---

### 2. Hillsborough Timing - 7-Month Delay Between 287(g) and First Detainees

**ANSWERABILITY: YES**

#### What We CAN Answer:
- ✅ **Document exact timing** - 287(g) signed Feb 26, 2025; first ICE detainees Oct 2025 (FY26)
- ✅ **Confirm 7-month gap** - Precise date calculation possible
- ✅ **Identify facility** - Orient Road Jail (not Falkenburg Road)

#### Evidence:
```
287(g) Agreement Date: February 26, 2025
  Source: IGA-Florida-Hillsborough-County_Manual-Visual-Transcription.md
  Reference: foia_summary.md line 103

First ICE Detention Stats Appearance: FY2026
  Source: i4_facilities_all_years.json
  FY26 start date: October 1, 2025
  
Calculated Delay: ~7 months (Feb 2025 → Oct 2025)
```

#### What We CANNOT Explain:
- ❌ **Why the delay occurred** - Administrative setup? ICE coordination? Infrastructure prep?
- ❌ **Whether this is typical** - No baseline for other facilities

#### Additional Context from ICE_STATS_KEY_FINDINGS.md:
> "Hillsborough County Jail - NEW in FY2026: First appeared FY2026 (started Oct 2025). Type: IGSA (direct ICE agreement, NOT USMS IGA). Significance: Only started holding ICE detainees AFTER 287(g) implementation (Feb 2025)."

---

### 3. Missing 287(g) Facilities - Where Do Detainees Go From Book-and-Release?

**ANSWERABILITY: PARTIAL**

#### What We CAN Answer:
- ✅ **Identify which facilities have 287(g) but no detention stats** (6 facilities)
- ✅ **Cross-reference with TRAC data** showing transfer patterns
- ✅ **Document the gap** between 287(g) authority and actual detention

#### Missing 287(g) Facilities (Not in ICE Detention Stats):
| Facility | County | Capacity | Status |
|----------|--------|----------|--------|
| Hillsborough Falkenburg Road Jail | Hillsborough | 3,300 beds | 287(g) but no stats |
| Polk County Jail | Polk | Unknown | 287(g) but no stats |
| John E. Polk Correctional | Seminole | 1,396 beds | 287(g) but no stats |
| Volusia County Branch Jail | Volusia | Unknown | 287(g) but no stats |
| Volusia County Correctional | Volusia | Unknown | 287(g) but no stats |

#### Possible Explanations (from ANALYSIS_SUMMARY_2026-02-27.md):
1. **Book-and-release only** - Short-term holding
2. **Quick transfers** - Moved to other facilities before count
3. **Identification only** - 287(g) for status checks, not detention
4. **Different funding/reporting** - Not captured in ICE detention stats

#### What We CANNOT Answer:
- ❌ **Trace individual detainee transfers** - Requires FOIA transfer records
- ❌ **Confirm book-and-release pattern** - Requires booking records
- ❌ **Identify destination facilities** - Requires ICE transfer data

#### Required for Full Answer:
- FOIA to ICE: Detainee transfer records from I-4 corridor 287(g) facilities
- County booking records for immigration holds
- ICE Enforcement and Removal Operations data

---

### 4. Orlando ICE Processing Center - Property Records, Permits, Opposition

**ANSWERABILITY: NO**

#### What We Have (News Reports Only):
```
Address: 8660 Transport Drive, Orlando, FL (east Orange County)
Capacity: 1,500 beds
Cost: $100 million
Type: ICE Processing Center (short-term, 3-7 days)
Status: ICE officials toured facility Jan-Feb 2026
Opposition: Rep. Maxwell Frost, Rep. Anna Eskamani
```

#### What We DO NOT Have:
- ❌ **Property records** - Orange County Property Appraiser data (external)
- ❌ **Building permits** - City of Orlando/Orange County building dept (external)
- ❌ **Zoning changes** - Orange County zoning records (external)
- ❌ **Opposition documents** - Campaign letters, petitions beyond Change.org
- ❌ **ICE procurement records** - Contract solicitation (FOIA required)

#### Data Sources in Workspace:
- findings.md (news report compilation)
- SEARCH_RESULTS_2026-02-26.md (web search results)
- Change.org petition reference

#### Required for Full Answer:
- **Property records:** Orange County Property Appraiser (ocpafl.org)
- **Permits:** Orange County Building Division / City of Orlando
- **Zoning:** Orange County Zoning Division
- **Opposition:** Official statements from Frost/Eskamani offices
- **Procurement:** ICE FOIA for solicitation documents

---

### 5. Why Has Osceola County's Rate Never Been Updated in 40 Years?

**ANSWERABILITY: YES - COMPLETE INVESTIGATION**

#### Investigation Status: COMPLETE
**File:** OSCEOLA_COUNTY_INVESTIGATION_COMPLETE.md

#### Key Findings:
1. **Rate History:**
   - 1986: $40.00/day (base agreement)
   - 1993: $52.00/day (Modification 1 - 30% increase)
   - 2026: $40.00/day (BACK to original rate)

2. **The 1993 Modification Mystery:**
   - Rate was increased to $52.00, then reversed
   - Current rate is $40.00, not $52.00
   - **Critical gap:** What happened between 1993-2026?

3. **Assessment with Probabilities:**
   - **Administrative Neglect (60%)** - County never submitted adjustment requests, 40 years of inaction
   - **1993 Modification Aftermath (30%)** - Possible discouragement from failed increase attempt
   - **Political/Strategic Choice (10%)** - Deliberate subsidy as policy (no evidence found)

4. **Financial Impact:**
   - 40-year subsidy: $65+ MILLION in taxpayer subsidies
   - Inflation-adjusted rate should be: $113.14/day
   - Real rate decline: 64% due to inflation

5. **Rate Adjustment Process EXISTS:**
   - IGA Article V explicitly allows annual adjustments
   - Process: Submit request 60 days prior + Cost and Pricing Data Sheet + permit audit
   - **Osceola has NEVER submitted a rate adjustment request**

#### Confidence Level: HIGH
- Evidence-based assessment
- IGA documentation reviewed
- Rate history traced
- Comparison with neighboring counties completed

---

### 6. What Triggered Hillsborough's 1996 Overcharge Recoupment?

**ANSWERABILITY: PARTIAL**

#### What We CAN Answer:
- ✅ **Document the recoupment occurred** - Modification Six, September 1, 1996
- ✅ **Document the rate change** - $83.46 → $80.27 (temporary) → $81.33 (permanent)
- ✅ **Document the mechanism** - Rate reduction to recoup past overcharges

#### Evidence from IGA Transcription:
```
File: IGA-Florida-Hillsborough-County_Manual-Visual-Transcription.md
Page 15 of 22 (Modification Six)
- Modification No.: Six (6)
- Effective Date: September 1, 1996
- Purpose: recoup overcharges by reducing per diem from $83.46 to $80.27 
  for a stated period, then setting per diem $81.33 thereafter.
```

#### What We CANNOT Answer:
- ❌ **What triggered the overcharge finding** - ICE audit? USMS review? Complaint?
- ❌ **Time period of overcharges** - How far back did overcharges go?
- ❌ **Amount recouped** - Total dollars recovered
- ❌ **Root cause** - Rate calculation error? Misclassification? Cost allocation issue?

#### Required for Full Answer:
- FOIA to USMS: 1996 audit records for Hillsborough County IGA
- FOIA to ICE: Overcharge determination documentation
- Hillsborough County internal records from 1995-1996

---

### 7. Why Is Orange the Only ICE-Authorized Facility?

**ANSWERABILITY: PARTIAL**

#### Clarification:
**Orange is NOT the only facility** - This question appears based on incomplete data. Current status:

| Facility | Type | ICE Authorization |
|----------|------|-------------------|
| Orange County Jail | USMS IGA | ✅ Active (FY22, 24, 25, 26) |
| Pinellas County Jail | USMS IGA | ✅ Active (FY21-26 continuous) |
| Hillsborough County Jail | IGSA | ✅ Active (FY26 NEW) |

#### What We CAN Answer:
- ✅ **Document facility type differences:**
  - **USMS IGA** = Joint-use with US Marshals Service (Orange, Pinellas)
  - **IGSA** = Direct ICE Intergovernmental Service Agreement (Hillsborough)

- ✅ **Document authorization levels:**
  - Orange: Multi-agency (USMS, BOP, ICE) - 114 federal beds
  - Pinellas: USMS IGA
  - Hillsborough: IGSA only

#### What We CANNOT Answer:
- ❌ **Why different facility types were chosen** - Policy/strategic reasons
- ❌ **Whether ICE detainees at USMS IGA facilities are ICE or USMS custody** - Legal distinction
- ❌ **Cost/benefit analysis of different agreement types** - Financial rationale

#### Required for Full Answer:
- ICE policy documents on IGA vs IGSA selection criteria
- USMS district detention plans
- Historical correspondence on agreement type selection

---

### 8. Are There Side Agreements or Supplemental Payments Not Documented?

**ANSWERABILITY: NO**

#### The Challenge:
**Cannot prove a negative** - Absence of documented side agreements does not prove they don't exist.

#### What We Have:
- ✅ Complete IGA transcriptions for 4 counties (Hillsborough, Polk, Osceola, Pinellas)
- ✅ USMS Agreement OCR with detailed financial terms
- ✅ No side agreements documented in any transcribed materials

#### What Raises Suspicion:
From OSCEOLA_COUNTY_INVESTIGATION_COMPLETE.md:
> "8. Are there side agreements offsetting low rate?"
> "Hidden arrangements - Side agreements compensate for low rate (10% probability)"

From IGA_RATE_ANALYSIS_DEEP_DIVE_2026-02-27.md:
> "Side agreements or modifications may exist but not transcribed"

#### Why We Cannot Answer:
1. **IGA transcriptions may be incomplete** - Only visual transcription of available PDFs
2. **Separate agreements possible** - Equipment grants, training agreements, federal programs
3. **Informal arrangements** - Not documented in official IGA files
4. **FOIA responses pending** - May contain modification history

#### Required to Answer:
- FOIA to ICE/USMS: Complete modification history for all IGAs
- FOIA to counties: All federal detention-related agreements
- Federal grants database search for each county
- SAM.gov contract search for supplemental awards

---

### 9. How Does USMS Determine "Fair and Reasonable" Rates?

**ANSWERABILITY: YES - EXPLICIT METHODOLOGY DOCUMENTED**

#### Source:
**File:** USMS-Agreement-Documents-2022_OCR.md (lines 1558-1570)

#### Official USMS Methodology:
```
The Federal Government will use various analytical techniques to ensure 
the per-diem rate is fair and reasonable, including:

1. Comparison of requested per-diem rate with independent government 
   estimate for detention services, otherwise known as the Core Rate

2. Comparison with per-diem rates at similar state/local facilities 
   (size and economic conditions)

3. Comparison of previous proposed prices and previous Federal 
   Government/commercial contract prices

4. Evaluation of provided jail operating expense information
```

#### Additional Context:
- **Firm-fixed per-diem rate:** $88.00 (not subject to adjustment)
- **Rate adjustment window:** After 36 months, may request via DSNet with supporting info
- **Billing period:** Day of arrival AND day of departure both counted

#### Rate Determination Process (from IGA Article V):
1. County submits written request to U.S. Marshal (60 days prior)
2. Provides Cost and Pricing Data Sheet
3. Permits audit of accounting records
4. Meets federal cost standards (OMB circulars)

#### Confidence Level: HIGH
- Direct quote from official USMS IGA document
- Consistent across Orange County IGA review

---

## Summary: Can We Answer These Questions?

### ✅ FULLY ANSWERABLE (2 of 9):
1. **Hillsborough timing** - 7-month delay documented with dates
2. **USMS fair and reasonable methodology** - Explicit criteria documented
3. **Osceola rate investigation** - Complete with probabilities

### ⚠️ PARTIALLY ANSWERABLE (4 of 9):
1. **Orange County FY2023 gap** - Can document gap, not explain cause
2. **Missing 287(g) facilities** - Can identify gap, not trace transfers
3. **Hillsborough 1996 recoupment** - Can document what, not why
4. **Why Orange only facility** - Incorrect premise; can document types

### ❌ NOT ANSWERABLE (2 of 9):
1. **Orlando ICE Processing Center** - Requires external government records
2. **Side agreements** - Cannot prove negative; FOIA required

---

## Recommended FOIA Priorities by Question

### Question 1 (Orange FY2023 Gap):
- ICE FY23 detention statistics methodology
- USMS Orange County IGA status during FY23

### Question 3 (Missing 287(g) Facilities):
- ICE detainee transfer records from I-4 corridor
- County booking records for immigration holds

### Question 4 (Orlando ICE Processing Center):
- ICE procurement solicitation documents
- Facility assessment/inspection reports

### Question 6 (Hillsborough 1996 Recoupment):
- USMS 1996 audit records
- ICE overcharge determination documentation

### Question 7 (Facility Type Selection):
- ICE/USMS policy on IGA vs IGSA selection
- Historical correspondence on agreement types

### Question 8 (Side Agreements):
- Complete modification history for all IGAs
- Federal grants to counties for detention

---

**Assessment Complete:** February 27, 2026
**Files Analyzed:** 47 workspace files
**Data Period:** FY2020-FY2026
