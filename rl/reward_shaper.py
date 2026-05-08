"""
rl/reward_shaper.py
--------------------
Computes RL rewards based on observed network outcomes.

Reward components:
  +10  successful packet delivery
  + 2  energy variance is low (balanced network)
  + 3  congestion is low
  + 1  path hop count is reasonable
  -10  packet dropped / no path found
  - 5  a node just died
  - 3  high energy variance (uneven drain)
  - 2  congestion detected
"""

from __future__ import annotations
import math
from typing import List, Optional
from backend.models import NodeState


# ─── Reward constants ─────────────────────────────────────────────────────────
R_DELIVERY_SUCCESS   = +10.0
R_ENERGY_BALANCED    = + 2.0
R_LOW_CONGESTION     = + 3.0
R_SHORT_PATH         = + 1.0
R_AVOIDED_CONGESTION = + 2.0    # rerouted away from overloaded node

R_DELIVERY_FAIL      = -10.0
R_NODE_DEATH         = - 5.0
R_ENERGY_IMBALANCED  = - 3.0
R_HIGH_CONGESTION    = - 2.0
R_PATH_CONGESTED     = - 3.0    # path goes through overloaded node

# Thresholds
ENERGY_VARIANCE_LOW  = 100.0    # variance below this is "balanced"
LOAD_THRESHOLD       = 10       # avg load above this is "congested"
LOAD_HIGH_THRESHOLD  = 50       # individual node is overloaded
PATH_HOP_IDEAL       = 5        # hop count ≤ this is "short" (multi-hop now)


def compute_reward(
    packet_success:   bool,
    nodes:            List[NodeState],
    newly_dead:       List[str],
    path:             Optional[List[str]] = None,
) -> float:
    """
    Compute the total reward signal after a routing/packet event.

    Parameters
    ----------
    packet_success  : was the packet successfully delivered?
    nodes           : current list of all NodeState objects
    newly_dead      : list of node_ids that just died this step
    path            : the path taken (list of node_id strings)

    Returns
    -------
    float reward value
    """
    reward = 0.0

    # ── Delivery outcome ──────────────────────────────────────────────────────
    reward += R_DELIVERY_SUCCESS if packet_success else R_DELIVERY_FAIL

    # ── Node death penalty ────────────────────────────────────────────────────
    reward += R_NODE_DEATH * len(newly_dead)

    # ── Energy variance ───────────────────────────────────────────────────────
    alive_energies = [n.energy for n in nodes if n.alive and n.node_id != "SINK"]
    if alive_energies:
        variance = _energy_variance(alive_energies)
        if variance < ENERGY_VARIANCE_LOW:
            reward += R_ENERGY_BALANCED
        else:
            reward += R_ENERGY_IMBALANCED

    # ── Congestion ────────────────────────────────────────────────────────────
    alive_loads = [n.load for n in nodes if n.alive]
    if alive_loads:
        avg_load = sum(alive_loads) / len(alive_loads)
        if avg_load < LOAD_THRESHOLD:
            reward += R_LOW_CONGESTION
        else:
            reward += R_HIGH_CONGESTION

    # ── Path length ───────────────────────────────────────────────────────────
    if path and len(path) - 1 <= PATH_HOP_IDEAL:
        reward += R_SHORT_PATH

    # ── Path congestion ───────────────────────────────────────────────────────
    # Penalise if any intermediate node on the path has high load
    if path:
        node_map = {n.node_id: n for n in nodes}
        path_congested = False
        for nid in path[1:-1]:  # exclude source and sink
            n = node_map.get(nid)
            if n and n.load > LOAD_HIGH_THRESHOLD:
                path_congested = True
                break
        if path_congested:
            reward += R_PATH_CONGESTED
        else:
            reward += R_AVOIDED_CONGESTION

    return round(reward, 2)


def _energy_variance(energies: List[float]) -> float:
    """Sample variance of energy values."""
    if len(energies) < 2:
        return 0.0
    mean = sum(energies) / len(energies)
    return sum((e - mean) ** 2 for e in energies) / len(energies)


def compute_energy_variance(nodes: List[NodeState]) -> float:
    """Public helper for the dashboard and metrics."""
    return _energy_variance([n.energy for n in nodes if n.alive and n.node_id != "SINK"])


def compute_pdr(sent: int, received: int) -> float:
    """Packet Delivery Ratio."""
    if sent == 0:
        return 1.0
    return min(received / sent, 1.0)
