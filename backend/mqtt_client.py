"""
backend/mqtt_client.py
-----------------------
MQTT subscriber for receiving telemetry from real ESP32 and Wokwi nodes.

Connects to: broker.hivemq.com:1883 (public broker, zero config needed)

Topic structure:
  wsn/<node_id>/telemetry    → incoming telemetry JSON
  wsn/<node_id>/ack          → packet ACK / delivery feedback

Expected telemetry JSON:
  {
    "node_id":   "ESP32_REAL_1",
    "node_type": "real",       ← optional ("real" | "wokwi")
    "energy":    82.5,
    "load":      3,
    "rssi":      -65.0,
    "timestamp": 1710000000
  }
"""

from __future__ import annotations
import json
import time
import threading
from typing import Optional, Callable

import paho.mqtt.client as mqtt

from backend.telemetry_store import TelemetryStore
from backend.utils import get_logger, log_telemetry

log = get_logger("mqtt_client")

# ─── Configuration ────────────────────────────────────────────────────────────
DEFAULT_BROKER   = "broker.hivemq.com"
DEFAULT_PORT     = 1883
TELEMETRY_TOPIC  = "wsn/+/telemetry"
ACK_TOPIC        = "wsn/+/ack"
COMMAND_TOPIC_FMT = "wsn/{node_id}/command"   # outbound: send routing commands


class MQTTIngestor:
    """
    Listens on the MQTT broker for node telemetry and ACK messages,
    then pushes updates into the TelemetryStore.

    Runs in its own thread (loop_start()).
    """

    def __init__(
        self,
        store:          TelemetryStore,
        broker:         str           = DEFAULT_BROKER,
        port:           int           = DEFAULT_PORT,
        on_telemetry:   Optional[Callable] = None,
    ) -> None:
        self.store        = store
        self.broker       = broker
        self.port         = port
        self._on_telemetry = on_telemetry    # optional callback for each message

        self._client = mqtt.Client(client_id="wsn_backend", clean_session=True)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message
        self._connected = False

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def start(self, timeout_s: float = 10.0) -> bool:
        """
        Connect to broker and start background loop.
        Returns True if connected, False if timed out.
        """
        try:
            log.info(f"Connecting to MQTT broker: {self.broker}:{self.port}")
            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()

            # Wait for connection confirmation
            deadline = time.time() + timeout_s
            while not self._connected and time.time() < deadline:
                time.sleep(0.1)

            if self._connected:
                log.info("MQTT connected — listening for telemetry")
            else:
                log.warning("MQTT connection timed out — will retry in background")
            return self._connected

        except Exception as e:
            log.error(f"MQTT connection failed: {e}")
            return False

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
        log.info("MQTT disconnected")

    # ─── MQTT callbacks ───────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self._connected = True
            client.subscribe([(TELEMETRY_TOPIC, 0), (ACK_TOPIC, 0)])
            log.info(f"Subscribed to: {TELEMETRY_TOPIC}, {ACK_TOPIC}")
        else:
            log.error(f"MQTT connect failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc != 0:
            log.warning(f"Unexpected MQTT disconnect (rc={rc}), will auto-reconnect")

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic   = msg.topic

            if "/telemetry" in topic:
                self._handle_telemetry(payload)
            elif "/ack" in topic:
                self._handle_ack(payload)

        except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
            log.warning(f"Bad MQTT message on {msg.topic}: {e}")

    # ─── Message handlers ─────────────────────────────────────────────────────

    def _handle_telemetry(self, data: dict) -> None:
        """Process incoming telemetry and update TelemetryStore."""
        node_id = data.get("node_id")
        if not node_id:
            log.warning("Telemetry missing node_id, skipping")
            return

        # Infer node type from prefix if not explicitly set
        if "node_type" not in data:
            if node_id.upper().startswith("WOKWI"):
                data["node_type"] = "wokwi"
            else:
                data["node_type"] = "real"

        node = self.store.update_from_telemetry(data)
        log_telemetry(data)

        log.debug(
            f"[{node.node_type.upper()}] {node_id} "
            f"E={node.energy:.1f}% L={node.load} RSSI={node.rssi:.1f}dBm"
        )

        if self._on_telemetry:
            self._on_telemetry(node)

    def _handle_ack(self, data: dict) -> None:
        """Process packet ACK / failure feedback."""
        node_id   = data.get("node_id", "unknown")
        packet_id = data.get("packet_id", -1)
        status    = data.get("status", "unknown")
        log.info(f"ACK from {node_id}: packet #{packet_id} → {status}")

    # ─── Outbound commands ────────────────────────────────────────────────────

    def send_routing_command(self, node_id: str, next_hop: str, packet_id: int) -> None:
        """Publish a routing command to a hardware node."""
        payload = json.dumps({
            "packet_id": packet_id,
            "next_hop":  next_hop,
        })
        topic = COMMAND_TOPIC_FMT.format(node_id=node_id)
        self._client.publish(topic, payload, qos=0)
        log.debug(f"Command → {node_id}: route packet #{packet_id} via {next_hop}")

    @property
    def is_connected(self) -> bool:
        return self._connected
