"""
SQLite document tracking database.
Stores processing status, compliance results, and audit trail for each PDF.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "docmatch.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    """Context manager for DB connections with WAL mode."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist, and add missing columns for schema evolution."""
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                pdf_path TEXT,
                json_path TEXT,
                status TEXT DEFAULT 'pending',
                pages INTEGER DEFAULT 0,
                ocr_started_at TEXT,
                ocr_completed_at TEXT,
                compliance_score REAL,
                compliance_status TEXT,
                missing_fields TEXT DEFAULT '[]',
                sanity_score REAL,
                sanity_status TEXT,
                sanity_issues TEXT DEFAULT '[]',
                sanity_full_results TEXT DEFAULT '{}',
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Auto-migrate: add any missing columns to existing tables
        existing_cols = {r[1] for r in db.execute("PRAGMA table_info(documents)").fetchall()}
        desired_cols = {
            "sanity_score": "REAL",
            "sanity_status": "TEXT",
            "sanity_issues": "TEXT DEFAULT '[]'",
            "sanity_full_results": "TEXT DEFAULT '{}'",
        }
        for col, typ in desired_cols.items():
            if col not in existing_cols:
                db.execute(f"ALTER TABLE documents ADD COLUMN {col} {typ}")

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename)
        """)


def upsert_document(filename: str, pdf_path: str = None, json_path: str = None) -> int:
    """Insert or update a document record. Returns the document id."""
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM documents WHERE filename = ?", (filename,)
        ).fetchone()
        if existing:
            doc_id = existing["id"]
            updates = ["updated_at = ?"]
            params = [_now()]
            if pdf_path:
                updates.append("pdf_path = ?")
                params.append(pdf_path)
            if json_path:
                updates.append("json_path = ?")
                params.append(json_path)
            params.append(doc_id)
            db.execute(
                f"UPDATE documents SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        else:
            cur = db.execute(
                "INSERT INTO documents (filename, pdf_path, json_path) VALUES (?, ?, ?)",
                (filename, pdf_path, json_path),
            )
            doc_id = cur.lastrowid
        return doc_id


def update_status(filename: str, status: str, **kwargs):
    """Update document status and optional fields."""
    with get_db() as db:
        sets = ["status = ?", "updated_at = ?"]
        params = [status, _now()]
        for key, val in kwargs.items():
            if key == "missing_fields" and isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            sets.append(f"{key} = ?")
            params.append(val)
        params.append(filename)
        db.execute(
            f"UPDATE documents SET {', '.join(sets)} WHERE filename = ?",
            params,
        )


def get_document(filename: str) -> dict | None:
    """Get a single document record."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM documents WHERE filename = ?", (filename,)
        ).fetchone()
        return dict(row) if row else None


def get_documents(status: str = None, limit: int = 100) -> list[dict]:
    """List documents, optionally filtered by status."""
    with get_db() as db:
        if status:
            rows = db.execute(
                "SELECT * FROM documents WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_pending_documents() -> list[dict]:
    """Get documents that need OCR processing."""
    return get_documents(status="pending")


def get_unprocessed_filenames(directory: Path) -> set[str]:
    """Return set of PDF basenames in directory not yet in the DB."""
    pdf_files = {p.stem for p in directory.glob("*.pdf")}
    with get_db() as db:
        rows = db.execute("SELECT filename FROM documents").fetchall()
        known = {r["filename"] for r in rows}
    return pdf_files - known


# Auto-initialize on import
init_db()
