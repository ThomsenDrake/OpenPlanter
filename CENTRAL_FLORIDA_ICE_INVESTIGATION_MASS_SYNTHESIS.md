# Central Florida ICE Investigation: Mass Analysis & Synthesis
## Comprehensive State-of-the-Investigation Report

**Report Date:** March 12, 2026  
**Scope:** ICE detention operations along Florida's Interstate 4 corridor (Tampa Bay to Daytona Beach)  
**Investigation Duration:** ~3 weeks (February 20 – March 12, 2026)  
**Overall Completion:** ~50%  
**Classification:** Working investigative synthesis — not for public distribution

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [Investigation Architecture](#investigation-architecture)
3. [Facilities & Operations Map](#facilities--operations-map)
4. [Financial Crisis Analysis](#financial-crisis-analysis)
5. [Legal & Policy Framework](#legal--policy-framework)
6. [Key Pressure Points](#key-pressure-points)
7. [Data Sources & Cross-Reference Findings](#data-sources--cross-reference-findings)
8. [Surveillance & Technology](#surveillance--technology)
9. [Public Records & FOIA Campaign](#public-records--foia-campaign)
10. [Entity Resolution & Procurement Intelligence](#entity-resolution--procurement-intelligence)
11. [Open Questions & Contradictions](#open-questions--contradictions)
12. [Parallel Investigation: Scout Microtransit](#parallel-investigation-scout-microtransit)
13. [Methodology & Limitations](#methodology--limitations)
14. [Master File Index](#master-file-index)

---

## 1. EXECUTIVE SUMMARY

This investigation has mapped the Trump administration's ICE detention expansion across Florida's I-4 corridor — a six-county region from Tampa to Daytona Beach — and identified structural vulnerabilities, financial unsustainability, legal over-compliance, and transparency gaps that create actionable pressure points for public accountability.

### The Core Finding

**County governments along the I-4 corridor are systematically subsidizing federal immigration enforcement at a collective loss of $7.3 million per year**, with per-diem rates that haven't been updated in 15–40 years, while Florida's ICE detention population has surged 278% since March 2024 (from 1,385 to 5,231 detainees). This creates a structural contradiction: the federal government is expanding enforcement capacity while refusing to pay the actual costs, forcing local taxpayers to absorb the deficit.

### Top 5 Findings (Confidence: HIGH)

| # | Finding | Evidence Strength | Key Source |
|---|---------|-------------------|------------|
| 1 | Orange County loses $92/day per ICE detainee ($88 reimbursement vs $180 actual cost), facing a March 13, 2026 IGSA termination deadline | **CONFIRMED** — Demings letters, county records | PSL-resources, county communications |
| 2 | The planned Orlando ICE Processing Center at 8660 Transport Drive (1,500 beds, $100M) is owned by Beachline Logistics Center LLC / TPA Group (Atlanta) — a commercial real estate developer with zero detention history | **CONFIRMED** — Property records, LoopNet, corporate filings | ORLANDO_ICE_PROCESSING_CENTER_OWNERSHIP_INVESTIGATION |
| 3 | All 67 Florida counties signed 287(g) Task Force Model agreements on Feb 26, 2025 — far beyond legal requirements (only jail operators required, and only narrowest WSO model) | **CONFIRMED** — ICE MOAs, PSL-resources legal analysis | IGA transcriptions, PSL-resources |
| 4 | ICE was operating a "rebooking" practice at Orange County Jail — removing detainees every 72 hours and rebooking under new numbers to circumvent legal hold limits; practice ended March 1, 2026 | **CONFIRMED** — County communications | Demings Letter #2, PSL-resources |
| 5 | BOAs (Basic Ordering Agreements) are 100% voluntary under federal law (FAR § 16.703, Printz v. US) despite Orange County officials presenting them as "mandatory" if IGSA terminates | **CONFIRMED** — Legal analysis of FAR, anti-commandeering doctrine | BOA_MANDATE_INVESTIGATION.md |

### What We Don't Yet Know

- **Who will operate the Orlando Processing Center** (CoreCivic? GEO Group? New entrant?)
- **Whether the rebooking practice continues in other counties** beyond Orange
- **Transfer flow patterns** from 287(g)-only facilities to active detention sites
- **Why Orange County disappeared from ICE detention statistics in FY2023**
- **Osceola County's actual detainee population** (confirmed active but not in federal data)

---

## 2. INVESTIGATION ARCHITECTURE

### Data Sources Ingested (23 distinct sources)

| Category | Sources | Key Datasets |
|----------|---------|-------------|
| **Federal Detention Data** | ICE Detention Statistics (FY2020-FY2026), TRAC Immigration Tools | 7 annual XLSX files, 12 FL facilities in TRAC |
| **Federal Contracts** | FPDS via BLN, GSA records | 197 ICE FL contracts, $923.6M detention-related |
| **County Agreements** | USMS IGAs, IGSAs, BOAs (5 counties transcribed) | Rate histories 1983–2026, 287(g) MOAs |
| **FOIA/PRR Documents** | MuckRock (Polk, Sarasota, Walton, Broward), direct county PRRs | 16+ PDF agreements, 6,007 Clearview AI records |
| **Community Intelligence** | PSL-resources, public testimony | Demings letters, IGSA analysis, 287(g) legal briefing |
| **Government Meetings** | Orange County BCC (March 10, 2026) | Full transcripts, resolution text, public comment |
| **News & Media** | 10+ outlets (CFPM, Sentinel, Weekly, WESH, etc.) | ICE facility reporting, county policy coverage |
| **Property Records** | Orange County Appraiser, LoopNet, TPA Group filings | 8660 Transport Drive ownership chain |
| **Law Enforcement Records** | Seminole County UOF data (1,623 incidents), Clearview AI logs | OCSO facial recognition searches |

### Entity Resolution

**Entity Map:** 9 canonical entities resolved across datasets (primarily for Scout microtransit parallel investigation). For the ICE investigation, key entity resolution includes:

- **Facility name normalization** across TRAC, ICE Stats, USMS IGAs (e.g., "Orange County Jail" vs "Orange County Correctional Facility" vs facility code 4CM)
- **Contract type classification** — IGSA vs USMS IGA vs BOA vs 287(g) MOA, with documented mismatches between TRAC (classifies Pinellas as IGSA) and ICE Stats (classifies it as USMS IGA)
- **Vendor resolution** — GEO Group, G4S Secure Solutions, CoreCivic cross-referenced across FPDS contracts and facility operation records

### Canonical Document Hierarchy

| Level | Document | Purpose |
|-------|----------|---------|
| **Master** | `I4_CORRIDOR_MASTER_INVESTIGATION.md` | Single source of truth, contradiction register |
| **Status** | `INVESTIGATION_STATUS_INTEGRATED_2026-03-05.md` | Latest operational status |
| **Brief** | `QUICK_BRIEF_2026-03-05.md` | Decision-maker summary |
| **Deep Dives** | 12 topic-specific canonical documents | Detailed evidence and analysis |
| **Data** | 15+ JSON files | Structured data extractions |
| **Archive** | `archive/` directory | Superseded documents preserved |

---

## 3. FACILITIES & OPERATIONS MAP

### The Three-Tier Model

The investigation identified a **three-tier operational model** for ICE detention along the I-4 corridor:

#### Tier 1: Active Detention Nodes (3 facilities, ~400 detainees)

| Facility | County | Type | Population (Feb 2026) | Rate/Day | Annual Loss |
|----------|--------|------|----------------------|----------|-------------|
| Hillsborough Orient Road Jail | Hillsborough | IGSA | 132 | $101.06 | $3,803,329 |
| Orange County Jail | Orange | USMS IGA | ~100-142 | $88.00 | $3,358,000 |
| Pinellas County Jail | Pinellas | USMS IGA | 4 | $80.00 | $116,800 |

These are the **only I-4 corridor facilities that appear in ICE detention statistics** and actively hold ICE detainees for extended periods.

#### Tier 2: 287(g) Processing / Book-and-Release (5 facilities)

| Facility | County | Capacity | 287(g) Model | ICE Stats? |
|----------|--------|----------|--------------|-----------|
| Hillsborough Falkenburg | Hillsborough | 3,300 | Task Force + WSO | ❌ No |
| Polk County Jail | Polk | Unknown | Task Force | ❌ No |
| John E. Polk (Seminole) | Seminole | 1,396 | WSO (since 2010) | ❌ No |
| Volusia Branch Jail | Volusia | Unknown | 287(g) | ❌ No |
| Volusia Correctional | Volusia | Unknown | 287(g) | ❌ No |

**Operational hypothesis:** These facilities identify and screen individuals during booking under 287(g), issue ICE detainers, then **transfer** detainees to Tier 1 facilities for extended detention. They are ICE's **feeder network** but don't appear in detention statistics because they don't hold ICE detainees long-term.

**Evidence gap:** Transfer destination data not yet available. Pending FOIA (PENDING-010) would confirm.

#### Tier 3: Planned Expansion (1 facility, 1,500 beds)

| Facility | Status | Capacity | Target Date | Estimated Cost |
|----------|--------|----------|-------------|---------------|
| Orlando ICE Processing Center | Planned | 1,500 | November 2026 | $100M |

**Location:** 8660 Transport Drive, Orlando, FL 32832 (east Orange County, near Lake Nona / SR 528)  
**Owner:** Beachline Logistics Center LLC (TPA Group, Atlanta)  
**Building:** 439,945 SF Class A cross-dock warehouse, built 2024  
**Status:** ICE Senior Advisor David Venturella toured January 16, 2026; property listing removed from LoopNet February 2026 (possible deal pending)  
**Opposition:** Orange County BCC unanimously passed opposing resolution March 10, 2026 (symbolic — cannot legally block)

#### The TRAC Anomaly

TRAC Immigration data (Feb 5, 2026) lists the Orlando ICE Processing Center as **already operational** with **167 detainees** and a **150-bed guaranteed minimum** — classified as IGSA. However, ICE's own detention statistics **do not list this facility at all**. This is tracked as **Contradiction C-002** in the Master Investigation.

**Possible explanations:**
1. TRAC data reflects a facility that is partially operational but not yet in ICE's published statistics
2. TRAC may be conflating the planned facility with the existing Orange County Jail operations
3. ICE may be operating a non-public detention site in advance of the formal processing center
4. Data collection methodology difference between TRAC and ICE OIS

#### Counties Missing from Both Datasets

| County | TRAC | ICE Stats | Evidence of Activity |
|--------|------|-----------|---------------------|
| Polk | ❌ | ❌ | 43 ICE detainers, 200+ transfers, 7 ICE agreements on file |
| Seminole | ❌ | ❌ | Active 287(g) since 2010, $94/day USMS IGA, 1,396-bed facility |
| Volusia | ❌ | ❌ | 220 ICE detainees since 2025, 33 removal warrants |
| Osceola | ❌ | ❌ | **Active facility, $40/day rate (unchanged 40 years), confirmed ICE detainees 2025** |

---

## 4. FINANCIAL CRISIS ANALYSIS

### The $7.3 Million Taxpayer Subsidy

County jails along the I-4 corridor collectively lose **$7.3 million annually** on ICE detention operations:

```
Hillsborough County:  $3,803,329/year  (132 detainees × $78.94/day loss)
Orange County:        $3,358,000/year  (~100 detainees × $92.00/day loss)
Pinellas County:      $  116,800/year  (4 detainees × $80.00/day loss)
──────────────────────────────────────────────────────────────
TOTAL:                $7,278,129/year  (active Tier 1 facilities only)
```

**This does not include:**
- Osceola County ($140/day estimated loss per detainee, population unknown)
- Seminole County ($86/day estimated loss per detainee, population unknown)
- Tier 2 287(g) processing costs (staffing, booking, screening)

### Rate Stagnation: The Core Structural Problem

| Facility | Rate/Day | Last Updated | Years Stale | Inflation-Adjusted Value |
|----------|----------|-------------|-------------|------------------------|
| Hillsborough | $101.06 | 2005 | 21 years | ~$160 |
| Orange | $88.00 | 2011 | 15 years | ~$120 |
| Pinellas | $80.00 | Unknown | Unknown | Unknown |
| Seminole (J.E. Polk) | $56.71 | 2004 | 22 years | ~$95 |
| **Osceola** | **$40.00** | **1986** | **40 years** | **$113.14** |

**Key insight:** Every IGA contains a rate adjustment mechanism (Article V) allowing annual renegotiation after 12 months. **Osceola County has never exercised this right in 40 years**, representing an estimated **$65+ million in cumulative taxpayer subsidies** to the federal government.

### The Osceola Anomaly

Osceola County's $40/day rate is the most extreme case of administrative neglect in the investigation:

- **1986:** Base rate set at $40/day
- **1993:** Modification raised rate to $52/day
- **2026:** Rate is back at $40/day (reversal unexplained)
- **Current estimated cost:** ~$180/day (same as Orange County)
- **Per-detainee daily loss:** $140/day (52% MORE than Orange County's $92 loss)
- **40-year cumulative subsidy:** $65+ million
- **Rate adjustment requests filed:** ZERO

### The 278% Population Surge Without Rate Adjustments

| Period | Florida ICE Population | Change |
|--------|----------------------|--------|
| March 2024 | 1,385 | Baseline |
| February 2026 | 5,231 | **+278%** |

Despite this **nearly fourfold increase** in the Florida detention population, and **$75 billion in federal funding through 2029**, county per-diem rates remain frozen. Federal money flows to private contractors (GEO Group, G4S) while counties absorb unfunded mandates.

### Orange County IGSA Crisis Timeline

| Date | Event | Significance |
|------|-------|-------------|
| Aug 11, 2025 | County requests IGSA renegotiation | First formal challenge |
| Dec 22, 2025 | Demings Letter #1 to USMS | Documents $333,592+ deficit |
| Feb 3, 2026 | Demings caps detainees, ends rebooking | Operational countermeasure |
| Feb 13, 2026 | Demings Letter #2 — **March 13 deadline** | Formal ultimatum |
| Mar 1, 2026 | Caps (130 beds) and rebooking ban take effect | Implemented |
| Mar 10, 2026 | BCC unanimously opposes Orlando facility | Political statement |
| **Mar 13, 2026** | **IGSA renegotiation deadline** | **Decision point** |

---

## 5. LEGAL & POLICY FRAMEWORK

### What Florida Law Actually Requires

**Required under Florida SB 168 (2019) and subsequent legislation:**
- Honor ICE detainer requests (48-hour holds)
- Provide inmate information to ICE
- Allow ICE access to jails
- "Best efforts" cooperation (vague standard)
- Jail operators must participate in **at least** 287(g) WSO (narrowest model)

**NOT required:**
- ❌ City police participation in 287(g)
- ❌ University/college police participation
- ❌ School police participation
- ❌ Signing BOA (Basic Ordering Agreement)
- ❌ Signing IGSA (direct ICE contract)
- ❌ Housing detainees beyond 48-hour detainer period
- ❌ Accepting any specific 287(g) model beyond WSO

### 287(g) Over-Implementation

**What happened:** On February 26, 2025, all 67 Florida counties simultaneously signed 287(g) agreements — most choosing the **Task Force Model** (broadest authority, allows community arrests) when only the **Warrant Service Officer** model (narrowest, in-custody only) was legally required for jail operators.

**Why it matters:**
- Task Force Model authorizes immigration arrests in the **community**, not just in jail
- Many agencies signed beyond legal requirements — voluntary overreach
- Any agency can terminate with written notice to ICE field office at any time
- **Pressure point:** Education campaign targeting agencies that signed beyond requirements

### BOA Voluntariness (KEY LEGAL FINDING)

Orange County officials have presented BOAs as "mandatory" if the IGSA is terminated. **This is legally false.**

**Legal basis for voluntariness:**
1. **FAR § 16.703:** "A basic ordering agreement is not a contract" — neither party is obligated
2. **Printz v. United States (1997):** Federal government cannot commandeer local officials to administer federal programs
3. **National Sheriffs' Association:** "A service provider that enters into a BOA is not required to accept any order"
4. **SB 168:** Requires cooperation but NOT participation in specific federal programs

**Termination path for any county:**
1. Terminate IGSA → no more long-term detention
2. Refuse BOA → no reimbursement obligation, no detention obligation
3. Honor 48-hour detainers → satisfies SB 168 cooperation requirement
4. Notify ICE of release dates → satisfies information-sharing requirement
5. **Result:** County complies with state law while eliminating all detention costs

### The Rebooking Practice

**What ICE was doing at Orange County Jail:**
- Remove detainees every 72 hours
- Rebook under new booking number
- Artificially reset the 72-hour hold clock
- Prolonged detention without due process
- Created chaos for defense attorneys trying to locate clients

**Legal significance:** This circumvented the intended 72-hour limit in the IGSA, constituting potential due process violations and deliberate manipulation of county booking systems.

**Status:** Ended at Orange County March 1, 2026. **Unknown whether practice continues at other I-4 corridor facilities** — critical follow-up needed.

---

## 6. KEY PRESSURE POINTS (Ranked)

### Pressure Point #1: Orange County Financial Crisis ⭐⭐⭐⭐⭐
**Leverage:** Taxpayer subsidy of $3.4M/year, active political leadership (Demings), coalition support, imminent deadline
**Action window:** March 13, 2026 deadline
**Outcome scenarios:**
- Rate increase → precedent for all counties
- IGSA termination → removes ~130 beds from detention capacity
- Stalemate → continued taxpayer loss, escalating political pressure

### Pressure Point #2: Orlando Processing Center Transparency ⭐⭐⭐⭐⭐
**Leverage:** Unknown operator, no contract awarded, local opposition, BCC resolution
**Action window:** GSA FOIA due March 25, 2026; Orange County PRR-158704 (1,420 emails about 8660 Transport Drive)
**Key questions:** Who operates? What's the contract value? What permits has the county issued?

### Pressure Point #3: 287(g) Over-Implementation ⭐⭐⭐⭐
**Leverage:** Most agencies signed beyond legal requirements; can terminate at any time
**Action window:** Ongoing — no deadline
**Target:** Agencies that chose Task Force Model when only WSO required

### Pressure Point #4: Osceola County Rate Scandal ⭐⭐⭐⭐
**Leverage:** 40-year rate freeze, $65M+ cumulative subsidy, easy comparison to Orange County crisis
**Action window:** Evergreen — but amplified by current crisis
**Target:** County Commission awareness, media investigation

### Pressure Point #5: Rebooking Practice Accountability ⭐⭐⭐
**Leverage:** Due process violations, ended in Orange County but possibly continuing elsewhere
**Action window:** Immediate PRR campaign to other counties
**Target:** Documentation of practice at Hillsborough, Polk, Seminole, Volusia

### Pressure Point #6: Federal Contract Concentration ⭐⭐⭐
**Leverage:** $923.6M in detention contracts flow to private vendors (GEO Group, G4S) while counties lose money
**Action window:** Procurement monitoring
**Key finding:** 22 ICE contracts in Pinellas County (tactical operations hub), $858K Orlando OPLA office investment

---

## 7. DATA SOURCES & CROSS-REFERENCE FINDINGS

### TRAC vs. ICE Stats Cross-Reference

| Finding | Significance |
|---------|-------------|
| Pinellas typed as IGSA (TRAC) vs USMS IGA (ICE Stats) | Classification system mismatch — affects rate/contract analysis |
| Orange County Jail missing from TRAC but present in ICE Stats | Population undercount in TRAC |
| Orlando Processing Center in TRAC (167 detainees) but absent from ICE Stats | Either premature TRAC data or undisclosed ICE operations |
| Hillsborough consistent across both datasets | Only validated I-4 facility |
| 4 counties (Polk, Seminole, Volusia, Osceola) missing from BOTH datasets | Feeder network invisible to public data |

### BigLocalNews (BLN) / FPDS Findings

- **197 ICE closed/cancelled contracts in Florida**
- **83 detention-related contracts totaling $923.6 million**
- **101 contracts associated with I-4 corridor region**
- **Top vendors:** GEO Group (Broward TC, $42.9M + $38.9M), G4S Secure Solutions (detention transportation, $5-10M each)
- **Orlando ICE infrastructure:** $858K office furniture for OPLA, $181K telecom — expanding permanent presence
- **Pinellas tactical hub:** 22 contracts, primarily ICE OFTP (Firearms & Tactical Programs) — suggests major training/operations base

### MuckRock FOIA Database Findings

- **Critical routing discovery:** Orange County jail is run by **Orange County Government**, NOT the Sheriff's Office — all prior FOIA attempts went to wrong entity
- **Polk County:** 7 PDF ICE agreements (2007-2019) downloaded — complete timeline including BOA template
- **Sarasota County:** IGSA (2003), MOA (2019), BOA (2018) — BOA contract number format (70CDCR18G00000015) matches FPDS
- **Walton County:** MOA + BOA documents
- **Broward County:** Confirmed NO ICE contracts — houses federal detainees under USMS only

### IGA Rate Comparison (5 Counties)

| Rank | County | Per-Diem | Guard Rate | Base Year | Agreement # |
|------|--------|----------|------------|-----------|-------------|
| 1 | Hillsborough | $101.06 | $20.94 | 1983 (Mod 15: 2005) | J-B18-M-038 |
| 2 | Orange | $88.00 | $31.75 | 1983 (Mod 6: 2011) | 18-04-0023 |
| 3 | Pinellas | $80.00 | $27.57 | Unknown | 18-91-0041 |
| 4 | Seminole | $56.71 | $24.72 | 2004 | 18-04-0024 |
| 5 | Osceola | $40.00 | $12.00 | 1986 | J-B18-M-529 |

**Rate variance: 152.7%** between highest (Hillsborough) and lowest (Osceola) — same region, same federal district, same era of agreements.

---

## 8. SURVEILLANCE & TECHNOLOGY

### Clearview AI / Facial Recognition (OCSO)

**Source:** PRR_25-6990 — 6,007 Clearview AI searches by Orange County Sheriff's Office (Oct 2021 – Aug 2025)

**Key findings:**
1. **One search explicitly categorized as "Immigration"** — HSI case Ol19hr25te0011 (May 2025)
2. **25 searches tied to HSI (Homeland Security Investigations) case numbers** — 82+ facial recognition queries for federal operations
3. **4 human smuggling/trafficking cases** with immigration enforcement overlap
4. **6 searches tied to CFIX** (Central Florida Intelligence Exchange, DHS-funded fusion center)
5. **46% of all searches (2,777) conducted by exempt personnel** — identity shielded under Florida surveillance exemptions, making full scope of immigration enforcement use unknowable

**Significance:** Demonstrates that local law enforcement is using locally-procured surveillance technology (Clearview AI) to support federal immigration enforcement operations, including explicit "Immigration" category searches.

### Use of Force Data (Seminole County)

**Source:** UOF_Request_1-1-2022_through_12-31-2025.xlsx — 1,623 incidents at John E. Polk Correctional Facility

**Key findings:**
- **No explicit ICE detainee markers** in the data (critical gap)
- **Corrections UOF rebounded 17% in 2025** after multi-year decline — correlates with expanded federal enforcement
- **H2 2025 corrections UOF spiked 55%** over H2 2024
- **Hispanic corrections UOF share rebounded** from 6.2% (2024) to 8.9% (2025)
- **Chemical agent deployment doubled** in 2025 (9 incidents vs 4 in 2024)
- **Intake division** (where 287(g) screening occurs) logged 27 UOF incidents

**Limitation:** Without inmate classification data, it is impossible to isolate ICE-related UOF incidents. The trends are **circumstantially consistent** with increased federal detention but not conclusive.

---

## 9. PUBLIC RECORDS & FOIA CAMPAIGN

### Status Overview

| Category | Submitted | Acknowledged | Responses Received | Pending Submission |
|----------|-----------|-------------|--------------------|--------------------|
| **Florida PRR (County)** | 5 | 5 | 0 | 2 |
| **Federal FOIA** | 1 | 1 | 0 | 10 |
| **Targeted PRR** | 1 (PRR-158704) | 1 | Amended, awaiting cost | 0 |
| **TOTAL** | 7 | 7 | 0 | 12 |

### Submitted & Active Requests

| ID | Agency | Target Data | Status | Expected Response |
|----|--------|------------|--------|-------------------|
| 2026-FOI-01240 | GSA | Orlando facility property assessments | Acknowledged | March 25, 2026 |
| P390162-022326 | Hillsborough County SO | IGSA/287(g)/financial | Acknowledged | March 10, 2026 |
| R008264-022326 | Seminole County SO | IGSA/287(g)/financial | Acknowledged | March 10, 2026 |
| R052454-022226 | Volusia County SO | IGSA/287(g)/financial | Acknowledged | March 10, 2026 |
| 1587404 | Orange County Corrections | IGSA/287(g)/financial | Acknowledged | March 10, 2026 |
| PRR-158704 | Orange County Government | ICE emails (8660 Transport Dr + IGSA dispute) | Amended — awaiting revised cost | ~March 12, 2026 |

**Note:** Four county PRR responses were expected by March 10, 2026. Status of actual delivery unknown at time of this synthesis.

### PRR-158704: Highest-Value Pending Request

This Orange County email search covers **1,420+ emails** mentioning "ICE" and "8660 Transport Drive" — the planned Orlando Processing Center site. After amendment to narrow timeframe (Jan 20, 2025 – present), expected cost reduced from $211 to ~$50-100.

**Expected intelligence yield:**
- County's role in Orlando facility planning/permitting
- IGSA dispute internal communications
- Post-March 13 deadline contingency planning
- Whether county is facilitating or resisting the 1,500-bed expansion

### Not Yet Submitted (High Priority)

| ID | Agency | Target | Why It Matters |
|----|--------|--------|---------------|
| PENDING-001 | Pinellas County SO | IGSA/287(g)/financial | Completes I-4 county set |
| PENDING-002 | Polk County SO | IGSA/287(g)/financial | Completes I-4 county set |
| PENDING-003 | ICE ERO | Facility codes for I-4 | Resolves classification discrepancies |
| PENDING-004 | ICE 287(g) Office | MOA amendments, compliance | Documents over-implementation |
| PENDING-005 | ICE ODO | Inspection reports | Quality/conditions evidence |
| PENDING-009 | ICE Acquisition | Orlando procurement | Operator identification |

### Seminole County PRR Pushback (Scout Investigation)

**Invoice #111:** $3,178.89 fee estimate for Scout microtransit records — **75.5% attributable to "Excessive Administrative Time"** by three high-salaried officials. Legal analysis completed under Florida § 119.07(1)(b) identifies multiple grounds for challenge:
- Statute limits charges to "clerical or supervisory assistance" — not Director-level review
- 18 hours for MicroTransit Division Manager ($1,411.20) lacks task-level justification
- Escalation to County Manager Darren Gray produced same-day response after 17 days of silence

---

## 10. ENTITY RESOLUTION & PROCUREMENT INTELLIGENCE

### Key Entities

| Entity | Type | Role | Investigation Relevance |
|--------|------|------|------------------------|
| **GEO Group** | Private Prison Corp | Operates Broward TC ($42.9M + $38.9M FPDS contracts) | Possible Orlando facility operator |
| **CoreCivic** | Private Prison Corp | National ICE contractor | Possible Orlando facility operator |
| **G4S Secure Solutions** | Security/Transport | Detention officer transportation ($5-10M per contract) | Active in FL ICE operations |
| **TPA Group** | Real Estate Developer | Owns 8660 Transport Drive via Beachline Logistics Center LLC | Orlando facility landlord |
| **HLI Partners** | Industrial Broker | Marketed 8660 Transport Drive | May have ICE deal intelligence |
| **Eola Power LLC** | Power Systems | UPS maintenance at Krome SPC ($9.3K + $4K) | Minor vendor |
| **David Venturella** | ICE Senior Advisor | Toured Orlando site Jan 16, 2026 | Key decision-maker |
| **Mayor Jerry Demings** | Orange County Mayor | Leading IGSA renegotiation/resistance | Critical political actor |
| **Commissioner Nicole Wilson** | OC District 1 | Sponsored anti-facility resolution | Political actor |

### Federal Contract Intelligence

**FPDS close-out data** (via BLN) reveals the structure of ICE's Florida spending:

- **83 detention-related contracts** in Florida
- **Total obligations:** $923.6 million
- **Geographic concentration:** Pinellas (22 contracts — tactical hub), Orange (6 — OPLA office), Hillsborough (2), Miami-Dade (1), Broward (1)
- **Contract number format:** 70CDCR[YY][type][seq] (e.g., 70CDCR18G00000016 = FY2018 BLN/Grant, Walton County)
- **BOA numbering:** All Florida BOAs follow 70CDCR18G000000XX format — 29 counties as of Feb 2019

---

## 11. OPEN QUESTIONS & CONTRADICTIONS

### Contradiction Register (from Master Investigation)

| ID | Contradiction | Status | Resolution Path |
|----|-------------|--------|----------------|
| C-001 | Osceola/Seminole reimbursement figures vary across documents | **Open** | Reconcile against original IGA language |
| C-002 | Orlando facility framed as planned in some docs but active in TRAC | **Open** | Date-aligned TRAC extract + permitting timeline |
| C-003 | Facility type labels (USMS IGA vs IGSA) differ by source | **Open** | Normalize source-of-record precedence |
| C-004 | ICE metric column interpretations vary | **Open** | Awaiting ICE/OIS data dictionary (FOIA) |

### Critical Unresolved Questions

1. **Orlando Processing Center operator** — Who has the contract? CoreCivic, GEO Group, or someone else?
2. **Rebooking practice scope** — Is it happening at Hillsborough, Polk, Seminole, Volusia?
3. **Orange County FY2023 disappearance** — Why did it vanish from ICE detention stats for one year?
4. **Transfer flow patterns** — Where do detainees from Tier 2 facilities go?
5. **Osceola 1993 rate reversal** — Why was the $52/day rate reduced back to $40/day?
6. **Orlando TRAC data** — Is TRAC showing a real operational facility or a data artifact?
7. **BOA county list (current)** — The 2019 list shows 29 FL counties. What's the 2026 count?
8. **Post-March 13 outcome** — What actually happened with the Orange County IGSA deadline?

---

## 12. PARALLEL INVESTIGATION: SCOUT MICROTRANSIT

A secondary investigation track examines Seminole County's **Scout microtransit program** (replacing LYNX fixed-route bus service):

**Key findings:**
- BeFree LLC (d/b/a Freebee) awarded contract via RFP 604918-25/PCD (May 20, 2025)
- Cost driver: LYNX costs increased from $7M (2019) to $17M (2025) — 143% increase
- Some buses averaged half a rider on Sundays
- Full service launched October 2025
- **Seminole County charging $3,178.89 for records** — potential deterrent pricing under challenge

**Connection to ICE investigation:** Seminole County Sheriff's Office operates 287(g) at John E. Polk Correctional Facility (active since 2010) with $94/day USMS IGA. The county's approach to public records requests may reflect broader institutional transparency resistance.

---

## 13. METHODOLOGY & LIMITATIONS

### Approach

1. **Data ingestion:** Systematically accessed ICE detention statistics (7 years), TRAC Immigration tools, FPDS via BLN, MuckRock FOIA database, county meeting records, property records, UOF data, Clearview AI logs, and community organizer intelligence
2. **Entity resolution:** Normalized facility names, contract types, and vendor identities across 23+ data sources
3. **Cross-referencing:** Built facility-by-facility comparison tables across TRAC, ICE Stats, USMS IGA documents, FPDS contracts, and county records
4. **Financial modeling:** Calculated per-diem losses using actual county costs ($180/day benchmark from Orange County) against IGA rates
5. **Legal analysis:** Reviewed FAR regulations, constitutional precedent, and Florida statutes to assess legal obligations vs. voluntary participation
6. **Contradiction tracking:** Logged discrepancies in a formal register in the Master Investigation document

### Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| No county PRR responses received yet | Cannot verify contract terms, current populations, financial details | Estimated response dates March 10-25 |
| ICE metric column headers not decoded | Cannot interpret FY2026 population metrics with certainty | Pending OIS data dictionary FOIA |
| UOF data lacks inmate classification | Cannot isolate ICE-related use of force | Would require booking record cross-reference |
| Transfer data unavailable | Cannot map Tier 2 → Tier 1 flow patterns | Pending FOIA PENDING-010 |
| Osceola population unknown | Cannot calculate actual current financial losses | Direct inquiry needed |
| TRAC vs ICE Stats contradictions unresolved | Facility classification uncertain for 2 facilities | Multiple FOIAs targeting this |
| 46% of Clearview AI searches by exempt personnel | Cannot determine full scope of immigration enforcement surveillance | Structural limit of Florida exemption law |
| Investigation conducted during active crisis | Situation evolving daily around March 13 deadline | Time-sensitive findings documented |

### Confidence Framework

| Level | Meaning | Count of Findings at This Level |
|-------|---------|-------------------------------|
| **CONFIRMED** | Direct evidence from primary records | 12 |
| **HIGH** | Multiple corroborating sources | 8 |
| **MODERATE** | Single credible source or circumstantial pattern | 5 |
| **HYPOTHESIS** | Reasonable inference without direct evidence | 3 |
| **UNRESOLVED** | Contradictory evidence, awaiting data | 4 |

---

## 14. MASTER FILE INDEX

### Core Investigation Documents

| File | Type | Content |
|------|------|---------|
| `I4_CORRIDOR_MASTER_INVESTIGATION.md` | Master | Canonical synthesis, contradiction register |
| `INVESTIGATION_STATUS_INTEGRATED_2026-03-05.md` | Status | Latest integrated status with PSL-resources |
| `QUICK_BRIEF_2026-03-05.md` | Brief | Decision-maker summary |
| `findings.md` | Deep-dive | 9-facility inventory |
| `FINANCIAL_UNSUSTAINABILITY_I4_CORRIDOR_ICE_DETENTIONS.md` | Deep-dive | $7.3M annual loss analysis |
| `IGA_RATE_ANALYSIS_DEEP_DIVE_2026-02-27.md` | Deep-dive | 5-county rate comparison |
| `TRAC_ICE_CROSS_REFERENCE_ANALYSIS.md` | Deep-dive | TRAC vs ICE Stats discrepancies |
| `POPULATION_TRENDS_2026-02-27.md` | Deep-dive | FY2020-FY2026 facility timeline |
| `BOA_MANDATE_INVESTIGATION.md` | Legal | BOA voluntariness legal analysis |
| `ORLANDO_ICE_PROCESSING_CENTER_OWNERSHIP_INVESTIGATION_2026-02-27.md` | Deep-dive | Property ownership chain |
| `OSCEOLA_COUNTY_INVESTIGATION_COMPLETE.md` | Deep-dive | 40-year rate anomaly |
| `occ_bcc_march10_2026_findings.md` | Deep-dive | BCC resolution analysis |

### Intelligence & Evidence

| File | Type | Content |
|------|------|---------|
| `clearview_ai_ice_findings.md` | Intelligence | Facial recognition / immigration enforcement |
| `SEMINOLE_UOF_ICE_ANALYSIS.md` | Intelligence | Use of force trends |
| `BLN_ICE_INVESTIGATION_FINDINGS.md` | Intelligence | $923.6M in FPDS contracts |
| `MUCKROCK_ICE_CENTRAL_FL_FINDINGS.md` | Intelligence | Prior FOIA documents & routing |
| `TRAC_REMOVALS_FLORIDA_ANALYSIS.md` | Intelligence | Deportation statistics |

### FOIA & Records

| File | Type | Content |
|------|------|---------|
| `FOIA_STRATEGY.md` | Strategy | Phase 1-3 FOIA plan |
| `FOIA_Status_Summary_2026-02-26.md` | Tracker | Live request status |
| `foia_prr_tracking.csv` | Data | Machine-readable request tracker |
| `PRR_STATUS_SUMMARY_2026-03-09.md` | Status | Orange County PRR-158704 |
| `pushback_analysis.md` | Analysis | Seminole County fee challenge |

### Data Files (JSON)

| File | Records | Content |
|------|---------|---------|
| `FY26_detentionStats_02122026_parsed.json` | Full dataset | Parsed ICE detention stats |
| `bln_ice_fl_contracts.json` | 83 records | ICE detention contracts, Florida |
| `bln_dhs_contracts.json` | Large | DHS contracts via BLN/FPDS |
| `TRAC_I4_CORRIDOR_COMPREHENSIVE_DATA.json` | 12 facilities | TRAC facility data |
| `TRAC_287G_CROSS_REFERENCE.json` | 9 facilities | 287(g) cross-reference |
| `ice_facilities_i4_corridor_updated.json` | 9 facilities | Master facility inventory |
| `iga_rate_comparison.json` | 5 facilities | Rate comparison data |
| `entity_map.json` | 9 entities | Entity resolution (primarily Scout) |

### IGA Transcriptions

| File | Content |
|------|---------|
| `IGA-Florida-Hillsborough-County_Manual-Visual-Transcription.md` | Full agreement with 15 modifications |
| `IGA-Florida-Pinellas-County-Sheriffs-Office_Manual-Visual-Transcription.md` | Full agreement |
| `IGA-Florida-John-E-Polk-Correctional-Facility_Manual-Visual-Transcription.md` | Seminole County agreement |
| `IGA-Florida-Osceola-County-Sheriffs-Department_Manual-Visual-Transcription.md` | 40-year-old agreement |
| `USMS-Agreement-Documents-2022_OCR.md` | Orange County USMS documents |

---

## BOTTOM LINE

This investigation has reached the point where **the structural picture is clear but operational details remain locked behind pending FOIA/PRR responses.** The core narrative is robust and evidence-backed:

**The federal government is expanding ICE detention capacity in Central Florida at an unprecedented rate while systematically underpaying counties that bear the cost — creating a fiscal crisis that local governments can use as leverage to resist or reshape the detention system.**

The three most time-sensitive elements are:
1. **March 13 IGSA deadline** — What Orange County does next sets the template for the region
2. **GSA FOIA (March 25)** — May reveal Orlando facility procurement details
3. **Four county PRR responses (overdue as of March 10)** — Will fill the operational intelligence gaps

The investigation is structured for rapid integration of incoming records through the canonical document hierarchy, contradiction register, and structured data files. Every finding traces to a specific source record with documented confidence levels.

---

*This synthesis reflects the state of the investigation as of March 12, 2026. All findings are subject to revision as pending records requests are fulfilled.*
