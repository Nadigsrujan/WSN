"""
backend/graph_engine.py
-----------------------
Builds and maintains the weighted NetworkX graph from live NodeState data.

Uses EXPLICIT ADJACENCY from the mesh topology — no distance-based guessing.
Edges are created only between declared neighbors in the mesh.

Hybrid graph: real ESP32, Wokwi ESP32, virtual nodes, and the sink node
all coexist as graph vertices — the backend doesn't distinguish.
"""

from __future__ import annotations
import math
import time
from typing import Dict, List, Optional, Tuple

import networkx as nx

from backend.models import NodeState
from backend.utils import get_logger
from routing.cost_functions import compute_edge_cost, DEFAULT_WEIGHTS

log = get_logger("graph_engine")


class GraphEngine:
    """
    Manages the live weighted graph G(V, E).

    Call `rebuild(nodes, weights, adjacency)` every tick to produce the latest graph.
    The resulting graph is stored in `self.G` and used by the routing engine.
    """

    def __init__(self) -> None:
        self.G: nx.Graph = nx.Graph()
        self._last_rebuild: float = 0.0
        self._weights: Dict[str, float] = dict(DEFAULT_WEIGHTS)
        self._adjacency: Dict[str, List[str]] = {}

    # ─── Public API ───────────────────────────────────────────────────────────

    def rebuild(
        self,
        nodes: List[NodeState],
        weights: Dict[str, float] = None,
        adjacency: Dict[str, List[str]] = None,
    ) -> nx.Graph:
        """
        Clear and rebuild the graph from the current node list.

        Uses EXPLICIT ADJACENCY to create edges — not distance.
        Only alive nodes get edges; dead nodes are added for visualisation.
        """
        if weights:
            self._weights = weights
        if adjacency:
            self._adjacency = adjacency

        self.G.clear()

        node_map: Dict[str, NodeState] = {n.node_id: n for n in nodes}
        alive_ids = {n.node_id for n in nodes if n.alive}

        # ── Add ALL nodes as vertices (alive + dead for dashboard) ────────────
        for node in nodes:
            self.G.add_node(
                node.node_id,
                energy=node.energy if node.alive else 0.0,
                load=node.load if node.alive else 0,
                rssi=node.rssi,
                node_type=node.node_type,
                x=node.x,
                y=node.y,
                alive=node.alive,
            )

        # ── Add edges ONLY between declared neighbors, both alive ─────────────
        added_edges = set()
        for u_id, neighbors in self._adjacency.items():
            if u_id not in alive_ids:
                continue
            u = node_map.get(u_id)
            if not u:
                continue

            for v_id in neighbors:
                if v_id not in alive_ids:
                    continue
                v = node_map.get(v_id)
                if not v:
                    continue

                edge_key = tuple(sorted([u_id, v_id]))
                if edge_key in added_edges:
                    continue
                added_edges.add(edge_key)

                # Compute cost in both directions and average
                cost_uv = compute_edge_cost(u, v, self._weights)
                cost_vu = compute_edge_cost(v, u, self._weights)
                avg_cost = (cost_uv + cost_vu) / 2.0

                dist = self._distance(u, v)
                self.G.add_edge(
                    u_id, v_id,
                    weight=avg_cost,
                    distance=round(dist, 2),
                    lqi=round((u.lqi + v.lqi) / 2.0, 3),
                )

        self._last_rebuild = time.time()
        log.debug(
            f"Graph rebuilt: {self.G.number_of_nodes()} nodes, "
            f"{self.G.number_of_edges()} edges"
        )
        return self.G

    def update_edge_weights(self, weights: Dict[str, float], nodes: List[NodeState]) -> None:
        """Re-weight all existing edges without rebuilding the full graph."""
        self._weights = weights
        for u_id, v_id in self.G.edges():
            u = next((n for n in nodes if n.node_id == u_id), None)
            v = next((n for n in nodes if n.node_id == v_id), None)
            if u and v and u.alive and v.alive:
                cost = (compute_edge_cost(u, v, weights) +
                        compute_edge_cost(v, u, weights)) / 2.0
                self.G[u_id][v_id]["weight"] = cost

    # ─── Alternate path computation ───────────────────────────────────────────

    def compute_k_shortest_paths(
        self, source: str, target: str, k: int = 2
    ) -> List[List[str]]:
        """
        Compute the k-shortest simple paths from source to target.
        Uses Yen's algorithm via NetworkX.
        Returns up to k paths (may return fewer if not enough paths exist).
        """
        G = self.alive_subgraph()
        if source not in G or target not in G:
            return []
        try:
            paths = list(nx.shortest_simple_paths(G, source, target, weight="weight"))
            return paths[:k]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    # ─── Query helpers ────────────────────────────────────────────────────────

    def get_neighbors(self, node_id: str) -> List[str]:
        if node_id not in self.G:
            return []
        return list(self.G.neighbors(node_id))

    def get_edge_cost(self, u: str, v: str) -> Optional[float]:
        if self.G.has_edge(u, v):
            return self.G[u][v].get("weight")
        return None

    def node_exists(self, node_id: str) -> bool:
        return node_id in self.G

    def is_connected(self, u: str, v: str) -> bool:
        try:
            return nx.has_path(self.G, u, v)
        except nx.NodeNotFound:
            return False

    def alive_subgraph(self) -> nx.Graph:
        """Return a subgraph containing only alive nodes."""
        alive_ids = [n for n, d in self.G.nodes(data=True) if d.get("alive", False)]
        return self.G.subgraph(alive_ids).copy()

    def get_node_degree(self, node_id: str) -> int:
        """Return the degree of a node in the alive subgraph."""
        G = self.alive_subgraph()
        if node_id in G:
            return G.degree(node_id)
        return 0

    def graph_stats(self) -> Dict:
        alive_g = self.alive_subgraph()
        return {
            "total_nodes":    self.G.number_of_nodes(),
            "alive_nodes":    alive_g.number_of_nodes(),
            "total_edges":    self.G.number_of_edges(),
            "is_connected":   nx.is_connected(alive_g) if alive_g.number_of_nodes() > 0 else False,
            "avg_degree":     (sum(d for _, d in alive_g.degree()) / alive_g.number_of_nodes()
                               if alive_g.number_of_nodes() > 0 else 0),
            "last_rebuild":   self._last_rebuild,
        }

    # ─── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _distance(a: NodeState, b: NodeState) -> float:
        return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)

    def to_serialisable(self) -> Dict:
        """Return graph data as plain dicts for JSON serialisation."""
        nodes = []
        for nid, data in self.G.nodes(data=True):
            nodes.append({"id": nid, **data})

        edges = []
        for u, v, data in self.G.edges(data=True):
            edges.append({"source": u, "target": v, **data})

        return {"nodes": nodes, "edges": edges}
