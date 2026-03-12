# Recursive Investigation Plan: I-4 Corridor ICE Detention Deep Dive
**Date:** March 11, 2026  
**Status:** Active  
**Trigger:** PRR responses from county sheriff's offices acknowledged; window for recursive investigation

---

## What "Recursive" Means Here

Each finding generates new queries. Each new query generates new findings. We follow chains until they dead-end or produce actionable intelligence. The goal is to extract maximum value from existing data and open-source intelligence while PRR responses are in processing.

---

## Recursion Threads

### Thread 1: Vendor Network Recursion (FPDS → Corporate → Cross-Contract)
**Starting point:** 48 unique ICE FL vendors from FPDS data  
**Recursion logic:**
- For each key vendor → search FL corporate registrations (Sunbiz.org)
- For each vendor → search FPDS for ALL their federal contracts (not just ICE)
- For each corporate officer → cross-reference with other entities
- For each vendor address → check property records, other tenants

**Priority vendors:**
1. GEO Group Inc. (largest detention contractor)
2. G4S Secure Solutions (detention transport)
3. EOLA Power LLC (Krome SPC maintenance)
4. Price Modern LLC (Orlando OPLA furniture)
5. Akima Global Services (DHS support)

### Thread 2: Address/Property Recursion
**Starting point:** Key addresses from findings
- 8660 Transport Drive, Orlando (planned ICE Processing Center)
- 1201 Orient Road, Tampa (Hillsborough Orient Road Jail)
- 211 Eslinger Way, Sanford (John E. Polk Correctional)
- 3723 Vision Blvd, Orlando (Orange County Jail)

**Recursion logic:**
- Property appraiser records → owner → owner's other properties
- Building permits → contractors → other government projects
- Zoning changes → timeline of facility planning
- Corporate owner → Sunbiz registration → officers → other entities

### Thread 3: Contract Number Chain Recursion
**Starting point:** Known contract/agreement numbers
- USMS IGA 18-04-0023 (Orange County)
- USMS IGA 18-04-0024 (Seminole/Polk)  
- BOA 70CDCR18G00000015 (Sarasota)
- BOA 70CDCR18G00000016 (Walton)
- 70CDCR24FR0000053 (GEO/Broward)

**Recursion logic:**
- Contract prefix patterns → identify all contracts in same series
- Modification history → trace amendments and rate changes
- Referenced documents in contracts → pull underlying agreements
- Vendor in one contract → all contracts with that vendor

### Thread 4: Cross-County Pattern Recursion
**Starting point:** What we know from Orange County IGSA crisis
**Recursion logic:**
- Orange County pays $88/day → what do other I-4 counties pay?
- Orange County capped at 130 beds → what are caps elsewhere?
- Orange County ended rebooking → is rebooking happening elsewhere?
- Demings sent ultimatum letters → have other counties?

### Thread 5: ICE FOIA Reading Room / Published Data Recursion
**Starting point:** Contract numbers and facility names
**Recursion logic:**
- Search ICE FOIA reading room for previously released documents
- Search USCIS/DHS reading rooms
- Check MuckRock for related FOIA requests
- Search DocumentCloud for uploaded ICE documents

### Thread 6: Financial Flow Mapping
**Starting point:** Known rates and contract values
**Recursion logic:**
- Federal appropriations → ICE ERO budget → detention allocation → per-facility
- Per-diem rates across counties → identify anomalies
- County budgets → detention line items → compare to reimbursement
- Vendor revenue from ICE → proportion of total vendor revenue

---

## Execution Priority

1. **Thread 5** (FOIA reading rooms) - fastest, purely digital
2. **Thread 1** (Vendor recursion) - Sunbiz + FPDS cross-reference
3. **Thread 2** (Address/property) - Orange County Property Appraiser
4. **Thread 3** (Contract chains) - pattern analysis on existing data
5. **Thread 4** (Cross-county) - news + public data
6. **Thread 6** (Financial flows) - county budgets + federal data

---

## Expected Deliverables

1. `RECURSIVE_FINDINGS.md` - Master findings document
2. `vendor_network_map.json` - Vendor entity network
3. `contract_chain_analysis.json` - Contract linkage chains
4. `property_ownership_chain.json` - Property ownership traces
5. Updated wiki entries for new data sources discovered
