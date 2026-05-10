"""
backend/topology_manager.py
---------------------------
Dynamically generates the adjacency matrix for the Hierarchical Mesh.
Rules:
1. Normal nodes connect ONLY to their Cluster Head (CH).
2. CH nodes connect to neighboring CHs (Mesh Backbone) and to the SINK.
"""

from typing import List, Dict, Tuple
import math
from backend.models import NodeState

class TopologyManager:
    def __init__(self, ch_range: float = 60.0) -> None:
        # Maximum communication range between CHs
        self.ch_range = ch_range

    def get_hierarchical_adjacency(self, nodes: List[NodeState]) -> Dict[str, List[str]]:
        """
        Builds adjacency dict {node_id: [neighbor_id1, neighbor_id2, ...]}
        based on the current cluster assignments and CH statuses.
        """
        adjacency: Dict[str, List[str]] = {}
        
        alive_nodes = [n for n in nodes if n.alive]
        node_map = {n.node_id: n for n in alive_nodes}
        
        chs = [n for n in alive_nodes if n.is_ch]
        
        # SINK connects to all CHs within reasonable range or nearest CHs
        sink = node_map.get("SINK")
        if sink:
            adjacency["SINK"] = []
            
        for n in alive_nodes:
            if n.node_id == "SINK":
                continue
                
            adjacency[n.node_id] = []
            
            if n.is_ch:
                # 1. Connect to all members of its cluster
                members = [m for m in alive_nodes if m.cluster_id == n.cluster_id and not m.is_ch]
                adjacency[n.node_id].extend([m.node_id for m in members])
                
                # 2. Connect to ALL other CHs (Full Mesh Backbone)
                # The user wants all cluster heads connected to each other
                for other_ch in chs:
                    if other_ch.node_id != n.node_id:
                        adjacency[n.node_id].append(other_ch.node_id)
                
                # 3. Connect to SINK (Mandatory for all CHs)
                # The user wants the sink connected to all cluster heads
                if sink:
                    if n.node_id not in adjacency["SINK"]:
                        adjacency["SINK"].append(n.node_id)
                    adjacency[n.node_id].append("SINK")
            else:
                # Normal node: Connect to its CH
                my_ch = next((ch for ch in chs if ch.cluster_id == n.cluster_id), None)
                if my_ch:
                    adjacency[n.node_id].append(my_ch.node_id)
                else:
                    # Self-healing fallback: if no CH in my cluster, connect to nearest CH
                    best_ch = None
                    min_dist = float('inf')
                    for ch in chs:
                        dist = math.sqrt((n.x - ch.x)**2 + (n.y - ch.y)**2)
                        if dist < min_dist:
                            min_dist = dist
                            best_ch = ch
                    if best_ch:
                        adjacency[n.node_id].append(best_ch.node_id)
                        
        return adjacency

    def get_backbone_edges(self, nodes: List[NodeState]) -> List[Tuple[str, str]]:
        """
        Returns a list of edge tuples (source_id, target_id) representing the mesh backbone.
        The backbone consists ONLY of CH↔CH and CH↔SINK connections.
        Used primarily for visualization and targeted routing.
        """
        backbone_edges = []
        alive_nodes = [n for n in nodes if n.alive]
        chs = [n for n in alive_nodes if n.is_ch]
        ch_ids = {ch.node_id for ch in chs}
        
        # 1. CH to SINK
        if any(n.node_id == "SINK" for n in alive_nodes):
            for ch in chs:
                backbone_edges.append((ch.node_id, "SINK"))
                backbone_edges.append(("SINK", ch.node_id))
                
        # 2. CH to CH
        for i in range(len(chs)):
            for j in range(i + 1, len(chs)):
                ch1 = chs[i]
                ch2 = chs[j]
                backbone_edges.append((ch1.node_id, ch2.node_id))
                backbone_edges.append((ch2.node_id, ch1.node_id))
                
        return backbone_edges
