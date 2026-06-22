"""
backend/cluster_manager.py
--------------------------
Handles the Hierarchical Clustering Layer.

Architecture:
  - Cluster assignments are FROZEN after initialization using the geographic
    partitions defined in mesh_topology.CLUSTER_MEMBERS.
  - Within each cluster, the CH role is dynamically elected based on node health.
  - CH election only changes the `is_ch` flag — NEVER node positions or cluster ids.
  - CH re-election uses hysteresis so the role does NOT flip every tick.

Rules:
  - Cluster assignments: permanent, position-based, loaded from static mesh config.
  - CH election: energy-driven, hysteresis-protected.
  - ESP32 is treated as a fully equal mesh node — can be CH or member.
  - No position data is read or written here.
"""

import math
from typing import List, Dict, Optional, Tuple
from backend.models import NodeState
from backend.utils import get_logger
from simulation.mesh_topology import (
    CLUSTER_MEMBERS,
    INITIAL_CH,
    get_cluster_for_node,
)

log = get_logger("cluster_manager")

# How many ticks between forced re-election checks
ELECTION_INTERVAL = 1
# A candidate must beat the current CH by this margin to trigger migration
HYSTERESIS_MARGIN = 0.1


class ClusterManager:
    def __init__(self, num_clusters: int = 3) -> None:
        self.num_clusters = num_clusters

        # Cluster membership loaded from static config (never changes)
        self.clusters: Dict[int, List[str]] = {
            k: list(v) for k, v in CLUSTER_MEMBERS.items()
        }
        self.cluster_heads: Dict[int, Optional[str]] = {
            k: INITIAL_CH[k] for k in CLUSTER_MEMBERS
        }

        self._tick_count = 0
        self._initialized = False

        # Election formula weights — energy-driven only
        self.w_e = 1.0    # Residual energy
        self.w_r = 0.0
        self.w_c = 0.0
        self.w_l = 0.0

        # Track CH changes for event generation
        self._ch_change_events: List[Dict] = []

    # ─── Public tick ─────────────────────────────────────────────────────────

    def tick(self, nodes: List[NodeState]) -> None:
        """
        Called every simulation tick.
        1. On first call, apply the static cluster assignments to all nodes.
        2. Every ELECTION_INTERVAL ticks, re-evaluate CH elections.
        Positions are NEVER modified here.
        """
        alive_nodes = [n for n in nodes if n.alive and n.node_id != "SINK"]
        if not alive_nodes:
            return

        self._tick_count += 1

        # Step 1: Apply stable geographic cluster assignments
        self._assign_static_clusters(alive_nodes)

        # Step 2: Elect CHs periodically (only flips is_ch flag)
        if self._tick_count % ELECTION_INTERVAL == 0 or not self._initialized:
            self._initialized = True
            self._elect_cluster_heads(alive_nodes)
        else:
            self._apply_ch_flags(alive_nodes)

    def get_ch_change_events(self) -> List[Dict]:
        """Return and clear pending CH change events."""
        events = list(self._ch_change_events)
        self._ch_change_events.clear()
        return events

    def get_cluster_membership(self) -> Dict[int, List[str]]:
        """Return {cluster_id: [node_ids]}."""
        return dict(self.clusters)

    # ─── Cluster Assignment ───────────────────────────────────────────────────

    def _assign_static_clusters(self, nodes: List[NodeState]) -> None:
        """
        Apply the STATIC cluster assignments from mesh_topology.CLUSTER_MEMBERS
        to all alive nodes. This is the canonical cluster definition —
        it NEVER changes, even when CH roles change.
        """
        node_map = {n.node_id: n for n in nodes}

        for cluster_id, member_ids in self.clusters.items():
            for nid in member_ids:
                n = node_map.get(nid)
                if n and n.cluster_id != cluster_id:
                    n.cluster_id = cluster_id

        # Handle real ESP32 nodes that arrived via MQTT and aren't in the
        # static list yet — assign them based on geographic proximity.
        known_ids = set(nid for members in self.clusters.values() for nid in members)
        for n in nodes:
            if n.node_id not in known_ids:
                # New node (e.g. a second ESP32) — assign to nearest cluster
                cid = self._nearest_cluster(n)
                n.cluster_id = cid
                if n.node_id not in self.clusters[cid]:
                    self.clusters[cid].append(n.node_id)
                    log.info(
                        f"New node {n.node_id} dynamically assigned to cluster {cid}"
                    )

    # ─── CH Election ─────────────────────────────────────────────────────────

    def _score_node(self, n: NodeState, cluster_size: int) -> float:
        """Compute CH candidacy score for a node (energy-only by default)."""
        e_i    = n.energy                   # [0, 100]
        rssi_i = (n.rssi + 100)             # [-100,-30] → [0,70]
        c_i    = cluster_size               # connectivity proxy
        load_i = n.load                     # [0, 100]
        return (
            self.w_e * e_i
            + self.w_r * rssi_i
            + self.w_c * c_i
            - self.w_l * load_i
        )

    def _elect_cluster_heads(self, nodes: List[NodeState]) -> None:
        """
        Elect best CH per cluster with hysteresis.
        A candidate must beat the current CH by HYSTERESIS_MARGIN to take over.
        Only the `is_ch` flag is changed — positions are untouched.
        """
        node_map = {n.node_id: n for n in nodes}

        for k, member_ids in self.clusters.items():
            alive_members = [
                nid for nid in member_ids if nid in node_map
            ]
            if not alive_members:
                continue

            cluster_size = len(alive_members)
            current_ch_id = self.cluster_heads.get(k)

            best_nid   = None
            best_score = -float("inf")

            for nid in alive_members:
                n = node_map[nid]
                score = self._score_node(n, cluster_size)
                if score > best_score:
                    best_score = score
                    best_nid = nid

            # Apply hysteresis: only migrate if challenger beats current CH significantly
            if current_ch_id and current_ch_id in node_map:
                current_score = self._score_node(
                    node_map[current_ch_id], cluster_size
                )
                if best_score < current_score + HYSTERESIS_MARGIN:
                    best_nid = current_ch_id  # Keep current CH

            # Detect CH change
            if best_nid != current_ch_id and current_ch_id:
                old_ch_node = node_map.get(current_ch_id)
                log.info(
                    f"CH Migration cluster {k}: {current_ch_id} → {best_nid} "
                    f"(score: {best_score:.2f})"
                )
                self._ch_change_events.append({
                    "type": "ch_change",
                    "cluster": k,
                    "old_ch": current_ch_id,
                    "new_ch": best_nid,
                    "message": (
                        f"⚡ CH Election: {best_nid} is now Cluster Head "
                        f"of Cluster {k + 1} (was {current_ch_id})"
                    ),
                })

            # Apply CH status — ONLY the is_ch flag changes
            for nid in alive_members:
                n = node_map[nid]
                is_new_ch = (nid == best_nid)
                if not n.is_ch and is_new_ch:
                    log.info(
                        f"CH Elected: {nid} in cluster {k} "
                        f"(score={best_score:.2f})"
                    )
                n.is_ch = is_new_ch

            self.cluster_heads[k] = best_nid

    def _apply_ch_flags(self, nodes: List[NodeState]) -> None:
        """
        Re-apply CH flags from stored elections without running a new election.
        Handles the case where a CH node has died mid-interval.
        """
        node_map = {n.node_id: n for n in nodes}
        for k, member_ids in self.clusters.items():
            ch_id = self.cluster_heads.get(k)
            # If current CH died, trigger emergency re-election
            if ch_id and ch_id not in node_map:
                log.warning(
                    f"CH {ch_id} in cluster {k} died — "
                    f"triggering emergency re-election"
                )
                self._elect_cluster_heads_for_cluster(k, member_ids, node_map)
            else:
                for nid in member_ids:
                    n = node_map.get(nid)
                    if n:
                        n.is_ch = (nid == ch_id)

    def _elect_cluster_heads_for_cluster(
        self,
        k: int,
        member_ids: List[str],
        node_map: Dict[str, NodeState],
    ) -> None:
        """Emergency re-election for a single cluster whose CH died."""
        alive_members = [nid for nid in member_ids if nid in node_map]
        cluster_size = len(alive_members)
        best_nid   = None
        best_score = -float("inf")

        for nid in alive_members:
            n = node_map[nid]
            score = self._score_node(n, cluster_size)
            if score > best_score:
                best_score = score
                best_nid = nid

        old_ch = self.cluster_heads.get(k)
        if best_nid and best_nid != old_ch:
            self._ch_change_events.append({
                "type": "ch_change",
                "cluster": k,
                "old_ch": old_ch or "—",
                "new_ch": best_nid,
                "message": (
                    f"⚡ Emergency CH Election: {best_nid} takes over "
                    f"Cluster {k + 1} (old CH died)"
                ),
            })

        for nid in alive_members:
            n = node_map[nid]
            is_new_ch = (nid == best_nid)
            if not n.is_ch and is_new_ch:
                log.info(
                    f"Emergency CH Elected: {nid} in cluster {k}"
                )
            n.is_ch = is_new_ch

        self.cluster_heads[k] = best_nid

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _nearest_cluster(self, node: NodeState) -> int:
        """Find the nearest cluster based on centroid proximity."""
        from simulation.mesh_topology import STATIC_POSITIONS, CLUSTER_MEMBERS
        best_k = 0
        best_dist = float("inf")
        for cid, members in CLUSTER_MEMBERS.items():
            # Compute centroid from static positions
            positions = [
                STATIC_POSITIONS[m]
                for m in members
                if m in STATIC_POSITIONS
            ]
            if not positions:
                continue
            cx = sum(p[0] for p in positions) / len(positions)
            cy = sum(p[1] for p in positions) / len(positions)
            dist = math.sqrt((node.x - cx) ** 2 + (node.y - cy) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_k = cid
        return best_k
