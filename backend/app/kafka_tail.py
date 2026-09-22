"""Tails the ospf.* Kafka topics into the UI live feed. Separate from bus.py's producer: this is
a real consumer reading back what was published, for the Kafka tab. Fail-soft: if Kafka is down
or unreachable, the tab just shows nothing instead of crashing the backend."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque

from .config import settings
from .events import publish as ui_publish

log = logging.getLogger("ospf.kafka_tail")

KAFKA_CHANNEL = "__ospf_kafka__"
RECENT: deque[dict] = deque(maxlen=200)
COUNTS: dict[str, int] = {}


def topics() -> list[str]:
    return [settings.topic_events, settings.topic_snapshots, settings.topic_config]


def _decode(raw: bytes | None):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw.decode(errors="replace")


async def run_forever() -> None:
    if not settings.kafka_bootstrap:
        return
    from confluent_kafka import Consumer, KafkaException

    consumer = Consumer({
        "bootstrap.servers": settings.kafka_bootstrap,
        "group.id": f"ospf-ui-tail-{uuid.uuid4().hex[:8]}",  # unique + ephemeral: always tails from "latest"
        "auto.offset.reset": "latest",
        "enable.auto.commit": False,
    })
    try:
        consumer.subscribe(topics())
        while True:
            msg = await asyncio.to_thread(consumer.poll, 1.0)
            if msg is None:
                continue
            if msg.error():
                log.warning("kafka consume error: %s", msg.error())
                continue
            item = {
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset(),
                "key": msg.key().decode() if msg.key() else None,
                "value": _decode(msg.value()),
            }
            RECENT.appendleft(item)
            COUNTS[item["topic"]] = COUNTS.get(item["topic"], 0) + 1
            ui_publish(KAFKA_CHANNEL, "kafka", json.dumps(item, default=str))
    except asyncio.CancelledError:
        raise
    except KafkaException as exc:  # noqa: BLE001
        log.warning("kafka tail stopped: %s", exc)
    finally:
        consumer.close()
