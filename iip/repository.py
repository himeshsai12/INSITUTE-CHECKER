"""Local persistence, transactional request quotas and bounded research caching."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from iip.config import now_iso, today
from iip.models import Evidence, Institution


class LimitReached(RuntimeError):
    pass


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS institutions (id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS watchlist (institution_id TEXT PRIMARY KEY, added_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notes (institution_id TEXT PRIMARY KEY, note TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, institution_id TEXT, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS api_events (id TEXT PRIMARY KEY, day TEXT NOT NULL, provider TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_day ON api_events(day);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed_demo(self):
        from iip.sample_data import demo_institutions
        with self.connect() as db:
            if db.execute("SELECT 1 FROM metadata WHERE key='demo_initialized'").fetchone():
                return
            for institution in demo_institutions():
                db.execute("INSERT OR IGNORE INTO institutions VALUES (?,?,?)", (institution.id, institution.model_dump_json(), now_iso()))
            db.execute("INSERT INTO metadata VALUES ('demo_initialized','1')")

    def institutions(self):
        with self.connect() as db:
            return [Institution.model_validate_json(row[0]) for row in db.execute("SELECT payload FROM institutions ORDER BY id")]

    def get(self, institution_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM institutions WHERE id=?", (institution_id,)).fetchone()
        return Institution.model_validate_json(row[0]) if row else None

    def save_many(self, institutions, action="Profile imported"):
        with self.connect() as db:
            for institution in institutions:
                institution = Institution.model_validate(institution.model_dump())
                db.execute("INSERT INTO institutions VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at", (institution.id, institution.model_dump_json(), now_iso()))
                self._audit(db, institution.id, action, "Validated profile saved")

    def _audit(self, db, institution_id, action, detail):
        db.execute("INSERT INTO audit (institution_id,action,detail,created_at) VALUES (?,?,?,?)", (institution_id, action, detail, now_iso()))

    def add_evidence(self, institution_id, evidence):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM institutions WHERE id=?", (institution_id,)).fetchone()
            if not row:
                raise ValueError("Institution no longer exists.")
            data = json.loads(row[0])
            data["evidence"].append(evidence.model_dump(mode="json"))
            institution = Institution.model_validate(data)
            db.execute("UPDATE institutions SET payload=?, updated_at=? WHERE id=?", (institution.model_dump_json(), now_iso(), institution_id))
            self._audit(db, institution_id, "Evidence added", evidence.title)

    def review_evidence(self, institution_id, evidence_id, status, reviewer, note):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM institutions WHERE id=?", (institution_id,)).fetchone()
            if not row:
                raise ValueError("Institution no longer exists.")
            data = json.loads(row[0])
            evidence = next((e for e in data["evidence"] if e["id"] == evidence_id), None)
            if not evidence:
                raise ValueError("Evidence no longer exists.")
            previous = evidence["status"]
            evidence.update(status=status, reviewer=reviewer, reviewed_on=today().isoformat(), review_note=note)
            institution = Institution.model_validate(data)
            db.execute("UPDATE institutions SET payload=?,updated_at=? WHERE id=?", (institution.model_dump_json(), now_iso(), institution_id))
            self._audit(db, institution_id, "Evidence reviewed", f"{evidence_id}: {previous} → {status}. Reviewer: {reviewer}. {note}")

    def audit(self, institution_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT action,detail,created_at FROM audit WHERE institution_id=? ORDER BY id DESC LIMIT 100", (institution_id,))]

    def watched(self):
        with self.connect() as db:
            return {r[0] for r in db.execute("SELECT institution_id FROM watchlist")}

    def toggle_watch(self, institution_id):
        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM watchlist WHERE institution_id=?", (institution_id,)).fetchone()
            if exists:
                db.execute("DELETE FROM watchlist WHERE institution_id=?", (institution_id,))
            else:
                db.execute("INSERT INTO watchlist VALUES (?,?)", (institution_id, now_iso()))
        return not bool(exists)

    def note(self, institution_id):
        with self.connect() as db:
            row = db.execute("SELECT note FROM notes WHERE institution_id=?", (institution_id,)).fetchone()
            return row[0] if row else ""

    def save_note(self, institution_id, note):
        with self.connect() as db:
            db.execute("INSERT INTO notes VALUES (?,?,?) ON CONFLICT(institution_id) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at", (institution_id, note[:20000], now_iso()))
            self._audit(db, institution_id, "Diligence note saved", "Internal note updated")

    def cache_get(self, key):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM research_cache WHERE key=? AND expires_at>?", (key, time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def cache_set(self, key, payload, ttl_hours):
        with self.connect() as db:
            db.execute("DELETE FROM research_cache WHERE expires_at<=?", (time.time(),))
            db.execute("INSERT INTO research_cache VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at, created_at=excluded.created_at", (key, json.dumps(payload), time.time()+ttl_hours*3600, now_iso()))
            db.execute("DELETE FROM research_cache WHERE key NOT IN (SELECT key FROM research_cache ORDER BY created_at DESC LIMIT 200)")

    def clear_research_cache(self):
        with self.connect() as db:
            db.execute("DELETE FROM research_cache")

    def reserve_request(self, provider, kind, limit):
        event_id = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM api_events WHERE day=? AND kind!='cache'", (today().isoformat(),)).fetchone()[0]
            if count >= limit:
                raise LimitReached(f"Daily API request limit ({limit}) reached. Cached results remain available; the limit resets at midnight IST.")
            db.execute("INSERT INTO api_events (id,day,provider,kind,status,created_at) VALUES (?,?,?,?,?,?)", (event_id, today().isoformat(), provider, kind, "pending", now_iso()))
        return event_id

    def complete_request(self, event_id, status, usage=None):
        usage = usage or {}
        with self.connect() as db:
            db.execute("UPDATE api_events SET status=?,input_tokens=?,output_tokens=? WHERE id=?", (status, usage.get("input_tokens", 0), usage.get("output_tokens", 0), event_id))

    def cache_hit(self, provider):
        with self.connect() as db:
            db.execute("INSERT INTO api_events (id,day,provider,kind,status,created_at) VALUES (?,?,?,?,?,?)", (uuid4().hex, today().isoformat(), provider, "cache", "hit", now_iso()))

    def usage(self):
        with self.connect() as db:
            rows = list(db.execute("SELECT * FROM api_events WHERE day=?", (today().isoformat(),)))
        return {"requests": sum(r["kind"] != "cache" for r in rows), "cache_hits": sum(r["kind"] == "cache" for r in rows), "input_tokens": sum(r["input_tokens"] for r in rows), "output_tokens": sum(r["output_tokens"] for r in rows), "failed": sum(r["status"] == "error" for r in rows)}
