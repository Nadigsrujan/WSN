"""
backend/main.py
----------------
Main orchestration loop for the WSN backend.

Flow (every 2 seconds):
  1. Virtual nodes step (simulation tick)
  2. Real/Wokwi nodes update via MQTT (background thread)
  3. Rebuild weighted graph using MESH ADJACENCY
  4. Run routing → compute best path + alternate path SOURCE → SINK
  5. Run RL tick → update routing weights
  6. Update metrics
  7. Build full routing table with alt paths
  8. Detect rerouting events and log them
  9. Write network state snapshot for dashboard

Source node: first alive non-sink node (configurable)
Sink node:   "SINK"
"""

from __future__ import annotations
import time
import signal
import sys
from typing import List, Dict

from backend.telemetry_store import TelemetryStore
from backend.graph_engine import GraphEngine
from backend.routing import RoutingEngine
from backend.rl import RLController
from backend.metrics import MetricsTracker
from backend.mqtt_client import MQTTIngestor
from backend.cluster_manager import ClusterManager
from backend.topology_manager import TopologyManager
from backend.environment_analyzer import EnvironmentAnalyzer
from simulation.network_sim import NetworkSimulator
from simulation.failure_injection import FailureInjector
from simulation.mesh_topology import get_all_positions, get_virtual_node_ids
from backend.utils import get_logger, write_network_state

log = get_logger("main")

# ─── Configuration ────────────────────────────────────────────────────────────
MQTT_BROKER      = "broker.hivemq.com"
MQTT_PORT        = 1883
TICK_INTERVAL_S  = 2.0         # seconds per orchestration tick
SOURCE_NODE      = "VNODE_1"   # default source (can be a real ESP32 ID)
SINK_NODE        = "SINK"
ESP32_NODE_ID    = "ESP32_REAL_1"   # expected ID of the real ESP32


def main() -> None:
    log.info("=" * 60)
    log.info("  RL-Assisted WSN — Hybrid HIL Backend Starting")
    log.info("=" * 60)

    # Get mesh positions, with ESP32 slot mapped to real ID
    mesh_positions = get_all_positions(esp32_id=ESP32_NODE_ID)
    virtual_ids = get_virtual_node_ids()

    n_virtual = len(virtual_ids)
    log.info(f"Mesh topology initialized: {n_virtual} virtual nodes + SINK + ESP32 slot")

    # ── 2. Shared state store ─────────────────────────────────────────────────
    store = TelemetryStore()

    # ── 3. Simulation engine (virtual nodes with fixed mesh positions) ────────
    sim = NetworkSimulator(
        store=store,
        n_virtual=n_virtual,
        area_m=100.0,
        tick_interval_s=TICK_INTERVAL_S,
        sink_position=mesh_positions["SINK"],
        mesh_positions={k: v for k, v in mesh_positions.items()
                        if k.startswith("VNODE")},
    )
    sim.start()

    # ── 4. MQTT ingestor (real + Wokwi nodes) ────────────────────────────────
    mqtt = MQTTIngestor(store=store, broker=MQTT_BROKER, port=MQTT_PORT)
    mqtt_ok = mqtt.start(timeout_s=8.0)
    if not mqtt_ok:
        log.warning("MQTT unavailable — running in simulation-only mode")

    # ── 5. Core engines ──────────────────────────────────────────────────────
    graph_engine = GraphEngine()
    router       = RoutingEngine(graph_engine)
    total_nodes  = n_virtual + 1   # vnodes + sink; real nodes add dynamically
    rl_ctrl      = RLController(total_nodes=total_nodes)
    metrics      = MetricsTracker(total_nodes=total_nodes)
    injector     = FailureInjector(sim.vnodes)
    
    # ── 6. Hierarchical Overlay Managers ──────────────────────────────────────
    cluster_mgr  = ClusterManager(expected_cluster_size=3)
    topology_mgr = TopologyManager(ch_range=150.0)
    env_analyzer = EnvironmentAnalyzer(field_size=100.0)

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    running = [True]
    def _shutdown(sig, frame):
        log.info("Shutdown signal received")
        running[0] = False
    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Event log ─────────────────────────────────────────────────────────────
    event_log: List[Dict] = []

    def add_event(msg: str, etype: str = "info"):
        event = {"timestamp": time.time(), "type": etype, "message": msg}
        event_log.append(event)
        if len(event_log) > 50:
            event_log.pop(0)
        log.info(f"[EVENT] {msg}")

    add_event("Backend started — mesh topology loaded", "info")

    # ── Main loop ─────────────────────────────────────────────────────────────
    step        = 0
    prev_alive  = set()

    log.info(f"Orchestrator running (tick={TICK_INTERVAL_S}s) — Ctrl+C to stop")

    while running[0]:
        tick_start = time.time()
        step      += 1

        # 3a. Snapshot all nodes (virtual + any real/Wokwi via MQTT)
        all_nodes  = store.all_nodes()
        curr_alive = {n.node_id for n in all_nodes if n.alive}
        newly_dead = list(prev_alive - curr_alive)
        prev_alive = curr_alive

        # Log node deaths as events
        for dead_id in newly_dead:
            add_event(f"Node {dead_id} died", "warning")

        # 3b. Check for stale real/Wokwi nodes (increased to 1 hour to prevent vanishing)
        store.check_stale_nodes(max_age_s=3600.0)

        # 3c. Override ESP32 position to mesh slot (if it exists in store)
        if store.get(ESP32_NODE_ID):
            esp32_pos = mesh_positions.get(ESP32_NODE_ID)
            if esp32_pos:
                store.set_node_position(ESP32_NODE_ID, esp32_pos[0], esp32_pos[1])

        # 3d. Update Environment & Clusters
        env_analyzer.tick(all_nodes)
        cluster_mgr.tick(all_nodes)
        
        # 3e. Generate Hierarchical Adjacency & Rebuild Graph
        hierarchical_adjacency = topology_mgr.get_hierarchical_adjacency(all_nodes)
        graph_engine.rebuild(all_nodes, weights=rl_ctrl.weights, adjacency=hierarchical_adjacency)

        # 3e. Compute best route SOURCE → SINK
        # PREFER the real ESP32 as source if it is alive, otherwise use VNODE_1
        source = ESP32_NODE_ID if (store.get(ESP32_NODE_ID) and store.get(ESP32_NODE_ID).alive) else SOURCE_NODE
        
        # If preferred source is dead, find ANY alive node
        if not store.get(source) or not store.get(source).alive:
            source = next((n.node_id for n in all_nodes if n.alive and n.node_id != SINK_NODE), None)

        path         = []
        delivered    = False
        if source:
            decision = router.make_routing_decision(source, SINK_NODE)
            path     = decision.path
            delivered = decision.success
            if path:
                log.info(f"Route ({source} -> SINK): {' → '.join(path)} (cost={decision.cost:.3f})")
            else:
                log.warning(f"No path from {source} to {SINK_NODE}")

        # 3f. Check for congestion events
        for node in all_nodes:
            if node.alive and node.load > 50 and node.node_id != SINK_NODE:
                add_event(
                    f"{node.node_id} congestion threshold exceeded (load={node.load})",
                    "warning"
                )

        # 3g. RL tick — observe outcome, update Q-table, get new weights
        # Exclude SINK from RL's alive list so energy stats are unbiased
        non_sink_nodes = [n for n in all_nodes if n.node_id != SINK_NODE]
        new_weights = rl_ctrl.tick(
            nodes=non_sink_nodes,
            newly_dead=newly_dead,
            packet_success=delivered,
            path=path,
        )

        # 3h. Update graph with new weights immediately
        graph_engine.update_edge_weights(new_weights, all_nodes)

        # 3i. Metrics
        metrics.update(
            nodes=all_nodes,
            step=step,
            path=path,
            delivered=delivered,
            weights=new_weights,
        )

        # 3j. Build full routing table
        routing_table = router.get_full_routing_table(SINK_NODE, all_nodes)

        # 3k. Collect rerouting events into event log
        for evt in router.get_recent_events():
            if evt not in event_log:
                event_log.append(evt)
        # Cap event log
        while len(event_log) > 50:
            event_log.pop(0)

        # 3l. Write state for dashboard
        snapshot = store.snapshot()
        snapshot.update({
            "current_path":  path,
            "alt_path":      router.last_alt_path,
            "rl":            rl_ctrl.rl_summary,
            "metrics":       metrics.summary(),
            "graph":         graph_engine.to_serialisable(),
            "newly_dead":    newly_dead,
            "source":        source or "",
            "sink":          SINK_NODE,
            "routing_table": routing_table,
            "event_log":     event_log[-30:],
        })
        write_network_state(snapshot)

        if step % 10 == 0:
            m = metrics.summary()
            log.info(
                f"Step {step:4d} | Alive={store.alive_count()}/{store.count()} "
                f"| PDR={m['pdr']:.1f}% | Reroutes={m['rerouting_events']} "
                f"| Variance={m['energy_variance']:.1f} "
                f"| α={new_weights.get('alpha',0):.2f} "
                f"β={new_weights.get('beta',0):.2f}"
            )

        # Respect tick interval
        elapsed = time.time() - tick_start
        sleep_t = max(0.0, TICK_INTERVAL_S - elapsed)
        time.sleep(sleep_t)

    # ── Cleanup ──────────────────────────────────────────────────────────────
    sim.stop()
    mqtt.stop()
    log.info(f"Backend stopped after {step} steps")
    log.info(f"Final metrics: {metrics.summary()}")


if __name__ == "__main__":
    main()
