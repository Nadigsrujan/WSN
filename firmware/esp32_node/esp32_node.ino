#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// =====================================================
// CONFIG
// =====================================================

#define NODE_ID "ESP32_REAL_1"

#define WIFI_SSID "Nova_1560"
#define WIFI_PASSWORD "24071974"

#define MQTT_BROKER "broker.hivemq.com"
#define MQTT_PORT 1883

#define TELEMETRY_INTERVAL 2000

// =====================================================
// POSITION (Note: Backend may override these to fit mesh)
// =====================================================

#define NODE_X 20
#define NODE_Y 30

// =====================================================
// WIFI + MQTT
// =====================================================

WiFiClient espClient;
PubSubClient client(espClient);

// =====================================================
// VARIABLES
// =====================================================

unsigned long lastTelemetry = 0;
int packetsSent = 0;

// =====================================================
// WIFI CONNECT
// =====================================================

void connectWiFi() {
  Serial.println();
  Serial.println("Connecting WiFi...");
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

// =====================================================
// MQTT CONNECT
// =====================================================

void reconnectMQTT() {
  while (!client.connected()) {
    Serial.println("Connecting MQTT...");
    if (client.connect(NODE_ID)) {
      Serial.println("MQTT Connected");
    } else {
      Serial.print("MQTT Failed: ");
      Serial.println(client.state());
      delay(2000);
    }
  }
}

// =====================================================
// SEND TELEMETRY
// =====================================================

void publishTelemetry() {
  StaticJsonDocument<256> doc;

  // -------------------------------------------------
  // BASIC NODE INFO
  // -------------------------------------------------
  doc["node_id"] = NODE_ID;
  doc["node_type"] = "real"; // Backend prefers 'node_type'

  // -------------------------------------------------
  // NODE STATUS
  // -------------------------------------------------
  doc["energy"] = 100; // MUST send energy for backend to consider it 'alive'
  doc["alive"] = true;
  doc["load"] = 20;
  doc["rssi"] = WiFi.RSSI();

  // -------------------------------------------------
  // POSITION
  // -------------------------------------------------
  doc["x"] = NODE_X;
  doc["y"] = NODE_Y;

  // -------------------------------------------------
  // DEBUG INFO
  // -------------------------------------------------
  doc["packets_sent"] = packetsSent;
  doc["timestamp"] = millis();

  // -------------------------------------------------
  // SERIALIZE JSON
  // -------------------------------------------------
  char buffer[256];
  serializeJson(doc, buffer);

  // -------------------------------------------------
  // MQTT PUBLISH (Critical: Must use hierarchical topic)
  // -------------------------------------------------
  String topic = "wsn/" + String(NODE_ID) + "/telemetry";
  client.publish(topic.c_str(), buffer);

  packetsSent++;

  // -------------------------------------------------
  // SERIAL MONITOR
  // -------------------------------------------------
  Serial.println();
  Serial.print("Telemetry Sent to: ");
  Serial.println(topic);
  Serial.println(buffer);
}

// =====================================================
// SETUP
// =====================================================

void setup() {
  Serial.begin(115200);
  connectWiFi();
  client.setServer(MQTT_BROKER, MQTT_PORT);
}

// =====================================================
// LOOP
// =====================================================

void loop() {
  if (!client.connected()) {
    reconnectMQTT();
  }
  client.loop();

  if (millis() - lastTelemetry >= TELEMETRY_INTERVAL) {
    lastTelemetry = millis();
    publishTelemetry();
  }
}