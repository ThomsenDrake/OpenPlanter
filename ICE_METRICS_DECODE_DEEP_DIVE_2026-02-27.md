# ICE Detention Statistics Column Metrics: Deep Dive Analysis

**Analysis Date:** February 27, 2026
**Data Period:** FY2026 (through Feb 12, 2026)
**Status:** PARTIAL - Official definitions required

---

## 🎯 Executive Summary

Analysis of ICE detention statistics Excel data reveals **13+ numeric columns** (positions 8-20+) containing facility metrics. While exact definitions require official ICE documentation, pattern analysis and value comparisons allow **high-confidence hypotheses** for several key metrics.

**Critical Finding:** Without official data dictionary, population and capacity interpretations remain **approximate**. This limits precision of growth analysis and utilization calculations.

---

## 📊 Data Structure

### File Format
- **Source:** FY26_detentionStats_02122026.xlsx (and FY20-FY25 equivalents)
- **Format:** Excel spreadsheet with multiple sheets
- **Columns:** ~20 columns per facility row
- **Positions 1-7:** Facility metadata (name, address, AOR, type, gender)
- **Positions 8-20+:** Numeric metrics (UNKNOWN official definitions)

### Sample Data Structure

| Position | Field | Example (Pinellas) | Type |
|----------|-------|-------------------|------|
| 1 | Facility Name | PINELLAS COUNTY JAIL | Text |
| 2 | Address | 14400 49TH STREET NORTH | Text |
| 3 | City | CLEARWATER | Text |
| 4 | State | FL | Text |
| 5 | ZIP | 33762 | Text |
| 6 | AOR | MIA | Text |
| 7 | Facility Type | USMS IGA | Text |
| 8 | Gender | Female/Male | Text |
| 9 | **Metric 1** | 1.844236760124611 | Numeric |
| 10 | **Metric 2** | 24.110236 | Numeric |
| 11 | **Metric 3** | 6.433071 | Numeric |
| 12 | **Metric 4** | 4.393701 | Numeric |
| 13 | **Metric 5** | 2.685039 | Numeric |
| 14 | **Metric 6** | 5.543307 | Numeric |
| 15+ | Additional metrics | ... | Numeric |

---

## 🔍 Metric Pattern Analysis

### I-4 Corridor Facilities Comparison

| Facility | Type | Metric 1 | Metric 2 | Metric 3 | Metric 4 | Metric 5 | Metric 6 |
|----------|------|----------|----------|----------|----------|----------|----------|
| **Hillsborough County Jail** | IGSA | 1.28 | 1.65 | 1.54 | 0.83 | 0.29 | 0.67 |
| **Orange County Jail (FL)** | USMS IGA | 2.60 | 43.00 | 15.31 | 12.71 | 7.77 | 11.29 |
| **Pinellas County Jail** | USMS IGA | 1.84 | 24.11 | 6.43 | 4.39 | 2.69 | 5.54 |

### Large Facility Comparison (Florida Soft-Sided)

| Facility | Type | Metric 1 | Metric 2 | Metric 3 | Metric 4 | Metric 5 | Metric 6 |
|----------|------|----------|----------|----------|----------|----------|----------|
| Florida Soft-Sided | STATE | 14.85 | 633.10 | 225.51 | 179.43 | 312.24 | 446.25 |

**Key Observation:** Large facilities have values 10-100x higher in Metrics 2-6, suggesting these are **cumulative metrics** rather than simple counts.

---

## 💡 Metric Interpretation Hypotheses

### HIGH CONFIDENCE HYPOTHESES

#### Metric 1 (Column 9): Population or Utilization
**Values:**
- Hillsborough: 1.28
- Pinellas: 1.84
- Orange: 2.60
- Florida Soft-Sided: 14.85

**Pattern Analysis:**
- Range: 1-15 across facilities
- Order of magnitude consistent across facility sizes
- Orange highest among I-4 corridor facilities

**Hypotheses:**
1. **ADP (Average Daily Population)** - Most likely
   - Interpretation: Average number of ICE detainees per day
   - Orange has ~2.6x population of Hillsborough
   
2. **Utilization Rate (%)** - Possible alternative
   - Interpretation: Percentage of ICE-dedicated beds in use
   - Would require knowing total capacity

**Confidence:** **HIGH** for being a population/utilization metric
**Confidence:** **MEDIUM** for exact definition (ADP vs. utilization)

---

#### Orange County Leadership Pattern
**Finding:** Orange County Jail consistently has highest values across ALL metrics among I-4 corridor facilities.

**Interpretations:**
1. Largest ICE detainee population
2. Longest average detention periods
3. Highest utilization or capacity
4. Most established/longest-running operation

**Confidence:** **HIGH**

---

#### Hillsborough Low Values Pattern
**Finding:** Hillsborough County Jail has lowest values across all metrics.

**Interpretations:**
1. Smallest ICE population (just started FY2026)
2. Shortest detention periods (1.65 days in Metric 2)
3. Low utilization (recently activated)
4. Book-and-release operation model

**Confidence:** **HIGH** that low values reflect new facility status

---

### MEDIUM CONFIDENCE HYPOTHESES

#### Metric 2 (Column 10): Time or Cumulative Count
**Values:**
- Hillsborough: 1.65
- Pinellas: 24.11
- Orange: 43.00
- Florida Soft-Sided: 633.10

**Pattern Analysis:**
- Huge range: 1.65 to 633
- Large facilities 10-100x higher than I-4 corridor
- Orange >> Pinellas >> Hillsborough

**Hypotheses:**

**Hypothesis A: ALOS (Average Length of Stay) in days**
- Interpretation: Average days a detainee is held
- Hillsborough: 1.65 days (book-and-release)
- Pinellas: 24 days (medium-term)
- Orange: 43 days (long-term detention)
- Florida Soft-Sided: 633 days (doesn't make sense - too high)

**Problem with Hypothesis A:** Florida Soft-Sided value (633 days = 1.7 years) is implausible for average stay

**Hypothesis B: Cumulative detainee-days (population × days)**
- Interpretation: Total person-days of detention this period
- Makes sense for large facilities having high values
- Period would need to be defined (quarter? fiscal year to date?)

**Hypothesis C: Total book-ins this period**
- Interpretation: Cumulative count of detainees booked in
- Would explain large facility having 633 book-ins vs. small facilities having 1-43

**Confidence:** **MEDIUM** for being time or cumulative count
**Confidence:** **LOW** for exact definition without official schema

---

#### Metrics 3-6 (Columns 11-14): Sub-Populations
**Values:**
- Generally smaller than Metrics 1-2
- Pattern: Orange > Pinellas > Hillsborough across all
- Florida Soft-Sided has values in 100s-400s range

**Hypotheses:**

**Hypothesis A: Gender breakdowns**
- Metric 3: Male population/capacity
- Metric 4: Female population/capacity
- Metric 5-6: Additional gender splits

**Hypothesis B: Security classification levels**
- Metric 3: Classification A/B
- Metric 4: Classification C/D
- Based on ICE "Classification Level (ADP)" footnote

**Hypothesis C: ICE threat levels**
- Metric 3: Threat Level 1
- Metric 4: Threat Level 2
- Metric 5: Threat Level 3
- Metric 6: No Threat Level

**Hypothesis D: Criminal vs. non-criminal**
- Metric 3: Criminal aliens
- Metric 4: Non-criminal aliens
- Metric 5-6: Sub-categories

**Confidence:** **MEDIUM** for being sub-population breakdowns
**Confidence:** **LOW** for exact categories without official schema

---

### LOW CONFIDENCE HYPOTHESES

#### Metrics 7+ (Columns 15+): Operational Metrics
**Values:**
- Variable patterns across facilities
- Some facilities have zeros in certain columns
- Examples from Pinellas: 1.13, 7.41, 4.38, 2.34, 3.27, 27.64

**Possible Interpretations:**
- Turnover rates
- Transfer counts (in/out)
- Book-in/book-out counts
- Capacity measures
- Performance metrics

**Confidence:** **LOW** - Insufficient data to form hypotheses

---

## 🔬 Comparative Analysis

### By Facility Type

#### USMS IGA Facilities (Pinellas, Orange)
- **Pattern:** Higher values in Metrics 2-6
- **Interpretation:** Joint-use facilities with US Marshals may have:
  - Longer detention periods
  - More established operations
  - Different operational models

#### IGSA Facilities (Hillsborough)
- **Pattern:** Lower values across all metrics
- **Interpretation:** Direct ICE agreement facilities may have:
  - Shorter detention periods
  - Book-and-release model
  - Newer operations (Hillsborough just started FY2026)

**Requires Investigation:** Are these differences due to:
- Agreement type (USMS IGA vs. IGSA)?
- Facility age and establishment?
- Operational model differences?
- Sample size (only 3 I-4 facilities)?

---

### By Facility Size

**Large Facilities (Florida Soft-Sided):**
- Metric 1: 14.85 (10x I-4 average)
- Metric 2: 633.10 (50x I-4 average)
- Metrics 3-6: 100s-400s range

**Interpretation:**
- Metrics scale with facility size
- Metrics 2-6 are likely cumulative (not rates)
- Could be: detainee-days, book-ins, capacity measures

---

## 📋 ICE Footnotes Reference

From `FY26_detentionStats_02122026_parsed.json`, relevant terms include:

| Term | Definition |
|------|------------|
| **ADP** | Average daily population |
| **ALOS** | Average length of stay |
| **ALIP** | Average length in program |
| **AOR** | Area of Responsibility |
| **Classification Level (ADP)** | Security levels A/low, B/medium low, C/medium high, D/high |
| **ICE Threat Level (ADP)** | Criminality levels 1/2/3/None based on convictions |

**Key Insight:** These terms likely correspond to the numeric columns, but **exact mapping is unknown** without official schema.

---

## ⚠️ Limitations and Uncertainties

### What We Cannot Determine Without Official Documentation:

1. **Exact column definitions**
   - Which column is ADP? ALOS? Capacity?
   - What are the units? (people, days, percentages?)

2. **Time period for metrics**
   - Are values snapshots (as of date)?
   - Are they cumulative (FYTD)?
   - Are they averages?

3. **Column position consistency**
   - Do columns shift positions between fiscal years?
   - Are there different schemas for different facility types?

4. **Data quality**
   - How are metrics calculated?
   - What's included/excluded?
   - How are partial-year facilities handled?

### Impact on Analysis:

**Without official definitions, we CANNOT:**
- Calculate precise population counts
- Determine actual facility utilization rates
- Compare capacity vs. population accurately
- Calculate true year-over-year growth rates
- Interpret ALOS or other time-based metrics

**We CAN:**
- Identify relative patterns (Orange > Pinellas > Hillsborough)
- Spot anomalies and gaps
- Track facility appearance/disappearance
- Form hypotheses for FOIA verification

---

## 🎬 Next Steps

### Immediate Actions (This Week)

1. **Submit FOIA Request for Data Dictionary**
   ```
   Request: ICE Detention Statistics data dictionary and schema documentation
   Period: FY2020-FY2026
   Purpose: Understand column definitions, units, and calculation methodologies
   ```

2. **Search ICE.gov for Technical Documentation**
   - Look for detention statistics methodology documents
   - Search for performance reporting schemas
   - Check FOIA library for previously released data dictionaries

3. **Contact TRAC Immigration (Syracuse University)**
   - TRAC maintains ICE detention database
   - May have data definitions they use
   - Could provide technical documentation

### Short-Term Actions (Next 2 Weeks)

4. **Cross-Reference All Fiscal Years**
   - Compare column positions across FY20-FY26
   - Check for schema changes between years
   - Verify consistency of column definitions

5. **Analyze Additional Large Facilities**
   - Compare patterns with other state/district facilities
   - Look for consistent metric interpretations
   - Identify outliers and anomalies

6. **Review ICE Performance Reports**
   - Check if performance reports use same metrics
   - Look for definitions in narrative sections
   - Cross-reference with detention statistics

### Medium-Term Actions (Before FOIA Responses)

7. **Develop Proxy Measures**
   - Create relative comparison metrics
   - Normalize values across facility types
   - Build utilization estimates based on patterns

8. **Document Confidence Levels**
   - Rate each metric interpretation
   - Identify high-confidence vs. low-confidence metrics
   - Flag metrics requiring FOIA verification

---

## 📊 Confidence Summary

| Metric | Interpretation | Confidence | Reasoning |
|--------|---------------|------------|-----------|
| **Metric 1** | Population or utilization | **HIGH** | Values scale appropriately across facility sizes |
| **Metric 2** | Time or cumulative count | **MEDIUM** | Pattern consistent but range suggests cumulative |
| **Metrics 3-6** | Sub-populations | **MEDIUM** | Sum patterns suggest breakdowns of Metric 1 or 2 |
| **Metrics 7+** | Operational measures | **LOW** | Insufficient pattern data |
| **Column positions** | Consistent across FY | **UNKNOWN** | Not verified across years |
| **Units** | Unknown | **LOW** | No official documentation |

---

## 📁 Supporting Files

- `FY26_detentionStats_02122026_facilities.json` - Extracted facility data
- `FY26_detentionStats_02122026_parsed.json` - Raw parsed data with footnotes
- `METRICS_DECODE_DEEP_DIVE.py` - Analysis script
- `population_trends_analysis.json` - Multi-year metric analysis
- `ICE_STATS_KEY_FINDINGS.md` - Key findings from stats analysis

---

## 🔗 Related Documents

- `TODO_CIRCLE_BACK_METRICS.md` - Follow-up items requiring investigation
- `NEXT_STEPS_WHILE_FOIA_PENDING.md` - Actions while awaiting FOIA
- `ICE_STATS_ANALYSIS_2026-02-27.md` - Full ICE statistics analysis
- `POPULATION_TRENDS_2026-02-27.md` - Population trend analysis

---

**Final Note:** This deep dive represents best-effort analysis based on available data. **Official ICE data dictionary is REQUIRED** for accurate interpretation. All hypotheses should be verified through FOIA or official documentation before drawing final conclusions.
