"""Small SQLite event store plus durable JSON records, one connection per process."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from packages.contracts import Event


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT, run_id TEXT, body TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS event_incident ON events(incident_id, sequence);
        CREATE INDEX IF NOT EXISTS event_run ON events(run_id, sequence);
        CREATE TABLE IF NOT EXISTS records (
            kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id)
        );
        """)
        self.db.commit()

    def emit(
        self,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        incident_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        event = Event(
            event_type=event_type,
            source=source,
            payload=payload,
            incident_id=incident_id,
            run_id=run_id,
        )
        cursor = self.db.execute(
            "INSERT INTO events(incident_id,run_id,body) VALUES(?,?,?)",
            (incident_id, run_id, event.model_dump_json()),
        )
        event.sequence = int(cursor.lastrowid or 0)
        self.db.commit()
        return event.model_dump()

    def events(
        self,
        after: int = 0,
        incident_id: str | None = None,
        run_id: str | None = None,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        query = "SELECT sequence, body FROM events WHERE sequence > ?"
        args: list[Any] = [after]
        for column, value in [("incident_id", incident_id), ("run_id", run_id)]:
            if value:
                query += f" AND {column} = ?"
                args.append(value)
        query += " ORDER BY sequence LIMIT ?"
        args.append(limit)
        return [dict(json.loads(body), sequence=seq) for seq, body in self.db.execute(query, args)]

    def trajectory(self, incident_id: str) -> list[dict[str, Any]]:
        return [
            dict(json.loads(body), sequence=seq)
            for seq, body in self.db.execute(
                "SELECT sequence,body FROM events WHERE incident_id=? ORDER BY sequence",
                (incident_id,),
            )
        ]

    def put(self, kind: str, key: str, value: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body",
            (kind, key, json.dumps(value)),
        )
        self.db.commit()

    def get(self, kind: str, key: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", (kind, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str) -> list[dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT body FROM records WHERE kind=? ORDER BY rowid DESC", (kind,)
            )
        ]

    def close(self) -> None:
        self.db.close()
