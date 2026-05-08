"""
simulation/network_sim.py
--------------------------
Simulation engine: manages a fleet of VirtualNodes and integrates
their state into the shared TelemetryStore each tick.

Supports:
  - N virtual nodes with FIXED MESH positions (or random fallback)
  - A fixed VirtualSink node
  - Per-step energy drain and RSSI updates
  - Periodic random packet forwarding events
  - State injection into TelemetryStore
"""

from __future__ import annotations
import random
import time
import threading
from typing import Dict, List, Optional, Tuple

from backend.models import NodeState
from backend.telemetry_store import TelemetryStore
from simulation.virtual_nodes import VirtualNode, VirtualSink, create_random_topology
from backend.utils import get_logger, log_telemetry

log = get_logger("network_sim")


class NetworkSimulator:
    """
    Runs virtual nodes in background and injects their state into
    the TelemetryStore on every tick.
    """

    def __init__(
        self,
        store:           TelemetryStore,
        n_virtual:       int   = 5,
        area_m:          float = 100.0,
        tick_interval_s: float = 2.0,
        sink_position:   tuple = (50.0, 50.0),
        mesh_positions:  Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> None:
        self.store           = store
        self.tick_interval   = tick_interval_s
        self.area_m          = area_m

        # Create virtual nodes — use mesh positions if provided
        if mesh_positions:
            self.vnodes: List[VirtualNode] = []
            for nid, (x, y) in sorted(mesh_positions.items()):
                vnode = VirtualNode(
                    node_id=nid,
                    x=x,
                    y=y,
                    energy=random.uniform(70.0, 100.0),
                )
                self.vnodes.append(vnode)
            log.info(f"Created {len(self.vnodes)} virtual nodes from mesh positions")
        else:
            self.vnodes = create_random_topology(
                n_nodes=n_virtual,
                area_m=area_m,
                prefix="VNODE",
            )

        # Sink
        self.sink = VirtualSink(
            node_id="SINK",
            x=sink_position[0],
            y=sink_position[1],
        )

        self._running    = False
        self._thread:    Optional[threading.Thread] = None
        self._step       = 0
        self._dead_log:  List[str] = []

        # Register all nodes in the store immediately
        self._sync_to_store()

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start background simulation thread."""
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info(f"Simulation started: {len(self.vnodes)} virtual nodes + SINK")

    def stop(self) -> None:
        """Stop simulation thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Simulation stopped")

    # ─── Main loop ────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        while self._running:
            self._tick()
            time.sleep(self.tick_interval)

    def _tick(self) -> None:
        self._step += 1

        # Simulate a random routing event: pick a source node, it forwards
        alive = [n for n in self.vnodes if n.is_alive]
        if not alive:
            log.warning("All virtual nodes are dead!")
            return

        # Randomly pick 1–2 nodes that forward a packet this step
        forwarders = random.sample(alive, k=min(2, len(alive)))
        for node in forwarders:
            node.forward_packet()

        # Randomly pick 1–3 nodes that receive a packet
        receivers = random.sample(alive, k=min(3, len(alive)))
        for node in receivers:
            node.receive_packet()

        # Step all alive nodes
        prev_alive = {n.node_id for n in self.vnodes if n.is_alive}
        for vnode in self.vnodes:
            if vnode.is_alive:
                packets_tx = 1 if vnode in forwarders else 0
                packets_rx = 1 if vnode in receivers  else 0
                vnode.step(packets_tx=packets_tx, packets_rx=packets_rx)
                vnode.update_rssi_from_neighbors(
                    [n for n in self.vnodes if n.node_id != vnode.node_id and n.is_alive]
                )

        # Detect newly dead nodes
        curr_alive = {n.node_id for n in self.vnodes if n.is_alive}
        newly_dead = prev_alive - curr_alive
        for nid in newly_dead:
            log.warning(f"Step {self._step}: {nid} just died")
            self._dead_log.append(nid)

        # Sync all node states into the TelemetryStore
        self._sync_to_store()

        if self._step % 10 == 0:
            alive_count = len(curr_alive)
            log.info(f"Step {self._step}: {alive_count}/{len(self.vnodes)} nodes alive")

    def _sync_to_store(self) -> None:
        """Push all virtual node states into the TelemetryStore."""
        # Virtual nodes
        for vnode in self.vnodes:
            self.store.upsert(vnode.state)
            log_telemetry(vnode.state.to_dict())

        # Sink
        self.store.upsert(self.sink.state)

    # ─── Manual control ───────────────────────────────────────────────────────

    def kill_node(self, node_id: str) -> bool:
        """Manually kill a virtual node."""
        for vnode in self.vnodes:
            if vnode.node_id == node_id:
                vnode.kill()
                self._sync_to_store()
                return True
        log.warning(f"Node {node_id} not found in virtual nodes")
        return False

    def revive_node(self, node_id: str, energy: float = 50.0) -> bool:
        """Revive a dead virtual node with given energy (for research testing)."""
        for vnode in self.vnodes:
            if vnode.node_id == node_id:
                vnode.state.energy = energy
                vnode.state.alive  = True
                self._sync_to_store()
                log.info(f"Node {node_id} revived with {energy}% energy")
                return True
        return False

    def add_node(self, node_id: str, x: float, y: float, energy: float = 100.0) -> VirtualNode:
        """Dynamically add a new virtual node (topology expansion)."""
        vnode = VirtualNode(node_id=node_id, x=x, y=y, energy=energy)
        self.vnodes.append(vnode)
        self.store.upsert(vnode.state)
        log.info(f"Added new virtual node: {node_id} at ({x:.1f}, {y:.1f})")
        return vnode

    # ─── Stats ────────────────────────────────────────────────────────────────

    @property
    def alive_count(self) -> int:
        return sum(1 for n in self.vnodes if n.is_alive)

    @property
    def dead_log(self) -> List[str]:
        return list(self._dead_log)

    @property
    def step(self) -> int:
        return self._step

    def all_node_states(self) -> List[NodeState]:
        states = [v.state for v in self.vnodes]
        states.append(self.sink.state)
        return states
