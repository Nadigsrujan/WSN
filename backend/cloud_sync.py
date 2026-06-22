"""
backend/cloud_sync.py
---------------------
Asynchronous bridge between the WSN backend and Google Firestore.

The orchestration loop (backend/main.py) calls `CloudSync.sync(...)` once per
tick with a read-only snapshot of the current network state. CloudSync diffs
that against the previous tick, builds documents for the five Firestore
collections, and pushes them onto an in-memory queue. A dedicated daemon
thread drains the queue and performs the actual (blocking) Firestore writes
via `FirestoreService`.

Design guarantees (per project requirements):
  * Writes are ASYNCHRONOUS — the main loop only enqueues; it never blocks
    on the network, so dashboard/tick performance is unaffected.
  * Failures NEVER crash the system — every write is wrapped, and if Firestore
    is unreachable the items are dropped after the queue fills (bounded queue),
    while `FirestoreService` keeps attempting reconnects in the background.
  * The RL routing engine, MQTT pipeline, and topology code are untouched —
    CloudSync is purely a consumer of the existing snapshot dict.

Collections written:
  telemetry            — one doc per node per tick (energy/load/rssi/…)
  routing_events       — one doc per detected path change
  cluster_head_events  — one doc per CH election change
  rl_decisions         — one doc per RL action (state/action/reward)
  gateway_logs         — sync lifecycle events (connect/flush/error)
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional

from backend.firestore_service import FirestoreService
from backend.utils import get_logger

log = get_logger("cloud_sync")

# Collection names (kept as constants to avoid typos across the codebase).
COL_TELEMETRY = "telemetry"
COL_ROUTING = "routing_events"
COL_CLUSTER_HEAD = "cluster_head_events"
COL_RL = "rl_decisions"
COL_GATEWAY = "gateway_logs"

ALL_COLLECTIONS = [
    COL_TELEMETRY,
    COL_ROUTING,
    COL_CLUSTER_HEAD,
    COL_RL,
    COL_GATEWAY,
]


class CloudSync:
    """
    Diffs network snapshots and asynchronously mirrors them into Firestore.

    Usage:
        cloud = CloudSync(gateway_id="ESP32_REAL_1")
        cloud.start()
        ...
        cloud.sync(snapshot, routing_engine, rl_summary, cluster_heads)
        status = cloud.status()   # for the dashboard
        ...
        cloud.stop()
    """

    def __init__(
        self,
        gateway_id: str = "ESP32_REAL_1",
        firestore: Optional[FirestoreService] = None,
        max_queue: int = 5000,
        telemetry_every_n_ticks: int = 1,
    ) -> None:
        self.gateway_id = gateway_id
        self._fs = firestore or FirestoreService()
        self._queue: "queue.Queue[tuple[str, Dict[str, Any]]]" = queue.Queue(
            maxsize=max_queue
        )
        self._telemetry_every_n = max(1, telemetry_every_n_ticks)

        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.RLock()

        # Per-collection write counters (successful writes).
        self._counts: Dict[str, int] = {c: 0 for c in ALL_COLLECTIONS}
        self._dropped = 0           # items discarded because the queue was full
        self._failed = 0            # write attempts that failed
        self._last_sync_ts: Optional[float] = None  # last SUCCESSFUL write time

        # Diff state across ticks.
        self._prev_path: List[str] = []
        self._prev_cluster_heads: Dict[int, str] = {}
        self._prev_rl_step: Optional[int] = None

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Connect (best-effort) and start the background writer thread."""
        if self._running:
            return
        self._running = True
        # Attempt an initial connection; non-fatal if it fails.
        connected = self._fs.connect() if self._fs.enabled else False
        self._worker = threading.Thread(
            target=self._drain_loop, name="cloud-sync-writer", daemon=True
        )
        self._worker.start()

        if not self._fs.library_available:
            log.warning("Cloud sync disabled: firebase-admin not installed.")
        elif not self._fs.credentials_available:
            log.warning(
                "Cloud sync disabled: service-account.json not found in backend/."
            )
        elif connected:
            log.info("Cloud sync started — Firestore online.")
            self._enqueue(
                COL_GATEWAY,
                {"event": "Gateway Sync", "status": "Success",
                 "message": "Firestore connection established"},
            )
        else:
            log.warning("Cloud sync started — Firestore offline, will retry.")

    def stop(self) -> None:
        """Signal the worker to finish and wait briefly for a clean exit."""
        self._running = False
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3.0)

    # ─── Public sync entrypoint (called from main loop, non-blocking) ─────────

    def sync(
        self,
        snapshot: Dict[str, Any],
        current_path: List[str],
        reroute_events: List[Dict[str, Any]],
        rl_summary: Dict[str, Any],
        cluster_heads: Dict[int, str],
        step: int,
    ) -> None:
        """
        Enqueue Firestore documents derived from the current tick.
        Returns immediately; all network I/O happens on the worker thread.
        Any exception here is swallowed so the main loop can never be harmed.
        """
        if not self._fs.enabled:
            return
        try:
            self._collect_telemetry(snapshot, step)
            self._collect_routing(current_path, reroute_events)
            self._collect_cluster_heads(cluster_heads, snapshot)
            self._collect_rl(rl_summary)
        except Exception as exc:  # noqa: BLE001 — never propagate to main loop
            log.warning(f"cloud_sync.sync error (ignored): {exc}")

    # ─── Collectors (build documents + enqueue) ───────────────────────────────

    def _collect_telemetry(self, snapshot: Dict[str, Any], step: int) -> None:
        if step % self._telemetry_every_n != 0:
            return
        nodes = snapshot.get("nodes", {})
        for node_id, n in nodes.items():
            doc = {
                "node_id": node_id,
                "node_type": n.get("node_type"),
                "energy": n.get("energy"),
                "predicted_energy": n.get("predicted_energy"),
                "load": n.get("load"),
                "rssi": n.get("rssi"),
                "alive": n.get("alive"),
                "is_ch": n.get("is_ch"),
                "cluster_id": n.get("cluster_id"),
                "packets_sent": n.get("packets_sent"),
                "packets_received": n.get("packets_received"),
                "packets_dropped": n.get("packets_dropped"),
                "step": step,
                "gateway_id": self.gateway_id,
                "timestamp": self._fs.server_timestamp(),
            }
            self._enqueue(COL_TELEMETRY, doc)

    def _collect_routing(
        self, current_path: List[str], reroute_events: List[Dict[str, Any]]
    ) -> None:
        # Use routing engine's own reroute events when available (richest data).
        for evt in reroute_events:
            old_path = evt.get("old_path") or []
            new_path = evt.get("new_path") or []
            doc = {
                "old_path": " -> ".join(old_path),
                "new_path": " -> ".join(new_path),
                "reason": evt.get("reason", "RL re-optimization"),
                "timestamp": self._fs.server_timestamp(),
            }
            self._enqueue(COL_ROUTING, doc)

        # Fallback: detect a change even if the engine didn't emit an event.
        if not reroute_events and current_path and current_path != self._prev_path:
            if self._prev_path:
                self._enqueue(
                    COL_ROUTING,
                    {
                        "old_path": " -> ".join(self._prev_path),
                        "new_path": " -> ".join(current_path),
                        "reason": "Path change",
                        "timestamp": self._fs.server_timestamp(),
                    },
                )
        if current_path:
            self._prev_path = list(current_path)

    def _collect_cluster_heads(
        self, cluster_heads: Dict[int, str], snapshot: Dict[str, Any]
    ) -> None:
        for cluster_id, new_ch in cluster_heads.items():
            old_ch = self._prev_cluster_heads.get(cluster_id)
            if old_ch is not None and old_ch != new_ch:
                self._enqueue(
                    COL_CLUSTER_HEAD,
                    {
                        "cluster_id": cluster_id,
                        "old_ch": old_ch,
                        "new_ch": new_ch,
                        "reason": "Energy Optimization",
                        "timestamp": self._fs.server_timestamp(),
                    },
                )
        if cluster_heads:
            self._prev_cluster_heads = dict(cluster_heads)

    def _collect_rl(self, rl_summary: Dict[str, Any]) -> None:
        if not rl_summary:
            return
        rl_step = rl_summary.get("step")
        # Only write when the RL agent has actually advanced a step.
        if rl_step is None or rl_step == self._prev_rl_step:
            return
        self._prev_rl_step = rl_step

        recent = rl_summary.get("recent_rewards") or []
        reward = recent[-1] if recent else None
        doc = {
            "state": rl_summary.get("last_state"),
            "action": rl_summary.get("last_action"),
            "reward": reward,
            "epsilon": rl_summary.get("epsilon"),
            "weights": rl_summary.get("weights"),
            "step": rl_step,
            "timestamp": self._fs.server_timestamp(),
        }
        self._enqueue(COL_RL, doc)

    # ─── Queue plumbing ───────────────────────────────────────────────────────

    def _enqueue(self, collection: str, document: Dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((collection, document))
        except queue.Full:
            with self._lock:
                self._dropped += 1
            # Log sparingly to avoid flooding when offline for a long time.
            if self._dropped % 100 == 1:
                log.warning(
                    f"Cloud sync queue full — dropping documents "
                    f"(total dropped={self._dropped})"
                )

    def _drain_loop(self) -> None:
        """Background thread: pull items and write them to Firestore."""
        while self._running or not self._queue.empty():
            try:
                collection, document = self._queue.get(timeout=0.5)
            except queue.Empty:
                # Idle: opportunistically keep the connection warm.
                if self._fs.enabled:
                    self._fs.ensure_connected()
                continue

            ok = self._fs.write(collection, document)
            with self._lock:
                if ok:
                    self._counts[collection] = self._counts.get(collection, 0) + 1
                    self._last_sync_ts = time.time()
                else:
                    self._failed += 1
            self._queue.task_done()

    # ─── Status for the dashboard ─────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """JSON-serialisable cloud status block embedded in the dashboard snapshot."""
        fs = self._fs.status()
        with self._lock:
            counts = dict(self._counts)
            total = sum(counts.values())
            return {
                "provider": "Google Firestore",
                "project_id": fs.get("project_id"),
                "gateway_id": self.gateway_id,
                "enabled": fs.get("enabled", False),
                "connected": fs.get("connected", False),
                # Human-friendly status strings for the panel.
                "cloud_status": "Connected" if fs.get("connected") else (
                    "Disabled" if not fs.get("enabled") else "Reconnecting"
                ),
                "firestore_status": fs.get("state"),
                "counts": counts,
                "total_records": total,
                "queue_depth": self._queue.qsize(),
                "dropped": self._dropped,
                "failed": self._failed,
                "last_sync": self._last_sync_ts,
                "last_error": fs.get("last_error"),
            }
