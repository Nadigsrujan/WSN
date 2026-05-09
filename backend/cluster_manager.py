"""
backend/cluster_manager.py
--------------------------
Handles the Hierarchical Clustering Layer.
Responsible for:
  - Grouping nodes into clusters based on distance (K-Means approach).
  - Dynamically electing Cluster Heads (CH) based on a multi-metric score.
"""

import math
from typing import List, Dict, Tuple
from backend.models import NodeState
from backend.utils import get_logger

log = get_logger("cluster_manager")

class ClusterManager:
    def __init__(self, expected_cluster_size: int = 5) -> None:
        self.expected_cluster_size = expected_cluster_size
        self.centroids: Dict[int, Tuple[float, float]] = {}
        self.clusters: Dict[int, List[str]] = {}  # cluster_id -> list of node_ids
        self.cluster_heads: Dict[int, str] = {}   # cluster_id -> CH node_id
        
        # Election formula weights
        self.w_e = 0.4    # Energy weight
        self.w_c = 0.2    # Connectivity degree (estimated via density)
        self.w_r = 0.2    # RSSI weight
        self.w_l = 0.2    # Load penalty weight

    def tick(self, nodes: List[NodeState]) -> None:
        """
        Periodically evaluate and update clusters and CHs.
        """
        alive_nodes = [n for n in nodes if n.alive and n.node_id != "SINK"]
        if not alive_nodes:
            return

        # 1. Update/Form Clusters
        self._assign_clusters(alive_nodes)
        
        # 2. Elect Cluster Heads
        self._elect_cluster_heads(alive_nodes)

    def _assign_clusters(self, nodes: List[NodeState]) -> None:
        """
        Simple geographic clustering.
        If centroids are empty, initialize them.
        """
        num_nodes = len(nodes)
        # Default to 3 clusters for a 10 node network, or scale down if fewer nodes
        k = min(num_nodes, max(3, num_nodes // self.expected_cluster_size))
        
        # Initialize centroids if needed
        if not self.centroids or len(self.centroids) != k:
            self.centroids = {}
            # Distribute centroids evenly (simplified grid approach)
            for i in range(k):
                self.centroids[i] = (
                    nodes[i % num_nodes].x,
                    nodes[i % num_nodes].y
                )
        
        # K-Means iteration (just 1-2 steps for performance)
        for _ in range(2):
            self.clusters = {i: [] for i in range(k)}
            # Assign
            for node in nodes:
                best_k = 0
                min_dist = float('inf')
                for i, (cx, cy) in self.centroids.items():
                    dist = math.sqrt((node.x - cx)**2 + (node.y - cy)**2)
                    if dist < min_dist:
                        min_dist = dist
                        best_k = i
                
                self.clusters[best_k].append(node.node_id)
                node.cluster_id = best_k
                
            # Update centroids
            for i in range(k):
                cluster_nodes = [n for n in nodes if n.cluster_id == i]
                if cluster_nodes:
                    avg_x = sum(n.x for n in cluster_nodes) / len(cluster_nodes)
                    avg_y = sum(n.y for n in cluster_nodes) / len(cluster_nodes)
                    self.centroids[i] = (avg_x, avg_y)

    def _elect_cluster_heads(self, nodes: List[NodeState]) -> None:
        """
        Elect CH per cluster using:
        Score = alpha*E + beta*C + gamma*RSSI - delta*Load
        """
        node_map = {n.node_id: n for n in nodes}
        
        for k, member_ids in self.clusters.items():
            if not member_ids:
                continue
                
            best_ch = None
            best_score = -float('inf')
            
            for nid in member_ids:
                n = node_map.get(nid)
                if not n:
                    continue
                    
                # E_i: energy [0, 100]
                e_i = n.energy
                # C_i: connectivity (number of members in same cluster)
                c_i = len(member_ids)
                # RSSI_i: Normalize RSSI to positive score
                rssi_i = (n.rssi + 100)  # [-100, -30] -> [0, 70]
                # Load_i: load penalty
                load_i = n.load
                
                score = (self.w_e * e_i) + (self.w_c * c_i) + (self.w_r * rssi_i) - (self.w_l * load_i)
                
                if score > best_score:
                    best_score = score
                    best_ch = nid
            
            # Apply CH status
            for nid in member_ids:
                n = node_map.get(nid)
                if n:
                    is_new_ch = (nid == best_ch)
                    if n.is_ch and not is_new_ch:
                        log.info(f"CH Migration: {nid} demoted in cluster {k}")
                    elif not n.is_ch and is_new_ch:
                        log.info(f"CH Election: {nid} elected in cluster {k} (Score: {best_score:.2f})")
                    n.is_ch = is_new_ch
                    
            self.cluster_heads[k] = best_ch
