# user-service

Identity + credibility + emergency contacts.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/signup` | – | `{phone, password, role}` → `{id, token}` |
| POST | `/login` | – | `{phone, password}` → `{id, token}` |
| GET | `/me` | Bearer | profile |
| POST | `/contacts` | Bearer | add emergency contact |
| GET | `/contacts` | Bearer | list emergency contacts |
| GET | `/healthz` | – | liveness |
| GET | `/readyz` | – | readiness (pings Kafka) |
| GET | `/metrics` | – | Prometheus |

Emits: `user.registered`.

Run locally:
```bash
pip install -r requirements.txt
KAFKA_BOOTSTRAP=localhost:9092 JWT_SECRET=dev DB_PATH=./user.db uvicorn app.main:app --port 8001
```
