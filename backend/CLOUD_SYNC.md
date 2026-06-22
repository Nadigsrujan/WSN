# Google Firestore Cloud Sync — Setup & Deployment

This document explains the **cloud persistence + monitoring** layer added to the
RL-Assisted Hybrid WSN. It mirrors live network state into **Google Firestore**
without modifying the routing engine, MQTT pipeline, or topology visualization.

```
Sensor Nodes → Cluster Head → ESP32 Gateway → MQTT → Python Backend → Google Firestore → Dashboard
```

The ESP32 is the *logical* edge gateway; the **backend** performs the actual
Firestore writes asynchronously on a background thread.

---

## 1. Architecture

| File | Responsibility |
|------|----------------|
| `backend/firestore_service.py` | Connection wrapper: init, **auto-reconnect** w/ backoff, blocking single-doc writes, graceful degradation. |
| `backend/cloud_sync.py` | Async orchestrator: diffs each tick's snapshot, builds documents, enqueues them, drains the queue on a daemon thread, tracks counters + status. |
| `backend/main.py` | Calls `cloud.sync(...)` once per tick and embeds `cloud.status()` into the dashboard snapshot. |
| `frontend/src/components/CloudPanel.jsx` | **Cloud Sync Panel** (visible in Gateway Mode). |

### Design guarantees
- **Asynchronous writes** — the main loop only *enqueues*; all network I/O runs
  on a separate `cloud-sync-writer` daemon thread. Tick/dashboard latency is unaffected.
- **Fail-safe** — every Firestore call is wrapped in `try/except`. If Firestore
  is unreachable, items are buffered in a bounded queue (oldest dropped when full),
  and the system keeps running. No cloud failure can crash the backend.
- **Auto-reconnect** — on any write/connect failure the connection is flagged down;
  the worker retries `connect()` every `reconnect_interval_s` (default 10s).
- **Untouched subsystems** — RL engine, routing engine, MQTT ingestor, and the
  existing topology visualization are not modified. Cloud sync is a pure consumer
  of the snapshot dict.
- **Optional dependency** — if `firebase-admin` is missing *or* credentials are
  absent, the service runs as a no-op and the dashboard shows `Cloud Status: Disabled`.

---

## 2. Firestore Collections

| Collection | Written when | Example document |
|------------|--------------|------------------|
| `telemetry` | every node, every tick | `{node_id, energy, load, rssi, alive, is_ch, cluster_id, packets_*, step, gateway_id, timestamp}` |
| `routing_events` | a routing path changes | `{old_path, new_path, reason, timestamp}` |
| `cluster_head_events` | a cluster-head election changes | `{cluster_id, old_ch, new_ch, reason, timestamp}` |
| `rl_decisions` | the RL agent advances a step | `{state, action, reward, epsilon, weights, step, timestamp}` |
| `gateway_logs` | sync lifecycle events | `{event, status, message}` |

`timestamp` uses Firestore's `SERVER_TIMESTAMP` sentinel when available.

---

## 3. Setup

### 3.1 Install the dependency
```bash
pip install -r requirements.txt        # includes firebase-admin>=6.5.0
```

### 3.2 Provide the service account key
1. Firebase Console → **Project Settings → Service Accounts → Generate new private key**.
2. Save the downloaded JSON as **`backend/service-account.json`**.

> ⚠️ The real key is **git-ignored** (`backend/service-account.json`). Never commit it.
> A template is provided at `backend/service-account.example.json` — copy it and fill in
> `private_key_id` and `private_key` from the console.

The pasted snippet in the project brief was missing `private_key`, so it will **not**
authenticate on its own — you must use the full key file from Firebase.

### 3.3 (Optional) Override paths via environment
```bash
export FIRESTORE_CREDENTIALS=/abs/path/to/service-account.json   # default: backend/service-account.json
export FIRESTORE_PROJECT_ID=wsn-el                               # default: read from the key file
```

### 3.4 Run
```bash
python run_backend.py     # backend + cloud sync
python run_api.py         # dashboard API on :8000
cd frontend && npm run dev
```
On the dashboard, toggle **Gateway Mode** (top-right) to reveal the **Cloud Sync** panel.

---

## 4. Dashboard — Cloud Sync Panel

Visible only in **Gateway Mode**. Reads the real `cloud` block from the backend
snapshot (falls back to derived counts if the backend reports nothing):

- **Cloud Status** — Connected / Reconnecting / Disabled
- **Firestore Connection** — connected / disconnected / credentials_missing / library_missing
- **Project / Gateway** — e.g. `wsn-el · ESP32_REAL_1`
- **Total Telemetry Records**, **Total Routing Events**, **Cluster Head Events**,
  **Total RL Decisions**, **Total Gateway Logs** (live Firestore write counters)
- **Last Synchronization** — timestamp of the most recent successful write
- An inline **error banner** + the **edge → cloud data-flow** chain

---

## 5. Verifying writes

In the Firebase Console → Firestore Database, you should see the five collections
populate within a few ticks. To confirm programmatically:

```python
from firebase_admin import credentials, firestore, initialize_app
app = initialize_app(credentials.Certificate("backend/service-account.json"))
db = firestore.client(app)
print("telemetry docs:", len(list(db.collection("telemetry").limit(5).stream())))
```

---

## 6. Deployment notes

- **Google Compute Engine / Cloud Run** — mount the service-account key as a secret
  (or use the instance's attached service account + Application Default Credentials)
  and run `run_backend.py` + `run_api.py`.
- **Cost control** — telemetry is the highest-volume collection. To reduce writes,
  construct `CloudSync(telemetry_every_n_ticks=N)` in `backend/main.py` to sample
  every N ticks instead of every tick.
- **Security rules** — restrict Firestore rules to the service account / authenticated
  readers; the demo writes server-side only, so client write access can stay closed.
