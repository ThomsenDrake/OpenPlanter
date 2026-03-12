# Recursive Investigation Findings V2: I-4 Corridor ICE Deep Dive
**Date:** March 11, 2026  
**Analysis Type:** Multi-phase recursive cross-reference of existing datasets  
**Status:** Complete (Phases 1-4)  
**Supersedes:** RECURSIVE_FINDINGS.md (Phase 1-2 only)

---

## Executive Summary

This recursive investigation extracted **maximum intelligence** from existing datasets while PRR responses from county sheriff's offices are processing. Across four phases of analysis, we performed:

- **197 ICE FL contracts** analyzed for vendor networks, facility mapping, and financial flows
- **506 additional DHS FL contracts** mined for hidden connections
- **9 county agreement portfolios** cross-referenced for rate patterns and structural taxonomy
- **14 MuckRock FOIA PDFs** integrated for agreement verification
- **Complete evidence chain audit** across all 9 I-4 corridor counties

### Top-Line Discoveries

| # | Finding | Confidence | Source |
|---|---------|------------|--------|
| 1 | **$946M total ICE FL contract value** in FPDS, 97.3% detention | HIGH | FPDS analysis of 197 contracts |
| 2 | **Counties subsidize 53.3% of actual detention costs** (~$18.9M/year across I-4 corridor) | MEDIUM-HIGH | Financial model from IGA rates vs estimated costs |
| 3 | **Contract acceleration: FY2024 = $384M** (double FY2023's $188M) | HIGH | FPDS fiscal year analysis |
| 4 | **"Phantom county" debunked**: Palm Beach $56M = GEO Group HQ artifact, not local detention | HIGH | Description analysis: Denver/Aurora facility |
| 5 | **BOA sequence 70CDCR18G: 27 of 29 county numbers still unmapped** | HIGH | Only #15 (Sarasota) and #16 (Walton) confirmed |
| 6 | **G4S → Allied Universal transition invisible in FPDS** — 0 Allied contracts found | HIGH | Vendor search across 197 records |
| 7 | **Pinellas = dual-role hub**: detention + OFTP tactical (22 tactical contracts, $5.2M) | HIGH | Contract prefix + description analysis |
| 8 | **Seven distinct agreement types** form ICE's FL legal architecture | HIGH | IGA/IGSA/BOA/MOA/MOU/CDF/287(g) taxonomy |
| 9 | **Osceola/Seminole $56.71/day rate unchanged for 22 years** since 2004 | HIGH | IGA transcription text |
| 10 | **Krome SPC supported by 9+ contracts** including telecom, x-ray, fitness, power | HIGH | Cross-prefix FPDS analysis |

---

## Methodology

### Recursive Analysis Method
Each finding was used to generate new queries against other datasets, creating evidence chains:

```
Phase 1: FPDS vendor extraction → vendor network mapping → contract family grouping
Phase 2: IGA transcription comparison → rate timeline construction → subsidy calculation
Phase 3: FL footprint atlas → phantom county identification → HQ artifact disambiguation
Phase 4: Financial flow model → evidence completeness audit → gap identification
```

### Data Sources Analyzed

| Source | Records | Description |
|--------|---------|-------------|
| bln_ice_fl_contracts.json | 197 | ICE FL contracts from FPDS close-outs |
| bln_dhs_contracts.json | 506 | Non-ICE DHS FL contracts |
| Broader DHS data | 7,934 | All DHS FL contracts in BLN dataset |
| IGA Transcriptions (5) | — | Hillsborough, Osceola, Seminole, Pinellas, Orange |
| MuckRock FOIA docs | 14 PDFs | Polk (7), Sarasota (3), Walton (2), Broward (1) |
| PSL-Resources | 7 docs | BOA analysis, Demings letters, rebooking docs |
| ICE Detention Stats | FY20-26 | Nationwide facility data |
| TRAC database | — | 287(g) cross-reference, detainer time series |

---

## Finding 1: ICE Florida Footprint Atlas

### County-Level Spending Map (FPDS Performance Locations)

| County | Contracts | Total Obligated | ICE Divisions Present | Status |
|--------|-----------|----------------|----------------------|--------|
| Broward | 11 | $82,300,354.94 | Detention, HSI, IT | Known detention (GEO CDF) |
| Palm Beach | 2 | $56,123,417.93 | Detention, HSI | **GEO HQ artifact** — Denver facility |
| Miami-Dade | 11 | $50,286,233.86 | Detention, HSI, IT | Known detention (Krome SPC) |
| Pinellas | 22 | $5,228,003.92 | Tactical, HSI | Known detention + **OFTP tactical hub** |
| Orange | 3 | $1,039,311.44 | Tactical, IT | Known detention (IGSA) |
| Hillsborough | 2 | $935,246.00 | Tactical, HSI | Known detention (IGSA) |
| Lee | 2 | $922,592.26 | Tactical, HSI | Equipment vendors only |
| Bay | 1 | $301,160.13 | IT | Equipment vendor only |
| Volusia | 1 | $37,787.40 | Detention prefix | Equipment vendor (night vision) |
| St. Lucie | 1 | $4,640.00 | HSI | Equipment vendor only |
| Duval | 1 | $13,094.82 | Tactical | Equipment vendor only |

### Methodological Finding: Vendor HQ Artifact
**Critical for data interpretation:** When a contract's performance location matches the vendor's business address (17 of 57 FL contracts), the "Florida" performance location may reflect the vendor's headquarters, not an actual FL operational facility. The GEO Group ($56M in Palm Beach County) is the most significant example — those funds support the Denver/Aurora facility in Colorado, not Florida detention.

**Source:** Contract description analysis of 70CDCR24FR0000001  
**Confidence:** HIGH

---

## Finding 2: Financial Flow Model

### Total ICE FL Contract Value: $946,040,418.30

| Category | Value | % of Total |
|----------|-------|------------|
| Detention (70CDCR) | $920,873,501.91 | 97.3% |
| Tactical/Weapons (70CMSW) | $13,618,916.48 | 1.4% |
| IT Infrastructure (70CTD0) | $7,104,319.98 | 0.8% |
| Investigations (70CMSD) | $4,410,576.83 | 0.5% |
| Legacy (HSCE) | $33,103.10 | 0.0% |

### I-4 Corridor Per-Diem Revenue Model

| County | Rate/Day | Est. Beds | Actual Cost/Day | Daily Subsidy | Annual ICE Revenue | Annual County Subsidy |
|--------|----------|-----------|-----------------|---------------|-------------------|---------------------|
| Orange | $88.00 | 130 | $180.00 | $92.00 | $4,175,600 | $4,365,400 |
| Hillsborough | $88.00 | 200 (est.) | $165.00 (est.) | $77.00 | $6,424,000 | $5,621,000 |
| Pinellas | $85.00 | 100 (est.) | $170.00 (est.) | $85.00 | $3,102,500 | $3,102,500 |
| Osceola | $56.71 | 50 (est.) | $150.00 (est.) | $93.29 | $1,034,958 | $1,702,543 |
| Seminole | $56.71 | 75 (est.) | $160.00 (est.) | $103.29 | $1,552,436 | $2,827,564 |
| Polk | $25.00 | 30 (est.) | $140.00 (est.) | $115.00 | $273,750 | $1,259,250 |
| **TOTAL** | | | | | **$16,563,244** | **$18,878,256** |

**Counties absorb 53.3% of actual detention costs.** ICE pays less than half the true cost of detention in the I-4 corridor.

**Confidence:** HIGH for known rates (Orange confirmed $88/day, actual $180/day from PSL-Resources); MEDIUM for estimated bed counts and costs for non-Orange counties.

**Source:** IGA transcriptions, PSL-Resources/IGSA Analysis.md, Demings letters

---

## Finding 3: Contract Acceleration

### ICE FL Contract Origination by Fiscal Year

| Fiscal Year | Contracts | Total Value | Vendors | Detention | Tactical | Investigations | IT |
|-------------|-----------|-------------|---------|-----------|----------|----------------|-----|
| FY2018 | 3 | $23,666,909 | 1 | 3 | 0 | 0 | 0 |
| FY2019 | 5 | $25,358,041 | 3 | 3 | 1 | 1 | 0 |
| FY2020 | 26 | $114,607,345 | 7 | 4 | 1 | 2 | 19 |
| FY2021 | 29 | $131,110,031 | 8 | 5 | 0 | 2 | 22 |
| FY2022 | 15 | $73,610,025 | 7 | 5 | 0 | 1 | 9 |
| **FY2023** | **45** | **$188,555,554** | **16** | **10** | **3** | **8** | **24** |
| **FY2024** | **48** | **$384,215,111** | **19** | **12** | **12** | **11** | **13** |
| FY2025 | 16 | $4,884,300 | 9 | 0 | 12 | 4 | 0 |

**Key pattern:** FY2023-2024 saw explosive growth — $572M across 93 contracts, versus $368M across 78 contracts in FY2018-2022 combined. The FY2025 data shows only tactical/investigations activity with zero new detention contracts, consistent with DOGE cancellations beginning February 2025.

**Source:** FPDS contract ID fiscal year encoding (characters 7-8)  
**Confidence:** HIGH

---

## Finding 4: GEO Group National Facility Portfolio (from FPDS)

| Facility | Contracts | Total Obligated | Location |
|----------|-----------|----------------|----------|
| Broward Transitional Center | 2 | $81,787,341 | Pompano Beach, FL |
| South Texas Detention Complex | 3 | $164,254,734 | Pearsall, TX |
| Northwest ICE Processing Center | 2 | $142,270,596 | Tacoma, WA |
| Mesa Verde ICE Processing Center | 2 | $57,183,779 | Bakersfield, CA |
| Denver/Aurora CDF | 1 | $56,009,253 | Aurora, CO (HQ: Boca Raton, FL) |
| Montgomery Processing Center | 1 | $36,813,530 | Conroe, TX |
| Adelanto ICE Processing Center | 1 | — | CA (de-obligation) |
| Rio Grande Detention Center | 1 | $6,796,406 | Laredo, TX |

**GEO Group's Boca Raton HQ means their FL vendor state artificially inflates Florida contract counts.** Of $713M in GEO contracts, only $81.8M (Broward) operates in Florida.

**Source:** FPDS description and performance location analysis  
**Confidence:** HIGH

---

## Finding 5: G4S → Allied Universal Transition Gap

G4S Secure Solutions was acquired by Allied Universal in 2021. However:

- **All 20 G4S contracts** in FPDS still bear the G4S name (through FY2024)
- **Zero "Allied Universal" contracts** found in the dataset
- G4S transport contracts span FY2018-FY2024 across LA, Sacramento, Phoenix, Atlanta, San Antonio, and Harlingen AORs
- Annual G4S contract value: ~$19-29M/year

**Implication:** Either (a) ICE continues using the legacy G4S corporate name in FPDS, (b) Allied Universal operates under the G4S subsidiary name, or (c) the transport contract structure changed post-acquisition in ways not visible in close-out data.

**Source:** Vendor name search across all 197 ICE FL contracts  
**Confidence:** HIGH (for the observation); MEDIUM (for the interpretation)

---

## Finding 6: Agreement Structure Taxonomy

Seven distinct legal instruments form ICE's Florida detention architecture:

| Type | Rate | Counties | Key Feature |
|------|------|----------|-------------|
| **IGSA** | $56.71 - $88/day | Orange, Hillsborough, Osceola, Pinellas, Sarasota | Direct bilateral; individually negotiated |
| **BOA** | $25/day (national) | 29 FL counties (FY2018 batch) | Standardized; no volume guarantee |
| **USMS IGA** | $56.71/day | Seminole (John E. Polk) | Pass-through; different funding stream |
| **MOA** | N/A (cooperation) | Polk, Sarasota, Walton | Supplements BOA with operational terms |
| **MOU** | Varies | Polk (2007, 2014) | Predecessor format; largely superseded |
| **CDF** | ~$96.5M/FY contract | Broward (GEO Group) | Private operator; highest cost |
| **287(g)** | N/A (authority) | 9 I-4 corridor counties | Enforcement authority, not detention |

**Finding within the finding:** Polk County has the most complex agreement structure — 7 documents spanning 3 agreement types (MOU + BOA + MOA), creating a layered legal framework unique among I-4 corridor counties.

**Source:** IGA transcriptions, MuckRock FOIA documents, PSL-Resources  
**Confidence:** HIGH

---

## Finding 7: BOA Contract Number Sequence

### Known Mappings in 70CDCR18G Series
| Number | County | Source |
|--------|--------|--------|
| 70CDCR18G00000015 | Sarasota County Sheriff | MuckRock FOIA (opclaudia) |
| 70CDCR18G00000016 | Walton County Sheriff | MuckRock FOIA (opclaudia) |

### 29-County BOA Pool (from PSL-Resources)
Bay, Brevard, Charlotte, Columbia, DeSoto, Flagler, Hernando, Highlands, **Hillsborough**, Indian River, Lake, Lee, Manatee, Martin, Monroe, Nassau, Okaloosa, **Orange**, **Osceola**, **Palm Beach**, Pasco, **Pinellas**, **Polk**, **Sarasota**, **Seminole**, St. Johns, St. Lucie, **Volusia**, **Walton**

Bold = also have IGSA/IGA or 287(g) (dual-agreement counties)

**Only 2 of 29 BOA numbers mapped (6.9%).** The remaining 27 county-to-number mappings require additional FOIA responses or FPDS awards data (not just close-outs).

---

## Finding 8: Krome SPC Supply Chain

Nine contracts support Krome Service Processing Center operations:

| Contract | Vendor | Service | Value |
|----------|--------|---------|-------|
| 70CDCR21FR0000025 | Akima Global Services | Detention operations | $50,049,270 |
| 70CTD024FC0000024 | Optivor Technologies | Telecom/VoIP | $74,040 |
| 70CTD024FC0000025 | Optivor Technologies | Telecom/VoIP | $37,614 |
| 70CTD024FC0000027 | Optivor Technologies | Telecom/VoIP | $30,360 |
| 70CDCR24P00000027 | EOLA Power LLC | UPS maintenance | $9,339 |
| 70CDCR24P00000018 | Leidos Security D&A | X-ray maintenance | $6,200 |
| 70CDCR23P00000028 | Leidos Security D&A | X-ray maintenance | $5,800 |
| 70CDCR23P00000037 | Action Target Inc | Range maintenance | $19,600 |
| 70CDCR22P00000038 | Action Target Inc | Range maintenance | $19,600 |

**Total Krome-associated: $50,251,823** (99.6% = Akima operations contract)

---

## Finding 9: Evidence Chain Completeness Audit

| County | Evidence Score | Key Gaps |
|--------|--------------|----------|
| Hillsborough | 62% (5/8) | Bed cap unknown; actual cost unknown (PRR pending) |
| Orange | 67% (6/9) | IGSA text pending (PRR-158704); termination deadline March 13 |
| Osceola | 43% (3/7) | Bed cap unknown; actual cost unknown; no PRR filed |
| Seminole | 40% (2/5) | Actual cost unknown (PRR pending); bed cap unknown |
| Pinellas | 43% (3/7) | Rate unconfirmed in agreement text; bed cap/cost unknown |
| Polk | 60% (3/5) | Actual cost unknown; BOA contract number unidentified |
| Broward | 80% (4/5) | Private contract rate unknown |
| Sarasota | 75% (3/4) | — |
| Walton | 75% (3/4) | — |

**What pending PRRs will fill:**
- **Hillsborough Sheriff PRR** → Actual detention costs, bed counts, IGSA amendment history
- **Seminole Sheriff PRR** → Actual detention costs, USMS IGA amendment history
- **Orange County PRR-158704** → Full IGSA text, rebooking documentation, ICE correspondence
- **Volusia Sheriff PRR** → 287(g) agreement text, any detention activity

---

## Finding 10: Master Timeline

| Date | Event | Source |
|------|-------|--------|
| 1983 | Hillsborough IGSA signed at $40/day | IGA transcription |
| 1997 | Orange County IGSA signed | PSL-Resources |
| 2003 | Sarasota IGSA signed | MuckRock FOIA |
| 2004 | Osceola IGSA + Seminole USMS IGA at $56.71/day | IGA transcriptions |
| 2007 | Polk County first MOU with ICE | MuckRock FOIA #75988 |
| 2010 | Seminole County 287(g) activated | TRAC data |
| 2014 | Hillsborough rate → $70/day; Polk MOU renewed | IGA + MuckRock |
| **2018** | **29 FL counties sign BOAs (70CDCR18G series)** | PSL-Resources + MuckRock |
| 2019 | Hillsborough → $80/day; Polk/Sarasota MOAs signed | IGA + MuckRock |
| 2021 | G4S acquired by Allied Universal; Akima $50M Krome | Public records + FPDS |
| 2023 | **Contract acceleration begins** (FY23-24: $572M) | FPDS analysis |
| 2024 | Hillsborough + Orange both reach $88/day | IGA + PSL-Resources |
| Oct 2024 | GEO Group Broward: $96.5M contract | FPDS |
| Feb 2025 | DOGE contract cancellations begin | BLN data |
| Jan 2026 | Orange County ends rebooking (effective March 1) | PSL-Resources |
| Feb 2026 | Demings ultimatum letters | PSL-Resources |
| March 1, 2026 | Orange County rebooking ends | PRR-158704 |
| March 9, 2026 | PRR requests acknowledged by 4 county sheriffs | foia_prr_tracking.csv |
| **March 13, 2026** | **Orange County IGSA DEADLINE** | Demings letters |

---

## Recursive Threads: What Each Finding Unlocked

```
FPDS vendor list (48 vendors)
  → GEO Group deep dive → 8 facility locations mapped nationally
  → G4S timeline → Allied Universal acquisition gap identified
  → ADS frequency (16 contracts) → Pinellas OFTP hub discovered
  → Optivor (64 contracts) → ICE office footprint mapping capability
  → C&C International (26 contracts) → cross-division vendor overlap

IGA rate comparison
  → Osceola/Seminole $56.71 identity → coordinated rate or USMS baseline hypothesis
  → Orange/Hillsborough $88 convergence → rate ceiling evidence
  → BOA $25/day floor → subsidy calculation ($115-155/day county gap)
  → 40-year Hillsborough timeline → longest continuous IGSA in FL

BOA contract numbers (Sarasota #15, Walton #16)
  → Sequential numbering → 29 predicted numbers (1-29+)
  → Cross-reference with FPDS → 17 counties with zero FPDS presence (dormant BOAs?)
  → 10 BOA counties with dual agreements (IGSA + BOA)

FL performance locations (57 contracts, 11 counties)
  → Vendor HQ artifact discovery → Palm Beach debunked as phantom
  → Volusia night vision vendor → not hidden detention
  → Lee County equipment → HSI field office presence

Financial flow model
  → $18.9M annual county subsidy estimate → fiscal pressure point mapping
  → 53.3% county cost absorption → unsustainability argument
  → Orange $4.4M/year → strongest documented fiscal pressure
```

---

## Deliverables Produced

| File | Type | Description |
|------|------|-------------|
| RECURSIVE_FINDINGS_V2.md | Analysis | This document - comprehensive findings |
| ice_entity_map.json | Entity Map | 25 entities, 18 relationships |
| vendor_network_map.json | Entity Map | Tiered vendor network |
| contract_chain_analysis.json | Entity Map | Contract family linkages |
| recursive_phase3_results.json | Data | Footprint atlas, timeline, BOA reconstruction |
| recursive_phase4_results.json | Data | Financial model, taxonomy, evidence audit |
| recursive_analysis_results.json | Data | Phase 1 vendor network, multi-agency vendors |
| recursive_phase2_results.json | Data | Phase 2 IGA cross-references |

---

## Known Limitations

1. **FPDS close-out data only** — We have contract close-outs and cancellations, not active awards. Active contract values may differ.
2. **Bed count estimates** — Only Orange County (130 beds from Demings letters) has a confirmed bed count. All others are estimates.
3. **Actual detention costs** — Only Orange County ($180/day from PSL-Resources) has a confirmed actual cost. County subsidies for other counties are estimated.
4. **Web access unavailable** — Sunbiz corporate registry, property appraiser, and ICE FOIA reading room searches could not be performed due to API limitations.
5. **BOA contract numbers** — Only 2 of 29 mapped. Additional FOIA responses needed for the remaining 27.

---

## Next Actions (When PRR Responses Arrive)

1. **Cross-reference PRR response rates against IGA transcription rates** — Verify no discrepancies
2. **Extract actual bed counts and costs from each county response** — Update financial model
3. **Look for BOA contract numbers in county responses** — Map more of the 70CDCR18G series
4. **Check for rebooking practices in non-Orange counties** — Key policy question
5. **When web access restored:** Sunbiz lookups for GEO Group FL entities, EOLA Power LLC, Optivor Technologies; Orange County Property Appraiser for 8660 Transport Drive
