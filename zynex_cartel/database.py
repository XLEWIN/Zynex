"""
ZYNEX CARTEL — Database Module
Async SQLite database with aiosqlite.
"""

import aiosqlite
import logging
from datetime import datetime, timezone
from typing import Optional

from config import DATABASE_URL

logger = logging.getLogger("zynex.database")

_db: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_URL)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _db.execute("PRAGMA busy_timeout=5000")
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Schema ────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    joined_at     TEXT NOT NULL,
    last_seen     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sudo_users (
    user_id   INTEGER PRIMARY KEY,
    added_by  INTEGER NOT NULL,
    added_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS banned_users (
    user_id   INTEGER PRIMARY KEY,
    banned_by INTEGER NOT NULL,
    banned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS giveaways (
    giveaway_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    type          INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'DRAFT',
    winner_count  INTEGER NOT NULL DEFAULT 1,
    start_time    TEXT NOT NULL,
    end_time      TEXT NOT NULL,
    group_id      INTEGER,
    channel_id    INTEGER,
    created_by    INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    ended_at      TEXT,
    announce_participation INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS giveaway_participants (
    giveaway_id  INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    joined_at    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    removed_by_admin INTEGER DEFAULT 0,
    removal_time TEXT,
    PRIMARY KEY (giveaway_id, user_id),
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id)
);

CREATE TABLE IF NOT EXISTS giveaway_votes (
    giveaway_id  INTEGER NOT NULL,
    voter_id     INTEGER NOT NULL,
    target_id    INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (giveaway_id, voter_id),
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id)
);

CREATE TABLE IF NOT EXISTS giveaway_winners (
    giveaway_id      INTEGER NOT NULL,
    user_id          INTEGER NOT NULL,
    position         INTEGER NOT NULL,
    selection_method TEXT NOT NULL,
    selected_at      TEXT NOT NULL,
    selected_by      INTEGER,
    PRIMARY KEY (giveaway_id, position),
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id)
);

CREATE TABLE IF NOT EXISTS slot_attempts (
    attempt_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    giveaway_id  INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    message_id   INTEGER,
    chat_id      INTEGER,
    result       TEXT NOT NULL,
    is_winner    INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id)
);

CREATE TABLE IF NOT EXISTS admin_overrides (
    override_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    giveaway_id    INTEGER NOT NULL,
    admin_id       INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    action         TEXT NOT NULL,
    metadata       TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id     INTEGER,
    action       TEXT NOT NULL,
    giveaway_id  INTEGER,
    target_user_id INTEGER,
    metadata     TEXT,
    previous_state TEXT,
    new_state    TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_winner_overrides (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    giveaway_id  INTEGER NOT NULL,
    admin_id     INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    position     INTEGER,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id)
);
"""


async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA_SQL)
    await db.commit()
    logger.info("Database initialized successfully.")


# ─── User Operations ───────────────────────────────────────────────

async def upsert_user(user_id: int, username: str = None, first_name: str = None):
    db = await get_db()
    now = utcnow()
    await db.execute(
        """INSERT INTO users (user_id, username, first_name, joined_at, last_seen)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               username = COALESCE(excluded.username, users.username),
               first_name = COALESCE(excluded.first_name, users.first_name),
               last_seen = excluded.last_seen""",
        (user_id, username, first_name, now, now),
    )
    await db.commit()


async def get_user(user_id: int):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return await cursor.fetchone()


# ─── Sudo Operations ──────────────────────────────────────────────

async def add_sudo(user_id: int, added_by: int):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO sudo_users (user_id, added_by, added_at) VALUES (?, ?, ?)",
        (user_id, added_by, utcnow()),
    )
    await db.commit()


async def remove_sudo(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM sudo_users WHERE user_id = ?", (user_id,))
    await db.commit()


async def is_sudo(user_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT 1 FROM sudo_users WHERE user_id = ?", (user_id,))
    return await cursor.fetchone() is not None


async def get_all_sudo():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM sudo_users")
    return await cursor.fetchall()


# ─── Ban Operations ───────────────────────────────────────────────

async def ban_user(user_id: int, banned_by: int):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO banned_users (user_id, banned_by, banned_at) VALUES (?, ?, ?)",
        (user_id, banned_by, utcnow()),
    )
    await db.commit()


async def unban_user(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
    await db.commit()


async def is_banned(user_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,))
    return await cursor.fetchone() is not None


# ─── Giveaway Operations ──────────────────────────────────────────

async def create_giveaway(
    name: str, giveaway_type: int, winner_count: int,
    start_time: str, end_time: str, group_id: int,
    channel_id: int, created_by: int
) -> int:
    db = await get_db()
    now = utcnow()
    cursor = await db.execute(
        """INSERT INTO giveaways
           (name, type, status, winner_count, start_time, end_time,
            group_id, channel_id, created_by, created_at)
           VALUES (?, ?, 'SCHEDULED', ?, ?, ?, ?, ?, ?, ?)""",
        (name, giveaway_type, winner_count, start_time, end_time,
         group_id, channel_id, created_by, now),
    )
    await db.commit()
    return cursor.lastrowid


async def update_giveaway_status(giveaway_id: int, status: str):
    db = await get_db()
    updates = {"status": status}
    if status == "ENDED":
        updates["ended_at"] = utcnow()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [giveaway_id]
    await db.execute(f"UPDATE giveaways SET {set_clause} WHERE giveaway_id = ?", values)
    await db.commit()


async def get_giveaway(giveaway_id: int):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM giveaways WHERE giveaway_id = ?", (giveaway_id,)
    )
    return await cursor.fetchone()


async def get_active_giveaways(group_id: int = None):
    db = await get_db()
    if group_id:
        cursor = await db.execute(
            "SELECT * FROM giveaways WHERE status = 'ACTIVE' AND group_id = ?",
            (group_id,),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM giveaways WHERE status = 'ACTIVE'"
        )
    return await cursor.fetchall()


async def get_scheduled_giveaways():
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM giveaways WHERE status = 'SCHEDULED'"
    )
    return await cursor.fetchall()


async def get_all_active_giveaways():
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM giveaways WHERE status IN ('ACTIVE', 'SCHEDULED')"
    )
    return await cursor.fetchall()


async def get_active_giveaway_for_group(group_id: int):
    """Get the currently active giveaway for a specific group."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM giveaways WHERE status = 'ACTIVE' AND group_id = ? ORDER BY giveaway_id DESC LIMIT 1",
        (group_id,),
    )
    return await cursor.fetchone()


# ─── Participant Operations ────────────────────────────────────────

async def add_participant(giveaway_id: int, user_id: int) -> bool:
    """Returns True if added, False if duplicate."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO giveaway_participants (giveaway_id, user_id, joined_at) VALUES (?, ?, ?)",
            (giveaway_id, user_id, utcnow()),
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_participant(giveaway_id: int, user_id: int, removed_by: int = 0):
    db = await get_db()
    await db.execute(
        """UPDATE giveaway_participants
           SET status = 'removed', removed_by_admin = ?, removal_time = ?
           WHERE giveaway_id = ? AND user_id = ?""",
        (removed_by, utcnow(), giveaway_id, user_id),
    )
    await db.commit()


async def is_participant(giveaway_id: int, user_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM giveaway_participants WHERE giveaway_id = ? AND user_id = ? AND status = 'active'",
        (giveaway_id, user_id),
    )
    return await cursor.fetchone() is not None


async def is_removed_from_giveaway(giveaway_id: int, user_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM giveaway_participants WHERE giveaway_id = ? AND user_id = ? AND status = 'removed'",
        (giveaway_id, user_id),
    )
    return await cursor.fetchone() is not None


async def get_participant_count(giveaway_id: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM giveaway_participants WHERE giveaway_id = ? AND status = 'active'",
        (giveaway_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_all_participants(giveaway_id: int):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM giveaway_participants WHERE giveaway_id = ? AND status = 'active'",
        (giveaway_id,),
    )
    return await cursor.fetchall()


# ─── Vote Operations ──────────────────────────────────────────────

async def add_vote(giveaway_id: int, voter_id: int, target_id: int) -> bool:
    """Returns True if vote cast, False if already voted."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO giveaway_votes (giveaway_id, voter_id, target_id, created_at) VALUES (?, ?, ?, ?)",
            (giveaway_id, voter_id, target_id, utcnow()),
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def has_voted(giveaway_id: int, voter_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM giveaway_votes WHERE giveaway_id = ? AND voter_id = ?",
        (giveaway_id, voter_id),
    )
    return await cursor.fetchone() is not None


async def get_vote_leaderboard(giveaway_id: int, limit: int = 10):
    db = await get_db()
    cursor = await db.execute(
        """SELECT target_id, COUNT(*) as vote_count
           FROM giveaway_votes WHERE giveaway_id = ?
           GROUP BY target_id ORDER BY vote_count DESC LIMIT ?""",
        (giveaway_id, limit),
    )
    return await cursor.fetchall()


async def get_vote_count(giveaway_id: int, target_id: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM giveaway_votes WHERE giveaway_id = ? AND target_id = ?",
        (giveaway_id, target_id),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def admin_adjust_votes(giveaway_id: int, target_id: int, delta: int, admin_id: int):
    """Add or remove votes for a user. delta can be positive or negative."""
    db = await get_db()
    now = utcnow()
    if delta > 0:
        for _ in range(delta):
            await db.execute(
                "INSERT INTO giveaway_votes (giveaway_id, voter_id, target_id, created_at) VALUES (?, ?, ?, ?)",
                (giveaway_id, admin_id, target_id, now),
            )
    elif delta < 0:
        # Remove votes (admin votes are used for removal tracking)
        abs_delta = abs(delta)
        cursor = await db.execute(
            "SELECT rowid FROM giveaway_votes WHERE giveaway_id = ? AND target_id = ? ORDER BY rowid DESC LIMIT ?",
            (giveaway_id, target_id, abs_delta),
        )
        rows = await cursor.fetchall()
        for row in rows:
            await db.execute("DELETE FROM giveaway_votes WHERE rowid = ?", (row[0],))
    await db.commit()


# ─── Winner Operations ────────────────────────────────────────────

async def add_winner(
    giveaway_id: int, user_id: int, position: int,
    selection_method: str, selected_by: int = None
):
    db = await get_db()
    # Delete existing winner at this position first to avoid UNIQUE constraint
    await db.execute(
        "DELETE FROM giveaway_winners WHERE giveaway_id = ? AND position = ?",
        (giveaway_id, position),
    )
    await db.execute(
        """INSERT INTO giveaway_winners
           (giveaway_id, user_id, position, selection_method, selected_at, selected_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (giveaway_id, user_id, position, selection_method, utcnow(), selected_by),
    )
    await db.commit()


async def get_winners(giveaway_id: int):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM giveaway_winners WHERE giveaway_id = ? ORDER BY position",
        (giveaway_id,),
    )
    return await cursor.fetchall()


async def get_winner_ids(giveaway_id: int) -> list[int]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT user_id FROM giveaway_winners WHERE giveaway_id = ? ORDER BY position",
        (giveaway_id,),
    )
    rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def is_winner(giveaway_id: int, user_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM giveaway_winners WHERE giveaway_id = ? AND user_id = ?",
        (giveaway_id, user_id),
    )
    return await cursor.fetchone() is not None


# ─── Slot Operations ──────────────────────────────────────────────

async def add_slot_attempt(
    giveaway_id: int, user_id: int, message_id: int,
    chat_id: int, result: str, is_winner: bool = False
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO slot_attempts
           (giveaway_id, user_id, message_id, chat_id, result, is_winner, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (giveaway_id, user_id, message_id, chat_id, result, int(is_winner), utcnow()),
    )
    await db.commit()
    return cursor.lastrowid


async def get_slot_winners_count(giveaway_id: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM slot_attempts WHERE giveaway_id = ? AND is_winner = 1",
        (giveaway_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def has_slot_winner(giveaway_id: int, user_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM slot_attempts WHERE giveaway_id = ? AND user_id = ? AND is_winner = 1",
        (giveaway_id, user_id),
    )
    return await cursor.fetchone() is not None


# ─── Admin Override Operations ────────────────────────────────────

async def add_admin_override(
    giveaway_id: int, admin_id: int, target_user_id: int, action: str, metadata: str = None
):
    db = await get_db()
    await db.execute(
        """INSERT INTO admin_overrides
           (giveaway_id, admin_id, target_user_id, action, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (giveaway_id, admin_id, target_user_id, action, metadata, utcnow()),
    )
    await db.commit()


async def get_admin_overrides(giveaway_id: int, action: str = None):
    db = await get_db()
    if action:
        cursor = await db.execute(
            "SELECT * FROM admin_overrides WHERE giveaway_id = ? AND action = ?",
            (giveaway_id, action),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM admin_overrides WHERE giveaway_id = ?", (giveaway_id,)
        )
    return await cursor.fetchall()


# ─── Admin Winner Override ────────────────────────────────────────

async def add_admin_winner_override(giveaway_id: int, admin_id: int, target_user_id: int):
    db = await get_db()
    await db.execute(
        """INSERT INTO admin_winner_overrides
           (giveaway_id, admin_id, target_user_id, created_at)
           VALUES (?, ?, ?, ?)""",
        (giveaway_id, admin_id, target_user_id, utcnow()),
    )
    await db.commit()


async def get_admin_winner_overrides(giveaway_id: int):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM admin_winner_overrides WHERE giveaway_id = ? ORDER BY id",
        (giveaway_id,),
    )
    return await cursor.fetchall()


async def clear_admin_winner_overrides(giveaway_id: int):
    db = await get_db()
    await db.execute(
        "DELETE FROM admin_winner_overrides WHERE giveaway_id = ?", (giveaway_id,)
    )
    await db.commit()


# ─── Audit Log ────────────────────────────────────────────────────

async def add_audit_log(
    action: str, admin_id: int = None, giveaway_id: int = None,
    target_user_id: int = None, metadata: str = None,
    previous_state: str = None, new_state: str = None
):
    db = await get_db()
    await db.execute(
        """INSERT INTO audit_logs
           (admin_id, action, giveaway_id, target_user_id, metadata,
            previous_state, new_state, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (admin_id, action, giveaway_id, target_user_id, metadata,
         previous_state, new_state, utcnow()),
    )
    await db.commit()
