# notification-service

Simulated SMS / push. Real gateway is **out of scope** — delivery = a `structlog` line + a row in `notifications`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notifications?limit=50` | latest notifications (newest first) |
| GET | `/healthz` `/readyz` `/metrics` | platform |

Consumes: `responder.assigned`, `safety.zone.entered`, `sos.triggered` (offline mode only).
Produces: `notification.sent`.

Run locally:
```bash
pip install -r requirements.txt
KAFKA_BOOTSTRAP=localhost:9092 DB_PATH=./notif.db uvicorn app.main:app --port 8004
```
