"""
backend/routing.py
------------------
Routing engine: Dijkstra-based path selection over the live NetworkX graph.

Provides:
  - get_best_path(source, sink)  → full path list
  - get_alternate_path(source, sink)  → 2nd shortest path
  - get_next_hop(source, sink)   → single next hop
  - get_full_routing_table(sink) → complete routing table with alt paths
  - greedy_next_hop(source, sink, nodes) → local greedy selection
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import time

import networkx as nx

from backend.graph_engine import GraphEngine
from backend.models import NodeState, RoutingDecision
from backend.utils import get_logger, log_routing

log = get_logger("routing")


class RoutingEngine:
    """
    Manages path computation for the WSN.

    Uses Dijkstra on the weighted NetworkX graph maintained by GraphEngine.
    Computes primary and alternate paths for fault tolerance.
    """

    def __init__(self, graph_engine: GraphEngine) -> None:
        self.graph_engine    = graph_engine
        self._packet_counter = 0
        self._last_path: List[str] = []
        self._last_alt_path: List[str] = []
        self._reroute_events: List[Dict] = []

    # ─── Primary routing API ──────────────────────────────────────────────────

    def get_best_path(self, source: str, sink: str) -> List[str]:
        """
        Compute lowest-cost path from source to sink using Dijkstra.
        Applies a 'stability bias' to the previous path to prevent jitter.
        """
        G = self.graph_engine.alive_subgraph()

        if source not in G or sink not in G:
            log.warning(f"Source '{source}' or sink '{sink}' not in alive graph")
            return []

        # ── Apply Stability Factor ────────────────────────────────────────────
        # Reduce cost of edges on the PREVIOUS path by 15% to avoid 'ping-ponging'
        # between paths with nearly identical weights.
        STABILITY_FACTOR = 0.85
        if self._last_path and len(self._last_path) >= 2:
            for i in range(len(self._last_path) - 1):
                u, v = self._last_path[i], self._last_path[i+1]
                if G.has_edge(u, v):
                    G[u][v]["weight"] *= STABILITY_FACTOR

        try:
            path = nx.shortest_path(G, source=source, target=sink, weight="weight")
            return path
        except nx.NetworkXNoPath:
            log.warning(f"No path from {source} to {sink}")
            return []
        except nx.NodeNotFound as e:
            log.error(f"Node not found during routing: {e}")
            return []

    def get_alternate_path(self, source: str, sink: str) -> List[str]:
        """
        Compute the 2nd shortest path (alternate route) from source to sink.
        Returns empty list if no alternate path exists.
        """
        paths = self.graph_engine.compute_k_shortest_paths(source, sink, k=2)
        if len(paths) >= 2:
            return paths[1]
        return []

    def get_path_cost(self, path: List[str]) -> float:
        """Sum of edge weights along a path."""
        if len(path) < 2:
            return 0.0
        G = self.graph_engine.G
        total = 0.0
        for i in range(len(path) - 1):
            edge_data = G.get_edge_data(path[i], path[i + 1])
            if edge_data:
                total += edge_data.get("weight", 0.0)
        return round(total, 4)

    def get_next_hop(self, source: str, sink: str) -> Optional[str]:
        """Return only the immediate next hop from source toward sink."""
        path = self.get_best_path(source, sink)
        if len(path) >= 2:
            return path[1]
        return None

    def get_alternate_next_hop(self, source: str, sink: str) -> Optional[str]:
        """Return the immediate next hop from the alternate path."""
        path = self.get_alternate_path(source, sink)
        if len(path) >= 2:
            return path[1]
        return None

    def greedy_next_hop(
        self,
        source: str,
        sink: str,
        node_lookup: Dict[str, NodeState],
    ) -> Optional[str]:
        """
        Local greedy selection: pick the alive neighbour with the lowest
        edge weight toward the sink. Does not require a full graph traversal.
        """
        neighbors = self.graph_engine.get_neighbors(source)
        if not neighbors:
            return None

        best_hop  = None
        best_cost = float("inf")

        for nid in neighbors:
            n = node_lookup.get(nid)
            if n is None or not n.alive:
                continue
            edge_cost = self.graph_engine.get_edge_cost(source, nid) or float("inf")
            if edge_cost < best_cost:
                best_cost = edge_cost
                best_hop  = nid

        return best_hop

    # ─── Full routing table ───────────────────────────────────────────────────

    def get_full_routing_table(
        self, sink: str, all_nodes: List[NodeState]
    ) -> Dict[str, Dict]:
        """
        Compute the full routing table for every alive node.

        Returns: {
            node_id: {
                "next_hop": str,
                "alt_hop": str,
                "cost": float,
                "alt_cost": float,
                "status": str,  # "active" | "congested" | "rerouted"
            }
        }
        """
        node_map = {n.node_id: n for n in all_nodes}
        table = {}

        for node in all_nodes:
            if node.node_id == sink or not node.alive:
                continue

            primary = self.get_best_path(node.node_id, sink)
            alt = self.get_alternate_path(node.node_id, sink)

            next_hop = primary[1] if len(primary) >= 2 else "—"
            alt_hop = alt[1] if len(alt) >= 2 else "—"
            cost = self.get_path_cost(primary)
            alt_cost = self.get_path_cost(alt) if alt else 0.0

            # Determine status
            status = "active"
            # Check if any node on primary path is congested (load > 50)
            for nid in primary[1:-1]:  # exclude source and sink
                n = node_map.get(nid)
                if n and n.load > 50:
                    status = "congested"
                    break

            table[node.node_id] = {
                "next_hop": next_hop,
                "alt_hop": alt_hop,
                "cost": round(cost, 3),
                "alt_cost": round(alt_cost, 3),
                "status": status,
            }

        return table

    # ─── Routing decision record ──────────────────────────────────────────────

    def make_routing_decision(
        self,
        source: str,
        sink: str,
        success: bool = True,
    ) -> RoutingDecision:
        """Build a RoutingDecision object and log it."""
        self._packet_counter += 1
        path = self.get_best_path(source, sink)
        cost = self.get_path_cost(path)
        alt_path = self.get_alternate_path(source, sink)

        decision = RoutingDecision(
            source=source,
            sink=sink,
            path=path,
            cost=cost,
            hop_count=max(0, len(path) - 1),
            success=success and len(path) > 0,
            timestamp=time.time(),
        )
        log_routing(decision.to_dict())

        # Detect rerouting
        if self._last_path and path and path != self._last_path:
            event = {
                "timestamp": time.time(),
                "type": "reroute",
                "old_path": self._last_path,
                "new_path": path,
                "message": f"Rerouted: {' → '.join(self._last_path)} ⟶ {' → '.join(path)}",
            }
            self._reroute_events.append(event)
            log.info(f"REROUTING: {' → '.join(self._last_path)} ⟶ {' → '.join(path)}")

        self._last_path = list(path)
        self._last_alt_path = list(alt_path)

        return decision

    # ─── Event log ────────────────────────────────────────────────────────────

    def get_recent_events(self, max_events: int = 50) -> List[Dict]:
        """Return the most recent rerouting events."""
        return self._reroute_events[-max_events:]

    def add_event(self, event: Dict) -> None:
        """Add a custom event to the log (e.g. congestion detected)."""
        self._reroute_events.append(event)

    # ─── Utility ──────────────────────────────────────────────────────────────

    @property
    def last_path(self) -> List[str]:
        return self._last_path

    @property
    def last_alt_path(self) -> List[str]:
        return self._last_alt_path

    @property
    def packet_count(self) -> int:
        return self._packet_counter

    def all_pairs_shortest_paths(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Compute all-pairs shortest paths in the alive subgraph.
        Useful for dashboard heatmaps and research analysis.
        """
        G = self.graph_engine.alive_subgraph()
        try:
            return dict(nx.all_pairs_shortest_path(G, cutoff=10))
        except Exception:
            return {}
