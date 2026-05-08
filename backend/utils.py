"""
backend/utils.py
----------------
Logging setup, JSONL writers, and general utilities.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

import colorlog

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).resolve().parent.parent
DATA_DIR      = PROJECT_ROOT / "data"
LOGS_DIR      = DATA_DIR / "logs"
STATE_FILE    = DATA_DIR / "network_state.json"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

TELEMETRY_LOG  = LOGS_DIR / "telemetry.jsonl"
ROUTING_LOG    = LOGS_DIR / "routing.jsonl"
RL_WEIGHTS_LOG = LOGS_DIR / "rl_weights.jsonl"


# ─── Logger factory ───────────────────────────────────────────────────────────
def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Return a colour-formatted logger."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(name)s] %(levelname)s%(reset)s  %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        }
    ))
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


# ─── JSONL writers ────────────────────────────────────────────────────────────
def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    """Append a single JSON record to a .jsonl file."""
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def log_telemetry(record: Dict[str, Any]) -> None:
    append_jsonl(TELEMETRY_LOG, record)


def log_routing(record: Dict[str, Any]) -> None:
    append_jsonl(ROUTING_LOG, record)


def log_rl_weights(weights: Dict[str, float], reward: float, step: int) -> None:
    append_jsonl(RL_WEIGHTS_LOG, {
        "step": step,
        "timestamp": time.time(),
        "reward": reward,
        **weights,
    })


# ─── Shared state file (dashboard bridge) ─────────────────────────────────────
def write_network_state(state: Dict[str, Any]) -> None:
    """Atomically write the current network state for the dashboard to read."""
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f)
    tmp.replace(STATE_FILE)


def read_network_state() -> Dict[str, Any]:
    """Read the latest network state. Returns empty dict if not available."""
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ─── Misc helpers ─────────────────────────────────────────────────────────────
def now_ms() -> int:
    return int(time.time() * 1000)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def normalize_weights(w: Dict[str, float], minimum: float = 0.01) -> Dict[str, float]:
    """Ensure all weights are positive and sum to 1."""
    clipped = {k: max(v, minimum) for k, v in w.items()}
    total   = sum(clipped.values())
    return {k: v / total for k, v in clipped.items()}
