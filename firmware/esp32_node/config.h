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
