"""
backend/telemetry_store.py
--------------------------
Thread-safe in-memory store for all node states.
Accepts updates from:
  - MQTT ingestor (real / Wokwi nodes)
  - simulation engine (virtual nodes)

Position-freezing:
  - Once freeze_position(node_id) is called for a node, its x/y coordinates
    are permanently locked. Any subsequent call to set_node_position() is
    silently ignored (logged as debug). This guarantees physical positions
    NEVER change at runtime.
  - update_from_telemetry() NEVER updates x/y from incoming data — real
    ESP32s report position in their JSON payload, but we always use the
    static mesh position instead.
"""

import threading
import time
from typing import Dict, List, Optional, Set

from backend.models import NodeState, NODE_TYPE_VIRTUAL, NODE_TYPE_SINK
from backend.utils import get_logger

log = get_logger("telemetry_store")


class TelemetryStore:
    """
    Central store for NodeState objects.

    All read/write operations are protected by a reentrant lock so both
    the MQTT thread and the main orchestration loop can safely access it.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, NodeState] = {}
        self._lock  = threading.RLock()
        self._step  = 0
        # Set of node IDs whose positions are permanently frozen
        self._frozen_positions: Set[str] = set()

    # ─── Write operations ─────────────────────────────────────────────────────

    def upsert(self, node: NodeState) -> None:
        """Insert or replace a node state entry.
        If the node's position is frozen, x/y from the incoming state are
        ignored and the stored coordinates are preserved."""
        with self._lock:
            if node.node_id in self._nodes and node.node_id in self._frozen_positions:
                # Preserve frozen position
                existing = self._nodes[node.node_id]
                node.x = existing.x
                node.y = existing.y
            self._nodes[node.node_id] = node

    def update_from_telemetry(self, data: dict) -> NodeState:
        """
        Merge incoming telemetry dict into existing state.
        Creates the node entry if not present.
        Returns the updated NodeState.

        IMPORTANT: x/y coordinates from telemetry are NEVER applied —
        we always use static mesh positions only.
        """
        with self._lock:
            node_id   = data["node_id"]
            node_type = data.get("node_type", "real")

            if node_id not in self._nodes:
                node = NodeState(node_id=node_id, node_type=node_type)
                log.info(f"New node registered: {node_id} ({node_type})")
            else:
                node = self._nodes[node_id]

            # Update telemetry fields (energy, load, rssi, etc.)
            # but NEVER x/y — those come from static mesh config only
            node.energy    = float(data.get("energy",   node.energy))
            node.load      = int(data.get("load",     node.load))
            node.rssi      = float(data.get("rssi",     node.rssi))
            node.alive     = node.energy > 0
            node.last_seen = time.time()

            # Optional fields from firmware
            if "packets_sent" in data:
                node.packets_sent = int(data["packets_sent"])
            if "current_mA" in data:
                pass  # Hardware telemetry — stored if needed in future

            self._nodes[node_id] = node
            return node

    def mark_dead(self, node_id: str) -> None:
        with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].alive = False
                log.warning(f"Node {node_id} marked dead")

    def remove(self, node_id: str) -> None:
        with self._lock:
            self._nodes.pop(node_id, None)
            self._frozen_positions.discard(node_id)

    def increment_step(self) -> int:
        with self._lock:
            self._step += 1
            return self._step

    # ─── Position management ──────────────────────────────────────────────────

    def freeze_position(self, node_id: str) -> None:
        """
        Permanently lock a node's x/y coordinates.
        After calling this, any set_node_position() call for this node
        will be silently ignored.
        """
        with self._lock:
            self._frozen_positions.add(node_id)
            log.debug(f"Position frozen for node {node_id}")

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        """
        Override the position of a node.
        If the node's position is frozen, this call is ignored.
        """
        with self._lock:
            if node_id in self._frozen_positions:
                log.debug(
                    f"Position override ignored for {node_id} "
                    f"(position is frozen at {self._nodes[node_id].x:.1f}, "
                    f"{self._nodes[node_id].y:.1f})"
                )
                return
            if node_id in self._nodes:
                self._nodes[node_id].x = x
                self._nodes[node_id].y = y
                log.info(f"Position set: {node_id} → ({x:.1f}, {y:.1f})")

    def initialize_position(self, node_id: str, x: float, y: float) -> None:
        """
        Set a node's position and immediately freeze it.
        Use this during startup to place nodes at their static mesh coordinates.
        """
        with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].x = x
                self._nodes[node_id].y = y
            self._frozen_positions.add(node_id)
            log.debug(
                f"Position initialized and frozen: {node_id} → ({x:.1f}, {y:.1f})"
            )

    def update_node_cluster_status(
        self, node_id: str, cluster_id: int, is_ch: bool
    ) -> None:
        """Update and persist the clustering role for a node.
        Only is_ch and cluster_id are written — never x/y."""
        with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].cluster_id = cluster_id
                self._nodes[node_id].is_ch = is_ch
                self._nodes[node_id].last_seen = time.time()

    # ─── Read operations ──────────────────────────────────────────────────────

    def get(self, node_id: str) -> Optional[NodeState]:
        with self._lock:
            return self._nodes.get(node_id)

    def all_nodes(self) -> List[NodeState]:
        with self._lock:
            return list(self._nodes.values())

    def alive_nodes(self) -> List[NodeState]:
        with self._lock:
            return [n for n in self._nodes.values() if n.alive]

    def dead_nodes(self) -> List[NodeState]:
        with self._lock:
            return [n for n in self._nodes.values() if not n.alive]

    def node_ids(self) -> List[str]:
        with self._lock:
            return list(self._nodes.keys())

    def count(self) -> int:
        with self._lock:
            return len(self._nodes)

    def alive_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._nodes.values() if n.alive)

    def step(self) -> int:
        return self._step

    # ─── Failure detection ────────────────────────────────────────────────────

    def check_stale_nodes(self, max_age_s: float = 3600.0) -> List[str]:
        """
        Mark real/Wokwi nodes dead if we haven't heard from them recently.
        Increased default timeout to 1 hour for real nodes to prevent vanishing.
        Virtual nodes are managed by the simulation, not here.
        """
        now   = time.time()
        stale = []
        with self._lock:
            for node in self._nodes.values():
                if node.node_type in ("real", "wokwi") and node.alive:
                    age = now - node.last_seen

                    # GRACE PERIOD: give newly connected nodes 5 mins to settle
                    if age < 300.0:
                        continue

                    if age > max_age_s:
                        node.alive = False
                        stale.append(node.node_id)
                        log.warning(
                            f"Node {node.node_id} stale ({age:.1f}s) — marked dead"
                        )
        return stale

    # ─── Snapshot for dashboard ───────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of the current network state."""
        with self._lock:
            return {
                "step":        self._step,
                "timestamp":   time.time(),
                "node_count":  len(self._nodes),
                "alive_count": self.alive_count(),
                "nodes":       {n.node_id: n.to_dict() for n in self._nodes.values()},
            }
