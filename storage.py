"""
storage.py
==========
Simple JSON-in-SQLite storage. Each flow stores a list of entries under its
own key. Mirrors the TBL Bot.set/get model so both versions behave the same.
"""

import json
import sqlite3
import threading


class Storage:
    def __init__(self, path: str = "ingress_bot.db"):
        self.path = path
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    # ── Low-level key/value ─────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        row = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value):
        self._conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    # ── List helpers (one bucket per flow) ──────────────────────────────────────

    def next_id(self, id_key: str) -> int:
        current = self.get(id_key, 0) + 1
        self.set(id_key, current)
        return current

    def append(self, store_key: str, entry: dict):
        items = self.get(store_key, [])
        items.append(entry)
        self.set(store_key, items)

    def list(self, store_key: str) -> list:
        return self.get(store_key, [])

    def update_status(self, store_key: str, entry_id: int, new_status: str) -> dict | None:
        items = self.get(store_key, [])
        for item in items:
            if item["id"] == entry_id:
                item["status"] = new_status
                self.set(store_key, items)
                return item
        return None
