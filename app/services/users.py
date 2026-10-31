"""Who uses the bot: one SQLite row per user plus daily command counts, for /stats and /announce."""

import os
import sqlite3
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.utils.common import CACHE_DIR

DAY_SECONDS = 24 * 60 * 60
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    name         TEXT,
    username     TEXT,
    first_seen   INTEGER,           -- unix seconds; NULL for users carried over from before this table
    last_seen    INTEGER,
    interactions INTEGER NOT NULL DEFAULT 0,
    dm           INTEGER NOT NULL DEFAULT 0,  -- has a private chat with the bot, so announcements reach them
    blocked      INTEGER NOT NULL DEFAULT 0   -- the last announcement bounced: bot blocked or account gone
);
CREATE TABLE IF NOT EXISTS command_usage (
    day     TEXT NOT NULL,
    command TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, command)
);
"""


class UserStore:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)

    def record(self, user_id: int, name: str, username: str | None, private: bool,
               command: str | None = None, now: float | None = None) -> None:
        now = int(now if now is not None else time.time())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO users (user_id, name, username, first_seen, last_seen, interactions, dm)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    username = excluded.username,
                    first_seen = COALESCE(users.first_seen, excluded.first_seen),
                    last_seen = excluded.last_seen,
                    interactions = users.interactions + 1,
                    dm = MAX(users.dm, excluded.dm),
                    blocked = CASE WHEN excluded.dm = 1 THEN 0 ELSE users.blocked END
                """,
                (user_id, name, username, now, now, int(private)),
            )
            if command:
                self._conn.execute(
                    """
                    INSERT INTO command_usage (day, command, count) VALUES (?, ?, 1)
                    ON CONFLICT(day, command) DO UPDATE SET count = count + 1
                    """,
                    (_local_day(now), command),
                )

    def import_known(self, user_ids) -> int:
        """Add users known only from the old per-user settings file; returns how many were new."""
        with self._lock, self._conn:
            before = self._conn.total_changes
            self._conn.executemany(
                "INSERT OR IGNORE INTO users (user_id, dm) VALUES (?, 1)",
                [(int(user_id),) for user_id in user_ids],
            )
            return self._conn.total_changes - before

    def recipients(self) -> list[int]:
        with self._lock:
            rows = self._conn.execute("SELECT user_id FROM users WHERE dm = 1 AND blocked = 0").fetchall()
        return [row[0] for row in rows]

    def mark_blocked(self, user_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE users SET blocked = 1 WHERE user_id = ?", (user_id,))

    def stats(self, now: float | None = None) -> dict:
        now = int(now if now is not None else time.time())
        with self._lock:
            def count(where: str, *args) -> int:
                return self._conn.execute(f"SELECT COUNT(*) FROM users WHERE {where}", args).fetchone()[0]

            result = {
                "total": count("1"),
                "reachable": count("dm = 1 AND blocked = 0"),
                "blocked": count("blocked = 1"),
                "never_seen": count("last_seen IS NULL"),
                "new_7d": count("first_seen >= ?", now - 7 * DAY_SECONDS),
            }
            for days in (1, 7, 30):
                result[f"active_{days}d"] = count("last_seen >= ?", now - days * DAY_SECONDS)
            since = _local_day(now - 6 * DAY_SECONDS)
            result["top_commands_7d"] = self._conn.execute(
                "SELECT command, SUM(count) AS total FROM command_usage WHERE day >= ? "
                "GROUP BY command ORDER BY total DESC, command LIMIT 10",
                (since,),
            ).fetchall()
        return result


def _local_day(timestamp: float) -> str:
    zone = ZoneInfo(os.getenv("TIMEZONE", "Asia/Singapore"))
    return datetime.fromtimestamp(timestamp, zone).date().isoformat()


_store: UserStore | None = None


def get_store() -> UserStore:
    global _store
    if _store is None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        _store = UserStore(os.path.join(CACHE_DIR, "users.db"))
    return _store
