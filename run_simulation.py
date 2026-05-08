"""
run_simulation.py
-----------------
Standalone simulation runner (no MQTT required).
Useful for testing routing + RL without real hardware.

Uses the deterministic MESH TOPOLOGY for proper multi-hop routing.

Usage:
    python run_simulation.py [--nodes N] [--steps S]

Runs N virtual nodes for S steps and prints a summary.
"""
import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.telemetry_store import TelemetryStore
from backend.graph_engine import GraphEngine
from backend.routing import RoutingEngine
from backend.rl import RLController
from backend.metrics import MetricsTracker
from simulation.network_sim import NetworkSimulator
from simulation.failure_injection import FailureInjector
from simulation.mesh_topology import (
    get_adjacency, get_all_positions, get_virtual_node_ids, validate_topology,
)
from backend.utils import get_logger, write_network_state

log = get_logger("run_simulation")

ESP32_NODE_ID = "ESP32_REAL_1"


def run(n_nodes: int = 10, n_steps: int = 100, tick_s: float = 0.5) -> None:
    # ── Load mesh topology ────────────────────────────────────────────────────
    mesh_positions = get_all_positions(esp32_id=ESP32_NODE_ID)
    mesh_adjacency = get_adjacency(esp32_id=ESP32_NODE_ID)
    virtual_ids = get_virtual_node_ids()

    try:
        validate_topology(mesh_adjacency)
    except AssertionError as e:
        log.error(f"Topology validation FAILED: {e}")
        sys.exit(1)

    n_virtual = len(virtual_ids)
    log.info(f"Standalone simulation: {n_virtual} mesh nodes, {n_steps} steps")

    store        = TelemetryStore()
    sim          = NetworkSimulator(
        store, n_virtual=n_virtual, tick_interval_s=tick_s,
        sink_position=mesh_positions["SINK"],
        mesh_positions={k: v for k, v in mesh_positions.items()
                        if k.startswith("VNODE")},
    )
    graph_engine = GraphEngine()
    router       = RoutingEngine(graph_engine)
    rl_ctrl      = RLController(total_nodes=n_virtual + 1)
    metrics      = MetricsTracker(total_nodes=n_virtual + 1)
    injector     = FailureInjector(sim.vnodes)

    sim.start()

    SINK = "SINK"
    event_log = []

    def add_event(msg, etype="info"):
        event = {"timestamp": time.time(), "type": etype, "message": msg}
        event_log.append(event)
        if len(event_log) > 50:
            event_log.pop(0)

    add_event("Simulation started — mesh topology loaded")

    for step in range(1, n_steps + 1):
        time.sleep(tick_s)

        all_nodes  = store.all_nodes()
        alive      = [n for n in all_nodes if n.alive]

        if not alive:
            log.warning("All nodes dead — stopping early")
            break

        source = next((n.node_id for n in alive if n.node_id != SINK), None)
        if not source:
            continue

        graph_engine.rebuild(all_nodes, weights=rl_ctrl.weights, adjacency=mesh_adjacency)
        decision  = router.make_routing_decision(source, SINK)
        new_weights = rl_ctrl.tick(
            nodes=all_nodes,
            newly_dead=[],
            packet_success=decision.success,
            path=decision.path,
        )
        graph_engine.update_edge_weights(new_weights, all_nodes)
        metrics.update(all_nodes, step, decision.path, decision.success, new_weights)

        # Build full routing table
        routing_table = router.get_full_routing_table(SINK, all_nodes)

        # Collect events
        for evt in router.get_recent_events():
            if evt not in event_log:
                event_log.append(evt)
        while len(event_log) > 50:
            event_log.pop(0)

        # Congestion detection
        for node in all_nodes:
            if node.alive and node.load > 50 and node.node_id != SINK:
                add_event(f"{node.node_id} congestion (load={node.load})", "warning")

        # Write state for dashboard
        snapshot = store.snapshot()
        snapshot.update({
            "current_path": decision.path,
            "alt_path":     router.last_alt_path,
            "rl":           rl_ctrl.rl_summary,
            "metrics":      metrics.summary(),
            "graph":        graph_engine.to_serialisable(),
            "newly_dead":   [],
            "source":       source,
            "sink":         SINK,
            "routing_table": routing_table,
            "event_log":    event_log[-30:],
        })
        write_network_state(snapshot)

        # Inject a random failure at step 40
        if step == 40:
            killed = injector.kill_weakest()
            if killed:
                add_event(f"Killed weakest node: {killed}", "warning")
                log.warning(f"[Experiment] Killed weakest node: {killed}")

        if step % 20 == 0:
            m = metrics.summary()
            log.info(
                f"Step {step:3d} | Alive={sim.alive_count}/{n_virtual} "
                f"| PDR={m['pdr']:.1f}% | Reroutes={m['rerouting_events']} "
                f"| Variance={m['energy_variance']:.1f}"
            )

    sim.stop()
    log.info("=" * 50)
    log.info("SIMULATION COMPLETE — Final Metrics")
    log.info("=" * 50)
    for k, v in metrics.summary().items():
        log.info(f"  {k:<25} = {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WSN Standalone Simulation")
    parser.add_argument("--nodes", type=int, default=10,  help="Number of virtual nodes")
    parser.add_argument("--steps", type=int, default=100, help="Number of simulation steps")
    parser.add_argument("--tick",  type=float, default=0.5, help="Tick interval in seconds")
    args = parser.parse_args()

    run(n_nodes=args.nodes, n_steps=args.steps, tick_s=args.tick)
