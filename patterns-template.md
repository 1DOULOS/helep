# L3 Patterns-in-Code Document — HELEP (Template)

> ~3 pages. Each pattern entry needs a **code citation** (`file:line`). No citation = no marks.

---

## Part A — Pre-implemented patterns

Identify and explain each pattern below as it appears in the starter code.

### A.1 Choreographed Saga
- **Where:** trace events from `sos-service/app/main.py` → `dispatch-service/app/main.py` → `notification-service/app/main.py`
- **Compensation step:** where, and what state is rolled back?
- **What event is the rollback trigger?**

### A.2 Pub/Sub via Apache Kafka
- **Where:** `app/events.py` in every service (`aiokafka` producer + consumer)
- **Consumer group semantics:** explain at-least-once + how manual `await consumer.commit()` AFTER handler success preserves the invariant (auto-commit is disabled)
- **Partition keying:** explain why `publish(..., key=incident_id)` matters for the saga (same-key events → same partition → ordering)

### A.3 Repository
- **Where:** `app/db.py` in every service
- **Why:** what would break if we let route handlers query SQLite directly?

### A.4 Strategy
- **Where:** `dispatch-service/app/matching.py`
- **How to switch:** environment variable `MATCHER`
- **Add a third strategy** (e.g. round-robin) and cite the lines you added

### A.5 Outbox-lite
- **Where:** `sos-service/app/main.py` `trigger()`
- **Why is this "lite"?** What would a real Outbox add?

### A.6 Circuit Breaker (stub → complete it)
- **Where:** `events.py` `class CircuitBreaker`
- **Task:** complete the `allow()` state machine (CLOSED → OPEN → HALF_OPEN) and cite the lines you added.
- Explain what triggers state transitions in your impl.

## Part B — Patterns you added (minimum 2)

For each pattern:
- Pattern name (GoF, EAA, or Cloud-Native catalogue)
- Where you added it (`file:line`)
- Problem it solves in HELEP
- Trade-off vs alternative pattern

### B.1 _your first pattern_

### B.2 _your second pattern_

## Part C — Anti-patterns avoided

Briefly call out **one anti-pattern** the architecture explicitly avoids (e.g. shared database across services, distributed monolith, synchronous fan-out) and cite the file that demonstrates the avoidance.

## Submission

Submit as `patterns.pdf`. Keep code excerpts ≤ 10 lines.
