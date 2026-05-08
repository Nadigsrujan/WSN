"""
simulation/failure_injection.py
---------------------------------
Controlled failure injection for research experiments.

Supports:
  - killing specific nodes by ID
  - killing the lowest-energy node (natural death simulation)
  - degrading link quality between two nodes
  - scheduled failure sequences
  - probabilistic random failure
"""

from __future__ import annotations
import random
import time
from typing import List, Optional, Dict, Callable

from simulation.virtual_nodes import VirtualNode
from backend.utils import get_logger

log = get_logger("failure_injection")


class FailureInjector:
    """
    Injects controlled failures into the virtual node fleet.
    Used for research experiments and dashboard demo controls.
    """

    def __init__(self, vnodes: List[VirtualNode]) -> None:
        self.vnodes = vnodes
        self._events: List[Dict] = []

    # ─── Immediate failures ───────────────────────────────────────────────────

    def kill_node(self, node_id: str) -> bool:
        """Kill a specific node immediately."""
        for v in self.vnodes:
            if v.node_id == node_id and v.is_alive:
                v.kill()
                self._log_event("kill", node_id)
                return True
        log.warning(f"Cannot kill {node_id}: not found or already dead")
        return False

    def kill_weakest(self) -> Optional[str]:
        """Kill the node with the lowest residual energy."""
        alive = [v for v in self.vnodes if v.is_alive]
        if not alive:
            return None
        weakest = min(alive, key=lambda v: v.state.energy)
        weakest.kill()
        self._log_event("kill_weakest", weakest.node_id)
        return weakest.node_id

    def kill_random(self, n: int = 1) -> List[str]:
        """Kill `n` random alive nodes."""
        alive   = [v for v in self.vnodes if v.is_alive]
        targets = random.sample(alive, k=min(n, len(alive)))
        killed  = []
        for t in targets:
            t.kill()
            killed.append(t.node_id)
            self._log_event("kill_random", t.node_id)
        return killed

    # ─── Energy drain injection ───────────────────────────────────────────────

    def drain_node(self, node_id: str, amount: float = 20.0) -> bool:
        """Drain energy from a specific node (simulate burst transmission)."""
        for v in self.vnodes:
            if v.node_id == node_id and v.is_alive:
                v.state.energy = max(0.0, v.state.energy - amount)
                if v.state.energy == 0.0:
                    v.state.alive = False
                self._log_event("drain", node_id, detail=f"-{amount}%")
                return True
        return False

    # ─── Link degradation ─────────────────────────────────────────────────────

    def degrade_link(self, node_id: str, rssi_penalty: float = 20.0) -> bool:
        """
        Degrade the link quality of a node by dropping its RSSI by
        `rssi_penalty` dBm (simulates interference or obstacle).
        """
        for v in self.vnodes:
            if v.node_id == node_id and v.is_alive:
                v.state.rssi = max(-100.0, v.state.rssi - rssi_penalty)
                self._log_event("degrade_link", node_id, detail=f"-{rssi_penalty}dBm")
                log.info(f"Link degraded: {node_id} RSSI → {v.state.rssi:.1f} dBm")
                return True
        return False

    # ─── Probabilistic failure ────────────────────────────────────────────────

    def probabilistic_step(self, failure_prob: float = 0.02) -> List[str]:
        """
        Each alive node has `failure_prob` chance of dying this step.
        Simulates random hardware failures.
        """
        killed = []
        for v in self.vnodes:
            if v.is_alive and random.random() < failure_prob:
                v.kill()
                killed.append(v.node_id)
                self._log_event("probabilistic", v.node_id)
        return killed

    # ─── Scheduled scenario ───────────────────────────────────────────────────

    def run_scenario(self, scenario: List[Dict], sim_step_fn: Callable, n_steps: int) -> None:
        """
        Run a timed failure scenario.

        scenario: list of {step: int, action: str, node_id: str}
        sim_step_fn: callable to advance the simulation by one step
        """
        schedule = {s["step"]: s for s in scenario}
        for step in range(n_steps):
            sim_step_fn()
            if step in schedule:
                event = schedule[step]
                action  = event.get("action", "kill")
                node_id = event.get("node_id")
                if action == "kill" and node_id:
                    self.kill_node(node_id)
                elif action == "drain" and node_id:
                    self.drain_node(node_id, event.get("amount", 20.0))
                elif action == "degrade" and node_id:
                    self.degrade_link(node_id, event.get("penalty", 20.0))

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _log_event(self, action: str, node_id: str, detail: str = "") -> None:
        event = {
            "timestamp": time.time(),
            "action":    action,
            "node_id":   node_id,
            "detail":    detail,
        }
        self._events.append(event)
        log.info(f"Failure event: {action} → {node_id} {detail}")

    @property
    def event_log(self) -> List[Dict]:
        return list(self._events)
