# RL-Assisted Hybrid Wireless Sensor Network with Cloud Synchronization

> **Final-Year Engineering Project** — Hybrid WSN combining Python Virtual Nodes, a Physical ESP32 Node, MQTT communication, Reinforcement Learning–based routing, dynamic cluster formation, intra-cluster mesh topology, and Google Firestore cloud synchronization, visualized on a React/Vite dashboard.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Edge-to-Cloud Architecture](#3-edge-to-cloud-architecture)
4. [Dynamic Node Roles](#4-dynamic-node-roles)
5. [Cluster Formation & Intra-Cluster Mesh](#5-cluster-formation--intra-cluster-mesh)
6. [RL-Based Routing](#6-rl-based-routing)
7. [Self-Healing & Fault Tolerance](#7-self-healing--fault-tolerance)
8. [Topology & Static Positions](#8-topology--static-positions)
9. [MQTT Communication](#9-mqtt-communication)
10. [Cloud Integration](#10-cloud-integration)
11. [Dashboard Features](#11-dashboard-features)
12. [Project Structure](#12-project-structure)
13. [ESP32 Firmware](#13-esp32-firmware)
14. [Quick Start](#14-quick-start)
15. [Performance Metrics](#15-performance-metrics)
16. [Required Libraries & Dependencies](#16-required-libraries--dependencies)

---

## 1. Project Overview

This system implements a **Hybrid Wireless Sensor Network (WSN)** that merges software-simulated virtual nodes with a physical ESP32 hardware node into a unified, co-operating network. The system demonstrates:

- **Hierarchical Cluster Architecture** — Nodes self-organize into clusters with dynamically elected Cluster Heads (CHs).
- **Reinforcement Learning Routing** — A Q-learning agent continuously tunes multi-metric routing weights to maximize network lifetime, load balance, and packet delivery ratio.
- **Physical-Virtual Hybrid** — A real ESP32 participates as a genuine network node alongside Python-simulated virtual nodes, sharing the same routing and cluster logic.
- **Cloud Persistence** — All telemetry, routing decisions, CH elections, RL decisions, and gateway events are mirrored to Google Firestore in real time.
- **Live Dashboard** — A React/Vite single-page application visualizes the topology, clusters, routing table, RL agent state, cloud sync status, and event log.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      HYBRID WSN SYSTEM                          │
│                                                                 │
│  ┌──────────────────┐     ┌─────────────────────────────────┐  │
│  │  VIRTUAL LAYER   │     │        PHYSICAL LAYER           │  │
│  │                  │     │                                 │  │
│  │  VNODE_1         │     │  ESP32_REAL_1                   │  │
│  │  VNODE_2         │     │  ├─ WiFi connected              │  │
│  │  VNODE_3         │     │  ├─ MQTT publisher              │  │
│  │  VNODE_4         │     │  ├─ Cluster Head Candidate      │  │
│  │  VNODE_5  ───────┼─────┤  └─ Gateway Candidate          │  │
│  │  VNODE_6         │     │                                 │  │
│  │  VNODE_7         │     └─────────────┬───────────────────┘  │
│  │  VNODE_8         │                   │                       │
│  │  SINK            │                   │ MQTT                  │
│  └──────────────────┘                   │                       │
│           │                             │                       │
│           └─────────────┬───────────────┘                       │
│                         │                                       │
│              ┌──────────▼──────────┐                            │
│              │   PYTHON BACKEND    │                            │
│              │                     │                            │
│              │  • Graph Engine     │                            │
│              │  • Cluster Manager  │                            │
│              │  • Routing Engine   │                            │
│              │  • RL Controller    │                            │
│              │  • Metrics Tracker  │                            │
│              │  • Cloud Sync       │                            │
│              └──────────┬──────────┘                            │
│                         │                                       │
│          ┌──────────────┼──────────────┐                        │
│          │              │              │                        │
│   ┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼───────────┐           │
│   │  FastAPI    │ │ Firestore  │ │  data/logs/     │           │
│   │  REST API   │ │  Cloud DB  │ │  (JSONL files)  │           │
│   └──────┬──────┘ └───────────┘ └─────────────────┘           │
│          │                                                      │
│   ┌──────▼──────┐                                              │
│   │  React/Vite │                                              │
│   │  Dashboard  │                                              │
│   └─────────────┘                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Edge-to-Cloud Architecture

Data flows from the network edge through the cluster hierarchy, via the ESP32 gateway, up to the cloud and finally to the dashboard:

```
Virtual Nodes  (VNODE_1 … VNODE_8)
       │
       ▼
 Cluster Formation  (3 clusters, intra-cluster mesh)
       │
       ▼
 Cluster Heads  (dynamically elected per cluster)
       │
       ▼
 ESP32 Gateway  (physical node — MQTT telemetry)
       │
       ▼
 MQTT Broker  (broker.hivemq.com:1883)
       │
       ▼
 Python Backend  (graph + RL + routing + metrics)
       │
       ▼
 Google Firestore  (cloud persistence)
       │
       ▼
 React/Vite Dashboard  (live visualization)
```

---

## 4. Dynamic Node Roles

The physical ESP32 node is not a passive sensor device. It operates as a **full network participant** and can assume any of three roles dynamically:

| Role | Description |
|------|-------------|
| **Sensor Node** | Transmits MQTT telemetry (energy, load, RSSI, position) every 2 seconds. Participates in routing as a regular mesh node. |
| **Cluster Head** | Elected by the Cluster Manager based on residual energy and load. Aggregates intra-cluster traffic and routes to the SINK. |
| **Gateway Node** | Acts as the bridge between the physical WiFi/MQTT layer and the Python backend. All physical-to-cloud traffic passes through this role. |

Role changes are reflected immediately in:
- The **Routing Table** (next-hop selection and cost recalculation)
- The **Dashboard** (cluster view, topology map, gateway status panel)
- **Cloud Logs** (Firestore `cluster_head_events` and `gateway_logs` collections)

---

## 5. Cluster Formation & Intra-Cluster Mesh

The network is partitioned into **3 clusters**. Within each cluster, nodes are fully mesh-connected (intra-cluster). Between clusters and the SINK, routing follows the **CH-mandatory path**: traffic must pass through a Cluster Head before reaching the SINK.

### Cluster Head Election Criteria

CH election runs every tick using a weighted scoring function:

| Factor | Weight | Description |
|--------|--------|-------------|
| Residual Energy | High | Prefer nodes with more remaining energy |
| Current Load | Medium | Avoid overloaded nodes |
| Centrality | Low | Prefer topologically central nodes |

### Hierarchical Routing Rule

```
Source Node  →  Intra-Cluster Mesh  →  Cluster Head  →  SINK
```

Non-CH to non-CH cross-cluster edges receive a **50× cost penalty** in the graph, ensuring Dijkstra always selects the CH-mandatory route.

---

## 6. RL-Based Routing

### Routing Cost Function

```
Cost(u, v) = α·(1/E_v) + β·d_uv + γ·(1/LQ_uv) + δ·L_v + ε·H
```

| Term | Symbol | Meaning |
|------|--------|---------|
| Residual Energy | `α·(1/E_v)` | Penalises low-energy next hops |
| Distance / Hop Cost | `β·d_uv` | Penalises distant or expensive hops |
| Link Quality (RSSI) | `γ·(1/LQ_uv)` | Penalises poor signal links |
| Network Load | `δ·L_v` | Penalises congested nodes |
| Hop Count | `ε·H` | Penalises long paths |

The weights **α, β, γ, δ, ε** are dynamically tuned by the Q-learning agent every simulation tick.

### Q-Learning Agent Design

| Component | Detail |
|-----------|--------|
| **State Space** | `(energy_level, rssi_level, load_level, network_health)` — 4 discrete dimensions |
| **Action Space** | `boost_energy`, `boost_distance`, `boost_lq`, `boost_load`, `keep_weights` |
| **Reward Signal** | Delivery +10 · Balanced energy +2 · Low congestion +3 · Node death −5 · Drop −10 |
| **Update Rule** | `Q(s,a) ← Q(s,a) + α[r + γ·max Q(s′,a′) − Q(s,a)]` |
| **Exploration** | ε-greedy with exponential decay: 0.25 → 0.05 |

### RL Optimization Objectives

The RL agent dynamically adjusts routing weights to improve:

- **Network Lifetime** — distribute energy consumption evenly across all nodes
- **Load Balancing** — prevent hot-spot congestion at any single node or CH
- **Packet Delivery Ratio (PDR)** — maximize end-to-end delivery success
- **Fault Tolerance** — discover alternative paths before links fail

---

## 7. Self-Healing & Fault Tolerance

The system detects and reacts to network degradation **without moving any node**:

```
Cluster Head becomes overloaded (load > 50%)
          │
          ▼
  RL detects rising routing cost
          │
          ▼
  Alternative routes evaluated (Dijkstra + penalized graph)
          │
          ▼
  Traffic rerouted via next best CH path
          │
          ▼
  New CH may be elected for the overloaded cluster
          │
          ▼
  Event logged → Firestore → Dashboard updated
```

> **Node positions remain entirely static throughout self-healing. Only traffic flow, CH assignment, and routing paths change.**

---

## 8. Topology & Static Positions

Node positions are defined **once at startup** and **never modified at runtime**.

| What is Static | What is Dynamic |
|---------------|-----------------|
| Node positions (x, y) | Traffic flow and routing paths |
| Network adjacency structure | Cluster Head assignment |
| Number of clusters | Routing weights (α, β, γ, δ, ε) |
| Intra-cluster mesh edges | Node alive/dead state |

The ESP32's position is reported via MQTT at connection time and is treated as its permanent position within the mesh.

> **There is no node mobility in this system. No node ever moves.**

---

## 9. MQTT Communication

**Broker:** `broker.hivemq.com:1883`

```
broker.hivemq.com:1883
        ↑
ESP32_REAL_1 ─────────┐
Virtual Nodes ─────────┼──→ Python Backend → Graph + RL → Dashboard
(via in-process sim)  ┘
```

### Topic Structure

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `wsn/<node_id>/telemetry` | Node → Backend | Energy, load, RSSI, position, alive state |
| `wsn/<node_id>/command` | Backend → Node | Load adjustment commands (`HIGH_LOAD`, `LOW_LOAD`) |
| `wsn/<node_id>/ack` | Node → Backend | Delivery acknowledgement |

### Telemetry Payload (ESP32)

```json
{
  "node_id": "ESP32_REAL_1",
  "type": "real",
  "energy": 94.3,
  "load": 18,
  "rssi": -61,
  "packets_sent": 47,
  "x": 20.0,
  "y": 30.0,
  "alive": true,
  "timestamp": 38420
}
```

---

## 10. Cloud Integration

**Cloud Provider:** Google Firebase Firestore

The `CloudSync` module runs on a background thread and mirrors all network events to Firestore asynchronously. If Firebase credentials are absent, the backend degrades gracefully — simulation, routing, RL, and the dashboard all continue operating normally.

### Firestore Collections

| Collection | Contents | Purpose |
|------------|----------|---------|
| `telemetry` | Per-node snapshots every tick | Telemetry persistence |
| `routing_events` | Source, path, cost, success flag | Routing history |
| `cluster_head_events` | CH elections with before/after | CH election history |
| `rl_decisions` | RL state, action, reward, new weights | RL decision history |
| `gateway_logs` | ESP32 connection and role events | Gateway event history |

### Cloud Sync Setup

```bash
# 1. Create a Firebase project and enable Firestore
# 2. Download a service account JSON key
# 3. Place it at: backend/service-account.json
# 4. The backend will auto-detect and enable cloud sync
```

> If `backend/service-account.json` is absent, the system logs a warning and continues without cloud sync.

---

## 11. Dashboard Features

**Tech Stack:** React 18 + Vite + FastAPI (REST polling every 2 s)

| Panel | Description |
|-------|-------------|
| 🗺️ **Topology View** | Force-directed graph of all nodes — color-coded by type (virtual / real / SINK), cluster membership, and CH status |
| 🔵 **Cluster View** | Cluster assignments, current CH for each cluster, intra-cluster mesh edges highlighted |
| 📋 **Routing Table** | Per-node next-hop and computed cost to SINK, best path highlighted end-to-end |
| 🤖 **RL Decision Panel** | Live bar chart of routing weights (α, β, γ, δ, ε), reward history line chart, current Q-agent action |
| ☁️ **Cloud Sync Panel** | Firestore sync status, last sync timestamp, document counts per collection |
| 📜 **Event Log Panel** | Chronological log of node deaths, CH elections, rerouting events, congestion warnings |
| 📡 **Gateway Status Panel** | ESP32 connection state, last seen timestamp, current role (sensor / CH / gateway) |

---

## 12. Project Structure

```
WSNEL/
│
├── backend/                        Python orchestration layer
│   ├── main.py                     Main loop — orchestrates all components every tick
│   ├── models.py                   NodeState dataclass (energy, load, RSSI, cluster, CH flag)
│   ├── telemetry_store.py          Thread-safe state store with frozen-position enforcement
│   ├── mqtt_client.py              MQTT subscriber — ingests real and virtual node telemetry
│   ├── graph_engine.py             NetworkX weighted graph builder and edge updater
│   ├── routing.py                  Dijkstra routing engine — best path + alternate path
│   ├── rl.py                       RL controller — wraps Q-agent and applies weight updates
│   ├── cluster_manager.py          Dynamic cluster head election and cluster assignment
│   ├── topology_manager.py         Static mesh adjacency builder and hierarchical overlay
│   ├── environment_analyzer.py     Environmental weight computation (link attenuation model)
│   ├── cloud_sync.py               Async Firestore sync — telemetry, routing, CH, RL events
│   ├── firestore_service.py        Firebase Admin SDK wrapper and collection writers
│   ├── metrics.py                  PDR, FND/HND, energy variance, rerouting event tracker
│   ├── utils.py                    Logger, network state JSON writer
│   ├── api.py                      FastAPI endpoints consumed by the dashboard
│   └── service-account.example.json  Template for Firebase credentials
│
├── simulation/                     Virtual node simulation engine
│   ├── virtual_nodes.py            VirtualNode class — energy drain, load variation, RSSI model
│   ├── energy_model.py             Tx/Rx/Idle energy drain equations
│   ├── network_sim.py              Background simulation thread — steps all virtual nodes
│   ├── mesh_topology.py            Static position map, adjacency list, topology validator
│   └── failure_injection.py        Controlled node failure injection for fault-tolerance testing
│
├── routing/
│   └── cost_functions.py           Multi-metric cost: α/E + β·d + γ/LQ + δ·L + ε·H
│
├── rl/
│   ├── q_agent.py                  Tabular Q-learning agent (ε-greedy, exponential decay)
│   ├── state_encoder.py            Discretises continuous state (energy, RSSI, load, health)
│   └── reward_shaper.py            Reward computation from delivery, energy balance, deaths
│
├── firmware/                       Physical ESP32 Arduino firmware
│   ├── esp32_node/
│   │   ├── esp32_node.ino          Main firmware — WiFi, MQTT, telemetry publish, command sub
│   │   ├── config.h                Per-node configuration (NODE_ID, MQTT broker, intervals)
│   │   └── secrets.h               WiFi credentials (not committed to version control)
│   └── wokwi/
│       ├── diagram.json            Wokwi circuit diagram
│       └── wokwi.toml              Wokwi project configuration
│
├── frontend/                       React/Vite dashboard
│   ├── src/
│   │   ├── App.jsx                 Root layout, polling loop, state management
│   │   ├── main.jsx                Vite entry point
│   │   ├── index.css               Premium dark-mode glassmorphism design system
│   │   └── components/
│   │       ├── TopologyGraph.jsx   Force-directed network graph (react-force-graph)
│   │       ├── MetricsPanel.jsx    KPI cards — PDR, throughput, FND/HND, energy variance
│   │       ├── EnergyPanel.jsx     Per-node energy bars and alive/dead indicators
│   │       ├── RlPanel.jsx         RL weights bar chart + reward history line chart
│   │       ├── RoutingTablePanel.jsx  Per-node next-hop routing table with cost column
│   │       ├── CloudPanel.jsx      Firestore sync status and collection document counts
│   │       └── EventLogPanel.jsx   Timestamped event log (deaths, CH elections, reroutes)
│   ├── package.json
│   └── vite.config.js
│
├── data/
│   ├── logs/
│   │   ├── telemetry.jsonl         JSONL telemetry archive
│   │   ├── routing.jsonl           JSONL routing decision archive
│   │   └── rl_weights.jsonl        JSONL RL weight history archive
│   └── network_state.json          Live state snapshot read by the dashboard API
│
├── run_backend.py                  Backend launcher (starts sim + MQTT + cloud + main loop)
├── run_api.py                      FastAPI server launcher (serves dashboard REST API)
├── run_simulation.py               Standalone simulation runner with CLI parameters
└── requirements.txt                Python dependencies
```

---

## 13. ESP32 Firmware

The physical ESP32 operates as a **real network node** — it connects to WiFi, subscribes to its command topic, and publishes telemetry at a configurable interval. It does **not** read physical sensors; its energy and load values are managed by the firmware's software model and reported to the backend.

### config.h — Key Parameters

```cpp
#define NODE_ID                "ESP32_REAL_1"   // Unique node identifier
#define NODE_TYPE              "real"           // Signals physical node to backend
#define MQTT_BROKER            "broker.hivemq.com"
#define MQTT_PORT              1883
#define TELEMETRY_INTERVAL_MS  2000             // Publish every 2 seconds

#define INITIAL_ENERGY         100.0f
#define IDLE_DRAIN_PER_S       0.01f
#define TX_DRAIN_PER_PKT       0.08f
#define LOW_ENERGY_THRESHOLD   20.0f

#define NODE_X  20.0f            // Static position — never changes at runtime
#define NODE_Y  30.0f
#define STATUS_LED  2            // GPIO2 — lit when energy < LOW_ENERGY_THRESHOLD
```

### secrets.h

```cpp
#define WIFI_SSID      "YOUR_WIFI_SSID"
#define WIFI_PASSWORD  "YOUR_WIFI_PASSWORD"
```

### Required Arduino Libraries

| Library | Purpose |
|---------|---------|
| `PubSubClient` | MQTT publish/subscribe |
| `ArduinoJson` | JSON telemetry serialization |

### Connecting the ESP32

1. Open `firmware/esp32_node/config.h`
2. Set `NODE_ID = "ESP32_REAL_1"` and confirm `NODE_TYPE = "real"`
3. Fill in `secrets.h` with your WiFi credentials
4. Flash `esp32_node.ino` to your board via Arduino IDE or PlatformIO
5. The ESP32 publishes to `wsn/ESP32_REAL_1/telemetry` on `broker.hivemq.com`
6. The Python backend auto-detects the node and integrates it into the mesh graph

### Serial Monitor Output Example

```text
WiFi Connected — IP: 192.168.1.42
MQTT Connected

Telemetry Sent:
{
  "node_id": "ESP32_REAL_1",
  "type": "real",
  "energy": 96.4,
  "load": 22,
  "rssi": -59,
  "packets_sent": 12,
  "x": 20.0,
  "y": 30.0,
  "alive": true,
  "timestamp": 24000
}
```

---

## 14. Quick Start

### Prerequisites

- Python ≥ 3.10
- Node.js ≥ 18
- (Optional) Firebase service account JSON for cloud sync

### Step 1 — Install Python Dependencies

```bash
cd WSNEL
pip install -r requirements.txt
```

### Step 2 — Install Dashboard Dependencies

```bash
cd frontend
npm install
```

### Step 3 — (Optional) Configure Cloud Sync

```bash
# Copy the example and fill in your Firebase credentials
cp backend/service-account.example.json backend/service-account.json
# Edit backend/service-account.json with your project's service account key
```

### Step 4 — Run in Simulation-Only Mode (no hardware required)

```bash
# Terminal 1 — start backend (simulation + MQTT + RL + cloud sync)
python run_backend.py

# Terminal 2 — start FastAPI REST server
python run_api.py

# Terminal 3 — start React/Vite dashboard
cd frontend
npm run dev
# Open: http://localhost:5173
```

### Step 5 — Standalone Simulation with Custom Parameters

```bash
python run_simulation.py --nodes 10 --steps 200 --tick 0.5
```

### Step 6 — Add the Physical ESP32

1. Flash the firmware (see [Section 13](#13-esp32-firmware))
2. Power on the ESP32 — it will auto-connect to MQTT
3. The backend detects `ESP32_REAL_1` and adds it to the mesh graph
4. The dashboard shows it as a real node (distinct color) in the topology view

---

## 15. Performance Metrics

| Metric | Description |
|--------|-------------|
| **PDR** | Packet Delivery Ratio — fraction of packets successfully delivered to SINK |
| **FND** | First Node Death — simulation step when the first virtual node exhausts energy |
| **HND** | Half Node Death — simulation step when 50% of virtual nodes have died |
| **Energy Variance** | Standard deviation of residual energy across all alive nodes — lower is more balanced |
| **Rerouting Events** | Count of path changes triggered by topology or load changes |
| **Network Lifetime** | Steps until FND and HND thresholds |
| **Throughput** | Delivered packets per simulation tick |
| **CH Stability** | Frequency of Cluster Head re-elections |

---

## 16. Required Libraries & Dependencies

### Python (`requirements.txt`)

| Package | Purpose |
|---------|---------|
| `networkx` | Graph construction and Dijkstra routing |
| `numpy` | Numerical operations in energy and cost models |
| `paho-mqtt` | MQTT client for ESP32 ingestion |
| `fastapi` | REST API server consumed by dashboard |
| `uvicorn` | ASGI server for FastAPI |
| `firebase-admin` | Google Firestore cloud sync (optional) |
| `python-dotenv` | Environment variable management |
| `colorlog` | Colored console logging |
| `pytest` / `pytest-mock` | Unit and integration testing |

### Frontend (`frontend/package.json`)

| Package | Purpose |
|---------|---------|
| `react` / `react-dom` | UI component framework |
| `vite` | Fast development server and bundler |
| `react-force-graph` | Force-directed network topology visualization |
| `recharts` | Line charts and bar charts for RL and metrics panels |

---

## License

This project is developed as an academic final-year engineering project. All source code is available for educational and research purposes.

---

*Built with Python · React · Vite · FastAPI · MQTT · Google Firestore · NetworkX · Q-Learning*
