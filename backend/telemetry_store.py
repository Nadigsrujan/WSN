"""
backend/telemetry_store.py
--------------------------
Thread-safe in-memory store for all node states.
Accepts updates from:
  - MQTT ingestor (real / Wokwi nodes)
  - simulation engine (virtual nodes)
"""

import threading
import time
from typing import Dict, List, Optional

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
        self._step  = 0                        # global simulation step counter

    # ─── Write operations ─────────────────────────────────────────────────────

    def upsert(self, node: NodeState) -> None:
        """Insert or replace a node state entry."""
        with self._lock:
            self._nodes[node.node_id] = node

    def update_from_telemetry(self, data: dict) -> NodeState:
        """
        Merge incoming telemetry dict into existing state.
        Creates the node entry if not present.
        Returns the updated NodeState.
        """
        with self._lock:
            node_id   = data["node_id"]
            node_type = data.get("node_type", "real")

            if node_id not in self._nodes:
                node = NodeState(node_id=node_id, node_type=node_type)
                log.info(f"New node registered: {node_id} ({node_type})")
            else:
                node = self._nodes[node_id]

            node.update_from_telemetry(data)
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

    def increment_step(self) -> int:
        with self._lock:
            self._step += 1
            return self._step

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

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        """Override the position of a node (used to place real ESP32 into the mesh)."""
        with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].x = x
                self._nodes[node_id].y = y
                log.info(f"Position override: {node_id} → ({x:.1f}, {y:.1f})")

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
                    # Only mark dead if it's REALLY long (1 hour by default now)
                    if age > max_age_s:
                        node.alive = False
                        stale.append(node.node_id)
                        log.warning(f"Node {node.node_id} stale ({age:.1f}s) — marked dead")
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
                "nodes":       {nid: n.to_dict() for nid, n in self._nodes.items()},
            }
