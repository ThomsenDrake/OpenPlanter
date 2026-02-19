# OpenPlanter: User Journeys & Demo Scenarios

**The pitch: What if Palantir's power was accessed through conversation, not training manuals?**

Palantir requires forward-deployed engineers and weeks of onboarding. OpenPlanter flips this: **the agent is the interface**. You describe what you need in plain language, and the agent ingests data, builds the ontology, resolves entities, generates visualizations, and takes action -- all grounded in a structured knowledge graph you own and control.

---

## Demo 1: "Follow the Money" -- Investigative Journalism

**Persona**: Mara, an investigative journalist at a mid-size newsroom.

**Setup**: Mara has three data sources -- a leaked corporate registry CSV, a public campaign finance database, and a collection of 200 scanned PDFs of property deeds.

### The Journey

**Mara**: *"I have a CSV of shell companies from a leaked offshore registry, a public FEC campaign donations dataset, and a folder of scanned property deeds. I want to find connections between these -- specifically, are any politicians receiving donations from people who own shell companies?"*

**Agent**: *"I'll set this up for you. Here's my plan:*
1. *Ingest the CSV and map it to Company and Person entity types*
2. *Connect to the FEC API and pull donation records, mapping them to Donor, Recipient, and Donation entities*
3. *Run OCR + entity extraction on the 200 property deeds to pull out names, addresses, and company references*
4. *Run entity resolution across all three sources -- matching people by name variants, addresses, and known aliases*
5. *Build a link graph: Person --owns--> Company, Person --donated_to--> Politician, Person --owns_property--> Address*

*Should I proceed?"*

**Mara**: *"Yes."*

**[Time passes -- the agent works. Mara sees a progress feed.]**

**Agent**: *"Done. I've created 14,203 entities across the three sources. Entity resolution merged 847 duplicate persons across datasets. Here's what I found:*

*23 individuals appear in both the offshore registry and the FEC donation records. Of those, 7 donated more than $50,000 total to candidates in the same state where they hold property through shell companies.*

*I've generated a graph view focused on these 7 individuals. Want to see it?"*

**Mara**: *"Show me the graph for the top one."*

**[The canvas opens. A person node in the center, with edges fanning out to shell companies on one side and politicians on the other. Property addresses cluster below. Each node is clickable, showing provenance -- which source it came from, confidence score from entity resolution.]**

**Mara**: *"Can you find any connections between these shell companies and the politicians' disclosed financial interests?"*

**Agent**: *"I'll cross-reference the shell company addresses and registered agents against the financial disclosure database. Give me a moment... Found 2 cases where a politician's disclosed real estate holdings share an address with a shell company owned by one of their donors. I've added these links to the graph in red."*

**Mara**: *"Generate a timeline of when the donations were made relative to when the shell companies were registered."*

**[A timeline view appears below the graph. Shell company registration dates on one track, donation dates on another. A clear pattern: donations spike 2-3 months after company registrations.]**

### What just happened

Mara never defined a schema. She never wrote a query. She never manually linked records. The agent:
- Built the ontology from her description of the domain
- Ingested structured, semi-structured, and unstructured data
- Resolved entities across sources with confidence scoring
- Found non-obvious connections through graph traversal
- Generated interactive visualizations on demand
- Answered follow-up questions by extending the graph in real time

---

## Demo 2: "What's Happening on the Ground?" -- Humanitarian Operations

**Persona**: David, operations coordinator for an NGO responding to a natural disaster.

**Setup**: 72 hours after a major earthquake. Data is flooding in from multiple systems -- none of them talk to each other.

### The Journey

**David**: *"We have our beneficiary registration database in Postgres, supply depot inventory spreadsheets from 12 field offices (all slightly different formats), a feed of GPS coordinates from our field teams' check-ins, satellite damage assessment imagery with tagged locations, and situation reports coming in as emails and WhatsApp messages. I need to know: where are the gaps? Where do we have people but no supplies reaching them?"*

**Agent**: *"I'll build a unified operational picture. Here's what I'll create:*

*Entity types: Beneficiary, Supply Depot, Field Team, Incident, Location, Supply Item*

*I'll:*
1. *Connect to your Postgres beneficiary DB directly*
2. *Normalize the 12 inventory spreadsheets into a common schema (I can see they vary in column naming -- I'll reconcile them)*
3. *Ingest GPS check-ins as Field Team location events*
4. *Map satellite damage assessments as Incidents at Locations*
5. *Extract structured data from sitrep emails/messages: who reported, what happened, where, what's needed*

*Then I'll overlay everything geospatially and identify coverage gaps."*

**[10 minutes later]**

**Agent**: *"Operational picture is live. Key findings:*

- *3,400 registered beneficiaries in the eastern district have no supply depot within 15km*
- *Field Team 7 hasn't checked in for 18 hours -- their last known position was near the heaviest damage zone*
- *Depot 4 has a 3-day insulin supply remaining but is serving an area with 200+ registered diabetic beneficiaries*
- *14 sitreps mention road blockages on Route 9, which is the primary supply corridor to depots 3, 4, and 6*

*I've flagged these as critical items. Want me to open the map?"*

**[The map view opens. Beneficiary clusters shown as heat maps. Supply depots as icons color-coded by days-of-supply remaining. Field team positions as moving dots. Damage zones from satellite imagery as shaded overlays. The coverage gaps glow red.]**

**David**: *"Can you draft a rerouting plan for supplies to reach the eastern district?"*

**Agent**: *"Based on the road blockage reports and available depot inventory, I recommend:*
1. *Redirect 40% of Depot 2's stock (which is over-supplied relative to local demand) via Route 12*
2. *Deploy Field Team 3 (currently in a low-need area) to the eastern district as forward distribution*
3. *Estimated travel time via Route 12: 4.5 hours*

*Want me to generate the logistics order and notify the relevant field teams?"*

**David**: *"Do it."*

**[The agent creates Action entities in the ontology -- a supply transfer order and a team redeployment directive -- and sends notifications to the field teams via the integrated messaging channel.]**

### What just happened

David went from chaos to an operational picture in 10 minutes. The agent:
- Handled wildly heterogeneous data sources (DB, spreadsheets, GPS, satellite, free text)
- Built domain-appropriate entities without David specifying a schema
- Performed geospatial analysis to identify coverage gaps
- Correlated unstructured reports (road blockages) with logistics implications
- Generated actionable recommendations grounded in the data
- Executed actions -- supply orders and team notifications -- directly from the platform

---

## Demo 3: "Why Do Our Machines Keep Breaking?" -- Manufacturing Operations

**Persona**: Lin, VP of Operations at a mid-size manufacturer with 3 plants.

**Setup**: Unplanned downtime is up 30% this quarter. Lin suspects a pattern but can't see across systems.

### The Journey

**Lin**: *"Connect to our SAP ERP, the Siemens IoT sensor feeds from all three plants, our maintenance ticketing system in ServiceNow, and the supplier quality reports we get as monthly PDFs. I want to understand why downtime is increasing."*

**Agent**: *"Connected to all four sources. I've mapped the following entity model:*

- *Machine (from SAP asset registry) -- 342 machines across 3 plants*
- *Sensor Reading (from Siemens IoT) -- 48M readings over last 6 months*
- *Maintenance Ticket (from ServiceNow) -- 1,847 tickets*
- *Supplier (from SAP) -- 89 suppliers*
- *Part (from SAP BOM) -- 2,100 unique parts*
- *Quality Report (from PDFs) -- 36 monthly reports, extracted*

*Entity resolution identified that SAP, ServiceNow, and Siemens use different IDs for the same machines. I've unified them. Building the analysis now..."*

**[A few minutes later]**

**Agent**: *"I found a pattern. Here's the story:*

*Downtime incidents cluster around 3 specific machine models: the X-200 press, the T-400 lathe, and the K-100 cutter. All three models share a common hydraulic pump assembly (Part #HP-2240) sourced from a single supplier: Meridian Components.*

*Cross-referencing with the extracted quality reports: Meridian's defect rate for HP-2240 jumped from 1.2% to 4.8% starting in Q3 -- the same quarter your downtime spiked. Their quality reports mention a 'raw material supplier change' in the June report.*

*Additionally, IoT sensor data shows that machines with HP-2240 pumps installed after July show abnormal vibration signatures 2-3 weeks before failure -- a detectable precursor.*

*Three recommendations:*
1. *Immediate: Flag all 47 machines with HP-2240 pumps installed after July for preventive maintenance*
2. *Short-term: Escalate to Meridian about the raw material change; demand corrective action*
3. *Long-term: I can set up an anomaly detection agent that monitors vibration signatures and auto-creates maintenance tickets when the precursor pattern appears*

*Want me to show the supply chain graph?"*

**[The graph view shows: Meridian Components --> HP-2240 --> [47 machines] --> [maintenance tickets clustered in time]. The timeline below shows the inflection point clearly.]**

**Lin**: *"Set up that anomaly detection agent."*

**Agent**: *"Done. The agent will:*
- *Monitor vibration sensor feeds every 15 minutes*
- *Compare against the failure precursor signature I identified*
- *Auto-create a ServiceNow maintenance ticket when confidence exceeds 85%*
- *Tag the ticket with the predicted failure mode and recommended action*
- *Notify the plant manager via Slack*

*It's running now. I'll also retroactively check all current HP-2240 machines and flag any showing early warning signs."*

### What just happened

Lin asked a vague question ("why is downtime increasing?") and got:
- Automated root cause analysis spanning 4 disconnected systems
- Entity resolution across different naming conventions
- Insight from unstructured PDFs that provided the causal link
- A predictive agent deployed in minutes, not months
- Closed-loop actions (maintenance tickets, notifications) flowing back to operational systems

---

## Demo 4: "Who Is This Person Really?" -- Fraud Investigation

**Persona**: Raj, fraud analyst at a regional bank.

**Setup**: A suspicious account application has come in. Raj needs to investigate.

### The Journey

**Raj**: *"New account application from a 'James Chen' at 450 Pine Street. Something feels off -- the address matches a known shell company location in our records. Pull everything we have and anything public."*

**Agent**: *"Searching across all connected sources for 'James Chen' and '450 Pine Street'...*

*Internal sources:*
- *3 existing accounts linked to 450 Pine Street (different names)*
- *1 previous SAR (Suspicious Activity Report) filed on one of those accounts*
- *The application SSN has a different name in our records from 2019*

*Public sources:*
- *450 Pine Street is registered to 'Pine Street Holdings LLC' (state corporate registry)*
- *Pine Street Holdings shares a registered agent with 4 other LLCs*
- *'James Chen' appears in business filings for 2 of those LLCs*
- *Property records show 450 Pine Street sold 3 times in 18 months*

*I've built an entity graph. The network contains 14 people, 6 companies, 3 addresses, and 23 accounts. Want to see it?"*

**[The graph opens. James Chen is at the center. Edges connect him to companies, which connect to other people, who connect to the flagged accounts. The SAR-flagged account glows yellow. The SSN mismatch is highlighted in red.]**

**Raj**: *"Score this network. How risky is it?"*

**Agent**: *"Risk assessment based on the graph topology and entity attributes:*

- *Identity inconsistency: SSN linked to different name (high risk)*
- *Address reuse: 3 accounts at same shell company address (high risk)*
- *Network density: 14 people sharing 3 addresses and 6 companies (indicative of layering)*
- *SAR proximity: Applicant is 2 hops from a SAR-flagged account (elevated risk)*
- *Property churning: 3 sales in 18 months at the linked address (elevated risk)*

*Composite risk score: 87/100. Recommend: decline the application and file a SAR.*

*I've drafted the SAR narrative based on the findings. Want to review it?"*

**Raj**: *"Yes, and flag all accounts in this network for enhanced monitoring."*

**Agent**: *"SAR narrative drafted and ready for your review. I've also:*
- *Applied enhanced monitoring tags to all 23 accounts in the network*
- *Set up an alert agent that will notify you if any new account applications, transactions over $5K, or address changes occur on any entity in this network*
- *Added the full investigation graph and findings to the case file"*

### What just happened

A fraud investigation that would normally take 2-3 days of manual searching across systems happened in a conversation. The agent:
- Searched across internal and public data sources simultaneously
- Built a complete entity network from fragments
- Identified risk indicators from graph structure (not just individual data points)
- Generated a compliance document (SAR narrative)
- Deployed ongoing monitoring as a persistent agent
- Took operational actions (tagging, alerting) within governed permissions

---

## The Common Thread: Agent-First Means...

Across all four demos, the pattern is the same:

1. **You describe the problem in natural language**, not in SQL, not in a config file, not by clicking through 15 menus.

2. **The agent builds the ontology for you**. It infers entity types, relationships, and mappings from your data and your description of the domain. You can refine it, but you don't start from scratch.

3. **The agent does the grunt work**. Data ingestion, format normalization, entity resolution, cross-referencing -- the tedious parts that take 80% of analyst time today.

4. **The agent finds what matters**. Graph traversal, anomaly detection, pattern matching, temporal analysis -- all grounded in the structured ontology, not hallucinated from training data.

5. **Visualizations are generated on demand**, not pre-built. The agent creates the right view (graph, map, timeline, dashboard) for the question you're asking, when you ask it.

6. **Actions close the loop**. The agent doesn't just show you insights -- it drafts the SAR, creates the maintenance ticket, sends the supply order, notifies the team. All governed by permissions and audit trails.

7. **Persistent agents keep watching**. You can deploy monitoring agents that run continuously against the ontology -- detecting anomalies, watching for new connections, alerting on changes -- without writing a single line of code.

---

## The 5-Minute Live Demo Script

For a live demo or pitch, here's a streamlined version that hits the key beats in 5 minutes:

### Setup (30 seconds)
*"Let me show you OpenPlanter. I have three CSV files -- one is a company registry, one is a list of financial transactions, and one is a list of people with their addresses. These could come from any source -- databases, APIs, documents -- but for this demo I'll keep it simple."*

### Act 1: Ingestion + Ontology (60 seconds)
*"I drag the files in and tell the agent: 'These are companies, transactions, and people. Connect them.'"*

The agent parses the files, infers the schema, creates entity types (Person, Company, Transaction), maps columns to properties, and builds relationships (person --works_at--> company, transaction --from--> person, transaction --to--> company).

*"I didn't define a schema. I didn't write a mapping config. The agent inferred it and I confirmed."*

### Act 2: Entity Resolution (45 seconds)
*"Notice the agent flagged something: 'Robert Smith' in the person list and 'R. Smith' in the transaction records probably refer to the same person -- same address, similar name. It resolved 34 duplicates across the three files, each with a confidence score."*

### Act 3: Discovery (60 seconds)
*"Now I ask: 'Are there any people who transact with more than 3 companies?' The graph view opens showing 5 people. I click one -- expand their connections -- and I can see the full network. I switch to map view and see where these entities are located. I switch to timeline and see when the transactions occurred."*

### Act 4: AI Analysis (45 seconds)
*"I ask: 'Anything unusual here?' The agent responds: 'One person, Sarah Liu, has small transactions with 7 different companies -- all registered in the same month at the same address. This pattern is consistent with structuring.' It highlights the subgraph."*

### Act 5: Action (45 seconds)
*"I say: 'Flag Sarah Liu's network for review and set up an alert if any new transactions appear.' Done. The agent creates the flag, sets up a persistent monitoring agent, and logs it to the audit trail. If new data comes in tomorrow that touches this network, I'll know."*

### Close (15 seconds)
*"That's OpenPlanter. From raw files to a structured knowledge graph, entity resolution, visual exploration, AI-powered analysis, and operational action -- all through conversation. Open source, self-hosted, your data stays yours."*

---

## What Makes This Different From "Just ChatGPT + a Database"

The question will come up. Here's the answer:

| | ChatGPT + Database | OpenPlanter |
|---|---|---|
| **Data model** | None -- LLM sees raw tables | Structured ontology with entity types, relationships, and provenance |
| **Entity resolution** | None -- "Robert Smith" and "R. Smith" are different strings | Built-in ML-powered ER with confidence scores and lineage |
| **Persistence** | Conversation context only | Permanent knowledge graph that grows over time |
| **Multi-source** | Manual joins, if at all | Automatic ingestion and resolution across sources |
| **Visualization** | Text descriptions or basic charts | Interactive graph, map, timeline, and dashboard views |
| **Grounding** | LLM might hallucinate connections | Every answer traceable to specific entities and sources in the ontology |
| **Actions** | Tell you what to do | Execute actions back to source systems with audit trail |
| **Collaboration** | Share a chat transcript | Shared ontology with RBAC, annotations, and workspaces |
| **Monitoring** | Ask the same question again tomorrow | Persistent agents watching the ontology 24/7 |

The ontology is the difference. ChatGPT can answer questions about data. OpenPlanter *understands* the domain -- entities, relationships, confidence, provenance -- and that understanding persists, grows, and can be acted upon.
