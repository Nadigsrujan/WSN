# RL-Assisted Multi-Agent Energy-Aware Routing in Wireless Sensor Networks

A complete **hybrid Hardware-in-the-Loop (HIL) WSN system** combining:
- 🔴 Real ESP32 nodes (physical hardware)
- 🔵 Wokwi-simulated ESP32 nodes (browser simulation)
- ⚪ Python virtual nodes (software simulation)
- 🤖 Q-learning adaptive routing
- 📡 Live React/Vite + FastAPI dashboard

---

## Quick Start

### 1. Install dependencies
```bash
cd WSN
pip install -r requirements.txt
```

### 2. Simulation-only mode (no hardware needed)
```bash
# Terminal 1 — run the backend + virtual nodes
python run_backend.py

# Terminal 2 — run the FastAPI bridge
python run_api.py

# Terminal 3 — run the Vite React dashboard
cd frontend
npm run dev
# Open: http://localhost:5173
```

### 3. Standalone simulation with custom parameters
```bash
python run_simulation.py --nodes 10 --steps 200 --tick 0.5
```

---

## Project Structure

```
WSN/
├── firmware/               ESP32 Arduino firmware + Wokwi config
│   ├── esp32_node/
│   │   ├── esp32_node.ino  Main firmware
│   │   └── config.h        Per-node configuration
│   └── wokwi/
│       ├── diagram.json    Wokwi circuit
│       └── wokwi.toml      Wokwi project config
│
├── backend/                Python orchestration layer
│   ├── main.py             Main loop (entry point)
│   ├── models.py           NodeState dataclass
│   ├── telemetry_store.py  Thread-safe state store
│   ├── mqtt_client.py      MQTT subscriber (real/Wokwi nodes)
│   ├── graph_engine.py     NetworkX graph builder
│   ├── routing.py          Dijkstra routing engine
│   ├── rl.py               RL integration layer
│   └── metrics.py          PDR, FND/HND, energy variance tracker
│
├── simulation/             Virtual node simulation engine
│   ├── virtual_nodes.py    VirtualNode + VirtualSink classes
│   ├── energy_model.py     Tx/Rx/Idle drain + RSSI model
│   ├── network_sim.py      Background simulation thread
│   └── failure_injection.py Controlled failure injection
│
├── routing/
│   └── cost_functions.py   Multi-metric cost: w1/Ev + w2*d + w3/LQ + w4*Lv
│
├── rl/
│   ├── q_agent.py          Tabular Q-learning agent
│   ├── state_encoder.py    State discretisation
│   └── reward_shaper.py    Reward computation
│
├── frontend/               React/Vite dashboard frontend
│   ├── src/
│   │   ├── App.jsx         Main layout & data fetching
│   │   ├── index.css       Premium dark-mode glassmorphism styling
│   │   └── components/     TopologyGraph, MetricsPanel, EnergyPanel, RlPanel
│   └── package.json
│
├── data/logs/              JSONL telemetry, routing, RL logs
├── run_backend.py          Backend launcher
├── run_api.py              FastAPI server launcher
└── run_simulation.py       Standalone simulation runner
```

---

## Connecting a Real ESP32

1. Open `firmware/esp32_node/config.h`
2. Set your WiFi credentials and `NODE_ID = "ESP32_REAL_1"`
3. Flash `esp32_node.ino` to your board
4. The ESP32 publishes to `broker.hivemq.com` topic `wsn/ESP32_REAL_1/telemetry`
5. The Python backend auto-detects and adds it to the graph

---

## Connecting a Wokwi Node

1. Go to [wokwi.com](https://wokwi.com) → New ESP32 project
2. Copy `esp32_node.ino` and `config.h`
3. Change `NODE_ID = "WOKWI_1"` and `NODE_TYPE = "wokwi"`
4. Run simulation — it connects to `broker.hivemq.com` automatically

---

## MQTT Architecture

```
broker.hivemq.com:1883
        ↑
Real ESP32  ──────┐
Wokwi ESP32 ──────┼──→ Python Backend → Graph + RL → Dashboard
Virtual Nodes ────┘       (in-process)
```

Topic structure:
- `wsn/<node_id>/telemetry` — node → backend
- `wsn/<node_id>/command`   — backend → node (routing decisions)
- `wsn/<node_id>/ack`       — node → backend (delivery feedback)

---

## Cost Function

```
Cost(u,v) = w1*(1/Ev) + w2*d_uv + w3*(1/LQ_uv) + w4*Lv
```

| Term | Meaning |
|------|---------|
| `w1*(1/Ev)` | Penalise low-energy next hops |
| `w2*d_uv` | Penalise distant hops |
| `w3*(1/LQ_uv)` | Penalise poor link quality |
| `w4*Lv` | Penalise congested nodes |

Weights `w1..w4` are dynamically tuned by the Q-learning agent.

---

## Q-Learning Design

- **State**: `(energy_level, rssi_level, load_level, network_health)` (4 discrete dims)
- **Actions**: `boost_energy | boost_distance | boost_lq | boost_load | keep`
- **Reward**: delivery +10, balanced energy +2, low congestion +3, node death -5, drop -10
- **Update**: `Q(s,a) ← Q(s,a) + α(r + γ·max Q(s',a') − Q(s,a))`
- **Exploration**: ε-greedy with exponential decay (0.25 → 0.05)

---

## Performance Metrics

| Metric | Description |
|--------|-------------|
| PDR | Packet Delivery Ratio |
| FND | Step of First Node Death |
| HND | Step of Half Node Death |
| Energy Variance | Standard deviation of node energies |
| Rerouting Events | Number of path changes |
| Network Lifetime | Time until first/half death |
| Throughput | Delivered packets per second |

---

## Dashboard Panels

| Panel | Contents |
|-----|---------|
| 🗺️ Topology Map | Live React-Force-Graph network visualization |
| ⚡ Energy Status | Node energy bars and health states |
| 📊 Performance KPIs | PDR, throughput, lifetime, FND/HND, variance |
| 🤖 Q-Learning Agent | Live routing weights (bar chart) and reward history (line chart) |

---

# Full ESP32 Hybrid WSN Firmware

## File Structure

```text
firmware/
│
├── config.h
├── esp32_node.ino
└── secrets.h
```

---

# 1. config.h

```cpp
#ifndef CONFIG_H
#define CONFIG_H

// ─────────────────────────────────────────────
// Node Identity
// ─────────────────────────────────────────────

#define NODE_ID       "ESP32_REAL_1"
#define NODE_TYPE     "real"

// ─────────────────────────────────────────────
// MQTT
// ─────────────────────────────────────────────

#define MQTT_BROKER   "broker.hivemq.com"
#define MQTT_PORT     1883

// ─────────────────────────────────────────────
// Telemetry
// ─────────────────────────────────────────────

#define TELEMETRY_INTERVAL_MS 2000

// ─────────────────────────────────────────────
// Energy Model
// ─────────────────────────────────────────────

#define USE_INA219 1

#define INITIAL_ENERGY      100.0f
#define IDLE_DRAIN_PER_S    0.01f
#define TX_DRAIN_PER_PKT    0.08f

#define LOW_ENERGY_THRESHOLD 20.0f

// ─────────────────────────────────────────────
// Routing / Load
// ─────────────────────────────────────────────

#define MAX_LOAD 100

// ─────────────────────────────────────────────
// ESP-NOW
// ─────────────────────────────────────────────

#define USE_ESP_NOW 0

// ─────────────────────────────────────────────
// Node Position
// ─────────────────────────────────────────────

#define NODE_X 20.0f
#define NODE_Y 30.0f

// ─────────────────────────────────────────────
// LED STATUS PIN
// ─────────────────────────────────────────────

#define STATUS_LED 2

#endif
```

---

# 2. secrets.h

```cpp
#ifndef SECRETS_H
#define SECRETS_H

#define WIFI_SSID     "YOUR_WIFI_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

#endif
```

---

# 3. esp32_node.ino

```cpp
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_INA219.h>

#include "config.h"
#include "secrets.h"

// ─────────────────────────────────────────────
// WiFi + MQTT
// ─────────────────────────────────────────────

WiFiClient espClient;
PubSubClient client(espClient);

// ─────────────────────────────────────────────
// INA219
// ─────────────────────────────────────────────

Adafruit_INA219 ina219;

// ─────────────────────────────────────────────
// Topics
// ─────────────────────────────────────────────

String telemetryTopic;
String ackTopic;
String commandTopic;

// ─────────────────────────────────────────────
// Node State
// ─────────────────────────────────────────────

float energy = INITIAL_ENERGY;
float voltage = 0;
float current_mA = 0;
float power_mW = 0;

int loadValue = 0;
int packetsSent = 0;

float simulatedRSSI = -60;

unsigned long lastTelemetry = 0;
unsigned long previousMillis = 0;

bool nodeAlive = true;

// ─────────────────────────────────────────────
// Connect WiFi
// ─────────────────────────────────────────────

void connectWiFi() {

  Serial.println();
  Serial.println("Connecting to WiFi...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi Connected");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

// ─────────────────────────────────────────────
// MQTT Reconnect
// ─────────────────────────────────────────────

void reconnectMQTT() {

  while (!client.connected()) {

    Serial.println("Connecting to MQTT...");

    if (client.connect(NODE_ID)) {

      Serial.println("MQTT Connected");

      client.subscribe(commandTopic.c_str());

    } else {

      Serial.print("MQTT Failed. rc=");
      Serial.println(client.state());

      delay(2000);
    }
  }
}

// ─────────────────────────────────────────────
// MQTT Callback
// ─────────────────────────────────────────────

void mqttCallback(char* topic, byte* payload, unsigned int length) {

  Serial.println("Command Received");

  String message = "";

  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.print("Message: ");
  Serial.println(message);

  if (message == "HIGH_LOAD") {
    loadValue += 20;
  }

  if (message == "LOW_LOAD") {
    loadValue -= 10;
  }

  if (loadValue < 0)
    loadValue = 0;

  if (loadValue > MAX_LOAD)
    loadValue = MAX_LOAD;
}

// ─────────────────────────────────────────────
// INA219 Readings
// ─────────────────────────────────────────────

void readINA219() {

#if USE_INA219

  current_mA = ina219.getCurrent_mA();
  voltage = ina219.getBusVoltage_V();
  power_mW = ina219.getPower_mW();

#else

  current_mA = 80 + random(-10, 10);
  voltage = 3.3;
  power_mW = current_mA * voltage;

#endif
}

// ─────────────────────────────────────────────
// Energy Update
// ─────────────────────────────────────────────

void updateEnergy() {

  unsigned long currentMillis = millis();

  float deltaSeconds = (currentMillis - previousMillis) / 1000.0;

  previousMillis = currentMillis;

  energy -= IDLE_DRAIN_PER_S * deltaSeconds;

  energy -= (loadValue * 0.001);

  if (energy < 0)
    energy = 0;

  if (energy <= LOW_ENERGY_THRESHOLD) {
    digitalWrite(STATUS_LED, HIGH);
  } else {
    digitalWrite(STATUS_LED, LOW);
  }

  if (energy <= 0)
    nodeAlive = false;
}

// ─────────────────────────────────────────────
// Simulate Load
// ─────────────────────────────────────────────

void updateLoad() {

  loadValue += random(-5, 6);

  if (loadValue < 0)
    loadValue = 0;

  if (loadValue > MAX_LOAD)
    loadValue = MAX_LOAD;
}

// ─────────────────────────────────────────────
// Publish Telemetry
// ─────────────────────────────────────────────

void publishTelemetry() {

  StaticJsonDocument<512> doc;

  doc["node_id"] = NODE_ID;
  doc["type"] = NODE_TYPE;

  doc["energy"] = energy;
  doc["load"] = loadValue;

  doc["rssi"] = WiFi.RSSI();

  doc["voltage"] = voltage;
  doc["current_mA"] = current_mA;
  doc["power_mW"] = power_mW;

  doc["packets_sent"] = packetsSent;

  doc["x"] = NODE_X;
  doc["y"] = NODE_Y;

  doc["alive"] = nodeAlive;

  doc["timestamp"] = millis();

  char buffer[512];

  serializeJson(doc, buffer);

  client.publish(telemetryTopic.c_str(), buffer);

  packetsSent++;

  energy -= TX_DRAIN_PER_PKT;

  Serial.println("Telemetry Sent:");
  Serial.println(buffer);
}

// ─────────────────────────────────────────────
// Setup
// ─────────────────────────────────────────────

void setup() {

  Serial.begin(115200);

  pinMode(STATUS_LED, OUTPUT);

  telemetryTopic = "wsn/" + String(NODE_ID) + "/telemetry";
  ackTopic = "wsn/" + String(NODE_ID) + "/ack";
  commandTopic = "wsn/" + String(NODE_ID) + "/command";

  connectWiFi();

  client.setServer(MQTT_BROKER, MQTT_PORT);
  client.setCallback(mqttCallback);

#if USE_INA219

  if (!ina219.begin()) {
    Serial.println("INA219 not found!");
  } else {
    Serial.println("INA219 initialized");
  }

#endif

  previousMillis = millis();
}

// ─────────────────────────────────────────────
// Main Loop
// ─────────────────────────────────────────────

void loop() {

  if (!client.connected()) {
    reconnectMQTT();
  }

  client.loop();

  updateLoad();

  readINA219();

  updateEnergy();

  if (millis() - lastTelemetry >= TELEMETRY_INTERVAL_MS) {

    lastTelemetry = millis();

    publishTelemetry();
  }
}
```

---

# INA219 CONNECTIONS

## ESP32 ↔ INA219

| INA219 | ESP32  |
| ------ | ------ |
| VCC    | 3.3V   |
| GND    | GND    |
| SDA    | GPIO21 |
| SCL    | GPIO22 |

---

# OPTIONAL LOAD DEMONSTRATION

You can connect:

* LEDs
* small DC fan
* buzzer
* OLED

through the INA219 current path.

Higher load → higher current → routing cost increases.

This allows:

* energy-aware routing
* congestion visualization
* RL adaptation
* rerouting demonstrations

---

# REQUIRED ARDUINO LIBRARIES

Install:

* PubSubClient
* ArduinoJson
* Adafruit INA219
* Adafruit BusIO

---

# SERIAL MONITOR OUTPUT

Example:

```text
WiFi Connected
MQTT Connected
INA219 initialized

Telemetry Sent:
{
  "node_id":"ESP32_REAL_1",
  "energy":98.7,
  "load":14,
  "rssi":-62,
  "current_mA":81.2
}
```

---

# MQTT TOPIC STRUCTURE

```text
wsn/ESP32_REAL_1/telemetry
wsn/ESP32_REAL_1/ack
wsn/ESP32_REAL_1/command
```

---

# NEXT STEP

After this firmware works:

1. Connect Python MQTT backend
2. Build NetworkX graph
3. Add virtual nodes
4. Add RL routing
5. Build React/Vite dashboard
