"""
backend/cluster_manager.py
--------------------------
Handles the Hierarchical Clustering Layer.
Responsible for:
  - Dynamically electing Cluster Heads (CH) within FIXED clusters 
    using a multi-metric score (Energy, Connectivity, RSSI, Load, Reliability).
  - Managing CH migrations and tenure to ensure fairness.
"""

from typing import List, Dict, Optional
from collections import defaultdict
from backend.models import NodeState
from backend.utils import get_logger

log = get_logger("cluster_manager")

class ClusterManager:
    def __init__(self) -> None:
        self.clusters: Dict[int, List[str]] = defaultdict(list)  # cluster_id -> list of node_ids
        self.cluster_heads: Dict[int, str] = {}                  # cluster_id -> CH node_id
        
        # Tracking history for stability metrics
        self._ch_tenure: Dict[str, int] = defaultdict(int)       # node_id -> steps as CH
        
        # Election formula weights (5 metrics)
        self.w_e   = 0.30  # Energy weight
        self.w_c   = 0.15  # Connectivity/Density weight
        self.w_r   = 0.15  # RSSI weight
        self.w_l   = 0.10  # Load penalty weight
        self.w_rel = 0.15  # Reliability weight
        self.w_ten = 0.05  # Tenure penalty (for fairness/rotation)

    def tick(self, nodes: List[NodeState]) -> None:
        """
        Periodically evaluate and elect CHs within their assigned clusters.
        """
        alive_nodes = [n for n in nodes if n.alive and n.node_id != "SINK"]
        if not alive_nodes:
            return

        # 1. Group nodes by their predefined cluster_id
        self.clusters.clear()
        for n in alive_nodes:
            if n.cluster_id is not None:
                self.clusters[n.cluster_id].append(n.node_id)
        
        # 2. Elect Cluster Heads
        self._elect_cluster_heads(alive_nodes)

    def _elect_cluster_heads(self, nodes: List[NodeState]) -> None:
        """
        Elect CH per cluster using the 5-metric formula.
        Score = w_e*E + w_c*C + w_r*RSSI - w_l*Load + w_rel*Rel - w_ten*Tenure
        """
        node_map = {n.node_id: n for n in nodes}
        
        for cid, member_ids in self.clusters.items():
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
                
                # C_i: connectivity (number of members in cluster)
                c_i = len(member_ids)
                
                # RSSI_i: Normalize RSSI to positive score
                rssi_i = (n.rssi + 100)  # [-100, -30] -> [0, 70]
                
                # Load_i: load penalty
                load_i = n.load
                
                # Rel_i: reliability score (0.0 to 1.0) -> scale to 100
                rel_i = n.reliability * 100.0
                
                # Tenure penalty: penalize nodes that have been CH for a long time
                tenure_i = self._ch_tenure[nid]
                
                # Compute final score
                score = (self.w_e * e_i) + \
                        (self.w_c * c_i) + \
                        (self.w_r * rssi_i) - \
                        (self.w_l * load_i) + \
                        (self.w_rel * rel_i) - \
                        (self.w_ten * tenure_i)
                
                n.ch_election_score = score
                
                if score > best_score:
                    best_score = score
                    best_ch = nid
            
            # Handle CH Migration and role assignment
            old_ch = self.cluster_heads.get(cid)
            if best_ch and old_ch != best_ch:
                self._handle_ch_migration(cid, old_ch, best_ch, best_score, node_map)
            else:
                # Same CH, just increase tenure
                if best_ch:
                    self._ch_tenure[best_ch] += 1
                    n_best = node_map.get(best_ch)
                    if n_best:
                        n_best.ch_tenure = self._ch_tenure[best_ch]
            
            # Apply CH status
            for nid in member_ids:
                n = node_map.get(nid)
                if n:
                    is_new_ch = (nid == best_ch)
                    n.is_ch = is_new_ch
                    n.role = "cluster_head" if is_new_ch else "member"
                    if not is_new_ch:
                        self._ch_tenure[nid] = max(0, self._ch_tenure[nid] - 1) # decay tenure when not CH
                        n.ch_tenure = self._ch_tenure[nid]
                    
            self.cluster_heads[cid] = best_ch

    def _handle_ch_migration(self, cid: int, old_ch: Optional[str], new_ch: str, score: float, node_map: Dict[str, NodeState]) -> None:
        """Log migration events and reset tenure for the new CH."""
        if old_ch:
            log.warning(f"[CLUSTER {cid}] CH Migration: {old_ch} demoted -> {new_ch} elected (Score: {score:.2f})")
        else:
            log.info(f"[CLUSTER {cid}] Initial CH Election: {new_ch} elected (Score: {score:.2f})")
            
        self._ch_tenure[new_ch] = 0
        n_new = node_map.get(new_ch)
        if n_new:
            n_new.ch_tenure = 0

    def get_cluster_info(self, nodes: List[NodeState]) -> List[Dict]:
        """Returns cluster summary for the frontend dashboard."""
        alive_nodes = [n for n in nodes if n.alive and n.node_id != "SINK"]
        
        # Regroup to ensure we have the latest snapshot
        temp_clusters = defaultdict(list)
        for n in alive_nodes:
            if n.cluster_id is not None:
                temp_clusters[n.cluster_id].append(n)
                
        info = []
        for cid, member_nodes in temp_clusters.items():
            ch_node = next((n for n in member_nodes if n.is_ch), None)
            
            avg_energy = sum(n.energy for n in member_nodes) / max(1, len(member_nodes))
            
            info.append({
                "cluster_id": cid,
                "ch_id": ch_node.node_id if ch_node else None,
                "ch_score": round(ch_node.ch_election_score, 2) if ch_node else 0.0,
                "member_count": len(member_nodes),
                "avg_energy": round(avg_energy, 1)
            })
            
        return sorted(info, key=lambda x: x["cluster_id"])
