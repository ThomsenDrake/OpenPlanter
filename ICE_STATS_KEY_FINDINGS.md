Document-Type: brief
Canonical: no
Derived-From: ICE_STATS_ANALYSIS_2026-02-27.md
Last-Reviewed: 2026-02-27
Status: active
Contradictions-Tracked-In: I4_CORRIDOR_MASTER_INVESTIGATION.md

# ICE Detention Statistics: Key Findings Summary
**Analysis Date:** February 27, 2026
**Data Period:** FY2020-FY2026 (through Feb 12, 2026)

---

## 🎯 CRITICAL FINDING

**Only 3 of 9 I-4 corridor facilities are currently holding ICE detainees** according to official ICE detention statistics, despite 8 facilities having active 287(g) agreements.

---

## 📊 Facilities in ICE Detention Statistics

### Currently Active (FY2026)

| Facility | County | Type | First Year | Years Active |
|----------|--------|------|------------|--------------|
| **Pinellas County Jail** | Pinellas | USMS IGA | FY2021 | 6 years (FY21-FY26) |
| **Orange County Jail** | Orange | USMS IGA | FY2022 | 5 years (FY22, FY24-FY26) |
| **Hillsborough County Jail** | Hillsborough | IGSA | FY2026 | 1 year (NEW) |

---

## 🔍 Key Discoveries

### 1. Hillsborough County Jail - NEW in FY2026
- **First appeared:** FY2026 (started Oct 2025)
- **Address:** 1201 North Orient Road, Tampa, FL 33619
- **Type:** IGSA (direct ICE agreement, NOT USMS IGA)
- **Significance:** Only started holding ICE detainees AFTER 287(g) implementation (Feb 2025)
- **Note:** Orient Road Jail, not Falkenburg Road

### 2. USMS Joint-Use Pattern Confirmed
- **Pinellas & Orange** classified as **USMS IGA** facilities
- Hold USMS prisoners + ICE detainees + county inmates
- **Hillsborough** is **IGSA only** (different arrangement)

### 3. Missing Facilities
**Facilities with 287(g) but NOT in ICE detention stats:**
- Hillsborough County Falkenburg Road Jail (3,300 beds)
- Polk County Jail (Bartow)
- John E. Polk Correctional Facility (Seminole)
- Volusia County Branch Jail
- Volusia County Correctional Facility

**Why?** Possible explanations:
- Book-and-release only (short-term holding)
- Quick transfers to other facilities
- 287(g) for identification only, not detention
- Different funding/reporting arrangements

---

## 📈 Timeline Pattern

```
FY2020: No I-4 corridor facilities
FY2021: Pinellas County Jail appears
FY2022: Orange County Jail added
FY2023: Only Pinellas (Orange gap)
FY2024: Orange returns (with "(FL)" suffix)
FY2025: Same as FY2024
FY2026: Hillsborough added (NEW)
```

---

## 🏢 Facility Type Breakdown

| Type | Facilities | Description |
|------|-----------|-------------|
| **USMS IGA** | 2 | Joint-use with US Marshals Service |
| **IGSA** | 1 | Direct ICE intergovernmental agreement |
| **287(g) only** | 6 | Have agreements but not in detention stats |

---

## 📍 Geographic Distribution

**Currently holding ICE detainees:**
- Tampa Bay: Hillsborough, Pinellas (2 facilities)
- Orlando: Orange (1 facility)

**NOT currently holding ICE detainees (despite 287(g)):**
- Lakeland/Bartow: Polk County
- Sanford: Seminole County
- Daytona Beach: Volusia County

---

## 📋 Address Verification

### Orange County Jail Address Discrepancy
- **ICE Stats:** 3855 South John Young Parkway, Orlando
- **Previous Docs:** 3723 Vision Blvd, Orlando
- **Explanation:** John Young = booking/intake; Vision Blvd = main facility

---

## 📁 Data Files Generated

1. **ICE_STATS_ANALYSIS_2026-02-27.md** - Full analysis report
2. **i4_facilities_all_years.json** - All facility records by year
3. **i4_facilities_grouped.json** - Facilities grouped by name
4. **FY##_detentionStats_facilities.json** - Individual year extractions

---

## ✅ Confidence Levels

- **CONFIRMED** (Official ICE statistics): 3 facilities currently holding detainees
- **PROBABLE** (287(g) agreements): 6 additional facilities with authority but not currently holding
- **REQUIRES INVESTIGATION**: Why 287(g) facilities don't appear in detention stats

---

## 🎬 Next Steps

1. Extract population data (ADP, ALOS, capacity) from Excel files
2. Analyze year-over-year trends
3. Investigate non-appearing 287(g) facilities
4. Cross-reference with FOIA responses
5. Update main ice_facilities_i4_corridor.json

---

## 📞 Questions Raised

1. Why did Orange County Jail disappear from FY2023 stats?
2. Why does Hillsborough use IGSA while Pinellas/Orange use USMS IGA?
3. What happens to ICE detainees at 287(g) facilities not in detention stats?
4. Are Polk/Seminole/Volusia facilities holding detainees under different arrangements?
5. What's the relationship between 287(g) agreements and actual ICE detention?

---

**Source:** ICE Detention Statistics FY2020-FY2026
**URL:** https://www.ice.gov/detain/detention-management
**Downloaded:** February 26, 2026
