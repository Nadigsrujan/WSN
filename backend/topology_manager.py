"""
backend/topology_manager.py
---------------------------
Builds the live mesh adjacency for the WSN graph engine.

Architecture:
  - INTRA-CLUSTER FULL MESH: every node in a cluster (static AND dynamically
    arrived real nodes) connects to every other node in the same cluster.
  - INTER-CLUSTER CH BACKBONE: every alive CH ↔ every other alive CH.
  - SINK: connects ONLY to alive Cluster Heads.
  - ROUTING ENFORCEMENT: non-CH ↔ non-CH edges inside a cluster carry a 50×
    cost penalty in graph_engine so Dijkstra always routes source → CH → SINK.

Dynamic real nodes (e.g. ESP32_REAL_1 arriving via MQTT) are fully supported:
  - They are connected to every alive member of their assigned cluster.
  - They participate in CH elections on equal terms with virtual nodes.
  - When elected CH they appear in the CH backbone and SINK adjacency.
  - They are never artificially excluded from routing.
"""

import math
from typing import List, Dict, Optional, Set, Tuple
from backend.models import NodeState
from backend.utils import get_logger
from simulation.mesh_topology import (
    get_full_static_adjacency,
    CLUSTER_MEMBERS,
    INITIAL_CH,
)

log = get_logger("topology_manager")

# Flat set of all node IDs that are statically declared in the mesh config
_STATIC_MEMBER_IDS: Set[str] = {
    nid for members in CLUSTER_MEMBERS.values() for nid in members
}


class TopologyManager:
    def __init__(self, esp32_id: Optional[str] = None) -> None:
        self.esp32_id = esp32_id
        self._base_adjacency: Dict[str, List[str]] = get_full_static_adjacency(
            esp32_id=esp32_id
        )
        log.info(
            f"Static mesh adjacency loaded: {len(self._base_adjacency)} nodes, "
            f"{sum(len(v) for v in self._base_adjacency.values()) // 2} undirected edges"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Core adjacency builder
    # ─────────────────────────────────────────────────────────────────────────

    def get_hierarchical_adjacency(
        self, nodes: List[NodeState]
    ) -> Dict[str, List[str]]:
        """
        Build the live adjacency dict for this simulation tick.

        Rules:
          1. Full mesh within each cluster — every alive node in a cluster
             connects to every other alive node in the same cluster.
             This includes both static virtual nodes AND any dynamically
             arrived real nodes (ESP32_REAL_1, etc.).
          2. CH ↔ CH full-mesh backbone across clusters.
          3. SINK ↔ every alive CH only.
        """
        alive_ids = {n.node_id for n in nodes if n.alive}
        ch_ids    = {n.node_id for n in nodes if n.alive and n.is_ch}
        node_map  = {n.node_id: n for n in nodes}

        # --- Build cluster membership including dynamic real nodes -----------
        # cluster_all_members[cid] = all alive node IDs assigned to that cluster
        cluster_all_members: Dict[int, List[str]] = {}

        for n in nodes:
            if n.node_id == "SINK" or not n.alive or n.cluster_id < 0:
                continue
            cid = n.cluster_id
            cluster_all_members.setdefault(cid, [])
            if n.node_id not in cluster_all_members[cid]:
                cluster_all_members[cid].append(n.node_id)

        adj: Dict[str, List[str]] = {}

        # ── Step 1: Full mesh within each cluster (static + dynamic nodes) ──
        for cid, members in cluster_all_members.items():
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    adj.setdefault(a, [])
                    adj.setdefault(b, [])
                    if b not in adj[a]:
                        adj[a].append(b)
                    if a not in adj[b]:
                        adj[b].append(a)

        # ── Step 2: CH ↔ CH full-mesh backbone ──────────────────────────────
        ch_list = list(ch_ids)
        for i, ch_a in enumerate(ch_list):
            for ch_b in ch_list[i + 1:]:
                adj.setdefault(ch_a, [])
                adj.setdefault(ch_b, [])
                if ch_b not in adj[ch_a]:
                    adj[ch_a].append(ch_b)
                if ch_a not in adj[ch_b]:
                    adj[ch_b].append(ch_a)

        # ── Step 3: SINK ↔ every alive CH only ──────────────────────────────
        if "SINK" in alive_ids:
            adj.setdefault("SINK", [])
            for ch_id in ch_ids:
                if ch_id not in adj["SINK"]:
                    adj["SINK"].append(ch_id)
                adj.setdefault(ch_id, [])
                if "SINK" not in adj[ch_id]:
                    adj[ch_id].append("SINK")

        if not ch_ids and "SINK" in alive_ids:
            log.warning("No alive CHs — SINK has no backbone connections this tick!")

        return adj

    # ─────────────────────────────────────────────────────────────────────────
    # Penalty edge set (used by graph_engine to enforce CH routing)
    # ─────────────────────────────────────────────────────────────────────────

    def get_non_ch_edge_pairs(self, nodes: List[NodeState]) -> Set[tuple]:
        """
        Return canonical (sorted) edge tuples for non-CH ↔ non-CH links
        within the same cluster. Graph engine multiplies these costs by 50×
        so Dijkstra naturally routes: source → CH → SINK.

        Includes both static virtual nodes and dynamic real nodes.
        """
        ch_ids = {n.node_id for n in nodes if n.alive and n.is_ch}

        # Group alive non-CH nodes by cluster
        cluster_non_ch: Dict[int, List[str]] = {}
        for n in nodes:
            if n.node_id == "SINK" or not n.alive or n.cluster_id < 0:
                continue
            if n.is_ch:
                continue
            cid = n.cluster_id
            cluster_non_ch.setdefault(cid, [])
            cluster_non_ch[cid].append(n.node_id)

        penalized: Set[tuple] = set()
        for cid, members in cluster_non_ch.items():
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    penalized.add(tuple(sorted([a, b])))
        return penalized

    @staticmethod
    def _find_nearest_ch(
        node: NodeState, chs: List[NodeState]
    ) -> "NodeState | None":
        if not chs:
            return None
        return min(
            chs,
            key=lambda ch: math.sqrt(
                (node.x - ch.x) ** 2 + (node.y - ch.y) ** 2
            ),
        )
