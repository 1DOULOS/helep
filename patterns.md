# L3 Patterns-in-Code Document — HELEP

**Student:** 1DOULOS  
**Project:** HELEP — Emergency Location & Emergency Response Platform  
**Date:** 2026-05-13

---

## Part A — Pre-implemented patterns

### A.1 Choreographed Saga

**Where:** `sos-service/app/main.py` → `dispatch-service/app/main.py` → `notification-service/app/main.py`

The saga coordinates an emergency response across three services without a central orchestrator:

1. `sos-service` (`main.py:416`) — `trigger()` inserts the incident row, then publishes `sos.triggered` keyed on `incident_id`.
2. `dispatch-service` (`main.py:702`) — `handle_sos()` consumes `sos.triggered`, selects a free responder via the Strategy pattern, atomically reserves the responder, and publishes `responder.assigned`.
3. `notification-service` (`main.py:1060`) — `on_event()` consumes `responder.assigned` and `safety.zone.entered`, logs simulated SMS/push delivery, persists a row, and emits `notification.sent` to close the chain.

**Compensation step:** When the victim calls `POST /sos/{id}/cancel`, `sos-service` sets the incident status to `CANCELLED` (`db.py:628`) and publishes `sos.cancelled`. `dispatch-service` `handle_cancel()` (`main.py:736`) then calls `release_assignment()` which:
- Sets `assignments.status = RELEASED`  
- Sets `responders.busy = 0`  
and publishes `responder.confirmed` with `status=RELEASED`.

**Rollback trigger:** The `sos.cancelled` Kafka event (topic keyed by `incident_id`).

---

### A.2 Pub/Sub via Apache Kafka

**Where:** `app/events.py` in every service — `AIOKafkaProducer` + `AIOKafkaConsumer` (`aiokafka`).

**Consumer group semantics:** Each service registers a named consumer group (e.g. `"dispatch-service"`, `"notification-service"`). With `enable_auto_commit=False` (`events.py:100`), the consumer only calls `await consumer.commit()` **after** the handler returns without exception (`events.py:112`). If the handler raises, the offset is not committed, so the broker re-delivers the message on the next poll cycle — achieving **at-least-once delivery**. Handlers are written to be idempotent (e.g. `dispatch-service/db.py:978` checks for an existing assignment row before inserting) so re-delivery is safe.

**Partition keying:** Every saga-critical `publish(...)` call passes `key=incident_id` (`events.py:226`). Kafka hashes the key to a partition, ensuring all events for a single incident land on the **same partition**. Within a consumer group only one pod owns a given partition at any moment. This guarantees ordering (sos.triggered arrives before responder.assigned for the same incident) and prevents two dispatch pods from both claiming a responder for the same SOS — the "no double-dispatch" invariant.

---

### A.3 Repository

**Where:** `app/db.py` in every service — exposes named functions (`insert_incident`, `all_free_responders`, `reserve_responder_for`, etc.) that hide all SQL and connection management behind a clean interface.

**Why:** If route handlers queried SQLite directly they would embed connection boilerplate and SQL strings throughout business logic. Testing would require a live database for every handler test. The Repository centralises the schema knowledge and makes it possible to swap the storage engine (e.g. SQLite → PostgreSQL with a PVC) without touching the service layer.

Example — `dispatch-service/db.py:969` `reserve_responder_for()` encapsulates an atomic `UPDATE … WHERE busy=0` that prevents double-dispatch. The caller in `main.py:714` simply calls `reserve_responder_for(pick["id"], iid)` and checks the boolean return — no SQL leaks into the service layer.

---

### A.4 Strategy

**Where:** `dispatch-service/app/matching.py`

Three concrete strategies implement the `Matcher` protocol:

| Class | Algorithm | Line |
|---|---|---|
| `NearestMatcher` | Haversine minimum distance | `matching.py:31` |
| `CredibilityWeightedMatcher` | `credibility / (distance_km + 1)` score | `matching.py:42` |
| `RoundRobinMatcher` | Rotate through pool by class-level counter | `matching.py:57` (added) |

**How to switch:** The `MATCHER` env-var (`matching.py:75`) selects the algorithm at startup:  
- `MATCHER=nearest` (default) → `NearestMatcher`  
- `MATCHER=credibility` → `CredibilityWeightedMatcher`  
- `MATCHER=round_robin` → `RoundRobinMatcher`

**Added third strategy — `RoundRobinMatcher`:**

```python
class RoundRobinMatcher:                                    # matching.py:57
    _index: int = 0  # class-level counter, shared across instances

    def pick(self, victim_lat, victim_lon, responders):
        rs = list(responders)
        if not rs:
            return None
        r = rs[RoundRobinMatcher._index % len(rs)]  # line A.4-added-1
        RoundRobinMatcher._index += 1               # line A.4-added-2
        return {"id": r["id"], "slot": RoundRobinMatcher._index - 1}
```

Round-robin is useful when all units are similarly positioned and fair workload distribution matters more than minimising travel time (e.g., a dense city grid where any unit arrives in under 2 minutes).

---

### A.5 Outbox-lite

**Where:** `sos-service/app/main.py` `trigger()` — lines `421–433`

```python
insert_incident(iid, claims["sub"], body.lat, body.lon, body.mode, media_ref)  # DB write
await publish("sos.triggered", {...}, key=iid)                                   # then publish
```

The DB write happens first in the same async block. If `publish` fails, the incident is already persisted and can be replayed. If the process crashes after the DB write but before Kafka acknowledges, the operator can re-trigger from the DB row — no event is silently dropped.

**Why "lite"?** A full Outbox pattern stores the pending event as a row in an `outbox` table inside the same DB transaction, then a background poller reads and publishes it. That guarantees exactly-once publication even if the process crashes between the write and the publish call. Our "lite" version relies on `acks="all"` + `enable_idempotence=True` on the Kafka producer (`events.py:179`) and manual retry to recover — acceptable for a 24-hour build but insufficient for production SLA where lost SOS events cannot be tolerated.

---

### A.6 Circuit Breaker — completed

**Where:** `app/events.py` `class CircuitBreaker` in all five services.

**Completed state machine (`events.py:58–91` in user-service, identical in other services):**

```python
def allow(self) -> bool:
    if self.opened_at is None:          # CLOSED state — gate open
        return True
    elapsed = _time.monotonic() - self.opened_at
    if elapsed >= self.reset_after_s:  # HALF_OPEN — one probe allowed
        self.opened_at = None
        self.fails = self.fail_threshold - 1  # primed: one more fail → OPEN
        return True
    return False                        # OPEN state — reject

def record_success(self) -> None:
    self.fails = 0
    self.opened_at = None               # → CLOSED

def record_failure(self) -> None:
    self.fails += 1
    if self.fails >= self.fail_threshold and self.opened_at is None:
        self.opened_at = _time.monotonic()  # → OPEN
```

**State transitions:**

| State | Condition | On `record_failure` | On `record_success` |
|---|---|---|---|
| **CLOSED** (`opened_at is None`) | allow all | increment `fails`; if ≥ threshold → **OPEN** | reset `fails` |
| **OPEN** (`opened_at` set, elapsed < `reset_after_s`) | reject all | — | — |
| **HALF_OPEN** (`opened_at` set, elapsed ≥ `reset_after_s`) | allow one probe | → **OPEN** (re-arms `opened_at`) | → **CLOSED** |

The breaker wraps every `publish()` call (`events.py:226`). If Kafka is unreachable, five consecutive failures trip the breaker to OPEN, giving Kafka 10 s to recover before one probe is attempted.

---

## Part B — Patterns added (minimum 2)

### B.1 Idempotency Key (EAA — *Idempotent Receiver*)

**Where:** `dispatch-service/app/db.py:969–987` `reserve_responder_for()`

```python
cur = c.execute(
    "UPDATE responders SET busy = 1 WHERE id = ? AND busy = 0", (rid,)
)
if cur.rowcount == 0:
    return False
try:
    c.execute(
        "INSERT INTO assignments (incident_id, responder_id, status) VALUES (?, ?, 'ASSIGNED')",
        (incident_id, rid),
    )
except sqlite3.IntegrityError:          # PRIMARY KEY violation → already assigned
    c.execute("UPDATE responders SET busy = 0 WHERE id = ?", (rid,))
    return False
return True
```

**Problem it solves in HELEP:** Kafka delivers at-least-once. If the broker re-delivers `sos.triggered` (e.g. after a consumer restart before commit), `handle_sos` would be called again for the same incident. Without the idempotency key, a second responder could be reserved and a duplicate `responder.assigned` event emitted, causing two units to rush to the same scene while another SOS goes unserved. The `incident_id PRIMARY KEY` on the `assignments` table makes the handler idempotent: the second invocation hits the `IntegrityError` path and aborts cleanly.

**Trade-off vs. Kafka transactional producer:** A transactional producer with `transactional.id` would guarantee exactly-once delivery at the broker level, eliminating the need for application-level idempotency checks. The trade-off is significantly higher broker configuration complexity and a ~10 ms latency overhead per batch. The DB-level check is sufficient for our SLA target (< 1 s end-to-end) while remaining simpler to operate.

---

### B.2 Bulkhead (Cloud-Native Catalogue — *Bulkhead*)

**Where:** Consumer group configuration — one group per service, declared in `dispatch-service/app/main.py:748`, `notification-service/app/main.py:1087`, `analytics-service/app/main.py:45`.

```python
# dispatch-service/main.py:748
asyncio.create_task(consume(["sos.triggered", "sos.cancelled"], "dispatch-service", on_event))

# notification-service/main.py:1087
asyncio.create_task(consume(
    ["responder.assigned", "safety.zone.entered", "sos.triggered"],
    "notification-service", on_event,
))

# analytics-service/main.py:45
asyncio.create_task(consume(STREAMS, "analytics-service", on_event))
```

**Problem it solves in HELEP:** If all services shared a single consumer group, a slow `analytics-service` (running expensive zone-aggregation queries) would delay offset commits for **all** consumers, starving `dispatch-service` of `sos.triggered` events and increasing response time. Separate groups provide isolation: analytics can lag without affecting dispatch throughput. This is the Bulkhead pattern — each service is its own failure compartment, preventing a bottleneck in one from cascading into others.

**Trade-off vs. single-group fan-out:** A single group with filtered topic subscriptions would consume fewer broker resources. The trade-off is coupling: one slow consumer blocks all. Separate groups cost one extra consumer-group session per service (negligible) but provide full isolation.

---

## Part C — Anti-patterns avoided

**Anti-pattern avoided: Shared Database**

**File demonstrating avoidance:** Each service has its own `app/db.py` with a service-specific `DB_PATH` env-var:
- `user-service/app/db.py:274` → `/data/user.db`  
- `dispatch-service/app/db.py:906` → `/data/dispatch.db`  
- `notification-service/app/db.py:1244` → `/data/notification.db`  
etc.

No service imports or references another service's `db.py`. Cross-service state flows exclusively via Kafka events, not shared tables.

**Why this matters:** A shared database would couple all services to a single schema. A migration on the `responders` table for dispatch-service would require downtime or coordination with user-service and analytics-service. Deployment independence — a core microservices benefit — would be lost. Per-service SQLite (backed by separate PVCs in Kubernetes) keeps schema ownership strictly within each service boundary.

---

*Submit as `patterns.pdf`.*
