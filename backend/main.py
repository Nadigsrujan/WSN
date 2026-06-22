"""
backend/main.py
----------------
Main orchestration loop for the WSN backend.

Flow (every 2 seconds):
  1. Virtual nodes step (simulation tick)
  2. Real/Wokwi nodes update via MQTT (background thread)
  3. Rebuild weighted graph using STATIC MESH ADJACENCY
  4. Run routing → compute best path + alternate path SOURCE → SINK
  5. Run RL tick → update routing weights (costs only, never positions)
  6. Update metrics
  7. Build full routing table with alt paths
  8. Detect rerouting events and log them
  9. Collect CH change events
  10. Write network state snapshot for dashboard

Key invariants:
  - Node positions are SET ONCE at startup from STATIC_POSITIONS and FROZEN.
  - No runtime code changes x/y coordinates.
  - RL only affects routing weights (alpha, beta, gamma, delta, epsilon).
  - CH elections only change the is_ch flag.

Source node: first alive non-sink node (configurable)
Sink node:   "SINK"
"""

from __future__ import annotations
import time
import signal
import sys
import random
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
from simulation.mesh_topology import (
    get_all_positions,
    get_virtual_node_ids,
    validate_topology,
    get_full_static_adjacency,
)
from backend.utils import get_logger, write_network_state
from backend.cloud_sync import CloudSync

log = get_logger("main")

# ─── Configuration ────────────────────────────────────────────────────────────
MQTT_BROKER      = "broker.hivemq.com"
MQTT_PORT        = 1883
TICK_INTERVAL_S  = 2.0
SOURCE_NODE      = "VNODE_1"   # default source
SINK_NODE        = "SINK"
ESP32_NODE_ID    = "ESP32_REAL_1"   # expected ID of the real ESP32


def main() -> None:
    log.info("=" * 60)
    log.info("  RL-Assisted WSN — Static Clustered Mesh Backend Starting")
    log.info("=" * 60)

    # ── 1. Validate static topology ───────────────────────────────────────────
    log.info("Validating static mesh topology...")
    static_adj = get_full_static_adjacency(esp32_id=ESP32_NODE_ID)
    try:
        validate_topology(static_adj)
        log.info("✓ Topology validation passed")
    except AssertionError as e:
        log.error(f"✗ Topology validation FAILED: {e}")
        sys.exit(1)

    # ── 2. Get static positions (never changes) ───────────────────────────────
    mesh_positions = get_all_positions(esp32_id=ESP32_NODE_ID)
    virtual_ids    = get_virtual_node_ids()
    n_virtual      = len(virtual_ids)
    log.info(
        f"Mesh topology: {n_virtual} virtual nodes + SINK "
        f"+ ESP32 slot → {len(mesh_positions)} positions loaded"
    )

    # ── 3. Shared state store ─────────────────────────────────────────────────
    store = TelemetryStore()

    # ── 4. Simulation engine ──────────────────────────────────────────────────
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

    # ── 5. FREEZE virtual node positions (VNODE_* and SINK only) ───────────
    # Real nodes (ESP32_REAL_1) are NOT frozen here — their position comes
    # from MQTT telemetry at runtime and determines which cluster they join.
    time.sleep(0.2)  # Let sim._sync_to_store() run once
    frozen_count = 0
    for node_id, (x, y) in mesh_positions.items():
        # Only freeze virtual nodes and SINK — never pre-freeze real hardware
        if node_id.startswith("VNODE") or node_id == "SINK":
            store.initialize_position(node_id, x, y)
            frozen_count += 1
    log.info(f"✓ Positions frozen for {frozen_count} virtual nodes (real hardware positions left dynamic)")

    # ── 6. MQTT ingestor (real + Wokwi nodes) ─────────────────────────────────
    mqtt = MQTTIngestor(store=store, broker=MQTT_BROKER, port=MQTT_PORT)
    mqtt_ok = mqtt.start(timeout_s=8.0)
    if not mqtt_ok:
        log.warning("MQTT unavailable — running in simulation-only mode")

    # ── Cloud sync (Google Firestore) — async, optional, fail-safe ─────────────
    # Mirrors telemetry / routing / CH / RL events to Firestore on a background
    # thread. If firebase-admin or credentials are missing it stays disabled and
    # never affects the simulation, MQTT, routing, RL, or the dashboard.
    cloud = CloudSync(gateway_id=ESP32_NODE_ID)
    cloud.start()

    # ── 7. Core engines ───────────────────────────────────────────────────────
    graph_engine = GraphEngine()
    router       = RoutingEngine(graph_engine)
    total_nodes  = n_virtual + 1   # vnodes + sink; real nodes add dynamically
    rl_ctrl      = RLController(total_nodes=total_nodes)
    metrics      = MetricsTracker(total_nodes=total_nodes)
    injector     = FailureInjector(sim.vnodes)

    # ── 8. Hierarchical overlay managers ──────────────────────────────────────
    cluster_mgr  = ClusterManager(num_clusters=3)
    topology_mgr = TopologyManager(esp32_id=ESP32_NODE_ID)
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

    add_event("Backend started — static mesh topology loaded", "info")

    # ── Main loop ─────────────────────────────────────────────────────────────
    step       = 0
    prev_alive = set()
    ch_events_accum: List[Dict] = []  # accumulate CH events for dashboard
    last_reroute_ts = 0.0             # high-water mark for reroutes sent to cloud

    log.info(f"Orchestrator running (tick={TICK_INTERVAL_S}s) — Ctrl+C to stop")

    while running[0]:
        tick_start = time.time()
        step      += 1

        # 3a. Snapshot all nodes
        all_nodes  = store.all_nodes()
        curr_alive = {n.node_id for n in all_nodes if n.alive}
        newly_dead = list(prev_alive - curr_alive)
        prev_alive = curr_alive

        # Log node deaths as events
        for dead_id in newly_dead:
            add_event(f"Node {dead_id} died", "warning")

        # 3b. Energy watchdog
        # Virtual nodes: die when energy < 5% (simulation-controlled drain).
        # Real/Wokwi nodes: NEVER killed by the backend — their energy value
        # comes from actual hardware reporting. They stay alive until MQTT
        # stops reporting (stale timeout) or their reported energy hits 0.
        for node in all_nodes:
            if node.node_type in ("virtual",) and node.energy < 5.0 and node.alive:
                node.alive = False
                log.warning(
                    f"CRITICAL: Virtual node {node.node_id} died "
                    f"(low energy: {node.energy:.1f}%)"
                )

        store.check_stale_nodes(max_age_s=3600.0)

        # 3c. Re-freeze positions for newly arrived VIRTUAL nodes only.
        # Real hardware nodes get their position from MQTT — don't override it.
        for node_id, (x, y) in mesh_positions.items():
            if node_id.startswith("VNODE") or node_id == "SINK":
                if store.get(node_id) and node_id not in store._frozen_positions:
                    store.initialize_position(node_id, x, y)

        # 3d. Update environment & run cluster elections
        env_analyzer.tick(all_nodes)
        cluster_mgr.tick(all_nodes)

        # Collect CH change events BEFORE persisting cluster status
        new_ch_events = cluster_mgr.get_ch_change_events()
        for evt in new_ch_events:
            add_event(evt["message"], "ch_change")
            ch_events_accum.append(evt)
            if len(ch_events_accum) > 20:
                ch_events_accum.pop(0)

        # Persist: Save the new CH/Cluster status back to the store
        # (positions are already frozen — only is_ch and cluster_id change)
        for n in all_nodes:
            if n.cluster_id is not None:
                store.update_node_cluster_status(
                    n.node_id, n.cluster_id, n.is_ch
                )

        # 3e. Generate static mesh adjacency & rebuild graph
        # Adjacency comes from the static mesh — no runtime position reads
        hierarchical_adjacency = topology_mgr.get_hierarchical_adjacency(all_nodes)
        # Penalized edges: non-CH ↔ non-CH links get 50x cost so Dijkstra
        # always routes: source → CH → SINK  (CH-mandatory routing)
        penalized = topology_mgr.get_non_ch_edge_pairs(all_nodes)
        graph_engine.rebuild(
            all_nodes,
            weights=rl_ctrl.weights,
            adjacency=hierarchical_adjacency,
            penalized_edges=penalized,
        )

        # 3f. Compute best route SOURCE → SINK
        # Real hardware nodes are treated as ordinary mesh nodes — they
        # participate in routing like any virtual node: the source is randomly
        # chosen from ALL alive non-sink nodes. Real nodes get preferred
        # slightly by being added to the pool twice (higher sampling weight),
        # but virtual nodes still generate traffic so the full mesh is active.
        all_alive_nodes = [
            n for n in all_nodes if n.alive and n.node_id != SINK_NODE
        ]
        real_nodes = [
            n for n in all_alive_nodes if n.node_type in ("real", "wokwi")
        ]

        source = None
        if all_alive_nodes:
            # Build weighted pool: real nodes appear twice so they're
            # preferred as source but virtual traffic still flows.
            source_pool = [n.node_id for n in all_alive_nodes]
            for rn in real_nodes:
                source_pool.append(rn.node_id)  # double-weight for real nodes
            source = random.choice(source_pool)
            if real_nodes:
                log.debug(
                    f"Real node(s) present: {[n.node_id for n in real_nodes]}. "
                    f"Source selected: {source}"
                )

        path      = []
        delivered = False
        if source:
            decision  = router.make_routing_decision(source, SINK_NODE)
            path      = decision.path
            delivered = decision.success
            if path:
                log.info(
                    f"Route ({source} → SINK): "
                    f"{' → '.join(path)} (cost={decision.cost:.3f})"
                )
            else:
                log.warning(f"No path from {source} to {SINK_NODE}")

        # 3g. Check for congestion events
        for node in all_nodes:
            if (
                node.alive
                and node.load > 50
                and node.node_id != SINK_NODE
            ):
                add_event(
                    f"{node.node_id} congestion threshold exceeded "
                    f"(load={node.load})",
                    "warning",
                )

        # 3h. RL tick — observe outcome, update Q-table, get new weights
        # RL only affects routing costs (alpha..epsilon). Never positions.
        non_sink_nodes = [n for n in all_nodes if n.node_id != SINK_NODE]
        new_weights = rl_ctrl.tick(
            nodes=non_sink_nodes,
            newly_dead=newly_dead,
            packet_success=delivered,
            path=path,
        )

        # 3i. Update graph with new weights immediately
        graph_engine.update_edge_weights(new_weights, all_nodes)

        # 3j. Metrics
        metrics.update(
            nodes=all_nodes,
            step=step,
            path=path,
            delivered=delivered,
            weights=new_weights,
        )

        # 3k. Build full routing table
        routing_table = router.get_full_routing_table(SINK_NODE, all_nodes)

        # 3l. Collect rerouting events into event log
        for evt in router.get_recent_events():
            if evt not in event_log:
                event_log.append(evt)
        while len(event_log) > 50:
            event_log.pop(0)

        # 3m. Cloud sync (async) — mirror this tick's state to Firestore.
        # Only NEW reroute events (since last tick) are forwarded to the cloud.
        recent_reroutes = router.get_recent_events()
        new_reroutes = [e for e in recent_reroutes
                        if e.get("timestamp", 0) > last_reroute_ts]
        if recent_reroutes:
            last_reroute_ts = max(e.get("timestamp", 0) for e in recent_reroutes)

        snapshot = store.snapshot()
        cloud.sync(
            snapshot=snapshot,
            current_path=path,
            reroute_events=new_reroutes,
            rl_summary=rl_ctrl.rl_summary,
            cluster_heads=cluster_mgr.cluster_heads,
            step=step,
        )

        # 3n. Write state for dashboard
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
            "ch_events":     ch_events_accum[-10:],  # last 10 CH changes
            "cloud":         cloud.status(),
        })
        write_network_state(snapshot)

        if step % 10 == 0:
            m = metrics.summary()
            log.info(
                f"Step {step:4d} | Alive={store.alive_count()}/{store.count()} "
                f"| PDR={m['pdr']:.1f}% | Reroutes={m['rerouting_events']} "
                f"| Variance={m['energy_variance']:.1f} "
                f"| α={new_weights.get('alpha', 0):.2f} "
                f"β={new_weights.get('beta', 0):.2f}"
            )

        # Respect tick interval
        elapsed = time.time() - tick_start
        sleep_t = max(0.0, TICK_INTERVAL_S - elapsed)
        time.sleep(sleep_t)

    # ── Cleanup ──────────────────────────────────────────────────────────────
    sim.stop()
    mqtt.stop()
    cloud.stop()
    log.info(f"Backend stopped after {step} steps")
    log.info(f"Final metrics: {metrics.summary()}")


if __name__ == "__main__":
    main()
