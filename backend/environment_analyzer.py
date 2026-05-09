"""
backend/environment_analyzer.py
-------------------------------
Simulates environmental factors (Terrain, Foliage, Interference) across the 
WSN deployment field based on spatial coordinates or node states.
"""

import math
import random
from typing import List
from backend.models import NodeState

class EnvironmentAnalyzer:
    def __init__(self, field_size: float = 100.0) -> None:
        self.field_size = field_size
        
        # Define some spatial zones for environmental effects
        # For example, a dense foliage zone in the center
        self.foliage_center = (50.0, 50.0)
        self.foliage_radius = 25.0
        
        # Terrain elevation gradient (e.g. going uphill towards the sink)
        # SINK is typically at Y=90
        
        # Interference zone (e.g., near an industrial machine)
        self.interference_center = (20.0, 70.0)
        self.interference_radius = 15.0

    def tick(self, nodes: List[NodeState]) -> None:
        """
        Update environmental parameters for each alive node.
        In a real deployment, these would be inferred from sensor data
        or packet loss metrics. Here, we simulate them spatially.
        """
        for node in nodes:
            if not node.alive or node.node_id == "SINK":
                continue
                
            # 1. Terrain Attenuation (T_f)
            # Simulate rougher terrain further from the SINK
            dist_to_sink = math.sqrt((node.x - 50)**2 + (node.y - 90)**2)
            base_t_f = min(1.0, dist_to_sink / 100.0)
            node.t_f = base_t_f * 0.8 + random.uniform(0, 0.2)
            
            # 2. Foliage Density (F_f)
            # High if within the foliage zone
            dist_to_foliage = math.sqrt((node.x - self.foliage_center[0])**2 + (node.y - self.foliage_center[1])**2)
            if dist_to_foliage < self.foliage_radius:
                intensity = 1.0 - (dist_to_foliage / self.foliage_radius)
                node.f_f = intensity * 0.9 + random.uniform(0, 0.1)
            else:
                node.f_f = random.uniform(0.0, 0.1)
                
            # 3. Interference Score (I_s)
            # High if near interference source, plus random noise
            dist_to_interference = math.sqrt((node.x - self.interference_center[0])**2 + (node.y - self.interference_center[1])**2)
            if dist_to_interference < self.interference_radius:
                intensity = 1.0 - (dist_to_interference / self.interference_radius)
                node.i_s = intensity * 0.8 + random.uniform(0, 0.2)
            else:
                node.i_s = random.uniform(0.0, 0.1)

            # Predict energy drain based on current load and environment
            drain_rate = 0.1 + (node.load * 0.05) + (node.t_f * 0.1) + (node.f_f * 0.05)
            node.predicted_energy = max(0.0, node.energy - drain_rate)
            
            # Queue delay estimate based on load
            node.queue_delay = min(1000.0, node.load * 15.0)

