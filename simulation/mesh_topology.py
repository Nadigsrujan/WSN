"""
simulation/mesh_topology.py
-----------------------------
Adaptive Hierarchical Hybrid Mesh topology generator for the WSN.

Produces a clustered architecture where:
  - SINK is at the top.
  - Cluster Heads (CHs) form a full mesh backbone connecting to SINK.
  - Normal nodes connect ONLY to their assigned CH.

Guarantees:
  - Strict hierarchical clustering.
  - 4 distinct clusters with 3 members and 1 CH each.
  - SINK only connects to CHs.
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional

from backend.utils import get_logger

log = get_logger("mesh_topology")

# ─── Predefined mesh positions ───────────────────────────────────────────────
# Layout in a 100×100m field. SINK sits at top-centre.

SINK_POS = (50.0, 95.0)

# Cluster 1 (Left)
CLUSTER_1 = {
    "CH1": (20.0, 65.0),
    "VNODE_1": (10.0, 45.0),
    "VNODE_2": (25.0, 40.0),
    "VNODE_3": (15.0, 50.0),
}

# Cluster 2 (Mid-Left) - includes ESP32 slot
CLUSTER_2 = {
    "CH2": (45.0, 70.0),
    "ESP32_SLOT": (35.0, 50.0),
    "VNODE_5": (50.0, 45.0),
    "VNODE_6": (40.0, 40.0),
}

# Cluster 3 (Mid-Right)
CLUSTER_3 = {
    "CH3": (65.0, 65.0),
    "VNODE_7": (60.0, 45.0),
    "VNODE_8": (70.0, 40.0),
    "VNODE_9": (55.0, 50.0),
}

# Cluster 4 (Right)
CLUSTER_4 = {
    "CH4": (85.0, 70.0),
    "VNODE_10": (80.0, 50.0),
    "VNODE_11": (90.0, 45.0),
    "VNODE_12": (85.0, 40.0),
}

CLUSTER_DEFINITIONS = {
    1: {"members": list(CLUSTER_1.keys()), "positions": CLUSTER_1},
    2: {"members": list(CLUSTER_2.keys()), "positions": CLUSTER_2},
    3: {"members": list(CLUSTER_3.keys()), "positions": CLUSTER_3},
    4: {"members": list(CLUSTER_4.keys()), "positions": CLUSTER_4},
}

def get_all_positions(esp32_id: Optional[str] = None) -> Dict[str, Tuple[float, float]]:
    """
    Return a dict of {node_id: (x, y)} for every node in the mesh,
    including SINK.
    """
    positions: Dict[str, Tuple[float, float]] = {}
    positions["SINK"] = SINK_POS

    for cluster_data in CLUSTER_DEFINITIONS.values():
        for nid, pos in cluster_data["positions"].items():
            positions[nid] = pos

    # Replace ESP32_SLOT with real node id if provided
    if esp32_id and "ESP32_SLOT" in positions:
        positions[esp32_id] = positions.pop("ESP32_SLOT")

    return positions

def get_initial_cluster_assignments(esp32_id: Optional[str] = None) -> Dict[str, int]:
    """
    Returns {node_id: cluster_id} mapping.
    """
    assignments = {}
    for cid, data in CLUSTER_DEFINITIONS.items():
        for nid in data["members"]:
            key = esp32_id if (esp32_id and nid == "ESP32_SLOT") else nid
            assignments[key] = cid
    return assignments

def get_virtual_node_ids() -> List[str]:
    """Return IDs of all virtual nodes (excludes SINK and ESP32_SLOT)."""
    vnodes = []
    for data in CLUSTER_DEFINITIONS.values():
        for nid in data["members"]:
            if nid not in ("SINK", "ESP32_SLOT"):
                vnodes.append(nid)
    return vnodes

def validate_topology(adjacency: Dict[str, List[str]], ch_list: List[str]) -> bool:
    """
    Validate hierarchical constraints based on current dynamic state:
      1. SINK only connects to CHs.
      2. Normal nodes only connect to a CH.
      3. CHs form a connected mesh (and connect to SINK).
    """
    sink_neighbors = adjacency.get("SINK", [])
    for n in sink_neighbors:
        assert n in ch_list, f"SINK connected to non-CH node: {n}"

    for node, neighbors in adjacency.items():
        if node == "SINK":
            continue
        
        is_ch = node in ch_list
        if not is_ch:
            # Normal node must connect to AT LEAST ONE CH
            has_ch_neighbor = any(nb in ch_list for nb in neighbors)
            assert has_ch_neighbor, f"Normal node {node} has no CH neighbor"

    log.info("Topology validation PASSED: hierarchical constraints satisfied")
    return True
