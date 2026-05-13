"""Apache Kafka producer + consumer helpers (aiokafka).

Patterns:
  - Pub/Sub (Kafka topics + consumer groups)
  - Outbox-lite (publish + db-write live in same async block in main.py)
  - Circuit Breaker (completed below — CLOSED/OPEN/HALF_OPEN state machine)

Partition keying:
  Every saga-critical publish should pass key=<incident_id> (or <user_id>).
  Same-key events land on the same partition, preserving ordering and ensuring
  the "no double dispatch" invariant holds even with multi-replica consumers
  (one partition is owned by one consumer at a time inside a group).
"""
from __future__ import annotations
import json
import os
import time as _time
from typing import Awaitable, Callable, Iterable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

_producer: AIOKafkaProducer | None = None


async def producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            enable_idempotence=True,
            acks="all",
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k else None,
        )
        await _producer.start()
    return _producer


async def stop_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def health() -> bool:
    """Liveness ping for /readyz — verify broker reachable + metadata fetch works."""
    try:
        p = await producer()
        await p.client.fetch_all_metadata()
        return True
    except Exception:
        return False


# ---- Circuit Breaker (completed) ----
class CircuitBreaker:
    """Three-state circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED.

    State transitions:
      CLOSED    (opened_at is None):  allow all calls; count failures.
      OPEN      (opened_at is set, elapsed < reset_after_s): reject all calls.
      HALF_OPEN (opened_at is set, elapsed >= reset_after_s): let one probe
                through. Success → CLOSED; failure → OPEN again.
    """

    def __init__(self, fail_threshold: int = 5, reset_after_s: float = 10.0):
        self.fail_threshold = fail_threshold
        self.reset_after_s = reset_after_s
        self.fails = 0
        self.opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            # CLOSED state — gate is open
            return True
        elapsed = _time.monotonic() - self.opened_at
        if elapsed >= self.reset_after_s:
            # HALF_OPEN: allow one probe; prime so next failure reopens immediately
            self.opened_at = None
            self.fails = self.fail_threshold - 1
            return True
        # OPEN state — reject
        return False

    def record_success(self) -> None:
        # Any success resets to CLOSED
        self.fails = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.fails += 1
        # Trip to OPEN once threshold is crossed (only if not already open)
        if self.fails >= self.fail_threshold and self.opened_at is None:
            self.opened_at = _time.monotonic()


_breaker = CircuitBreaker()


async def publish(topic: str, event: dict, key: str | None = None) -> None:
    """Outbox-lite: caller should db-write THEN await publish() in same async block."""
    if not _breaker.allow():
        raise RuntimeError(f"circuit-open: {topic}")
    try:
        p = await producer()
        await p.send_and_wait(topic, value=event, key=key)
        _breaker.record_success()
    except Exception:
        _breaker.record_failure()
        raise


Handler = Callable[[dict], Awaitable[None]]


async def consume(topics: Iterable[str], group: str, handler: Handler) -> None:
    """Consumer-group reader. Manual commit only on successful handler (at-least-once)."""
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode()),
    )
    await consumer.start()
    try:
        async for msg in consumer:
            payload = msg.value
            payload["_stream"] = msg.topic  # preserved name for back-compat with handlers
            try:
                await handler(payload)
                await consumer.commit()
            except Exception:
                # leave un-committed → re-delivered on next read (at-least-once)
                pass
    finally:
        await consumer.stop()
