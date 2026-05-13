# analytics-service

Sink: consumes every event stream, aggregates incidents per zone, exposes the **police view** stats.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/stats/zones` | per-zone hit count |
| GET | `/stats/crime` | recent incident lat/lon/mode (heatmap source) |
| GET | `/stats/events` | event counts by stream (sanity check) |
| GET | `/healthz` `/readyz` `/metrics` | platform |

Consumes: all 7 helep streams.
Produces: nothing.

Run locally:
```bash
pip install -r requirements.txt
KAFKA_BOOTSTRAP=localhost:9092 DB_PATH=./analytics.db uvicorn app.main:app --port 8005
```
