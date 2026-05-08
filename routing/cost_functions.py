"""
routing/cost_functions.py
--------------------------
Multi-metric edge cost function.

Cost(u,v) = w1*(1/Ev) + w2*d_uv + w3*(1/LQ_uv) + w4*Lv

Where:
  Ev     = residual energy of node v          (0–100)
  d_uv   = Euclidean distance u→v (metres)
  LQ_uv  = link quality index [0,1]           (from RSSI)
  Lv     = current load of node v             (packet count)

Default weights (tuned dynamically by the RL agent):
  w1=0.40  (energy)
  w2=0.20  (distance)
  w3=0.25  (link quality)
  w4=0.15  (load)
"""

from __future__ import annotations
import math
from typing import Dict

from backend.models import NodeState


# ─── Default weights ──────────────────────────────────────────────────────────
DEFAULT_WEIGHTS: Dict[str, float] = {
    "w1": 0.40,   # energy
    "w2": 0.20,   # distance
    "w3": 0.25,   # link quality
    "w4": 0.15,   # load
}


def euclidean_distance(a: NodeState, b: NodeState) -> float:
    """Euclidean distance between two nodes using their (x, y) positions."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def rssi_to_lqi(rssi: float) -> float:
    """
    Convert RSSI (dBm) to a normalised Link Quality Index [0, 1].
    Maps [-100, -30] dBm → [0.0, 1.0]
    """
    lqi = (rssi + 100.0) / 70.0
    return max(0.0, min(1.0, lqi))


def compute_edge_cost(
    u: NodeState,
    v: NodeState,
    weights: Dict[str, float] = None,
    rssi_override: float = None,
) -> float:
    """
    Compute the weighted multi-metric cost for the directed edge u→v.

    The cost is HIGH for undesirable next hops (low energy, far away,
    bad link, heavily loaded) and LOW for ideal next hops.

    Parameters
    ----------
    u             : source node
    v             : candidate next-hop node
    weights       : {w1, w2, w3, w4} dict (uses DEFAULT_WEIGHTS if None)
    rssi_override : use a specific RSSI value instead of v.rssi

    Returns
    -------
    float: edge cost ≥ 0  (lower = better)
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    w1 = weights.get("w1", DEFAULT_WEIGHTS["w1"])
    w2 = weights.get("w2", DEFAULT_WEIGHTS["w2"])
    w3 = weights.get("w3", DEFAULT_WEIGHTS["w3"])
    w4 = weights.get("w4", DEFAULT_WEIGHTS["w4"])

    # ── Energy term: 1/Ev — penalises low-energy nodes ────────────────────────
    ev = max(v.energy, 0.1)          # avoid /0
    energy_term = 1.0 / ev

    # ── Distance term: normalised Euclidean distance ───────────────────────────
    dist = euclidean_distance(u, v)
    # Normalise by reference distance of 100 m
    distance_term = dist / 100.0

    # ── Link quality term: 1/LQ — penalises poor links ────────────────────────
    rssi  = rssi_override if rssi_override is not None else v.rssi
    lq    = max(rssi_to_lqi(rssi), 0.01)   # avoid /0
    lq_term = 1.0 / lq

    # ── Load term: non-linear penalty for congested nodes ────────────────────
    # Quadratic: load=10 → 1.0, load=50 → 25.0, load=95 → 90.25
    # This ensures high-load nodes (e.g. ESP32 at load=95) get a DRAMATIC
    # cost spike, forcing the routing engine to reroute around them.
    load_term = (float(v.load) / 10.0) ** 2

    cost = (
        w1 * energy_term  +
        w2 * distance_term +
        w3 * lq_term       +
        w4 * load_term
    )

    return max(cost, 0.0)


def compute_link_cost_from_raw(
    energy_v: float,
    distance: float,
    rssi: float,
    load_v: int,
    weights: Dict[str, float] = None,
) -> float:
    """
    Raw-value version — useful when NodeState objects aren't available
    (e.g., inside the RL agent for hypothetical edge evaluation).
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    ev     = max(energy_v, 0.1)
    lq     = max(rssi_to_lqi(rssi), 0.01)
    d_norm = distance / 100.0

    return (
        weights.get("w1", 0.40) / ev          +
        weights.get("w2", 0.20) * d_norm      +
        weights.get("w3", 0.25) / lq          +
        weights.get("w4", 0.15) * float(load_v)
    )
