# HELEP — Capstone Source Tree

This folder is what a **student** receives at the start of the 24-hour exercise.

```
helep/
├── Lecture Notes Software Architecture Orchestration with K8s Mini Project Specifications.pdf   ← read this first
├── architecture-overview.md                   ← lecturer reference (not given to student)
├── design-process-template.md                 ← Part G template (you fill it in)
├── patterns-template.md                       ← Part H template (you fill it in)
├── docker-compose.dev.yml                     ← dev-only smoke test, NOT graded
└── services/
    ├── user-service/         (port 8001, FastAPI)
    ├── sos-service/          (port 8002)
    ├── dispatch-service/     (port 8003)
    ├── notification-service/ (port 8004)
    └── analytics-service/    (port 8005)
```

## What's wired in the starter code

- HTTP server + per-service ports
- `/healthz`, `/readyz`, `/metrics` on every service
- Structured JSON logs (`structlog`)
- Env-var config (`KAFKA_BOOTSTRAP`, `DB_PATH`, `JWT_SECRET`, `SERVICE_PORT`, `MATCHER`)
- SQLite per service + auto-migration on startup
- Apache Kafka producer + consumer-group reader via `aiokafka` (`app/events.py`)
- Saga skeleton across `sos` → `dispatch` → `notification`
- Strategy pattern for responder matching (`dispatch-service/app/matching.py`)
- Circuit-breaker class stub — you must complete the state machine (see `patterns-template.md` Part A.6)

## What's NOT in the starter (this is your work)

- Dockerfile per service
- Helm umbrella chart + sub-charts
- Kubernetes manifests (Deployment, Service, Ingress, ConfigMap, Secret, HPA, PVC, NetworkPolicy)
- Kafka cluster via Strimzi Operator (Kafka CR + KafkaTopic CRDs)
- Prometheus + Grafana stack
- CI/CD pipeline
- The two PDFs (design + patterns)
- Demo video

## Quick local smoke test (dev only)

```bash
docker compose -f docker-compose.dev.yml up --build
# in another shell:
curl -X POST localhost:8001/signup -H 'content-type: application/json' \
     -d '{"phone":"+237600000001","password":"hunter22","role":"citizen"}'
# -> { "id": "...", "token": "eyJ..." }
TOKEN=...
curl -X POST localhost:8002/sos -H "authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' \
     -d '{"lat":4.0500,"lon":9.7700,"mode":"online"}'
# tail notification-service logs to see the simulated SMS line:
docker compose -f docker-compose.dev.yml logs -f notification-service
# police stats:
curl localhost:8005/stats/events
curl localhost:8005/stats/zones
```

If the saga works in compose, the K8s version is just packaging.

## Submission

See **Section "Submission"** of the brief. https://forms.gle/9QCvLTMV3CSZpxPc8.
