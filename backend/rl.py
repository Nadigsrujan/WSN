"""
backend/rl.py
--------------
Integrates the Q-learning agent into the backend orchestration loop.

Responsibilities:
  1. Encode current network state → RL state tuple
  2. Choose an action (weight adjustment)
  3. Apply the action → update routing weights
  4. Compute reward from routing outcome
  5. Update Q-table
  6. Provide weights to GraphEngine for next tick
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from backend.models import NodeState
from backend.telemetry_store import TelemetryStore
from rl.q_agent import QLearningAgent
from rl.state_encoder import encode_global_state, RLState
from rl.reward_shaper import compute_reward
from backend.utils import get_logger

log = get_logger("rl_integration")


class RLController:
    """
    Thin wrapper that sits between the orchestrator loop and the Q-agent.
    Maintains state across ticks so we can do the full (s, a, r, s') update.
    """

    def __init__(self, total_nodes: int) -> None:
        self.agent       = QLearningAgent()
        self.total_nodes = total_nodes

        self._prev_state:   Optional[RLState] = None
        self._prev_action:  Optional[str]     = None

    # ─── Main API ─────────────────────────────────────────────────────────────

    def tick(
        self,
        nodes:         List[NodeState],
        newly_dead:    List[str],
        packet_success: bool,
        path:          List[str],
    ) -> Dict[str, float]:
        """
        Run one RL tick:
          1. Compute current state
          2. Compute reward (from LAST step's outcome)
          3. Update Q-table (s, a, r, s')
          4. Choose new action for NEXT step
          5. Return updated routing weights

        Returns the current routing weights dict.
        """
        alive       = [n for n in nodes if n.alive]
        alive_frac  = len(alive) / max(self.total_nodes, 1)

        # ── Compute global state metrics ──────────────────────────────────────
        avg_energy = sum(n.energy for n in alive) / max(len(alive), 1)
        avg_rssi   = sum(n.rssi   for n in alive) / max(len(alive), 1)
        avg_load   = sum(n.load   for n in alive) / max(len(alive), 1)

        curr_state = encode_global_state(avg_energy, avg_rssi, avg_load, alive_frac)

        # ── Update Q-table with previous step's outcome ───────────────────────
        if self._prev_state is not None and self._prev_action is not None:
            reward = compute_reward(
                packet_success=packet_success,
                nodes=nodes,
                newly_dead=newly_dead,
                path=path,
            )
            self.agent.update(
                state=self._prev_state,
                action=self._prev_action,
                reward=reward,
                next_state=curr_state,
            )

        # ── Choose next action ────────────────────────────────────────────────
        action = self.agent.choose_action(curr_state)

        # Store for next tick
        self._prev_state  = curr_state
        self._prev_action = action

        log.debug(
            f"RL: state={curr_state} action={action} "
            f"ε={self.agent.epsilon:.3f} weights={self.agent.weights}"
        )

        return dict(self.agent.weights)

    @property
    def weights(self) -> Dict[str, float]:
        return dict(self.agent.weights)

    @property
    def rl_summary(self) -> Dict:
        return {
            "weights":        self.weights,
            "epsilon":        round(self.agent.epsilon, 4),
            "step":           self.agent._step,
            "recent_rewards": self.agent.reward_history[-30:] if self.agent.reward_history else [],
            "q_table":        self.agent.q_table_summary(),
            "last_action":    self._prev_action or "—",
            "last_state":     list(self._prev_state) if self._prev_state else [],
        }
