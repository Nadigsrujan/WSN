"""
rl/state_encoder.py
--------------------
Converts continuous NodeState values into a discrete, hashable RL state tuple.

State = (energy_level, rssi_level, load_level, network_health)

Each dimension is discretised into 3 bins:
  energy_level  : "high" | "medium" | "low"
  rssi_level    : "strong" | "medium" | "weak"
  load_level    : "low"  | "medium" | "high"
  net_health    : "healthy" | "degraded" | "critical"
"""

from __future__ import annotations
from typing import Tuple, List
from backend.models import NodeState


# ─── Type alias ───────────────────────────────────────────────────────────────
RLState = Tuple[str, str, str, str]


def encode_node_state(node: NodeState, alive_fraction: float = 1.0) -> RLState:
    """
    Encode a single node's state + global network health into an RL state tuple.

    Parameters
    ----------
    node           : the node whose state we're encoding
    alive_fraction : fraction of network still alive  (0.0 → 1.0)

    Returns
    -------
    (energy_level, rssi_level, load_level, network_health)
    """
    energy_level  = node.energy_level
    rssi_level    = node.rssi_level
    load_level    = node.load_level
    net_health    = _encode_network_health(alive_fraction)

    return (energy_level, rssi_level, load_level, net_health)


def encode_global_state(
    avg_energy: float,
    avg_rssi: float,
    avg_load: float,
    alive_fraction: float,
) -> RLState:
    """
    Encode a global view of the network (used for weight-tuning RL actions).
    """
    energy_level = _bin_energy(avg_energy)
    rssi_level   = _bin_rssi(avg_rssi)
    load_level   = _bin_load(int(avg_load))
    net_health   = _encode_network_health(alive_fraction)
    return (energy_level, rssi_level, load_level, net_health)


# ─── Bin helpers ──────────────────────────────────────────────────────────────

def _bin_energy(energy: float) -> str:
    if energy > 66:
        return "high"
    elif energy > 33:
        return "medium"
    return "low"


def _bin_rssi(rssi: float) -> str:
    if rssi > -60:
        return "strong"
    elif rssi > -80:
        return "medium"
    return "weak"


def _bin_load(load: int) -> str:
    if load < 5:
        return "low"
    elif load < 15:
        return "medium"
    return "high"


def _encode_network_health(alive_fraction: float) -> str:
    if alive_fraction > 0.75:
        return "healthy"
    elif alive_fraction > 0.40:
        return "degraded"
    return "critical"


def state_to_str(state: RLState) -> str:
    """Human-readable state string."""
    return f"E={state[0]},R={state[1]},L={state[2]},N={state[3]}"
