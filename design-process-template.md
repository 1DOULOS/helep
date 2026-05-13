# L4 Design Process Document — HELEP (Template)

> Fill every section. Keep total length ~5 pages. Marks rest on **traceability**: every architectural choice must trace back to a requirement, driver, or constraint from the SRS.

---

## 1. Project Specification

Restate the HELEP problem in your own words (≤ 150 words). Identify primary users (citizens, responders, police, admin) and the business value.

## 2. Requirements Analysis

### 2.1 Functional requirements (from SRS §2)

| # | Requirement | Source line (SRS §2) |
|---|-------------|----------------------|
| F1 | … | … |

### 2.2 Non-functional requirements

For each NFR in SRS §3 (Availability, Usability, Confidentiality, Integrity, Reliability, Scalability, Compatibility), write **one measurable acceptance criterion** (e.g. "99% of SOS notifications delivered within 1 s under 100 req/s").

### 2.3 Constraints (SRS §4)

Restate each constraint and predict the architectural risk it imposes.

## 3. Architectural Drivers & ASRs (Lecture 1 material)

Identify the **3 most architecturally significant requirements** and justify why. For each ASR show:
- Quality attribute


## 4. Component Identification (Lecture 4 step)

### 4.1 SRS-listed components
List the components from SRS.

### 4.2 Your service decomposition
You will build **5 services**. Show your mapping (which SRS components collapse into which service) and **justify each merge or split**.


## 5. Architectural Style — Choice & Justification (Lecture 2)

Microservices + Event-Driven are **prescribed**. Defend the choice against **two alternatives** (e.g. monolith, layered, SOA, serverless). For each alternative answer:
- Could it satisfy our top ASRs? Where would it struggle?
- What is the dominant trade-off?

Cite the SRS NFRs you considered.

## 6. Architectural Patterns Applied (Lecture 3 material)

List patterns used in your build. Minimum: the 6 implemented in the starter (Saga, Pub/Sub, Repository, Strategy, Outbox-lite, Circuit-Breaker) + 2 of your own. For each:
- Pattern name
- Where it appears (file:line)
- What problem it solves in HELEP

> A separate `patterns-template.md` is provided for the dedicated patterns doc — this section may summarise and link.

## 7. Architecture Decision Records (ADRs)

Author **3 ADRs** using the format below.

```
# ADR-NNN: <decision title>
## Context
## Decision
## Consequences
## Alternatives Considered
```

Suggested ADR topics:
- Kafka partition count and keying strategy (why `incident_id` as the key, why 3 partitions)
- SQLite per service vs shared Postgres
- Helm umbrella vs separate charts

## 8. Trade-offs & Improvement Perspectives

Identify the **3 weakest points** of your current architecture and propose concrete fixes (don't implement — just argue).

## 9. Submission checklist

- [ ] Every section above completed
- [ ] At least 3 diagrams (mermaid / drawio / hand-drawn scan acceptable)
- [ ] Every choice traced to an SRS line, an NFR, or an ASR
- [ ] 3 ADRs included
- [ ] Word count ~2000–3000
