# dispatch-service

Localize victim, pick nearest responder, emit assignment. Enforces SRS constraints:
- "Single response at any moment in time" → `busy=1` atomic claim on the responders row.
- "No two responders for one SOS" → assignments PK on `incident_id`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/responders/confirm` | `{incident_id, responder_id}` — responder acks |
| GET | `/healthz` `/readyz` `/metrics` | platform |

Consumes: `sos.triggered`, `sos.cancelled`.
Produces: `responder.assigned`, `responder.confirmed`, `safety.zone.entered`.

Patterns:
- Strategy: `app/matching.py` (`MATCHER=nearest|credibility`)
- Saga middle step (choreography)
- Repository: `app/db.py`

Seed data: 3 responders + 1 danger zone (Buea-ish coordinates). Replace freely.

Run locally:
```bash
pip install -r requirements.txt
KAFKA_BOOTSTRAP=localhost:9092 DB_PATH=./dispatch.db uvicorn app.main:app --port 8003
```
