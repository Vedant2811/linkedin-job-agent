import sqlite3
from datetime import datetime


class JobDatabase:
    def __init__(self, db_path: str = "seen_jobs.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    job_id     TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    title      TEXT,
                    company    TEXT
                )
            """)
            conn.commit()

    def is_seen(self, job_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            return result is not None

    def mark_seen(self, job_id: str, title: str = "", company: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO seen_jobs
                   (job_id, first_seen, title, company)
                   VALUES (?, ?, ?, ?)""",
                (job_id, datetime.now().isoformat(), title, company),
            )
            conn.commit()

    def seen_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM seen_jobs"
            ).fetchone()[0]
