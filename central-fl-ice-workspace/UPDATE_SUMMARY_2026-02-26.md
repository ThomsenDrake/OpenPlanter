# Investigation Update: USMS Agreement Documents 2022 (OCR)

**Update Date:** February 26, 2026  
**Document Reviewed:** USMS-Agreement-Documents-2022_OCR.md  
**Facility Updated:** Orange County Jail / Orange County Correctional Facility (ORANGE-001)

---

## Summary

A comprehensive USMS (U.S. Marshals Service) Agreement OCR document from 2022 was reviewed and integrated into the investigation records. This document provides significant new details about the Orange County Correctional Facility's dual-use status and operational framework.

---

## Key New Information Added

### 1. **Facility Identification**
- **USMS Facility Code:** 4CM
- **USMS Agreement Number:** 18-04-0023
- **Physical Address:** 3723 Vision Blvd, Orlando, FL 32839
- **Original Agreement Date:** 1983 (40+ years of operation)

### 2. **Joint-Use Status**
The facility is now classified as **IGSA / USMS Joint-Use** because it simultaneously holds:
- U.S. Marshals Service prisoners (federal pretrial, witnesses, etc.)
- ICE detainees
- Orange County inmates

### 3. **Financial Details**
- **Reimbursement Rate:** $88/day (same for both USMS and ICE)
- **2022 Modification #3** effective February 1, 2022

### 4. **ICE-Specific Documentation**
The USMS OCR document contains dedicated ICE sections:
- **ICE Task Order / Invoice Instructions** (pages 31-38)
- **ICE ORSA MOU + 1982 IGA Schedule** (pages 67-73)

### 5. **2022 Operational Modifications**
The facility's 2022 modification includes updates to:
- COVID-19 protocols and infectious disease procedures
- PREA (Prison Rape Elimination Act) compliance
- Restrictive housing and suicide prevention standards
- Pregnant or post-partum prisoner handling
- Video teleconferencing capabilities
- Voter registration procedures
- Body camera information requests

---

## Files Updated

### 1. `ice_facilities_i4_corridor.json`
**Updated fields for ORANGE-001:**
- `address` → Added physical street address (3723 Vision Blvd) and mailing address
- `alternative_names` → Added "Orange County Correctional Facility"
- `facility_type` → Changed from "IGSA" to "IGSA / USMS Joint"
- `usms_facility_code` → "4CM" (new field)
- `usms_agreement_number` → "18-04-0023" (new field)
- `usms_agreement_date` → "1983" (new field)
- `usms_modification_number` → "3" (new field)
- `usms_modification_effective_date` → "2022-02-01" (new field)
- `usms_per_diem_rate` → "$88/day" (new field)
- `joint_use_status` → "Holds USMS prisoners, ICE detainees, and county inmates" (new field)
- `evidence_chain` → Added USMS OCR document as primary evidence source
- `metadata.data_sources` → Added "USMS Agreement Documents 2022 (OCR)"

### 2. `findings.md`
**Updated sections:**
- Orange County Jail entry (Section 5) → Added USMS facility code, agreement details, joint-use status, 2022 modifications
- Methodology → Added USMS Agreement Documents 2022 to Primary Sources list

---

## Implications for Investigation

### 1. **Dual-Agency Complexity**
The Orange County facility operates under a more complex framework than initially documented, with three distinct prisoner populations (county, USMS, ICE) each with different legal statuses and procedural requirements.

### 2. **Long-Term Federal Partnership**
The 1983 original agreement (40+ years) indicates a well-established federal-local partnership that predates many modern immigration enforcement frameworks.

### 3. **ICE Billing Transparency**
The inclusion of ICE-specific task order and invoice instructions (pages 31-38) in a USMS agreement document suggests:
- ICE detainees may be billed through USMS infrastructure
- ICE has standardized procedures for this facility
- Financial tracking may be more transparent than at single-use facilities

### 4. **Regulatory Compliance**
The 2022 modification's inclusion of PREA compliance, restrictive housing standards, and COVID-19 protocols indicates ongoing regulatory oversight and modernization.

---

## Evidence Chain

**Claim:** Orange County Correctional Facility holds ICE detainees under a joint-use agreement with USMS.

**Evidence:**
1. **Source:** USMS Agreement Documents 2022 (OCR), USMS-Agreement-Documents-2022_OCR.md
2. **Date Accessed:** 2026-02-26
3. **Confidence Level:** Confirmed
4. **Details:**
   - USMS IGA 18-04-0023, Modification #3, effective February 1, 2022
   - Facility Code 4CM
   - ICE Task Order/Invoice Instructions documented in pages 31-38
   - ICE ORSA MOU and 1982 IGA Schedule in pages 67-73
   - Physical address: 3723 Vision Blvd, Orlando, FL 32839
   - Per-diem rate: $88/day for both USMS and ICE

---

## Next Steps

1. **Cross-Reference Check:** Verify if other I-4 corridor facilities have similar USMS joint-use agreements
2. **FOIA Target:** Request USMS agreement documents for other facilities to identify additional joint-use operations
3. **Financial Analysis:** Investigate whether ICE detainees are billed through USMS channels at other facilities
4. **Capacity Analysis:** Determine if joint-use status affects ICE capacity allocations

---

## Related Documents

- `ice_facilities_i4_corridor.json` - Updated facility records
- `findings.md` - Updated investigation report
- `USMS-Agreement-Documents-2022_OCR.md` - Source document (73 pages)
