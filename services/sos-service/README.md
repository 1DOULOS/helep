# sos-service

SOS trigger, simulated media capture, cancellation.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/sos` | Bearer | `{lat, lon, mode, media_ref?}` → `{incident_id, status}` |
| POST | `/sos/{id}/cancel` | Bearer | victim cancels active SOS |
| GET | `/sos/{id}` | – | incident detail |
| GET | `/healthz` `/readyz` `/metrics` | – | platform |

Emits: `sos.triggered`, `sos.cancelled`.

Notes:
- Media is **simulated**: a filename like `sim://incident/{id}/blob.bin` is stored. Real audio/video upload is out of scope of the exercise.
- `mode=offline` represents SMS-fallback delivery in the SRS; here it just labels the event.

Run locally:
```bash
pip install -r requirements.txt
KAFKA_BOOTSTRAP=localhost:9092 JWT_SECRET=dev DB_PATH=./sos.db uvicorn app.main:app --port 8002
```
