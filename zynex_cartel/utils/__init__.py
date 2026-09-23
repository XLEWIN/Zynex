"""
ZYNEX CARTEL — Utility Functions
Emoji system, formatting, time helpers.

Emoji display uses the Robin-style custom Telegram emoji format:
<tg-emoji emoji-id="CUSTOM_EMOJI_ID">fallback</tg-emoji>

See emoji_packs.py for the full emoji system.
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import TIMEZONE, GiveawayType, GiveawayStatus

# Re-export E from emoji_packs for convenience
from emoji_packs import E, custom_emoji, get_emoji, get_emoji_text

logger = logging.getLogger("zynex.utils")

IST = timezone(timedelta(hours=5, minutes=30))


# ─── Time Helpers ─────────────────────────────────────────────────

def parse_ist_datetime(text: str) -> Optional[datetime]:
    """Parse IST datetime from various formats."""
    formats = [
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %I:%M %p",
        "%Y-%m-%d %I:%M %p",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text.strip(), fmt)
            return dt.replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def format_ist(dt: datetime) -> str:
    """Format datetime to IST display string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist_dt = dt.astimezone(IST)
    return ist_dt.strftime("%d %B %Y — %H:%M IST")


def format_ist_short(dt: datetime) -> str:
    """Short IST format."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist_dt = dt.astimezone(IST)
    return ist_dt.strftime("%d %b %Y — %H:%M IST")


def to_utc_iso(dt: datetime) -> str:
    """Convert to UTC ISO string for storage."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.isoformat()


def from_utc_iso(iso_str: str) -> datetime:
    """Parse UTC ISO string to datetime."""
    return datetime.fromisoformat(iso_str)


def is_expired(end_time_iso: str) -> bool:
    """Check if a giveaway end time has passed."""
    end_dt = from_utc_iso(end_time_iso)
    now = datetime.now(timezone.utc)
    return now >= end_dt


def is_started(start_time_iso: str) -> bool:
    """Check if a giveaway has started."""
    start_dt = from_utc_iso(start_time_iso)
    now = datetime.now(timezone.utc)
    return now >= start_dt


def time_remaining(end_time_iso: str) -> str:
    """Return human-readable time remaining."""
    end_dt = from_utc_iso(end_time_iso)
    now = datetime.now(timezone.utc)
    if now >= end_dt:
        return "Ended"
    diff = end_dt - now
    hours = int(diff.total_seconds() // 3600)
    minutes = int((diff.total_seconds() % 3600) // 60)
    if hours > 24:
        days = hours // 24
        hours = hours % 24
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


# ─── Display Helpers ──────────────────────────────────────────────

def giveaway_type_name(gtype: int) -> str:
    return GiveawayType.NAMES.get(gtype, "Unknown")


def giveaway_type_emoji(gtype: int) -> str:
    """Premium custom emoji for a giveaway type (HTML messages only)."""
    from emoji_packs import E
    mapping = {
        GiveawayType.VOTE: E.VOTE,
        GiveawayType.RANDOM: E.GIVEAWAY,
        GiveawayType.SLOT: E.SLOT,
    }
    return mapping.get(gtype, E.QUESTION)


def giveaway_type_emoji_plain(gtype: int) -> str:
    """Plain Unicode emoji for a giveaway type (inline buttons — no HTML)."""
    return GiveawayType.EMOJIS.get(gtype, "❓")


def status_emoji(status: str) -> str:
    """Premium custom emoji for a giveaway status (HTML messages only)."""
    from emoji_packs import E
    mapping = {
        GiveawayStatus.ACTIVE: E.CHECK,
        GiveawayStatus.SCHEDULED: E.CLOCK,
        GiveawayStatus.ENDED: E.CROSS,
        GiveawayStatus.CANCELLED: E.CROSS,
        GiveawayStatus.DRAFT: E.INFO,
        GiveawayStatus.ENDING: E.WARNING,
    }
    return mapping.get(status, E.QUESTION)


def mention_user(user_id: int, name: str = None) -> str:
    """Create a mention string for a user using HTML format."""
    if name:
        return f'<a href="tg://user?id={user_id}">{name}</a>'
    return f'<a href="tg://user?id={user_id}">User</a>'


def user_display(user_id: int, username: str = None, first_name: str = None) -> str:
    """Get best display name for a user using HTML format."""
    if username:
        return f"@{username}"
    if first_name:
        return f'<a href="tg://user?id={user_id}">{first_name}</a>'
    return f'<a href="tg://user?id={user_id}">User</a>'


def mask_user_id(user_id: int) -> str:
    """Partially mask a user ID for display."""
    s = str(user_id)
    if len(s) <= 4:
        return s
    return s[:3] + "****" + s[-2:]


# ─── Validation Helpers ───────────────────────────────────────────

def is_valid_user_id(text: str) -> bool:
    """Check if text is a valid Telegram user ID."""
    return text.isdigit() and len(text) >= 5


def parse_user_id(text: str) -> Optional[int]:
    """Parse a user ID from text. Handles @username and raw IDs."""
    text = text.strip()
    if text.startswith("@"):
        return None  # Can't resolve usernames server-side
    if text.isdigit():
        return int(text)
    return None


# ─── Message Helpers ──────────────────────────────────────────────

def chunk_text(text: str, max_len: int = 4096) -> list[str]:
    """Split text into Telegram message size chunks."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
