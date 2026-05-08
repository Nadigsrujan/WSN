"""
backend/metrics.py
-------------------
Performance metrics tracker for the WSN system.

Tracked metrics:
  - Packet Delivery Ratio (PDR)
  - First Node Death (FND) step
  - Half Node Death (HND) step
  - Network lifetime
  - Energy variance over time
  - Average routing latency
  - Rerouting events
  - Throughput (packets/step)
"""

from __future__ import annotations
import time
from typing import List, Optional, Dict

from backend.models import NodeState
from rl.reward_shaper import compute_energy_variance, compute_pdr
from backend.utils import get_logger

log = get_logger("metrics")


class MetricsTracker:
    """
    Tracks all WSN performance metrics over the lifetime of the simulation.
    """

    def __init__(self, total_nodes: int) -> None:
        self.total_nodes   = total_nodes
        self.start_time    = time.time()

        # Packet counters
        self.packets_sent      = 0
        self.packets_delivered = 0
        self.packets_dropped   = 0

        # Node death milestones
        self.fnd_step: Optional[int] = None   # First Node Death
        self.hnd_step: Optional[int] = None   # Half Node Death
        self._prev_dead_count = 0

        # Per-step history
        self.energy_variance_history: List[float] = []
        self.pdr_history:             List[float] = []
        self.alive_history:           List[int]   = []
        self.weight_history:          List[Dict]  = []

        # Routing
        self.rerouting_events = 0
        self.routing_latencies: List[float] = []
        self._last_path: List[str] = []

    # ─── Per-step update ──────────────────────────────────────────────────────

    def update(
        self,
        nodes:       List[NodeState],
        step:        int,
        path:        List[str],
        delivered:   bool,
        weights:     Dict[str, float],
        latency_ms:  float = 0.0,
    ) -> None:
        """Call once per simulation tick with current network state."""
        alive_nodes = [n for n in nodes if n.alive]
        alive_count = len(alive_nodes)
        dead_count  = self.total_nodes - alive_count

        # ── Packet stats ──────────────────────────────────────────────────────
        self.packets_sent += 1
        if delivered:
            self.packets_delivered += 1
        else:
            self.packets_dropped += 1

        # ── Rerouting detection ───────────────────────────────────────────────
        if self._last_path and path and path != self._last_path:
            self.rerouting_events += 1
            log.info(f"Step {step}: Rerouting detected (event #{self.rerouting_events})")
        self._last_path = list(path)

        # ── Node death milestones ─────────────────────────────────────────────
        if self.fnd_step is None and dead_count >= 1:
            self.fnd_step = step
            log.warning(f"FIRST NODE DEATH at step {step}")

        if self.hnd_step is None and dead_count >= (self.total_nodes // 2):
            self.hnd_step = step
            log.warning(f"HALF NODE DEATH at step {step}")

        self._prev_dead_count = dead_count

        # ── Histories ─────────────────────────────────────────────────────────
        self.energy_variance_history.append(
            round(compute_energy_variance(alive_nodes), 2)
        )
        self.pdr_history.append(round(self.pdr, 4))
        self.alive_history.append(alive_count)
        self.weight_history.append(dict(weights))
        if latency_ms > 0:
            self.routing_latencies.append(latency_ms)

    # ─── Derived metrics ──────────────────────────────────────────────────────

    @property
    def pdr(self) -> float:
        """Packet Delivery Ratio [0, 1]."""
        return compute_pdr(self.packets_sent, self.packets_delivered)

    @property
    def avg_latency_ms(self) -> float:
        if not self.routing_latencies:
            return 0.0
        return round(sum(self.routing_latencies) / len(self.routing_latencies), 2)

    @property
    def network_lifetime_s(self) -> float:
        """Seconds since simulation start."""
        return round(time.time() - self.start_time, 1)

    @property
    def throughput(self) -> float:
        """Delivered packets per second."""
        elapsed = max(self.network_lifetime_s, 1.0)
        return round(self.packets_delivered / elapsed, 3)

    @property
    def current_energy_variance(self) -> float:
        if not self.energy_variance_history:
            return 0.0
        return self.energy_variance_history[-1]

    # ─── Summary ──────────────────────────────────────────────────────────────

    def summary(self) -> Dict:
        return {
            "packets_sent":       self.packets_sent,
            "packets_delivered":  self.packets_delivered,
            "packets_dropped":    self.packets_dropped,
            "pdr":                round(self.pdr * 100, 1),
            "fnd_step":           self.fnd_step,
            "hnd_step":           self.hnd_step,
            "rerouting_events":   self.rerouting_events,
            "avg_latency_ms":     self.avg_latency_ms,
            "network_lifetime_s": self.network_lifetime_s,
            "throughput_pps":     self.throughput,
            "energy_variance":    self.current_energy_variance,
        }
