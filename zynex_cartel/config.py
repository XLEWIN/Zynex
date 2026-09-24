"""
ZYNEX CARTEL — Configuration Module
All bot settings loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Bot Credentials ───────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8991346662:AAF9Dj8YGqE-cjV1aHm7GBfmBo2x1X9BOIA")
OWNER_ID = int(os.getenv("OWNER_ID", "8301883098"))

# ─── Database ──────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "zynex_cartel.db")

# ─── Telegram Targets ──────────────────────────────────────────────
GIVEAWAY_GROUP_ID = int(os.getenv("GIVEAWAY_GROUP_ID", "-1003777955255"))
GIVEAWAY_CHANNEL_ID = int(os.getenv("GIVEAWAY_CHANNEL_ID", "-1004484790002"))
# Activity log channel (participation + vote events)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1004339460162"))

# ─── Timezone ──────────────────────────────────────────────────────
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

# ─── Sudo Users (comma-separated user IDs) ────────────────────────
_sudo_raw = os.getenv("SUDO_USERS", "")
SUDO_USERS: list[int] = [
    int(uid.strip()) for uid in _sudo_raw.split(",") if uid.strip().isdigit()
]

# ─── Mandatory Channels — channel ONLY for voting ─────────────────
# Group membership is NOT required to vote.
_mandatory_raw = os.getenv("MANDATORY_CHANNELS", "")
MANDATORY_CHANNELS: list[int] = [
    int(ch.strip()) for ch in _mandatory_raw.split(",") if ch.strip().isdigit()
]
# Default: giveaway channel only (group removed from mandate)
if not MANDATORY_CHANNELS:
    MANDATORY_CHANNELS = [GIVEAWAY_CHANNEL_ID]
else:
    # Drop any group id — only channels remain mandatory for voting
    MANDATORY_CHANNELS = [c for c in MANDATORY_CHANNELS if c != GIVEAWAY_GROUP_ID]

# ─── Giveaway Limits ──────────────────────────────────────────────
MAX_WINNERS = int(os.getenv("MAX_WINNERS", "10"))
MAX_GIVEAWAY_NAME_LEN = int(os.getenv("MAX_GIVEAWAY_NAME_LEN", "100"))
# Participant entry names: max 10 characters
MAX_PARTICIPANT_NAME_LEN = int(os.getenv("MAX_PARTICIPANT_NAME_LEN", "10"))

# ─── Giveaway Types ───────────────────────────────────────────────
class GiveawayType:
    VOTE = 1
    RANDOM = 2
    SLOT = 3

    NAMES = {1: "Vote Giveaway", 2: "Random Giveaway", 3: "Slot Giveaway"}
    EMOJIS = {1: "🗳️", 2: "🎲", 3: "🎰"}

# ─── Giveaway Status ──────────────────────────────────────────────
class GiveawayStatus:
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    ENDING = "ENDING"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"

# ─── Logging ───────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "zynex_cartel.log")
