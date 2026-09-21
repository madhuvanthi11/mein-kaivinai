"""Persistence for everything that is *not* weather.

Weather is never stored: it is fetched live and would be stale the moment it
was written. What lives here is the workflow record -- alerts, the transition
audit log, ward subscriptions and the in-app inbox.

The default implementation is a JSON file guarded by a process lock, so the
project runs with no database to install. `Repository` is the seam: a Firestore
implementation can replace `JsonRepository` without any caller changing.

Collections
-----------
alerts              one document per alert/advisory, carrying its current state
alert_transitions   append-only audit log; every state change, who and when
subscriptions       citizen ward subscriptions for in-app delivery
notifications       per-recipient in-app inbox entries
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from .. import config

COLLECTIONS = ("alerts", "alert_transitions", "subscriptions", "notifications")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Repository:
    """Interface. Implement against Firestore to move off the JSON file."""

    def insert(self, collection: str, doc: dict) -> dict: raise NotImplementedError

    def update(self, collection: str, doc_id: str, patch: dict) -> dict: raise NotImplementedError

    def get(self, collection: str, doc_id: str) -> dict | None: raise NotImplementedError

    def query(self, collection: str, **equals) -> list: raise NotImplementedError

    def clear(self) -> None: raise NotImplementedError


class JsonRepository(Repository):
    backend = "json-file"

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._lock = threading.RLock()
        self._data = None

    # -- disk -----------------------------------------------------------------
    def _load(self) -> dict:
        if self._data is not None:
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = {}
        self._data = {c: list(raw.get(c, [])) for c in COLLECTIONS}
        return self._data

    def _flush(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            # A read-only filesystem must not take the API down. The request
            # still succeeds in memory; /api/status reports persistence state.
            self.degraded = True

    degraded = False

    # -- operations -----------------------------------------------------------
    def insert(self, collection: str, doc: dict) -> dict:
        with self._lock:
            data = self._load()
            data[collection].append(doc)
            self._flush()
            return doc

    def update(self, collection: str, doc_id: str, patch: dict) -> dict:
        with self._lock:
            data = self._load()
            for i, d in enumerate(data[collection]):
                if d.get("id") == doc_id:
                    merged = {**d, **patch}
                    data[collection][i] = merged
                    self._flush()
                    return merged
            raise KeyError(doc_id)

    def get(self, collection: str, doc_id: str) -> dict | None:
        with self._lock:
            return next((d for d in self._load()[collection] if d.get("id") == doc_id), None)

    def query(self, collection: str, **equals) -> list:
        with self._lock:
            out = []
            for d in self._load()[collection]:
                if all(d.get(k) == v for k, v in equals.items()):
                    out.append(d)
            return out

    def clear(self) -> None:
        with self._lock:
            self._data = {c: [] for c in COLLECTIONS}
            self._flush()

    def stats(self) -> dict:
        with self._lock:
            data = self._load()
            return {"backend": self.backend, "path": self.path,
                    "writable": not self.degraded,
                    "counts": {c: len(data[c]) for c in COLLECTIONS}}


repo: Repository = JsonRepository(config.STORE_PATH)


def status() -> dict:
    return repo.stats() if isinstance(repo, JsonRepository) else {"backend": "custom"}
