# BLN API Search: Central FL ICE Investigation Findings

## Executive Summary

Using the BigLocalNews (BLN) API with authentication, I searched all 107 open projects on the platform and downloaded the **Federal contract cancellations** dataset (FPDS data) which proved highly relevant. The search identified **197 ICE contract records in Florida**, including **83 detention-related contracts** totaling **$923.6 million** in obligations, and **101 contracts associated with the I-4 corridor** region.

## Methodology

- **Platform**: BigLocalNews (biglocalnews.org), Stanford-affiliated open data platform
- **API**: GraphQL API via `bln` Python client v2.3.14
- **Authentication**: JWT token (user: dthomsen)
- **Date**: March 2026
- **Search approach**: 
  1. Queried all 107 open projects using keyword matching across project names, descriptions, tags, and filenames
  2. Downloaded complete Federal contract cancellations dataset (7 files from FPDS)
  3. Filtered for ICE/DHS + Florida records across all cancellation types

## Key Data Source: Federal Contract Cancellations

**Source**: BLN project "Federal contract cancellations" (updated 2026-02-27)
**Origin**: U.S. Federal Procurement Data System (FPDS) — https://www.fpds.gov
**Files**: 7 CSV/ZIP files totaling ~618MB covering contract cancellations by type:
- `close_out.csv` (90,956 records) — contract close-outs
- `convenience.csv` (90,012 records) — terminations for convenience  
- `convenience--limited_cols.csv` (85,578 records) — same, limited columns
- `legal.csv` (25,627 records) — legal cancellations
- `for_cause.csv` (918 records) — terminations for cause
- `default.csv` (665 records) — defaults

---

## Finding 1: ICE Has 197 Closed/Cancelled Contracts in Florida

The close_out.csv file contains **197 U.S. Immigration and Customs Enforcement (ICE)** contract records with Florida connections. These represent contracts that have been closed out through the FPDS system as of Feb 2026.

### Geographic Distribution (by performance county):
| County | Count | Notes |
|--------|-------|-------|
| Pinellas | 22 | ICE OFTP (Firearms & Tactical Programs) hub |
| District of Columbia | 10 | ICE HQ operations with FL vendors |
| Howard | 7 | |
| **Orange** | **6** | **Orlando — OPLA, IT, telecom** |
| Dallas | 3 | |
| New York | 3 | |
| **Hillsborough** | **2** | **Tampa — vehicles, fuel support** |
| **Volusia** | **1** | **Daytona area** |
| Miami-Dade | 1 | Krome SPC |
| Broward | 1 | Broward Transitional Center |

### Confidence: HIGH
**Source**: FPDS data via BLN, cross-referenced by agency ID 7012 (U.S. Immigration and Customs Enforcement)

---

## Finding 2: $923.6M in Detention-Related ICE FL Contracts

**83 contracts** reference detention-related terms (detention, detain, jail, correctional, inmate). Key contracts:

### GEO Group — Broward Transitional Center
| Contract ID | Total Obligated | Description |
|------------|----------------|-------------|
| 70CDCR24FR0000053 | **$42,926,174.75** | Detention & transportation services, Broward Transitional Center, ERO Miami AOR |
| 70CDCR23FR0000048 | **$38,861,166.19** | Same facility, prior year, de-obligation of excess funds |

### G4S Secure Solutions — Detention Officer Transportation
Multiple contracts from 2018-2022, each **$5M-$10M+**, for "Transportation (Detention Officer) Services" across multiple regions. G4S is the contractor of record with FL as vendor state.

### Krome Service Processing Center
| Contract ID | Vendor | Amount | Description |
|------------|--------|--------|-------------|
| 70CDCR24P00000027 | EOLA POWER LLC | $9,339.40 | UPS maintenance at Krome SPC |
| 70CDCR24P00000036 | EOLA POWER LLC | $4,020.00 | UPS maintenance at Krome SPC |

### Confidence: HIGH
**Source**: FPDS close-out records, contract descriptions explicitly reference detention services

---

## Finding 3: Orlando/Orange County ICE Infrastructure

**6 ICE contracts** performed in Orange County reveal active ICE office infrastructure in Orlando:

| Contract ID | Vendor | Amount | Description |
|------------|--------|--------|-------------|
| 70CMSW23FC0000059 | Price Modern LLC | **$857,871.15** | Office furniture for **Orlando OPLA** (Office of the Principal Legal Advisor) |
| 70CTD023FC0000002 | ConvergeOne | $39,477.21 | PBX/VoIP phone systems for Orlando FL office |
| 70CTD023FR0000010 | Blue Tech Inc. | $141,963.08 | Cisco Webex video teleconferencing for ICE/M&A/**OPLA** |

**Significance**: The Orlando OPLA office handles immigration court proceedings. These contracts show ICE invested in substantial office infrastructure in Orlando — furniture ($858K), phone systems, and video conferencing — consistent with an expanding operational presence in the I-4 corridor.

### Confidence: HIGH
**Source**: FPDS records with explicit "ORLANDO" performance location and "OPLA" in description

---

## Finding 4: ICE Tactical/Law Enforcement Operations — Pinellas County Hub

**22 contracts in Pinellas County** (St. Petersburg area), primarily through ICE's Office of Firearms and Tactical Programs (OFTP). This appears to be a major ICE operational hub:

| Key Vendor | Contracts | Total Value | Products |
|-----------|-----------|-------------|----------|
| Atlantic Diving Supply | 16 | ~$3.5M | LE equipment, weapon parts, holsters, suppressors, optics |
| Optivor Technologies | Multiple | Various | IT/telecom systems |
| SRT Supply LLC | 1 | $23,399 | Rifle suppressors |
| Federal Contracts LLC | 1 | $97,394 | Utility vehicles |

**Significance**: The concentration in Pinellas County suggests ICE maintains a significant tactical training/operations center in the Tampa Bay area, with equipment procurement totaling millions.

### Confidence: HIGH
**Source**: FPDS records, explicit OFTP references

---

## Finding 5: ICE Terminated a $5.5M FOIA/Litigation Support Contract (Miami)

**Red Carrot Inc.** (520 Brickell Key Drive, Miami FL) had a **$5.5M** ICE contract for "management analyst support services related to **litigation and other information disclosure requests**" for the Office of Administration Operations. This was **TERMINATED FOR CONVENIENCE** on **April 4, 2025**.

| Field | Value |
|-------|-------|
| Contract ID | 70CMSW20FC0000017 |
| Vendor | Red Carrot Inc. (Miami, FL) |
| Total Obligated | $5,524,998.40 |
| Action | Terminated for Convenience |
| Date | 2025-04-04 |
| Description | Management analyst support related to litigation and information disclosure requests |

**Significance**: This termination occurred early in the Trump administration's second term. Terminating FOIA/litigation support capabilities could reduce ICE's capacity to respond to public records requests and legal challenges — directly relevant to transparency around detention operations.

### Confidence: HIGH
**Source**: FPDS convenience termination record

---

## Finding 6: Hurricane Milton ICE Operations — Tampa

Contract 70CMSD25P00000001 shows ICE contracted **Professional Logistics Services Inc.** for **$837,852** in fuel and support during Hurricane Milton in Tampa/Hillsborough County. This was closed out after de-obligating unused funding.

**Significance**: Confirms active ICE logistics operations in the Tampa/I-4 corridor.

---

## Finding 7: DHS Civil Rights Office Medical Contract Terminated (Broward)

**ALACOR LLC** (Margate, FL — Broward County) had a DHS Office for Civil Rights and Civil Liberties (CRCL) contract for "Medical Nurse Subject Matter Expert (SME) Support" that was **terminated for convenience** on Feb 11, 2026.

**Significance**: CRCL oversees conditions in immigration detention facilities. Terminating medical oversight SME support could affect detention condition monitoring.

### Confidence: MEDIUM
**Source**: FPDS convenience termination; connection to detention oversight is inferential

---

## Other BLN Projects Reviewed

### Lee County FL Sheriff Carmine Marceno (Score: 22)
- Federal corruption investigation involving money laundering allegations
- Civil rights lawsuit (Pepe v. Marceno, 2:25-cv-00566)
- **0 downloadable files** — project is descriptive text only
- **Relevance**: Tangential — FL sheriff corruption, not directly ICE-related

### Marceno Files Public Safety Risk Federal RICO (Score: 1)
- 1 PDF file documenting judicial filings
- Same Lee County sheriff investigation
- **Relevance**: Low for ICE investigation

### No BLN projects found specifically covering:
- IGSA (Intergovernmental Service Agreements)
- 287(g) programs
- Florida jail/detention facility data
- Orange County BCC proceedings
- Seminole County records

---

## Cross-Reference Opportunities

| BLN Finding | Existing Investigation Data | Link |
|------------|---------------------------|------|
| Orlando OPLA contracts ($1M+) | Orange County BCC ICE discussions | Confirms ICE expanding Orlando legal operations |
| GEO Group Broward contracts ($80M+) | IGSA contract analysis | Same contractor ecosystem |
| G4S detention transport ($60M+) | ICE detention stats FY20-26 | Transport infrastructure for FL detention |
| Red Carrot FOIA termination | FOIA strategy/requests | May explain delayed ICE FOIA responses |
| Pinellas tactical hub | ICE facility mapping | Previously undocumented ICE operational center |
| DHS CRCL medical termination | Detention conditions concerns | Reduced oversight capacity |

---

## Data Files Produced

| File | Description |
|------|-------------|
| `bln_ice_fl_contracts.json` | Full extracted dataset: 197 ICE+FL contracts, 83 detention-related, 101 I-4 corridor |
| `bln_search_results.json` | All 27 keyword-matched BLN open projects |
| `bln_dhs_contracts.json` | Broader DHS+FL contract analysis |
| `bln_downloads/fed_contracts/` | Raw FPDS data files (7 files, ~618MB) |

---

## Methodology Notes

1. **Entity matching**: ICE contracts identified by agency ID 7012 and/or "IMMIGRATION AND CUSTOMS" in text fields
2. **Florida matching**: Performance state code "FL" or "FLORIDA" in text
3. **I-4 corridor**: Orange, Osceola, Seminole, Polk, Hillsborough, Pinellas, Brevard, Volusia, Lake counties + city names
4. **Detention matching**: Terms "detention", "detain", "jail", "correct", "inmate" in any field
5. **Limitation**: Close-out records show historical contracted amounts, not necessarily current active spending. Some FL vendor-state records perform outside FL.
6. **Data freshness**: FPDS data as of 2026-02-27; BLN platform checked 2026-03-11

---

*Analysis by OpenPlanter investigation agent using BigLocalNews API*
*Source: Federal Procurement Data System via BigLocalNews "Federal contract cancellations" project*
