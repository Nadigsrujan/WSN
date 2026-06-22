"""
simulation/mesh_topology.py
-----------------------------
Single source of truth for ALL node positions and adjacency in the WSN.

Design principles enforced here:
  - STATIC_POSITIONS: node coordinates NEVER change at runtime.
  - INTRA_CLUSTER_MESH: every node inside a cluster has ≥2 neighbors inside its cluster.
  - INTER_CLUSTER_LINKS: Cluster Heads form a full-mesh backbone.
  - SINK_LINKS: SINK connects to every cluster's CH representative nodes.

Cluster layout (100×100 m field, SINK at top-center):
  Cluster 0 (Left):   VNODE_1, VNODE_2, VNODE_4, VNODE_7
  Cluster 1 (Center): VNODE_3, VNODE_5, VNODE_8
  Cluster 2 (Right):  VNODE_6, VNODE_9, VNODE_10, ESP32_SLOT

Adjacency guarantees (per cluster):
  - Every node has degree ≥ 2 within its cluster
  - Every node has ≥ 2 disjoint paths to the cluster CH
  - Removing any single node does NOT isolate any other
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple

from backend.utils import get_logger

log = get_logger("mesh_topology")

# ─── Static Positions (NEVER changed at runtime) ──────────────────────────────
# Layout: 100×100 m field. SINK at top-center. Y increases upward toward SINK.

STATIC_POSITIONS: Dict[str, Tuple[float, float]] = {
    # Base station
    "SINK":       (50.0, 96.0),

    # Cluster 0 — Left (centered around X=20.0)
    "VNODE_7":    (20.0, 64.0),   # Layer 3 (upper relay)
    "VNODE_4":    (12.0, 45.0),   # Layer 2 (backbone)
    "VNODE_1":    (12.0, 20.0),   # Layer 1 (edge sensor)
    "VNODE_2":    (28.0, 20.0),   # Layer 1 (edge sensor)

    # Cluster 1 — Center (centered around X=50.0)
    "VNODE_8":    (50.0, 72.0),   # Layer 3 (upper relay) — adjusted to prevent overlap with SINK
    "VNODE_5":    (42.0, 45.0),   # Layer 2 (backbone)
    "VNODE_3":    (50.0, 20.0),   # Layer 1 (edge sensor)

    # Cluster 2 — Right (centered around X=80.0)
    "VNODE_9":    (80.0, 64.0),   # Layer 3 (upper relay)
    "ESP32_SLOT": (72.0, 45.0),   # Layer 2 (real ESP32 placeholder)
    "VNODE_6":    (88.0, 45.0),   # Layer 2 (backbone)
    "VNODE_10":   (80.0, 20.0),   # Layer 1 (edge sensor)
}

# ─── Cluster Membership (fixed geographic partitioning) ────────────────────────
CLUSTER_MEMBERS: Dict[int, List[str]] = {
    0: ["VNODE_1", "VNODE_2", "VNODE_4", "VNODE_7"],
    1: ["VNODE_3", "VNODE_5", "VNODE_8"],
    2: ["VNODE_6", "VNODE_9", "VNODE_10", "ESP32_SLOT"],
}

# Canonical initial CH for each cluster (highest-layer node = best relay position)
INITIAL_CH: Dict[int, str] = {
    0: "VNODE_7",
    1: "VNODE_8",
    2: "VNODE_9",
}

# ─── Intra-Cluster Mesh Adjacency ─────────────────────────────────────────────
# Hand-crafted to guarantee:
#   • Every non-CH member has degree ≥ 2 within the cluster
#   • Every member has ≥ 2 node-disjoint paths to the CH
#   • Removing any single node leaves all others connected

# Cluster 0: VNODE_7 – VNODE_4 – VNODE_1 – VNODE_2 – VNODE_7 (ring)
#            + diagonal VNODE_4 – VNODE_2  (adds redundancy, degree 3)
CLUSTER_0_LINKS: List[Tuple[str, str]] = [
    ("VNODE_7", "VNODE_4"),
    ("VNODE_4", "VNODE_1"),
    ("VNODE_1", "VNODE_2"),
    ("VNODE_2", "VNODE_7"),
    ("VNODE_4", "VNODE_2"),   # diagonal cross-link
]

# Cluster 1: Triangle — every pair connected  (each node has degree 2)
# VNODE_8 – VNODE_5 – VNODE_3 – VNODE_8
CLUSTER_1_LINKS: List[Tuple[str, str]] = [
    ("VNODE_8", "VNODE_5"),
    ("VNODE_5", "VNODE_3"),
    ("VNODE_3", "VNODE_8"),
]

# Cluster 2: VNODE_9 – VNODE_6 – VNODE_10 – ESP32_SLOT – VNODE_9 (ring)
#            + diagonal VNODE_9 – VNODE_6  and  VNODE_6 – ESP32_SLOT
CLUSTER_2_LINKS: List[Tuple[str, str]] = [
    ("VNODE_9",    "ESP32_SLOT"),
    ("VNODE_9",    "VNODE_6"),
    ("VNODE_6",    "ESP32_SLOT"),
    ("VNODE_6",    "VNODE_10"),
    ("VNODE_10",   "ESP32_SLOT"),
]

INTRA_CLUSTER_LINKS: List[Tuple[str, str]] = (
    CLUSTER_0_LINKS + CLUSTER_1_LINKS + CLUSTER_2_LINKS
)

# ─── Inter-Cluster CH Backbone (full mesh between initial CH nodes) ────────────
# Plus backup cross-cluster edges from backbone nodes to neighbouring clusters'
# backbone nodes, so removing any single upper-relay doesn't isolate a cluster.
INTER_CLUSTER_LINKS: List[Tuple[str, str]] = [
    # Primary CH-to-CH full mesh
    ("VNODE_7", "VNODE_8"),
    ("VNODE_7", "VNODE_9"),
    ("VNODE_8", "VNODE_9"),
    # Backup: Cluster-0 backbone (VNODE_4) → Cluster-1 backbone (VNODE_5)
    # If VNODE_7 or VNODE_8 dies, VNODE_4↔VNODE_5 keeps clusters 0 and 1 bridged
    ("VNODE_4", "VNODE_5"),
    # Backup: Cluster-1 backbone (VNODE_5) → Cluster-2 backbone (ESP32_SLOT)
    # If VNODE_8 or VNODE_9 dies, VNODE_5↔ESP32_SLOT bridges clusters 1 and 2
    ("VNODE_5", "ESP32_SLOT"),
]

# ─── SINK Links ────────────────────────────────────────────────────────────────
SINK_LINKS: List[Tuple[str, str]] = [
    ("SINK", "VNODE_7"),
    ("SINK", "VNODE_8"),
    ("SINK", "VNODE_9"),
]


# ─── Full Static Adjacency ────────────────────────────────────────────────────

def get_full_static_adjacency(
    esp32_id: Optional[str] = None,
) -> Dict[str, List[str]]:
    """
    Return the complete mesh adjacency list combining:
      - Intra-cluster mesh links (every node ≥ 2 neighbors in cluster)
      - Inter-cluster CH backbone (full mesh between CHs)
      - SINK → CH links

    If `esp32_id` is given (e.g. "ESP32_REAL_1"), replaces all
    occurrences of "ESP32_SLOT" with the real node ID.
    """
    all_links: List[Tuple[str, str]] = (
        INTRA_CLUSTER_LINKS + INTER_CLUSTER_LINKS + SINK_LINKS
    )

    adj: Dict[str, List[str]] = {}

    def _resolve(node_id: str) -> str:
        if esp32_id and node_id == "ESP32_SLOT":
            return esp32_id
        return node_id

    for raw_u, raw_v in all_links:
        u = _resolve(raw_u)
        v = _resolve(raw_v)
        adj.setdefault(u, [])
        adj.setdefault(v, [])
        if v not in adj[u]:
            adj[u].append(v)
        if u not in adj[v]:
            adj[v].append(u)

    return adj


def get_all_positions(
    esp32_id: Optional[str] = None,
) -> Dict[str, Tuple[float, float]]:
    """
    Return {node_id: (x, y)} for every node in the mesh.
    If `esp32_id` is given, replaces ESP32_SLOT with the real ID.
    """
    positions = dict(STATIC_POSITIONS)
    if esp32_id and "ESP32_SLOT" in positions:
        positions[esp32_id] = positions.pop("ESP32_SLOT")
    return positions


def get_adjacency(
    esp32_id: Optional[str] = None,
) -> Dict[str, List[str]]:
    """Backward-compatible alias for get_full_static_adjacency."""
    return get_full_static_adjacency(esp32_id=esp32_id)


def get_virtual_node_ids() -> List[str]:
    """Return IDs of all virtual nodes (excludes SINK and ESP32_SLOT)."""
    return [
        nid for nid in STATIC_POSITIONS
        if nid not in ("SINK", "ESP32_SLOT")
    ]


def get_cluster_for_node(node_id: str, esp32_id: Optional[str] = None) -> int:
    """Return the cluster ID (0/1/2) for a given node ID, or -1 if unknown."""
    check_id = "ESP32_SLOT" if (esp32_id and node_id == esp32_id) else node_id
    for cid, members in CLUSTER_MEMBERS.items():
        if check_id in members:
            return cid
    return -1


def get_layer(node_id: str) -> int:
    """Return the layer number (0=SINK, 1=edge, 2=backbone, 3=upper-relay)."""
    if node_id == "SINK":
        return 0
    layer3 = {"VNODE_7", "VNODE_8", "VNODE_9"}
    layer2 = {"VNODE_4", "VNODE_5", "ESP32_SLOT", "VNODE_6"}
    layer1 = {"VNODE_1", "VNODE_2", "VNODE_3", "VNODE_10"}
    if node_id in layer3:
        return 3
    if node_id in layer2:
        return 2
    if node_id in layer1:
        return 1
    # Real ESP32 lives at layer 2
    return 2


def validate_topology(
    adjacency: Dict[str, List[str]],
) -> bool:
    """
    Validate that the mesh topology satisfies all constraints:
      1. Every non-SINK node has degree ≥ 2
      2. Graph is connected
      3. Every non-SINK node has ≥ 2 node-disjoint paths to SINK (2-connectivity)

    Returns True if valid, raises AssertionError with details if not.
    """
    # 1. Degree constraints
    for node, neighbors in adjacency.items():
        deg = len(neighbors)
        if node == "SINK":
            assert deg >= 1, f"SINK has no connections"
        else:
            assert deg >= 2, f"{node} degree {deg} < 2 — does not meet mesh requirement"

    # 2. Connectivity — BFS from SINK
    visited: set = set()
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
    assert visited == all_nodes, (
        f"Disconnected nodes: {all_nodes - visited}"
    )

    # 3. 2-connectivity: removing any single non-SINK node should not disconnect
    non_sink = [n for n in all_nodes if n != "SINK"]
    for removed in non_sink:
        remaining = all_nodes - {removed}
        start = next(iter(remaining))
        vis2: set = set()
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
