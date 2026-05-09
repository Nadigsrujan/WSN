"""
rl/q_agent.py
--------------
Tabular Q-learning agent for adaptive WSN routing weight tuning.

Design:
  - STATE  : (energy_level, rssi_level, load_level, network_health)
  - ACTIONS: adjust one of the four routing weights {w1, w2, w3, w4}
  - Q-TABLE: defaultdict keyed by (state, action)
  - POLICY : epsilon-greedy with exponential epsilon decay

Weight actions:
  "boost_energy"    → increase w1 (energy), decrease others slightly
  "boost_distance"  → increase w2 (distance)
  "boost_lq"        → increase w3 (link quality)
  "boost_load"      → increase w4 (load balancing)
  "keep"            → no change (observe)

Q-update:
  Q(s,a) ← Q(s,a) + α * [r + γ * max_a' Q(s',a') - Q(s,a)]
"""

from __future__ import annotations
import random
import json
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from backend.utils import get_logger, normalize_weights, log_rl_weights
from rl.state_encoder import RLState, state_to_str

log = get_logger("q_agent")


# ─── Action definitions ───────────────────────────────────────────────────────
ACTIONS = [
    "boost_energy",
    "boost_lq",
    "boost_env",
    "boost_traffic",
    "boost_path",
    "keep",
]

# How much each "boost" action shifts the target weight
BOOST_AMOUNT  = 0.05
REDUCE_AMOUNT = 0.01


class QLearningAgent:
    """
    Lightweight tabular Q-learning agent.

    Manages routing weights {w1, w2, w3, w4} and updates them based on
    observed rewards from the routing/packet outcomes.
    """

    def __init__(
        self,
        alpha:   float = 0.15,    # learning rate
        gamma:   float = 0.90,    # discount factor
        epsilon: float = 0.25,    # initial exploration rate
        epsilon_min:   float = 0.05,
        epsilon_decay: float = 0.995,
    ) -> None:
        self.alpha         = alpha
        self.gamma         = gamma
        self.epsilon       = epsilon
        self.epsilon_min   = epsilon_min
        self.epsilon_decay = epsilon_decay

        # Q-table: Q[state][action] = float
        self.q: Dict[RLState, Dict[str, float]] = defaultdict(
            lambda: {a: 0.0 for a in ACTIONS}
        )

        # Current routing weights (tuned by this agent)
        self.weights: Dict[str, float] = {
            "alpha":   0.25,   # Energy
            "beta":    0.25,   # Link Quality
            "gamma":   0.15,   # Environment
            "delta":   0.15,   # Traffic
            "epsilon": 0.20,   # Path
        }

        # History for dashboard
        self.weight_history: List[Dict] = []
        self.reward_history: List[float] = []
        self._step = 0

    # ─── Action selection ──────────────────────────────────────────────────────

    def choose_action(self, state: RLState) -> str:
        """Epsilon-greedy action selection."""
        if random.random() < self.epsilon:
            return random.choice(ACTIONS)
        q_vals = self.q[state]
        return max(ACTIONS, key=lambda a: q_vals[a])

    # ─── Q-update ─────────────────────────────────────────────────────────────

    def update(
        self,
        state:       RLState,
        action:      str,
        reward:      float,
        next_state:  RLState,
    ) -> float:
        """
        Apply the Q-learning update rule and apply the chosen weight action.
        Returns the TD error (for logging).
        """
        # Q(s,a) ← Q(s,a) + α * [r + γ*max_a' Q(s',a') - Q(s,a)]
        max_next = max(self.q[next_state].values())
        old_q    = self.q[state][action]
        td_error = reward + self.gamma * max_next - old_q
        self.q[state][action] = old_q + self.alpha * td_error

        # Apply weight change
        self._apply_action(action)

        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        # Track history
        self._step += 1
        self.reward_history.append(reward)
        self.weight_history.append(dict(self.weights))
        log_rl_weights(self.weights, reward, self._step)

        log.debug(
            f"Step {self._step} | s={state_to_str(state)} a={action} "
            f"r={reward:.2f} TD={td_error:.3f} ε={self.epsilon:.3f}"
        )
        return td_error

    # ─── Weight application ────────────────────────────────────────────────────

    def _apply_action(self, action: str) -> None:
        """Shift routing weights according to the chosen action."""
        target_map = {
            "boost_energy":  "alpha",
            "boost_lq":      "beta",
            "boost_env":     "gamma",
            "boost_traffic": "delta",
            "boost_path":    "epsilon",
            "keep":          None,
        }
        target = target_map.get(action)

        if target is None:
            return   # "keep" — no change

        for k in self.weights:
            if k == target:
                self.weights[k] += BOOST_AMOUNT
            else:
                self.weights[k] -= REDUCE_AMOUNT

        # Normalise to ensure they sum to 1 and all are positive
        self.weights = normalize_weights(self.weights)

    # ─── Introspection helpers ─────────────────────────────────────────────────

    def best_action(self, state: RLState) -> str:
        """Return the greedy best action for a state (no exploration)."""
        return max(ACTIONS, key=lambda a: self.q[state][a])

    def q_table_summary(self) -> Dict:
        """Serialisable Q-table summary for dashboard display."""
        return {
            str(state_to_str(s)): dict(vals)
            for s, vals in self.q.items()
        }

    def save(self, path: str) -> None:
        """Save Q-table and weights to JSON."""
        data = {
            "weights": self.weights,
            "epsilon": self.epsilon,
            "step":    self._step,
            "q_table": {str(k): v for k, v in self.q.items()},
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        log.info(f"Q-table saved to {path}")

    def load(self, path: str) -> None:
        """Load Q-table and weights from JSON."""
        with open(path) as f:
            data = json.load(f)
        self.weights  = data["weights"]
        self.epsilon  = data["epsilon"]
        self._step    = data["step"]
        log.info(f"Q-table loaded from {path} (step {self._step})")
