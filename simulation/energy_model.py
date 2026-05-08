"""
simulation/energy_model.py
---------------------------
Energy consumption models for virtual WSN nodes.

Models:
  Tx (transmit)  : energy -= tx_cost * packets_sent
  Rx (receive)   : energy -= rx_cost per received packet
  Idle           : energy -= idle_cost per time step

RSSI propagation model:
  RSSI(d) = -20 * log10(d) + RSSI_ref + noise
  where RSSI_ref ≈ -30 dBm at 1 m

These match a simplified first-order radio model used in WSN research.
"""

from __future__ import annotations
import math
import random
from typing import Optional


# ─── Default energy parameters (all in percent per event) ─────────────────────
TX_COST_PER_PACKET  = 0.08    # % energy drained per transmitted packet
RX_COST_PER_PACKET  = 0.04    # % energy drained per received packet
IDLE_COST_PER_STEP  = 0.005   # % energy drained per simulation step (idle)
SENSING_COST        = 0.002   # % energy per sensing event

# ─── RSSI propagation constants ───────────────────────────────────────────────
RSSI_REF_DBM        = -30.0   # RSSI at 1 m reference distance
PATH_LOSS_EXPONENT  = 2.0     # free space = 2; indoor ≈ 2.5–3.5
RSSI_NOISE_STD      = 3.0     # Gaussian noise standard deviation (dBm)
MIN_RSSI_DBM        = -100.0
MAX_RSSI_DBM        = -30.0


# ─── Energy drain functions ───────────────────────────────────────────────────

def drain_tx(
    energy: float,
    packets: int = 1,
    tx_cost: float = TX_COST_PER_PACKET,
) -> float:
    """Drain energy for transmitting `packets` packets. Returns new energy."""
    drain  = tx_cost * packets
    return max(0.0, energy - drain)


def drain_rx(
    energy: float,
    packets: int = 1,
    rx_cost: float = RX_COST_PER_PACKET,
) -> float:
    """Drain energy for receiving `packets` packets. Returns new energy."""
    drain = rx_cost * packets
    return max(0.0, energy - drain)


def drain_idle(
    energy: float,
    idle_cost: float = IDLE_COST_PER_STEP,
) -> float:
    """Drain idle energy for one simulation step. Returns new energy."""
    return max(0.0, energy - idle_cost)


def drain_sensing(
    energy: float,
    sensing_cost: float = SENSING_COST,
) -> float:
    """Drain energy for one sensing event. Returns new energy."""
    return max(0.0, energy - sensing_cost)


def full_step_drain(
    energy:      float,
    packets_tx:  int   = 0,
    packets_rx:  int   = 0,
    sensing:     bool  = True,
) -> float:
    """
    Apply all energy drains for one simulation step.
    Returns new energy value.
    """
    e = energy
    e = drain_idle(e)
    e = drain_tx(e, packets_tx)
    e = drain_rx(e, packets_rx)
    if sensing:
        e = drain_sensing(e)
    return round(e, 4)


# ─── RSSI / distance model ────────────────────────────────────────────────────

def distance_to_rssi(
    distance_m: float,
    rssi_ref:   float = RSSI_REF_DBM,
    n:          float = PATH_LOSS_EXPONENT,
    noise_std:  float = RSSI_NOISE_STD,
) -> float:
    """
    Compute RSSI (dBm) for a given distance using log-distance path loss.

    RSSI(d) = RSSI_ref - 20 * n * log10(d) + N(0, noise_std)
    """
    if distance_m <= 0:
        return MAX_RSSI_DBM
    path_loss = 20 * n * math.log10(max(distance_m, 0.1))
    noise     = random.gauss(0, noise_std)
    rssi      = rssi_ref - path_loss + noise
    return round(max(MIN_RSSI_DBM, min(MAX_RSSI_DBM, rssi)), 1)


def rssi_to_distance(
    rssi:     float,
    rssi_ref: float = RSSI_REF_DBM,
    n:        float = PATH_LOSS_EXPONENT,
) -> float:
    """
    Estimate distance from RSSI reading (inverse log model).
    Returns distance in metres.
    """
    exponent  = (rssi_ref - rssi) / (20 * n)
    return round(10 ** exponent, 2)


def fluctuate_rssi(
    base_rssi: float,
    noise_std: float = RSSI_NOISE_STD,
) -> float:
    """Add Gaussian noise to simulate RSSI fluctuation."""
    noisy = base_rssi + random.gauss(0, noise_std)
    return round(max(MIN_RSSI_DBM, min(MAX_RSSI_DBM, noisy)), 1)
