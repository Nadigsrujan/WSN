"""
routing/cost_functions.py
--------------------------
Composite Multi-Metric edge cost function.

Cost(u,v) = α*W_E + β*W_L + γ*W_ENV + δ*W_T + ε*W_P

Where:
  W_E   = 1 / (E_r + E_p)                  [Energy]
  W_L   = 1 / (LQI * L_q) + I_s            [Link Quality]
  W_ENV = T_f + F_f                        [Environment]
  W_T   = N_l + Q_d                        [Traffic/Load]
  W_P   = D + H_c                          [Path Length]

Weights (tuned dynamically by RL):
  alpha, beta, gamma, delta, epsilon
"""

from __future__ import annotations
import math
from typing import Dict

from backend.models import NodeState


# ─── Default weights ──────────────────────────────────────────────────────────
DEFAULT_WEIGHTS: Dict[str, float] = {
    "alpha":   0.25,   # Energy
    "beta":    0.25,   # Link Quality
    "gamma":   0.15,   # Environment
    "delta":   0.15,   # Traffic
    "epsilon": 0.20,   # Path
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
    Compute the weighted composite multi-metric cost for directed edge u→v.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    alpha   = weights.get("alpha", DEFAULT_WEIGHTS["alpha"])
    beta    = weights.get("beta", DEFAULT_WEIGHTS["beta"])
    gamma   = weights.get("gamma", DEFAULT_WEIGHTS["gamma"])
    delta   = weights.get("delta", DEFAULT_WEIGHTS["delta"])
    epsilon = weights.get("epsilon", DEFAULT_WEIGHTS["epsilon"])

    # ── W_E: Energy Term ──────────────────────────────────────────────────────
    e_r = max(v.energy, 0.1)
    e_p = max(v.predicted_energy, 0.1)
    w_e = 1.0 / (e_r + e_p) * 100.0  # scale to reasonable range

    # ── W_L: Link Quality Term ────────────────────────────────────────────────
    rssi = rssi_override if rssi_override is not None else v.rssi
    lqi = max(rssi_to_lqi(rssi), 0.01)
    l_q = max(getattr(v, 'l_q', 0.9), 0.01)  # Using getattr in case of missing prop
    i_s = getattr(v, 'i_s', 0.0)
    w_l = (1.0 / (lqi * l_q)) + (i_s * 10.0)

    # ── W_ENV: Environment Term ───────────────────────────────────────────────
    t_f = getattr(v, 't_f', 0.0)
    f_f = getattr(v, 'f_f', 0.0)
    w_env = (t_f + f_f) * 10.0

    # ── W_T: Traffic Term ─────────────────────────────────────────────────────
    n_l = float(v.load)
    q_d = getattr(v, 'queue_delay', 0.0) / 100.0  # Normalize delay
    w_t = (n_l / 10.0)**2 + q_d  # Quadratic load penalty

    # ── W_P: Path Term ────────────────────────────────────────────────────────
    dist = euclidean_distance(u, v) / 100.0
    h_c = float(getattr(v, 'hop_count', 1))
    w_p = dist + h_c

    cost = (
        alpha * w_e +
        beta * w_l +
        gamma * w_env +
        delta * w_t +
        epsilon * w_p
    )

    return max(cost, 0.0)

def compute_link_cost_from_raw(
    energy_v: float,
    distance: float,
    rssi: float,
    load_v: int,
    weights: Dict[str, float] = None,
) -> float:
    """Fallback stub for raw calculation, mostly used in RL hypotheticals."""
    if weights is None:
        weights = DEFAULT_WEIGHTS
        
    e_r = max(energy_v, 0.1)
    lqi = max(rssi_to_lqi(rssi), 0.01)
    dist = distance / 100.0
    
    alpha = weights.get("alpha", 0.25)
    beta = weights.get("beta", 0.25)
    delta = weights.get("delta", 0.15)
    epsilon = weights.get("epsilon", 0.20)
    
    w_e = 1.0 / (e_r * 2) * 100.0
    w_l = 1.0 / (lqi * 0.9)
    w_t = (float(load_v) / 10.0)**2
    w_p = dist + 1.0
    
    return alpha*w_e + beta*w_l + delta*w_t + epsilon*w_p
