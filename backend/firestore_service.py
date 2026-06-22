"""
backend/firestore_service.py
----------------------------
Thin, defensive wrapper around the Firebase Admin / Firestore client.

Responsibilities:
  * Lazy initialization of the Firebase app + Firestore client.
  * Automatic reconnect with backoff when the connection is down.
  * Synchronous single-document writes (called by the cloud_sync worker thread).
  * Graceful degradation: if `firebase-admin` is not installed or the
    service-account credentials are missing, the service stays in a
    DISABLED state and every write becomes a no-op. The rest of the WSN
    backend (simulation, MQTT, RL, routing, dashboard) is never affected.

This module deliberately performs only BLOCKING work. All asynchronous
queueing/batching lives in `cloud_sync.py`, which runs this on a dedicated
background thread so the main orchestration loop never blocks on the network.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from backend.utils import get_logger

log = get_logger("firestore")

# ─── Optional dependency: firebase-admin ───────────────────────────────────────
# Importing is wrapped so the backend runs even when the package is absent.
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    _FIREBASE_IMPORTED = True
except Exception as exc:  # ImportError or any transitive failure
    firebase_admin = None  # type: ignore
    credentials = None      # type: ignore
    firestore = None        # type: ignore
    _FIREBASE_IMPORTED = False
    _IMPORT_ERROR = exc

# Default location of the service-account file (backend/service-account.json).
DEFAULT_CREDENTIALS_PATH = Path(__file__).resolve().parent / "service-account.json"

# Unique name so multiple FirestoreService instances don't clash on the
# default Firebase app (also lets tests create/destroy freely).
_APP_NAME = "wsn-cloud-sync"


class FirestoreService:
    """
    Manages a single Firestore connection with reconnect support.

    Thread-safety: `write()` and `ensure_connected()` are guarded by an
    RLock so the worker thread and any status reader stay consistent.
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        project_id: Optional[str] = None,
        reconnect_interval_s: float = 10.0,
    ) -> None:
        self._credentials_path = Path(
            credentials_path
            or os.environ.get("FIRESTORE_CREDENTIALS")
            or DEFAULT_CREDENTIALS_PATH
        )
        self._project_id = project_id or os.environ.get("FIRESTORE_PROJECT_ID")
        self._reconnect_interval_s = reconnect_interval_s

        self._app = None
        self._client = None
        self._connected = False
        self._lock = threading.RLock()

        self._last_error: Optional[str] = None
        self._last_connect_attempt = 0.0

    # ─── Capability checks ────────────────────────────────────────────────────

    @property
    def library_available(self) -> bool:
        """True if the firebase-admin package imported successfully."""
        return _FIREBASE_IMPORTED

    @property
    def credentials_available(self) -> bool:
        """True if the service-account.json file exists on disk."""
        return self._credentials_path.is_file()

    @property
    def enabled(self) -> bool:
        """Cloud sync can only work if both library + credentials are present."""
        return self.library_available and self.credentials_available

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    @property
    def project_id(self) -> Optional[str]:
        return self._project_id

    # ─── Connection lifecycle ─────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Initialize the Firebase app + Firestore client.
        Returns True on success. Never raises — failures are recorded
        in `last_error` and reported via the return value.
        """
        with self._lock:
            if self._connected:
                return True

            self._last_connect_attempt = time.time()

            if not self.library_available:
                self._last_error = (
                    "firebase-admin not installed "
                    "(`pip install firebase-admin`)"
                )
                return False

            if not self.credentials_available:
                self._last_error = (
                    f"service account file not found: {self._credentials_path}"
                )
                return False

            try:
                cred = credentials.Certificate(str(self._credentials_path))
                # Reuse the named app across reconnects instead of leaking apps.
                try:
                    self._app = firebase_admin.get_app(_APP_NAME)
                except ValueError:
                    options = {"projectId": self._project_id} if self._project_id else None
                    self._app = firebase_admin.initialize_app(
                        cred, options, name=_APP_NAME
                    )

                self._client = firestore.client(self._app)
                # Resolve the effective project id for the dashboard.
                self._project_id = self._project_id or getattr(
                    self._app, "project_id", None
                ) or cred.project_id

                self._connected = True
                self._last_error = None
                log.info(
                    f"Firestore connected (project={self._project_id})"
                )
                return True
            except Exception as exc:  # noqa: BLE001 — must never crash backend
                self._connected = False
                self._last_error = f"connect failed: {exc}"
                log.warning(f"Firestore connection failed: {exc}")
                return False

    def ensure_connected(self) -> bool:
        """
        Best-effort reconnect, throttled by `reconnect_interval_s`.
        Safe to call frequently from the worker loop.
        """
        with self._lock:
            if self._connected:
                return True
            if not self.enabled:
                return False
            # Backoff: only retry every reconnect_interval_s.
            if (time.time() - self._last_connect_attempt) < self._reconnect_interval_s:
                return False
        return self.connect()

    def _mark_disconnected(self, error: str) -> None:
        with self._lock:
            self._connected = False
            self._last_error = error

    # ─── Writes ───────────────────────────────────────────────────────────────

    def write(self, collection: str, document: Dict[str, Any]) -> bool:
        """
        Synchronously write one document to `collection`.
        Returns True on success. On failure, flags the connection as down so
        `ensure_connected()` will attempt a reconnect on the next cycle.

        BLOCKING — must only be called from the cloud_sync worker thread.
        """
        if not self.ensure_connected():
            return False
        try:
            client = self._client
            if client is None:
                return False
            client.collection(collection).add(document)
            return True
        except Exception as exc:  # noqa: BLE001
            self._mark_disconnected(f"write failed: {exc}")
            log.warning(f"Firestore write to '{collection}' failed: {exc}")
            return False

    def server_timestamp(self):
        """Return a Firestore server timestamp sentinel, or wall-clock fallback."""
        if _FIREBASE_IMPORTED and firestore is not None:
            return firestore.SERVER_TIMESTAMP
        return time.time()

    # ─── Status (for dashboard / logging) ─────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        with self._lock:
            if not self.library_available:
                state = "library_missing"
            elif not self.credentials_available:
                state = "credentials_missing"
            elif self._connected:
                state = "connected"
            else:
                state = "disconnected"
            return {
                "state": state,
                "connected": self._connected,
                "enabled": self.enabled,
                "project_id": self._project_id,
                "credentials_path": str(self._credentials_path),
                "last_error": self._last_error,
            }
