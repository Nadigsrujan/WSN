"""
simulation/virtual_nodes.py
-----------------------------
Python-simulated WSN nodes.

Each VirtualNode:
  - has a position (x, y) in metres
  - drains energy based on Tx/Rx/Idle model
  - simulates RSSI fluctuation
  - can be killed (energy = 0 or explicit kill)
  - integrates directly with TelemetryStore (no MQTT needed)
"""

from __future__ import annotations
import math
import random
import time
from typing import Dict, List, Optional

from backend.models import NodeState, NODE_TYPE_VIRTUAL, NODE_TYPE_SINK
from simulation.energy_model import (
    full_step_drain,
    distance_to_rssi,
    fluctuate_rssi,
)
from backend.utils import get_logger

log = get_logger("virtual_nodes")


class VirtualNode:
    """
    A fully software-simulated WSN node.
    Wraps a NodeState and adds simulation-specific behaviour.
    """

    def __init__(
        self,
        node_id:        str,
        x:              float,
        y:              float,
        energy:         float = 100.0,
        node_type:      str   = NODE_TYPE_VIRTUAL,
        tx_multiplier:  float = 1.0,    # simulate nodes under heavy load
    ) -> None:
        self.state = NodeState(
            node_id=node_id,
            node_type=node_type,
            energy=energy,
            load=0,
            rssi=-60.0,
            alive=True,
            x=x,
            y=y,
        )
        self.tx_multiplier   = tx_multiplier
        self._base_rssi: Dict[str, float] = {}   # {neighbor_id: base_rssi}
        self._packets_forwarded_this_step = 0

    # ─── Step simulation ──────────────────────────────────────────────────────

    def step(
        self,
        packets_tx: int = 0,
        packets_rx: int = 0,
        sensing:    bool = True,
    ) -> NodeState:
        """
        Advance the node by one simulation tick.
        Drains energy, fluctuates RSSI, updates load.
        """
        if not self.state.alive:
            return self.state

        # Apply energy drain
        self.state.energy = full_step_drain(
            self.state.energy,
            packets_tx=int(packets_tx * self.tx_multiplier),
            packets_rx=packets_rx,
            sensing=sensing,
        )

        # Check for death
        if self.state.energy <= 0:
            self.state.energy = 0.0
            self.state.alive  = False
            log.warning(f"Virtual node {self.state.node_id} ran out of energy")

        # Fluctuate RSSI
        self.state.rssi = fluctuate_rssi(self.state.rssi)

        # Update load (decay slowly each step)
        self.state.load = max(0, self.state.load - 1)
        self.state.load += self._packets_forwarded_this_step
        self._packets_forwarded_this_step = 0

        # Update timestamp
        self.state.last_seen = time.time()

        return self.state

    def forward_packet(self) -> None:
        """Record that this node forwarded a packet this step."""
        self._packets_forwarded_this_step += 1
        self.state.packets_sent += 1

    def receive_packet(self) -> None:
        """Record that this node received a packet."""
        self.state.packets_received += 1

    def kill(self) -> None:
        """Force-kill this node (simulate hardware failure)."""
        self.state.energy = 0.0
        self.state.alive  = False
        log.warning(f"Node {self.state.node_id} force-killed")

    def set_rssi_to(self, neighbor_id: str, distance_m: float) -> None:
        """Pre-compute and store base RSSI for a given neighbour distance."""
        base_rssi = distance_to_rssi(distance_m)
        self._base_rssi[neighbor_id] = base_rssi

    def update_rssi_from_neighbors(self, neighbors: List["VirtualNode"]) -> None:
        """Refresh RSSI based on Euclidean distances to alive neighbours."""
        if not neighbors:
            return
        distances = [
            math.sqrt((self.state.x - n.state.x)**2 + (self.state.y - n.state.y)**2)
            for n in neighbors if n.state.alive
        ]
        if distances:
            avg_dist        = sum(distances) / len(distances)
            self.state.rssi = distance_to_rssi(avg_dist)

    @property
    def node_id(self) -> str:
        return self.state.node_id

    @property
    def is_alive(self) -> bool:
        return self.state.alive


class VirtualSink(VirtualNode):
    """
    The base station / data sink.
    Has infinite energy and does not drain.
    """

    def __init__(self, node_id: str = "SINK", x: float = 0.0, y: float = 0.0) -> None:
        super().__init__(node_id=node_id, x=x, y=y, node_type=NODE_TYPE_SINK)
        self.state.energy = 999.0   # effectively infinite

    def step(self, **kwargs) -> NodeState:
        """Sink never drains energy."""
        self.state.last_seen = time.time()
        return self.state


def create_random_topology(
    n_nodes:    int   = 5,
    area_m:     float = 100.0,
    prefix:     str   = "VNODE",
    energy_min: float = 70.0,
    energy_max: float = 100.0,
) -> List[VirtualNode]:
    """
    Randomly place `n_nodes` virtual nodes in an `area_m` x `area_m` field.
    Useful for quick simulation setup.
    """
    nodes = []
    for i in range(1, n_nodes + 1):
        node = VirtualNode(
            node_id=f"{prefix}_{i}",
            x=random.uniform(10, area_m - 10),
            y=random.uniform(10, area_m - 10),
            energy=random.uniform(energy_min, energy_max),
        )
        nodes.append(node)
    log.info(f"Created {n_nodes} virtual nodes in {area_m}m x {area_m}m field")
    return nodes
