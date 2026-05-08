"""
backend/models.py
-----------------
Core data model for the WSN system.
NodeState is the unified representation for ALL node types:
  - real     : physical ESP32 (telemetry via MQTT)
  - wokwi    : Wokwi-simulated ESP32 (telemetry via MQTT)
  - virtual  : Python-simulated node (in-process)
  - sink     : base station / data collector
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


# ─── Node type literals ────────────────────────────────────────────────────────
NODE_TYPE_REAL    = "real"
NODE_TYPE_WOKWI   = "wokwi"
NODE_TYPE_VIRTUAL = "virtual"
NODE_TYPE_SINK    = "sink"


@dataclass
class LinkInfo:
    """Stores per-link metadata from a node's perspective."""
    neighbor_id: str
    rssi: float = -80.0        # dBm
    lqi: float  = 0.5          # link quality index [0,1]
    distance: float = 10.0     # estimated metres
    last_seen: float = field(default_factory=time.time)

    @property
    def is_fresh(self, max_age: float = 30.0) -> bool:
        return (time.time() - self.last_seen) < max_age


@dataclass
class NodeState:
    """
    Unified node state shared between real HW, Wokwi, virtual, and sink nodes.

    Energy scale: 0.0 (dead) → 100.0 (full charge)
    Load: number of packets currently buffered / being forwarded
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    node_id:   str
    node_type: str = NODE_TYPE_VIRTUAL     # "real" | "wokwi" | "virtual" | "sink"

    # ── Physical state ────────────────────────────────────────────────────────
    energy:   float = 100.0   # residual energy %
    load:     int   = 0       # forwarded packet count this window
    rssi:     float = -60.0   # latest RSSI reading (dBm)
    alive:    bool  = True

    # ── Position (for graph layout and distance calculation) ──────────────────
    x: float = 0.0
    y: float = 0.0

    # ── Neighbour table ────────────────────────────────────────────────────────
    neighbors: Dict[str, LinkInfo] = field(default_factory=dict)

    # ── Packet counters ───────────────────────────────────────────────────────
    packets_sent:     int = 0
    packets_received: int = 0
    packets_dropped:  int = 0

    # ── Timestamps ────────────────────────────────────────────────────────────
    last_seen:   float = field(default_factory=time.time)
    created_at:  float = field(default_factory=time.time)

    # ── Optional metadata ─────────────────────────────────────────────────────
    firmware_version: Optional[str] = None
    ip_address:       Optional[str] = None

    # ─── Derived helpers ──────────────────────────────────────────────────────
    @property
    def energy_level(self) -> str:
        """Discretised energy for RL state encoding."""
        if self.energy > 66:
            return "high"
        elif self.energy > 33:
            return "medium"
        else:
            return "low"

    @property
    def load_level(self) -> str:
        if self.load < 5:
            return "low"
        elif self.load < 15:
            return "medium"
        else:
            return "high"

    @property
    def rssi_level(self) -> str:
        if self.rssi > -60:
            return "strong"
        elif self.rssi > -80:
            return "medium"
        else:
            return "weak"

    @property
    def lqi(self) -> float:
        """Normalised link quality [0,1] from RSSI."""
        # Map [-100, -30] dBm → [0, 1]
        return max(0.0, min(1.0, (self.rssi + 100) / 70.0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id":         self.node_id,
            "node_type":       self.node_type,
            "energy":          round(self.energy, 2),
            "load":            self.load,
            "rssi":            round(self.rssi, 1),
            "alive":           self.alive,
            "x":               self.x,
            "y":               self.y,
            "packets_sent":    self.packets_sent,
            "packets_received":self.packets_received,
            "packets_dropped": self.packets_dropped,
            "last_seen":       self.last_seen,
        }

    def update_from_telemetry(self, data: Dict[str, Any]) -> None:
        """Merge a received telemetry dict into this node's state."""
        self.energy   = float(data.get("energy",   self.energy))
        self.load     = int(data.get("load",     self.load))
        self.rssi     = float(data.get("rssi",     self.rssi))
        self.alive    = self.energy > 0
        self.last_seen = time.time()


@dataclass
class RoutingDecision:
    """A logged routing decision made by the routing engine."""
    source:      str
    sink:        str
    path:        list
    cost:        float
    timestamp:   float = field(default_factory=time.time)
    success:     bool  = True
    hop_count:   int   = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source":    self.source,
            "sink":      self.sink,
            "path":      self.path,
            "cost":      round(self.cost, 4),
            "hop_count": self.hop_count,
            "success":   self.success,
            "timestamp": self.timestamp,
        }


@dataclass
class PacketEvent:
    """Represents a packet transmission event for RL reward computation."""
    packet_id:  int
    source:     str
    sink:       str
    path:       list
    success:    bool
    latency_ms: float
    energy_spent: float
    timestamp:  float = field(default_factory=time.time)
