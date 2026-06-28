"""Gateway MQTT bridge.

Dumb nodes (ESP32, Arduino-via-serial-gateway, LoRa) cannot hold a device
token or speak TLS+JSON to the cloud. They publish tiny readings to a LOCAL
MQTT broker; this bridge maps each `node_id` to a ledger subject + event kind
(via node-map.yaml) and forwards an EnvelopeIn to the local SiteIQ agent,
which owns the durable outbox + server upload. This is the concrete form of
the rule "everything dumber sits behind a gateway."

    pip install paho-mqtt pyyaml requests
    python mqtt_bridge.py --broker localhost --map node-map.yaml --agent http://127.0.0.1:9099
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt  # type: ignore
import requests
import yaml  # type: ignore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_envelope(node_id: str, payload: dict, mapping: dict, defaults: dict) -> dict | None:
    node = mapping.get(node_id)
    if node is None:
        return None
    # subject_id can be fixed or pulled from a payload field (e.g. RFID badge).
    subject_id = node.get("subject_id")
    if not subject_id and node.get("subject_id_field"):
        subject_id = str(payload.get(node["subject_id_field"], node_id))
    return {
        "subject_type": node["subject_type"],
        "subject_id": subject_id or node_id,
        "kind": node["kind"],
        "client_event_id": uuid.uuid4().hex,
        "occurred_at": _now_iso(),
        "payload": {**payload, "node_id": node_id},
        "confidence": float(node.get("confidence", defaults.get("confidence", 0.8))),
        "source": defaults.get("source", "sensor"),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="SiteIQ gateway MQTT bridge")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", default="siteiq/sensors/#")
    p.add_argument("--map", default="node-map.yaml")
    p.add_argument("--agent", default="http://127.0.0.1:9099")
    args = p.parse_args()

    with open(args.map) as f:
        cfg = yaml.safe_load(f)
    mapping = cfg.get("nodes", {})
    defaults = cfg.get("defaults", {})

    def on_message(_client, _userdata, msg):
        # Topic convention: siteiq/sensors/<node_id>
        node_id = msg.topic.rsplit("/", 1)[-1]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            payload = {"raw": msg.payload.decode("utf-8", "replace")}
        env = build_envelope(node_id, payload, mapping, defaults)
        if env is None:
            print(f"[bridge] no mapping for node {node_id!r}; ignoring")
            return
        try:
            requests.post(f"{args.agent}/local/events", json=[env], timeout=5)
        except Exception as exc:
            print(f"[bridge] forward failed: {exc}")

    client = mqtt.Client()
    client.on_message = on_message
    client.connect(args.broker, args.port, 60)
    client.subscribe(args.topic)
    print(f"[bridge] subscribed to {args.topic} on {args.broker}:{args.port} -> {args.agent}")
    client.loop_forever()


if __name__ == "__main__":
    main()
