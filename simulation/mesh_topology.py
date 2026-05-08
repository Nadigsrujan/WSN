"""
simulation/mesh_topology.py
-----------------------------
Deterministic layered mesh topology generator for the WSN.

Produces a 3-layer hierarchical mesh where:
  - Layer 1 (edge sensors): furthest from SINK
  - Layer 2 (backbone relays): middle tier, includes ESP32 slot
  - Layer 3 (upper relays): connects directly to SINK

Guarantees:
  - Every node has degree 2–4
  - Every node has ≥ 2 disjoint paths to SINK
  - SINK only connects to Layer 3
  - Removing any single node does NOT partition the graph
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional

from backend.utils import get_logger

log = get_logger("mesh_topology")

# ─── Predefined mesh positions ───────────────────────────────────────────────
# Layout in a 100×100m field.  SINK sits at top-centre.
# Y increases upward toward SINK.

SINK_POS = (50.0, 90.0)

# Layer 3 (upper relays) — connect to SINK
LAYER3_POSITIONS = {
    "VNODE_7": (25.0, 70.0),
    "VNODE_8": (50.0, 70.0),
    "VNODE_9": (75.0, 70.0),
}

# Layer 2 (backbone) — includes an ESP32 slot
LAYER2_POSITIONS = {
    "VNODE_4": (15.0, 45.0),
    "VNODE_5": (38.0, 45.0),
    "ESP32_SLOT": (60.0, 45.0),   # placeholder for real ESP32
    "VNODE_6": (82.0, 45.0),
}

# Layer 1 (edge sensors)
LAYER1_POSITIONS = {
    "VNODE_1": (12.0, 20.0),
    "VNODE_2": (35.0, 20.0),
    "VNODE_3": (58.0, 20.0),
    "VNODE_10": (80.0, 20.0),
}

# ─── Explicit adjacency (the core mesh definition) ───────────────────────────
# Each entry lists the neighbors for that node.
# This is hand-crafted to guarantee degree 2–4 and 2-connectivity.

MESH_ADJACENCY: Dict[str, List[str]] = {
    # SINK connects ONLY to Layer 3
    "SINK":     ["VNODE_7", "VNODE_8", "VNODE_9"],

    # Layer 3 — inter-layer + intra-layer links
    "VNODE_7":  ["SINK", "VNODE_8", "VNODE_4", "VNODE_5"],
    "VNODE_8":  ["SINK", "VNODE_7", "VNODE_9", "ESP32_SLOT"],
    "VNODE_9":  ["SINK", "VNODE_8", "ESP32_SLOT", "VNODE_6"],

    # Layer 2 — backbone
    "VNODE_4":  ["VNODE_7", "VNODE_5", "VNODE_1", "VNODE_2"],
    "VNODE_5":  ["VNODE_7", "VNODE_4", "VNODE_2", "VNODE_3"],
    "ESP32_SLOT": ["VNODE_8", "VNODE_9", "VNODE_3", "VNODE_6"],
    "VNODE_6":  ["VNODE_9", "ESP32_SLOT", "VNODE_3", "VNODE_10"],

    # Layer 1 — edge sensors
    "VNODE_1":  ["VNODE_4", "VNODE_2"],
    "VNODE_2":  ["VNODE_1", "VNODE_4", "VNODE_5", "VNODE_3"],
    "VNODE_3":  ["VNODE_2", "VNODE_5", "ESP32_SLOT", "VNODE_10"],
    "VNODE_10": ["VNODE_3", "VNODE_6"],
}


def get_all_positions(esp32_id: Optional[str] = None) -> Dict[str, Tuple[float, float]]:
    """
    Return a dict of {node_id: (x, y)} for every node in the mesh,
    including SINK.

    If `esp32_id` is given (e.g. "ESP32_REAL_1"), it replaces the
    ESP32_SLOT key with the real node's ID.
    """
    positions: Dict[str, Tuple[float, float]] = {}
    positions["SINK"] = SINK_POS

    for nid, pos in LAYER3_POSITIONS.items():
        positions[nid] = pos
    for nid, pos in LAYER2_POSITIONS.items():
        positions[nid] = pos
    for nid, pos in LAYER1_POSITIONS.items():
        positions[nid] = pos

    # Replace ESP32_SLOT with real node id if provided
    if esp32_id and "ESP32_SLOT" in positions:
        positions[esp32_id] = positions.pop("ESP32_SLOT")

    return positions


def get_adjacency(esp32_id: Optional[str] = None) -> Dict[str, List[str]]:
    """
    Return the mesh adjacency list.

    If `esp32_id` is given, replaces all occurrences of "ESP32_SLOT"
    with the real ESP32 node ID.
    """
    adj = {}
    for node, neighbors in MESH_ADJACENCY.items():
        key = esp32_id if (esp32_id and node == "ESP32_SLOT") else node
        adj[key] = [
            (esp32_id if (esp32_id and n == "ESP32_SLOT") else n)
            for n in neighbors
        ]
    return adj


def get_virtual_node_ids() -> List[str]:
    """Return IDs of all virtual nodes (excludes SINK and ESP32_SLOT)."""
    return [
        nid for nid in MESH_ADJACENCY.keys()
        if nid not in ("SINK", "ESP32_SLOT")
    ]


def get_layer(node_id: str) -> int:
    """Return the layer number (1, 2, 3) for a given node, or 0 for SINK."""
    if node_id == "SINK":
        return 0
    if node_id in LAYER3_POSITIONS:
        return 3
    if node_id in LAYER2_POSITIONS or node_id == "ESP32_SLOT":
        return 2
    if node_id in LAYER1_POSITIONS:
        return 1
    # Real ESP32 is always layer 2
    return 2


def validate_topology(adjacency: Dict[str, List[str]]) -> bool:
    """
    Validate that the mesh topology satisfies all constraints:
      1. Every non-SINK node has degree 2–4
      2. SINK has degree ≤ 4
      3. Graph is connected
      4. Every non-SINK node has ≥ 2 node-disjoint paths to SINK

    Returns True if valid, raises AssertionError with details if not.
    """
    # 1. Degree constraints
    for node, neighbors in adjacency.items():
        deg = len(neighbors)
        if node == "SINK":
            assert deg <= 4, f"SINK degree {deg} > 4"
        else:
            assert 2 <= deg <= 4, f"{node} degree {deg} not in [2,4]"

    # 2. Connectivity — BFS from SINK
    visited = set()
    queue = ["SINK"]
    while queue:
        curr = queue.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
        for nb in adjacency.get(curr, []):
            if nb not in visited:
                queue.append(nb)

    all_nodes = set(adjacency.keys())
    assert visited == all_nodes, f"Disconnected nodes: {all_nodes - visited}"

    # 3. 2-connectivity: removing any single non-SINK node should not disconnect
    non_sink = [n for n in all_nodes if n != "SINK"]
    for removed in non_sink:
        # BFS on reduced graph
        remaining = all_nodes - {removed}
        start = next(iter(remaining))
        vis2 = set()
        q2 = [start]
        while q2:
            c = q2.pop(0)
            if c in vis2:
                continue
            vis2.add(c)
            for nb in adjacency.get(c, []):
                if nb != removed and nb not in vis2:
                    q2.append(nb)
        assert vis2 == remaining, (
            f"Removing {removed} disconnects: unreachable = {remaining - vis2}"
        )

    log.info("Topology validation PASSED: all constraints satisfied")
    return True
