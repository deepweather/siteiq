# SiteIQ Edge

On-site software that turns physical devices into ledger producers. Devices
authenticate to a SiteIQ instance with a bearer **device token** (provisioned
via a one-time claim code), buffer events locally, and POST them to
`/api/ingest/events`. The server folds them into the hash-chained ledger and,
in Live Mode, a `LiveSource` projects them onto the dashboard.

## The tiering rule

> A **ledger client** is anything that can hold a device token and speak
> `/api/ingest`. Everything dumber (Arduino, LoRa nodes, BLE sensors) is a
> **sensor behind a gateway** that translates its readings into events.

```
Tier A  Smart edge (Mac mini / Jetson / RPi5)   agent (Go) + sidecar (Python CV)
Tier B  Thin Linux / IP camera                  agent only, or frames -> server
Tier C  ESP32 / Arduino / LoRa                   -> MQTT/serial/LoRa -> gateway -> agent
```

## Components

- **`agent/`** — the Go shell. Single static binary. Owns the device token,
  a durable SQLite **outbox** (idempotent on `client_event_id`), batched
  upload with exponential backoff, heartbeat, and config pull. It also
  exposes a **local ingest** HTTP endpoint (`127.0.0.1`) that the CV sidecar
  and any gateway bridge POST into — this is the single funnel into the
  outbox. Outbound-only to the server (NAT/4G friendly).
- **`sidecar/`** — the Python CV worker. Reads RTSP/USB frames, runs YOLO,
  applies the calibration homography (pixel -> site meters), debounces
  detections into **discrete events**, and POSTs them to the agent's local
  ingest. Optional: gateways with no camera run the agent alone.
- **`gateway/`** — bridges dumb nodes. `mqtt_bridge.py` subscribes to a local
  MQTT broker and maps `node_id -> (subject_type, subject_id, kind)` via
  `node-map.example.yaml`, forwarding to the agent's local ingest.
- **`firmware/esp32/`** — reference ESP32 sketch publishing a sensor reading
  over MQTT/TLS to the gateway broker.

## Quick start (Tier A)

```bash
# 1. In the SiteIQ UI: Settings -> Devices -> Add device -> copy the claim code.
# 2. On the device:
./siteiq-agent claim --server https://siteiq.example.com --code <CODE>
./siteiq-agent run   --server https://siteiq.example.com

# 3. Point the CV sidecar at a camera (or the bundled demo videos):
python sidecar.py --source rtsp://... --agent http://127.0.0.1:9099
```

Or use `docker compose -f docker-compose.edge.yml up` to run agent + sidecar
together.

## Event contract

The agent/sidecar/bridge all produce the same `EnvelopeIn` the server expects
(see `backend/api/ingest.py`):

```json
{
  "subject_type": "equipment",
  "subject_id": "crane-1",
  "kind": "equipment.state_changed",
  "client_event_id": "a-uuid",
  "occurred_at": "2026-06-28T09:00:00Z",
  "payload": {"state": "idle"},
  "confidence": 0.92,
  "source": "camera",
  "evidence_ref": "blob:..."
}
```

`client_event_id` makes replay exactly-once; `confidence` below the server's
floor lands the event as `proposed` for human review.
