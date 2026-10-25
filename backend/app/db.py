import sqlite3
import threading
from contextlib import contextmanager

from . import config

# Ledger rows are hash-chained, so writes must be serialised: two concurrent posts must not
# both read the same "previous hash". A single-process app makes a process lock sufficient.
WRITE_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS karigars(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT, language TEXT DEFAULT 'hi',
  pin TEXT NOT NULL, skills TEXT DEFAULT '', workshop TEXT DEFAULT '', active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, customer_name TEXT, customer_phone TEXT,
  item_type TEXT, design_category TEXT, occasion TEXT, occasion_date TEXT,
  status TEXT DEFAULT 'open', created_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, challan_no TEXT, order_id INTEGER,
  karigar_id INTEGER NOT NULL, item_type TEXT, design_category TEXT NOT NULL,
  purity_ppt INTEGER NOT NULL, agreed_wastage_bp INTEGER NOT NULL,
  wastage_policy TEXT DEFAULT 'agreed', making_paise_per_g INTEGER NOT NULL,
  due_date TEXT, status TEXT NOT NULL DEFAULT 'issued', progress_pct INTEGER DEFAULT 0,
  progress_at TEXT, issued_at TEXT, returned_at TEXT, settled_at TEXT
);
CREATE TABLE IF NOT EXISTS progress(
  id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, pct INTEGER, note TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS settlements(
  id INTEGER PRIMARY KEY, karigar_id INTEGER NOT NULL, job_id INTEGER, computed_json TEXT,
  wastage_credit_mg INTEGER, gold_net_mg INTEGER, making_paise INTEGER,
  status TEXT DEFAULT 'proposed', jeweller_ok INTEGER DEFAULT 0, karigar_ok INTEGER DEFAULT 0,
  karigar_comment TEXT, explanation TEXT, created_at TEXT, approved_at TEXT,
  paid_paise INTEGER DEFAULT 0, paid_at TEXT
);
CREATE TABLE IF NOT EXISTS entries(
  id INTEGER PRIMARY KEY, karigar_id INTEGER NOT NULL, job_id INTEGER, settlement_id INTEGER,
  kind TEXT NOT NULL, gross_mg INTEGER, purity_ppt INTEGER, fine_mg INTEGER DEFAULT 0,
  amount_paise INTEGER DEFAULT 0, note TEXT DEFAULT '', evidence TEXT, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL,
  jeweller_ack TEXT DEFAULT 'pending', karigar_ack TEXT DEFAULT 'pending',
  dispute_reason TEXT, claimed_gross_mg INTEGER, state TEXT DEFAULT 'active', superseded_by INTEGER
);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, entry_id INTEGER, settlement_id INTEGER, actor TEXT, action TEXT,
  detail TEXT, created_at TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_actions(
  id INTEGER PRIMARY KEY, dedupe_key TEXT UNIQUE, agent TEXT, kind TEXT, severity TEXT,
  title TEXT, detail TEXT, payload TEXT, requires_approval INTEGER DEFAULT 0,
  status TEXT DEFAULT 'open', source TEXT DEFAULT 'rules', created_at TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, karigar_id INTEGER, audience TEXT, to_name TEXT, direction TEXT,
  lang TEXT, text TEXT, related_job_id INTEGER, source TEXT DEFAULT 'template', created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_entries_karigar ON entries(karigar_id);
CREATE INDEX IF NOT EXISTS ix_entries_job ON entries(job_id);
CREATE INDEX IF NOT EXISTS ix_jobs_karigar ON jobs(karigar_id);
"""


def connect(path=None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    if str(path) != ":memory:":
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def write(conn: sqlite3.Connection):
    """Serialised write transaction: commit on success, roll back on error."""
    with WRITE_LOCK:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def one(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None
