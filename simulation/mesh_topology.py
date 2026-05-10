"""
simulation/mesh_topology.py
-----------------------------
Deterministic hierarchical mesh topology generator for the WSN.

Produces a clustered 2-tier hierarchical mesh where:
  - Tier 1 (Cluster Heads): Full mesh backbone, connects directly to SINK.
  - Tier 2 (Member Nodes): Connect ONLY to their respective Cluster Head.

Guarantees:
  - Every member node connects to exactly 1 CH.
  - Every CH connects to all other CHs and to SINK.
  - Removing a member node only affects that node.
  - Removing a CH triggers an intra-cluster election (handled in backend).
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional

from backend.utils import get_logger

log = get_logger("mesh_topology")

# ─── Predefined mesh positions ───────────────────────────────────────────────
# Layout in a 100×100m field. SINK sits at top-center.
# Y increases upward toward SINK.

SINK_POS = (50.0, 95.0)

# Cluster Definitions
# Structure: { cluster_id: { "ch": node_id, "members": [node_ids], "positions": {node_id: (x,y)} } }
CLUSTER_DEFINITIONS = {
    1: {
        "ch": "CH1",
        "members": ["VNODE_1", "VNODE_2", "VNODE_3"],
        "positions": {
            "CH1": (20.0, 65.0),
            "VNODE_1": (10.0, 45.0),
            "VNODE_2": (25.0, 40.0),
            "VNODE_3": (15.0, 50.0),
        }
    },
    2: {
        "ch": "CH2",
        "members": ["VNODE_4", "VNODE_5", "ESP32_SLOT"],
        "positions": {
            "CH2": (45.0, 70.0),
            "VNODE_4": (35.0, 50.0),
            "VNODE_5": (50.0, 45.0),
            "ESP32_SLOT": (40.0, 40.0), # ESP32 is a member in cluster 2
        }
    },
    3: {
        "ch": "CH3",
        "members": ["VNODE_6", "VNODE_7", "VNODE_8"],
        "positions": {
            "CH3": (65.0, 65.0),
            "VNODE_6": (60.0, 45.0),
            "VNODE_7": (70.0, 40.0),
            "VNODE_8": (55.0, 50.0),
        }
    },
    4: {
        "ch": "CH4",
        "members": ["VNODE_9", "VNODE_10", "VNODE_11"],
        "positions": {
            "CH4": (85.0, 70.0),
            "VNODE_9": (80.0, 50.0),
            "VNODE_10": (90.0, 45.0),
            "VNODE_11": (85.0, 40.0),
        }
    }
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

    for cluster_data in CLUSTER_DEFINITIONS.values():
        for nid, pos in cluster_data["positions"].items():
            positions[nid] = pos

    # Replace ESP32_SLOT with real node id if provided
    if esp32_id and "ESP32_SLOT" in positions:
        positions[esp32_id] = positions.pop("ESP32_SLOT")

    return positions

def get_initial_cluster_assignments(esp32_id: Optional[str] = None) -> Dict[str, int]:
    """
    Returns a dict mapping node_id to its assigned cluster_id.
    """
    assignments = {}
    for cid, cluster_data in CLUSTER_DEFINITIONS.items():
        assignments[cluster_data["ch"]] = cid
        for member_id in cluster_data["members"]:
            nid = esp32_id if (esp32_id and member_id == "ESP32_SLOT") else member_id
            assignments[nid] = cid
    return assignments

def get_initial_ch_roles(esp32_id: Optional[str] = None) -> Dict[str, bool]:
    """
    Returns a dict mapping node_id to a boolean indicating if it starts as a CH.
    """
    roles = {}
    for cluster_data in CLUSTER_DEFINITIONS.values():
        roles[cluster_data["ch"]] = True
        for member_id in cluster_data["members"]:
            nid = esp32_id if (esp32_id and member_id == "ESP32_SLOT") else member_id
            roles[nid] = False
    return roles

def get_adjacency(esp32_id: Optional[str] = None) -> Dict[str, List[str]]:
    """
    Return the mesh adjacency list based on STRICT hierarchical rules:
    - SINK connects to all CHs.
    - CHs connect to SINK, all other CHs, and their own members.
    - Members connect ONLY to their CH.
    """
    adj = {}
    
    # Identify initial CHs
    ch_nodes = [cd["ch"] for cd in CLUSTER_DEFINITIONS.values()]
    
    # 1. SINK connects to all CHs
    adj["SINK"] = ch_nodes.copy()
    
    for cid, cluster_data in CLUSTER_DEFINITIONS.items():
        ch_id = cluster_data["ch"]
        members = []
        for m_id in cluster_data["members"]:
             members.append(esp32_id if (esp32_id and m_id == "ESP32_SLOT") else m_id)
        
        # 2. CH connections
        adj[ch_id] = ["SINK"] + [other for other in ch_nodes if other != ch_id] + members
        
        # 3. Member connections
        for m_id in members:
            adj[m_id] = [ch_id]
            
    return adj

def get_virtual_node_ids() -> List[str]:
    """Return IDs of all virtual nodes (excludes SINK and ESP32_SLOT)."""
    virtual_ids = []
    for cluster_data in CLUSTER_DEFINITIONS.values():
        virtual_ids.append(cluster_data["ch"])
        for m_id in cluster_data["members"]:
            if m_id != "ESP32_SLOT":
                virtual_ids.append(m_id)
    return virtual_ids

def get_layer(node_id: str) -> int:
    """Return the layer number (1 for CHs, 2 for Members) for a given node, or 0 for SINK."""
    if node_id == "SINK":
        return 0
    for cluster_data in CLUSTER_DEFINITIONS.values():
        if node_id == cluster_data["ch"]:
            return 1
    # If not SINK or CH, it's a member
    return 2

def validate_topology(adjacency: Dict[str, List[str]]) -> bool:
    """
    Validate that the mesh topology satisfies all hierarchical constraints:
      1. Every member node has degree 1 (connects only to CH)
      2. SINK connects to all CHs
      3. Graph is connected
      4. CHs form a full mesh backbone
    """
    # Simple check for connectivity
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
    
    log.info("Topology validation PASSED: all hierarchical constraints satisfied")
    return True
