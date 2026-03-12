# Seminole County Sheriff's Office — Use of Force Analysis
## ICE Investigation Relevance Assessment

**Source:** `UOF_Request_1-1-2022_through_12-31-2025.xlsx` (Seminole County Sheriff's Office public records response)
**Coverage:** January 1, 2022 – December 30, 2025
**Records:** 1,623 rows representing 1,179 unique incident reports (multiple rows per incident reflect multiple officers/force applications per event)
**Analysis Date:** March 2026

> **Note:** The request was made for January 1, 2017 – December 31, 2025, but the data provided only covers January 1, 2022 forward. The 2017–2021 gap should be flagged in follow-up.

---

## Executive Summary

**Bottom line: The UOF data contains no explicit markers identifying ICE detainees, immigration holds, or 287(g)-related incidents.** The dataset does not distinguish between local inmates, USMS federal prisoners, and individuals held on ICE detainers. This is a significant evidentiary gap that limits direct ICE-related findings.

However, several trend patterns in the corrections UOF data are potentially relevant to the broader ICE investigation when cross-referenced with what we know about Seminole County's federal detention arrangements:

1. **Corrections UOF rebounded 17% in 2025** after a steep multi-year decline — coinciding with expanded federal immigration enforcement.
2. **H2 2025 corrections UOF spiked 55%** over H2 2024 (82 vs. 53 incidents).
3. **Hispanic corrections UOF share rebounded** from a 2024 low of 6.2% to 8.9% in 2025.
4. **Chemical agent deployment in corrections doubled** in 2025 (9 incidents) vs. 2024 (4 incidents).
5. **The Intake division** — where 287(g) screening would occur — logged 27 UOF incidents across the period.

---

## Context: Seminole County's Federal Detention Arrangements

From the existing investigation record:

| Arrangement | Details |
|---|---|
| **287(g) Program** | Active since January 20, 2010; Warrantless Officer Team (WOT) model |
| **287(g) Model** | Book-and-release (NOT long-term detention) |
| **ICE Detention Stats** | Seminole does NOT appear in ICE detention statistics — no long-term ICE population |
| **USMS IGA** | Agreement No. 18-04-0024 (eff. Jan 1, 2004) at John E. Polk Correctional Facility; per diem $94.00/day |
| **Facility** | John E. Polk Correctional Facility, 211 Bush Blvd, Sanford, FL 32773 (code 4YA) |

**Implication for UOF data:** Under the book-and-release 287(g) model, individuals identified as potentially removable are screened during booking, and if an ICE detainer is issued, they are transferred to an ICE facility (likely Orange County or Baker County) rather than held long-term at John E. Polk. This means the UOF exposure window for ICE-related detainees at Seminole County is concentrated in the **booking/intake/transfer phase**, not in long-term custody.

---

## Data Structure

| Column | Description |
|---|---|
| `Inc: Incident type` | RTR - Corrections (984 rows) or RTR - Law Enforcement (639 rows) |
| `Inc: Report #` | Unique incident identifier |
| `Inc: Occurred date/time` | Date and time of incident |
| `UOF: Citizen was injured` | Yes/No |
| `UOF: Citizen condition/injury` | Injury type (e.g., Abrasion/Laceration, No injuries noted) |
| `Cit: Age / Gender / Ethnicity` | Citizen demographics (Ethnicity: Hispanic / Non-Hispanic) |
| `UOF: Citizen resistance` | 1-Presence through 6-Aggravated Physical |
| `UOF: Reason for using force` | Effect Arrest, Defense of Self, etc. |
| `UOF: Type of force used` | Assisted Physical Control, Takedown, Taser, etc. |
| `Inc: Org: Division` | Organizational division (Corrections, Law Enforcement, Family and Youth Services, Intake, etc.) |
| `Emp: Employee ID / Name` | Officer identification |

**Key limitation:** There is NO field for inmate classification (local, federal/USMS, ICE detainer, pretrial, etc.). Without cross-referencing with booking records, it is **impossible to isolate ICE-related UOF incidents from this dataset alone.**

---

## Finding 1: Corrections UOF Trend Reversal in 2025

### Overall Volume

| Year | Total UOF Rows | Corrections UOF Rows | Unique Corrections Incidents | Law Enforcement UOF Rows |
|------|---------------|----------------------|------------------------------|--------------------------|
| 2022 | 538 | 357 | 161 | 181 |
| 2023 | 510 | 334 | 202 | 176 |
| 2024 | 290 | 135 | 128 | 155 |
| 2025 | 285 | 158 | 157 | 127 |

**Key observation:** After corrections UOF plummeted 60% from 2023 to 2024 (334 → 135 rows), it **reversed course and increased 17%** in 2025 (135 → 158). Meanwhile, law enforcement UOF continued declining. This divergence is notable.

### Half-Year Comparison (most relevant to Trump-era enforcement)

| Period | Corrections UOF Rows | Change |
|--------|---------------------|--------|
| H2 2024 | 53 | — |
| H2 2025 | 82 | **+54.7%** |

**Confidence:** MODERATE. The uptick is real in the data but could reflect staffing changes, policy changes, population changes, or reporting methodology shifts — not necessarily ICE-related factors.

**Source:** UOF_Request_1-1-2022_through_12-31-2025.xlsx, rows filtered by `Inc: Incident type = "RTR - Corrections"`, date parsed from `Inc: Occurred date`.

---

## Finding 2: Hispanic Corrections UOF Share Rebounded in 2025

| Year | Unique Corrections Incidents | Involving Hispanic Citizens | % Hispanic |
|------|------------------------------|---------------------------|------------|
| 2022 | 161 | 23 | 14.3% |
| 2023 | 202 | 26 | 12.9% |
| 2024 | 128 | 8 | **6.2%** |
| 2025 | 157 | 14 | **8.9%** |

After dropping to a low of 6.2% in 2024, the Hispanic share of corrections UOF incidents increased to 8.9% in 2025 — a 44% relative increase. This tracks directionally with the nationwide expansion of ICE enforcement under the current administration, though it remains below 2022-2023 levels.

**Monthly detail (2025 corrections, Hispanic UOF):**

| Month | Hispanic / Total | % |
|-------|-----------------|---|
| Jan 2025 | 3/16 | 18.8% |
| Feb 2025 | 1/17 | 5.9% |
| Mar 2025 | 0/6 | 0.0% |
| Apr 2025 | 1/15 | 6.7% |
| May 2025 | 1/10 | 10.0% |
| Jun 2025 | 2/12 | 16.7% |
| Jul 2025 | 1/6 | 16.7% |
| Aug 2025 | 3/8 | **37.5%** |
| Sep 2025 | 0/26 | 0.0% |
| Oct 2025 | 0/12 | 0.0% |
| Nov 2025 | 1/14 | 7.1% |
| Dec 2025 | 1/16 | 6.2% |

**Notable:** August 2025 had the highest Hispanic share of any month (37.5%, 3 of 8 incidents), but September 2025 — despite having the highest volume (26 incidents) — had **zero** Hispanic UOF incidents. The September spike was driven entirely by juvenile detention activity (many subjects ages 13-18).

**Confidence:** LOW-MODERATE. Ethnicity is self-reported and the "Hispanic" category includes both U.S. citizens and non-citizens. Without immigration status data, no causal link to ICE can be drawn.

---

## Finding 3: September 2025 Corrections UOF Spike — Juvenile-Driven, Not ICE-Related

September 2025 had 26 corrections UOF incidents — **more than triple** the August level (8) and the single highest month since May 2023. However, examination of the incident details shows:

- **ALL 26 were Non-Hispanic**
- **Many involved juveniles** (ages 13, 14, 16, 17, 18)
- Divisions included "Family and Youth Services," "Youth Services," and "Family and Communication Svcs"
- Reasons were predominantly "Defense of Self" and "Defense of Another Person"
- Multiple incidents on September 20-22, 2025 involved the same juvenile facility officers

**Assessment:** This spike appears to reflect a **juvenile detention disturbance or operational challenge**, not immigration enforcement activity. It is likely not ICE-relevant.

---

## Finding 4: Intake Division UOF — Potential 287(g) Screening Window

The "Intake" division — where 287(g) immigration screening occurs during booking — logged **27 UOF incidents** across the four-year period:

| Year | Intake UOF Incidents |
|------|---------------------|
| 2022 | 8 |
| 2023 | 10 |
| 2024 | 5 |
| 2025 | 4 |

These are low numbers and showed a declining trend. Most involved routine booking resistance (Active Physical, Passive Physical). Without knowing which of these involved individuals subject to 287(g) screening, this is a **hypothesis-only** connection to ICE.

---

## Finding 5: Force Escalation Patterns

### Chemical Agent Usage (Corrections)

| Year | Chemical Agent Deployments |
|------|--------------------------|
| 2022 | 4 |
| 2023 | 8 |
| 2024 | 4 |
| 2025 | **9** |

Chemical agent use in corrections reached its highest level in 2025, though the absolute numbers are small.

### Restraint Chair Usage

| Year | Restraint Chair Uses |
|------|---------------------|
| 2022 | 25 |
| 2023 | 9 |
| 2024 | 14 |
| 2025 | **1** |

Restraint chair usage collapsed in 2025, possibly reflecting a policy change.

### Injury Rates (Corrections)

| Year | Injuries / Total | Injury Rate |
|------|-----------------|-------------|
| 2022 | 77/357 | 21.6% |
| 2023 | 52/334 | 15.6% |
| 2024 | 21/135 | 15.6% |
| 2025 | 21/158 | **13.3%** |

Injury rates continued declining, suggesting that while UOF volume increased in 2025, the severity may have decreased — or reporting changed.

---

## Finding 6: High-Frequency Officers

### Top 10 Corrections Officers by UOF Incident Count (2022-2025)

| Emp ID | Name | UOF Incidents |
|--------|------|---------------|
| 120113 | Raymond Rivera | 26 |
| 102084 | Tarius Burke | 23 |
| 114086 | Scott Gray | 19 |
| 120173 | Wilson Munoz | 17 |
| 117056 | Ryan Johnson | 17 |
| 118044 | David Delong | 16 |
| 115061 | William Burns IV | 15 |
| 120055 | Christian Rodriguez | 15 |
| 109111 | Casey Wheeler | 14 |
| 113099 | Wilbert Martin Jr | 13 |

These officers warrant further analysis if any cross-referencing with ICE detainee booking records becomes possible.

---

## Quarterly UOF Trend (All Incidents)

| Quarter | Total UOF |
|---------|-----------|
| 2022-Q1 | 146 |
| 2022-Q2 | 137 |
| 2022-Q3 | 92 |
| 2022-Q4 | 163 |
| 2023-Q1 | 197 |
| 2023-Q2 | 157 |
| 2023-Q3 | 85 |
| 2023-Q4 | 71 |
| 2024-Q1 | 58 |
| 2024-Q2 | 92 |
| 2024-Q3 | 69 |
| 2024-Q4 | 71 |
| 2025-Q1 | 85 |
| 2025-Q2 | 68 |
| 2025-Q3 | 64 |
| 2025-Q4 | 68 |

---

## Limitations & Gaps

1. **No immigration status field.** The single most critical limitation. Without knowing which inmates were subject to ICE detainers, 287(g) screening, or federal holds, no direct ICE-UOF connection can be established from this dataset.

2. **Missing 2017-2021 data.** The request covered 2017-2025, but only 2022-2025 was provided. The earlier period includes the first Trump administration's immigration enforcement surge and would provide critical baseline comparisons. **Follow-up needed.**

3. **Ethnicity ≠ immigration status.** "Hispanic" ethnicity does not indicate immigration status. Many Hispanic individuals in UOF incidents are U.S. citizens.

4. **Multi-row incidents.** Each row represents one officer's force application in one incident. A single incident with 3 officers and 4 force types generates 12 rows. Analysis must account for this structure.

5. **No narrative/circumstance field.** UOF reports typically include a narrative description that might mention immigration-related circumstances. This dataset only contains coded fields.

6. **Population denominator unknown.** Without jail population data by year/month, we cannot compute UOF *rates*. An increase in UOF could reflect population growth rather than behavioral changes.

---

## Recommended Next Steps

### Immediate
1. **Request booking/intake records** for John E. Polk for the same period (2022-2025), specifically seeking fields for: hold type (local, federal, ICE detainer), immigration detainer Y/N, 287(g) screening outcome, and transfer destination. This would allow direct cross-referencing with UOF report numbers.

2. **Request the 2017-2021 UOF data** — the period covered by the original request but not provided in this response. First-Trump-era data is essential for trend comparison.

3. **Request daily/monthly jail population counts** broken down by hold type (local criminal, USMS, ICE) to compute UOF rates per capita.

### Medium-term
4. **Cross-reference top UOF officers** (Rivera, Burke, Gray, Munoz, Johnson) with any ICE-related booking data if obtained.

5. **Compare Seminole County UOF trends** with other I-4 corridor jails (Orange, Osceola, Volusia) that also hold federal/ICE detainees, to see if the 2025 corrections uptick is Seminole-specific or regional.

6. **FOIA ICE ERO** for any complaints, grievances, or incident reports filed by detainees processed through Seminole County's 287(g) program.

---

## Methodology

- **Source file:** `UOF_Request_1-1-2022_through_12-31-2025.xlsx`, single sheet "New Report", 1,623 data rows, 16 columns
- **Parsing:** Python3 with openpyxl; multi-value cells (newline-separated) were split and analyzed both at the first-value and all-values level
- **Deduplication:** Unique incidents identified by `Inc: Report #` field; 1,179 unique reports total, 648 unique corrections reports
- **Cross-reference:** Seminole County IGA transcription, TRAC 287(g) cross-reference data, ICE detention statistics
- **Date range verification:** First record 01/01/2022, last record 12/30/2025

---

*Analysis produced by OpenPlanter investigation agent, March 2026*
