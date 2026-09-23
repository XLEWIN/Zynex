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

-- ═══ VOTE GIVEAWAY SYSTEM ═══

CREATE TABLE IF NOT EXISTS vote_participants (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    giveaway_id       INTEGER NOT NULL,
    participant_name  TEXT NOT NULL,
    telegram_user_id  INTEGER,
    owner_registered  INTEGER DEFAULT 0,
    user_votes        INTEGER DEFAULT 0,
    admin_votes       INTEGER DEFAULT 0,
    channel_message_id INTEGER,
    created_at        TEXT NOT NULL,
    revoked           INTEGER DEFAULT 0,
    UNIQUE (giveaway_id, participant_name),
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id)
);

CREATE TABLE IF NOT EXISTS vote_votes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    giveaway_id    INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    voter_user_id  INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL,
    revoked_at     TEXT,
    UNIQUE (giveaway_id, voter_user_id),
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id),
    FOREIGN KEY (participant_id) REFERENCES vote_participants(id)
);

CREATE TABLE IF NOT EXISTS vote_admin_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    giveaway_id    INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    admin_id       INTEGER NOT NULL,
    amount         INTEGER NOT NULL,
    action         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id),
    FOREIGN KEY (participant_id) REFERENCES vote_participants(id)
);
"""


async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA_SQL)
    # Indexes for participant commands (rank / page / user lookup)
    await db.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_vote_participants_giveaway
            ON vote_participants(giveaway_id);
        CREATE INDEX IF NOT EXISTS idx_vote_participants_user
            ON vote_participants(giveaway_id, telegram_user_id);
        CREATE INDEX IF NOT EXISTS idx_vote_votes_participant
            ON vote_votes(participant_id, status);
        CREATE INDEX IF NOT EXISTS idx_vote_votes_giveaway
            ON vote_votes(giveaway_id, status);
        """
    )
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
    # Use INSERT OR REPLACE — atomic, no UNIQUE constraint race
    await db.execute(
        """INSERT OR REPLACE INTO giveaway_winners
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


# ═══════════════════════════════════════════════════════════════════
# VOTE GIVEAWAY SYSTEM — Database Operations
# ═══════════════════════════════════════════════════════════════════

# ─── Vote Participant Operations ──────────────────────────────────

async def get_active_vote_giveaway() -> Optional[dict]:
    """Get the currently active vote-type giveaway (type=1)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM giveaways WHERE type = 1 AND status = 'ACTIVE' ORDER BY giveaway_id DESC LIMIT 1"
    )
    return await cursor.fetchone()


async def create_vote_participant(
    giveaway_id: int, participant_name: str,
    telegram_user_id: Optional[int] = None,
    owner_registered: bool = False,
) -> Optional[int]:
    """Create a vote participant. Returns participant_id or None if duplicate."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO vote_participants
               (giveaway_id, participant_name, telegram_user_id, owner_registered, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (giveaway_id, participant_name, telegram_user_id, int(owner_registered), utcnow()),
        )
        await db.commit()
        return cursor.lastrowid
    except aiosqlite.IntegrityError:
        return None


async def get_vote_participant_by_user(giveaway_id: int, user_id: int) -> Optional[dict]:
    """Get active participant by their Telegram user ID."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM vote_participants WHERE giveaway_id = ? AND telegram_user_id = ? AND revoked = 0",
        (giveaway_id, user_id),
    )
    return await cursor.fetchone()


async def get_vote_participant_by_id(participant_id: int) -> Optional[dict]:
    """Get participant by internal ID."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM vote_participants WHERE id = ?", (participant_id,)
    )
    return await cursor.fetchone()


async def get_vote_participant_by_name(giveaway_id: int, name: str) -> Optional[dict]:
    """Get active participant by name (case-insensitive)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM vote_participants WHERE giveaway_id = ? AND LOWER(participant_name) = LOWER(?) AND revoked = 0",
        (giveaway_id, name),
    )
    return await cursor.fetchone()


async def get_all_vote_participants(giveaway_id: int) -> list:
    """Get all active (non-revoked) participants for a giveaway."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM vote_participants WHERE giveaway_id = ? AND revoked = 0 ORDER BY id",
        (giveaway_id,),
    )
    return await cursor.fetchall()


async def revoke_vote_participant(participant_id: int):
    """Mark a participant as revoked."""
    db = await get_db()
    await db.execute(
        "UPDATE vote_participants SET revoked = 1 WHERE id = ?", (participant_id,)
    )
    await db.commit()


async def set_vote_channel_message(participant_id: int, message_id: int):
    """Store the channel message ID for a participant."""
    db = await get_db()
    await db.execute(
        "UPDATE vote_participants SET channel_message_id = ? WHERE id = ?",
        (message_id, participant_id),
    )
    await db.commit()


async def recalculate_vote_counts(participant_id: int):
    """Recalculate user_votes from active votes. admin_votes is untouched."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM vote_votes WHERE participant_id = ? AND status = 'active'",
        (participant_id,),
    )
    row = await cursor.fetchone()
    user_count = row[0] if row else 0
    await db.execute(
        "UPDATE vote_participants SET user_votes = ? WHERE id = ?",
        (user_count, participant_id),
    )
    await db.commit()


async def get_vote_total(participant_id: int) -> int:
    """Get total active votes from vote_votes table (source of truth)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM vote_votes WHERE participant_id = ? AND status = 'active'",
        (participant_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


# ─── Vote Casting Operations ──────────────────────────────────────

async def cast_vote(giveaway_id: int, participant_id: int, voter_user_id: int) -> bool:
    """Atomically cast a vote. Returns True on success, False if already voted.
    If a revoked vote exists for the SAME participant, reactivate it (rejoin case).
    """
    db = await get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")

        # Check existing vote
        cursor = await db.execute(
            "SELECT status, participant_id FROM vote_votes WHERE giveaway_id = ? AND voter_user_id = ?",
            (giveaway_id, voter_user_id),
        )
        existing = await cursor.fetchone()

        if existing:
            old_status = existing["status"]
            old_pid = existing["participant_id"]

            if old_status == "active":
                await db.execute("ROLLBACK")
                return False

            # Revoked vote — only reactivate if SAME participant
            if old_pid != participant_id:
                await db.execute("ROLLBACK")
                return False

            # Reactivate: same participant, user rejoined
            await db.execute(
                """UPDATE vote_votes
                   SET status = 'active', revoked_at = NULL, created_at = ?
                   WHERE giveaway_id = ? AND voter_user_id = ?""",
                (utcnow(), giveaway_id, voter_user_id),
            )
            await db.execute(
                "UPDATE vote_participants SET user_votes = user_votes + 1 WHERE id = ?",
                (participant_id,),
            )
            await db.execute("COMMIT")
            return True

        # No existing record — insert new vote
        await db.execute(
            """INSERT INTO vote_votes
               (giveaway_id, participant_id, voter_user_id, status, created_at)
               VALUES (?, ?, ?, 'active', ?)""",
            (giveaway_id, participant_id, voter_user_id, utcnow()),
        )
        await db.execute(
            "UPDATE vote_participants SET user_votes = user_votes + 1 WHERE id = ?",
            (participant_id,),
        )
        await db.execute("COMMIT")
        return True
    except aiosqlite.IntegrityError:
        await db.execute("ROLLBACK")
        return False
    except Exception:
        try:
            await db.execute("ROLLBACK")
        except Exception:
            pass
        raise


async def get_vote_record(giveaway_id: int, voter_user_id: int) -> Optional[dict]:
    """Get any vote record (active or revoked) for a user."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM vote_votes WHERE giveaway_id = ? AND voter_user_id = ?",
        (giveaway_id, voter_user_id),
    )
    return await cursor.fetchone()


async def has_user_voted(giveaway_id: int, voter_user_id: int) -> bool:
    """Check if a user has an ACTIVE vote."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM vote_votes WHERE giveaway_id = ? AND voter_user_id = ? AND status = 'active'",
        (giveaway_id, voter_user_id),
    )
    return await cursor.fetchone() is not None


async def get_active_vote_record(giveaway_id: int, voter_user_id: int) -> Optional[dict]:
    """Get the active vote record for a user."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM vote_votes WHERE giveaway_id = ? AND voter_user_id = ? AND status = 'active'",
        (giveaway_id, voter_user_id),
    )
    return await cursor.fetchone()


async def revoke_vote_by_voter(giveaway_id: int, voter_user_id: int) -> Optional[int]:
    """Revoke a vote (membership loss). Returns participant_id or None."""
    db = await get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "SELECT participant_id FROM vote_votes WHERE giveaway_id = ? AND voter_user_id = ? AND status = 'active'",
            (giveaway_id, voter_user_id),
        )
        row = await cursor.fetchone()
        if not row:
            await db.execute("ROLLBACK")
            return None

        pid = row[0]
        await db.execute(
            "UPDATE vote_votes SET status = 'revoked', revoked_at = ? WHERE giveaway_id = ? AND voter_user_id = ?",
            (utcnow(), giveaway_id, voter_user_id),
        )
        await db.execute(
            "UPDATE vote_participants SET user_votes = MAX(user_votes - 1, 0) WHERE id = ?",
            (pid,),
        )
        await db.execute("COMMIT")
        return pid
    except Exception:
        try:
            await db.execute("ROLLBACK")
        except Exception:
            pass
        raise


async def get_all_active_voter_ids(giveaway_id: int) -> list[int]:
    """Get all users with active votes for a giveaway."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT voter_user_id FROM vote_votes WHERE giveaway_id = ? AND status = 'active'",
        (giveaway_id,),
    )
    rows = await cursor.fetchall()
    return [row[0] for row in rows]


# ─── Admin Vote Operations ────────────────────────────────────────

# Admin votes use voter_user_id = -(admin_id * 1_000_000 + seq) to create real records
# without conflicting with the UNIQUE(giveaway_id, voter_user_id) constraint.

_admin_vote_seq = 0


async def admin_add_votes(participant_id: int, admin_id: int, giveaway_id: int, amount: int):
    """Add admin votes as REAL records in vote_votes."""
    global _admin_vote_seq
    db = await get_db()
    _admin_vote_seq += 1
    # Negative unique ID: -(admin_id * 1_000_000 + seq) — never collides with real users
    marker_voter_id = -(admin_id * 1_000_000 + _admin_vote_seq)

    for _ in range(amount):
        _admin_vote_seq += 1
        marker = -(admin_id * 1_000_000 + _admin_vote_seq)
        await db.execute(
            """INSERT INTO vote_votes
               (giveaway_id, participant_id, voter_user_id, status, created_at)
               VALUES (?, ?, ?, 'active', ?)""",
            (giveaway_id, participant_id, marker, utcnow()),
        )

    # Track on participant for admin audit
    await db.execute(
        "UPDATE vote_participants SET admin_votes = admin_votes + ? WHERE id = ?",
        (amount, participant_id),
    )
    # Recalculate user_votes from all active vote records
    await db.execute(
        "UPDATE vote_participants SET user_votes = (SELECT COUNT(*) FROM vote_votes WHERE participant_id = ? AND status = 'active') WHERE id = ?",
        (participant_id, participant_id),
    )
    await db.execute(
        """INSERT INTO vote_admin_logs
           (giveaway_id, participant_id, admin_id, amount, action, created_at)
           VALUES (?, ?, ?, ?, 'add', ?)""",
        (giveaway_id, participant_id, admin_id, amount, utcnow()),
    )
    await db.commit()


async def admin_remove_votes(participant_id: int, admin_id: int, giveaway_id: int, amount: int) -> int:
    """Remove admin votes. Clamps at 0. Returns actual amount removed."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT admin_votes FROM vote_participants WHERE id = ?", (participant_id,)
    )
    row = await cursor.fetchone()
    current = row[0] if row else 0
    actual = min(amount, current)

    if actual > 0:
        # Remove real admin vote records (negative voter IDs)
        cursor = await db.execute(
            """SELECT id FROM vote_votes
               WHERE giveaway_id = ? AND participant_id = ?
                 AND voter_user_id < 0 AND status = 'active'
               ORDER BY id DESC LIMIT ?""",
            (giveaway_id, participant_id, actual),
        )
        rows = await cursor.fetchall()
        ids = [r[0] for r in rows]
        if ids:
            placeholders = ",".join("?" * len(ids))
            await db.execute(
                f"DELETE FROM vote_votes WHERE id IN ({placeholders})",
                ids,
            )

        await db.execute(
            "UPDATE vote_participants SET admin_votes = MAX(admin_votes - ?, 0) WHERE id = ?",
            (actual, participant_id),
        )
        # Recalculate user_votes from remaining active vote records
        await db.execute(
            "UPDATE vote_participants SET user_votes = (SELECT COUNT(*) FROM vote_votes WHERE participant_id = ? AND status = 'active') WHERE id = ?",
            (participant_id, participant_id),
        )

    await db.execute(
        """INSERT INTO vote_admin_logs
           (giveaway_id, participant_id, admin_id, amount, action, created_at)
           VALUES (?, ?, ?, ?, 'remove', ?)""",
        (giveaway_id, participant_id, admin_id, actual, utcnow()),
    )
    await db.commit()
    return actual


async def get_participant_by_user_id(giveaway_id: int, telegram_user_id: int) -> Optional[dict]:
    """Find participant by their linked Telegram user ID."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM vote_participants WHERE giveaway_id = ? AND telegram_user_id = ? AND revoked = 0",
        (giveaway_id, telegram_user_id),
    )
    return await cursor.fetchone()


# ─── Leaderboard / Rank (participant commands) ────────────────────
# Competition ranking: same vote total = same rank; next rank skips
# (1, 1, 3). Deterministic tie-break for display order: earliest id.

LEADERBOARD_PAGE_SIZE = 10

_VOTE_RANKED_CTE = """
WITH ranked AS (
    SELECT
        p.id,
        p.participant_name,
        p.telegram_user_id,
        p.channel_message_id,
        COUNT(v.id) AS total_votes,
        RANK() OVER (ORDER BY COUNT(v.id) DESC) AS rank_num
    FROM vote_participants p
    LEFT JOIN vote_votes v
        ON v.participant_id = p.id AND v.status = 'active'
    WHERE p.giveaway_id = ? AND p.revoked = 0
    GROUP BY p.id
)
"""


async def count_vote_participants(giveaway_id: int) -> int:
    """Active (non-revoked) participant count for a vote giveaway."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM vote_participants WHERE giveaway_id = ? AND revoked = 0",
        (giveaway_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_vote_leaderboard_page(
    giveaway_id: int, page: int = 1, page_size: int = LEADERBOARD_PAGE_SIZE,
) -> list:
    """One page of competition-ranked leaderboard (fresh SQL, not cached)."""
    page = max(1, page)
    offset = (page - 1) * page_size
    db = await get_db()
    cursor = await db.execute(
        _VOTE_RANKED_CTE
        + """
        SELECT id, participant_name, telegram_user_id, channel_message_id,
               total_votes, rank_num
        FROM ranked
        ORDER BY total_votes DESC, id ASC
        LIMIT ? OFFSET ?
        """,
        (giveaway_id, page_size, offset),
    )
    return await cursor.fetchall()


async def get_participant_rank(giveaway_id: int, participant_id: int) -> Optional[dict]:
    """Competition rank + vote total for one participant in the giveaway."""
    db = await get_db()
    cursor = await db.execute(
        _VOTE_RANKED_CTE
        + """
        SELECT id, participant_name, total_votes, rank_num
        FROM ranked WHERE id = ?
        """,
        (giveaway_id, participant_id),
    )
    return await cursor.fetchone()


async def get_leaderboard_total_pages(
    giveaway_id: int, page_size: int = LEADERBOARD_PAGE_SIZE,
) -> int:
    total = await count_vote_participants(giveaway_id)
    if total <= 0:
        return 1
    return (total + page_size - 1) // page_size
