"""
ZYNEX CARTEL — Vote Giveaway Engine
Complete vote giveaway system: registration, voting, anti-cheat, membership monitoring.
"""

import logging
import html
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import TelegramError

from config import (
    GIVEAWAY_CHANNEL_ID,
    GIVEAWAY_GROUP_ID,
    LOG_CHANNEL_ID,
    MAX_PARTICIPANT_NAME_LEN,
)
from database import (
    get_active_vote_giveaway,
    create_vote_participant,
    get_vote_participant_by_user,
    get_vote_participant_by_id,
    get_vote_participant_by_name,
    get_all_vote_participants,
    revoke_vote_participant,
    set_vote_channel_message,
    recalculate_vote_counts,
    get_vote_total,
    cast_vote,
    has_user_voted,
    get_active_vote_record,
    revoke_vote_by_voter,
    get_all_active_voter_ids,
    admin_add_votes,
    admin_remove_votes,
    get_participant_by_user_id,
    utcnow,
    # Participant command services
    count_vote_participants,
    get_vote_leaderboard_page,
    get_participant_rank,
    get_leaderboard_total_pages,
    LEADERBOARD_PAGE_SIZE,
)

logger = logging.getLogger("zynex.vote_engine")

# ─── Name Validation ──────────────────────────────────────────────

MAX_NAME_LEN = MAX_PARTICIPANT_NAME_LEN  # 10 characters max


def validate_name(raw: str) -> tuple[bool, str]:
    """Validate a participant name. Returns (ok, name_or_error)."""
    from emoji_packs import E
    name = raw.strip()
    if not name:
        return False, f"{E.CROSS} Participant name cannot be empty."
    if len(name) > MAX_NAME_LEN:
        return False, f"{E.CROSS} Name must be {MAX_NAME_LEN} characters or fewer."
    # Block control characters
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return False, f"{E.CROSS} Name contains invalid characters."
    # Escape HTML for safe rendering later
    return True, name


# ─── Membership Checker — CHANNEL only (group not required) ──────

async def check_membership(bot: Bot, user_id: int) -> dict:
    """Check channel membership only.
    Returns {channel: bool, group: bool, channel_error: bool, group_error: bool}
    Group is always True (not required for voting).
    If the API fails (bot lacks permission etc), treat as PASS — we cannot prove non-membership.
    """
    result = {
        "channel": True, "group": True,
        "channel_error": False, "group_error": False,
    }

    # Channel check (required)
    try:
        member = await bot.get_chat_member(chat_id=GIVEAWAY_CHANNEL_ID, user_id=user_id)
        status = str(member.status).lower()
        if status in ("left", "banned", "kicked"):
            result["channel"] = False
    except TelegramError as e:
        # Cannot verify — do NOT block (fail open for membership)
        logger.warning(f"Channel membership check failed for {user_id}: {e}")
        result["channel_error"] = True
        result["channel"] = True  # Fail open

    # Group is NOT required for voting — always pass
    result["group"] = True

    return result


def membership_messages(m: dict) -> list[str]:
    """Build user-facing membership error messages (HTML — premium emojis).
    Only the channel is required; group messages are never emitted."""
    from emoji_packs import E
    msgs = []
    if m.get("channel_error"):
        msgs.append(f"{E.CROSS} Could not verify channel membership. Please try again later.")
    elif not m.get("channel"):
        msgs.append(
            f"{E.CROSS} You must join our channel before joining the giveaway.\n\n"
            "Please join the channel and try again."
        )
    return msgs


# ─── Channel Message Builder ──────────────────────────────────────

def build_vote_button(participant_id: int, giveaway_id: int) -> InlineKeyboardMarkup:
    """Colored inline vote button — native green/success style (Bot API 9.4+)."""
    from utils.keyboards import small_caps, btn_success, BE
    return InlineKeyboardMarkup([
        [btn_success(f"{BE.VOTE} Vote Me", f"vgvote:{giveaway_id}:{participant_id}")],
    ])


def build_channel_message_text(name: str, total_votes: int, user_id: int = None) -> str:
    """Format the public voting message.
    Layout matches requested style:
      Name: <name>
      ID: <telegram_user_id>
      Votes: <count>
    """
    safe_name = html.escape(name)
    lines = [
        f"Name: <b>{safe_name}</b>",
    ]
    if user_id is not None:
        lines.append(f"ID: <code>{user_id}</code>")
    lines.append(f"Votes: <code>{total_votes}</code>")
    return "\n".join(lines)


def _row_get(row, key, default=None):
    """Safe key access for sqlite3.Row or dict."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


async def send_activity_log(bot: Bot, text: str) -> None:
    """Send a participation/vote log line to the log channel. Fail-soft."""
    if not LOG_CHANNEL_ID:
        return
    try:
        await bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=ParseMode.HTML)
    except TelegramError as e:
        logger.warning(f"Failed to send activity log: {e}")


async def log_participation(bot: Bot, participant: dict, giveaway_id: int) -> None:
    """Log a new participant registration to the log channel."""
    name = html.escape(str(_row_get(participant, "participant_name", "?")))
    uid = _row_get(participant, "telegram_user_id") or "—"
    text = (
        f"<b>JOIN</b>\n"
        f"Name: <b>{name}</b>\n"
        f"ID: <code>{uid}</code>\n"
        f"Giveaway: <code>#{giveaway_id}</code>"
    )
    await send_activity_log(bot, text)


async def log_vote(bot: Bot, participant: dict, voter_id: int, total: int) -> None:
    """Log a cast vote to the log channel."""
    name = html.escape(str(_row_get(participant, "participant_name", "?")))
    pid = _row_get(participant, "telegram_user_id") or "—"
    text = (
        f"<b>VOTE</b>\n"
        f"Participant: <b>{name}</b>\n"
        f"Participant ID: <code>{pid}</code>\n"
        f"Voter ID: <code>{voter_id}</code>\n"
        f"Total votes: <code>{total}</code>"
    )
    await send_activity_log(bot, text)


async def update_channel_message(bot: Bot, participant: dict, giveaway_id: int) -> bool:
    """Edit the participant's channel message with the current vote count."""
    pid = participant["id"]
    msg_id = participant["channel_message_id"]
    if not msg_id:
        return False

    total = await get_vote_total(pid)
    uid = None
    try:
        uid = participant["telegram_user_id"]
    except (KeyError, IndexError, TypeError):
        uid = None
    text = build_channel_message_text(participant["participant_name"], total, uid)

    try:
        await bot.edit_message_text(
            chat_id=GIVEAWAY_CHANNEL_ID,
            message_id=msg_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=build_vote_button(pid, giveaway_id),
        )
        return True
    except TelegramError as e:
        # "message is not modified" is expected when count unchanged
        if "not modified" in str(e).lower():
            return True
        logger.warning(f"Failed to update channel message for participant {pid}: {e}")
        return False


async def create_channel_message(bot: Bot, participant: dict, giveaway_id: int) -> bool:
    """Send the initial voting message to the channel."""
    pid = participant["id"]
    uid = None
    try:
        uid = participant["telegram_user_id"]
    except (KeyError, IndexError, TypeError):
        uid = None
    text = build_channel_message_text(participant["participant_name"], 0, uid)
    try:
        msg = await bot.send_message(
            chat_id=GIVEAWAY_CHANNEL_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=build_vote_button(pid, giveaway_id),
        )
        await set_vote_channel_message(pid, msg.message_id)
        return True
    except TelegramError as e:
        logger.error(f"Failed to send channel message for participant {pid}: {e}")
        return False


# ─── Registration ─────────────────────────────────────────────────

async def register_participant(
    bot: Bot, giveaway_id: int, participant_name: str,
    telegram_user_id: int = None, owner_registered: bool = False,
) -> dict:
    """Register a participant. Returns {success, error?, participant?}."""
    from emoji_packs import E
    # Validate name
    ok, name_or_err = validate_name(participant_name)
    if not ok:
        return {"success": False, "error": name_or_err}

    name = name_or_err

    # Membership check (only for self-registration, not owner)
    # Channel is mandatory; group is NOT required for voting
    if not owner_registered and telegram_user_id:
        m = await check_membership(bot, telegram_user_id)
        if not m["channel"]:
            return {"success": False, "errors": membership_messages(m)}

    # Already registered check (by Telegram user ID)
    if telegram_user_id and not owner_registered:
        existing = await get_vote_participant_by_user(giveaway_id, telegram_user_id)
        if existing:
            return {
                "success": False,
                "error": (
                    f"{E.WARNING} You are already registered in this giveaway.\n\n"
                    f"Participant: {existing['participant_name']}\n\n"
                    "Use /revoke if you want to remove your registration."
                ),
            }

    # Duplicate name check
    existing_name = await get_vote_participant_by_name(giveaway_id, name)
    if existing_name:
        return {
            "success": False,
            "error": (
                f"{E.CROSS} This participant name is already being used.\n"
                "Please choose another name."
            ),
        }

    # Create participant
    pid = await create_vote_participant(
        giveaway_id=giveaway_id,
        participant_name=name,
        telegram_user_id=telegram_user_id,
        owner_registered=owner_registered,
    )
    if pid is None:
        return {
            "success": False,
            "error": (
                f"{E.CROSS} This participant name is already being used.\n"
                "Please choose another name."
            ),
        }

    participant = await get_vote_participant_by_id(pid)

    # Send channel message
    msg_ok = await create_channel_message(bot, participant, giveaway_id)

    # Activity log → log channel
    await log_participation(bot, participant, giveaway_id)

    return {
        "success": True,
        "participant": participant,
        "channel_ok": msg_ok,
    }


# ─── Vote Casting ─────────────────────────────────────────────────

async def process_vote(bot: Bot, giveaway_id: int, participant_id: int, voter_id: int) -> dict:
    """Process a vote with all validations. Returns {status, message, ...}.
    Messages go to query.answer — NO emojis per policy (plain text only)."""
    # 1. Giveaway active?
    g = await get_active_vote_giveaway()
    if not g or g["giveaway_id"] != giveaway_id:
        return {"status": "ended", "message": "This giveaway has ended."}

    # 2. Participant exists?
    participant = await get_vote_participant_by_id(participant_id)
    if not participant or participant["revoked"] or participant["giveaway_id"] != giveaway_id:
        return {"status": "invalid", "message": "This participant no longer exists."}

    # 3. Membership check — CHANNEL only (group not required)
    #    Fail open on API errors — cannot prove non-membership
    m = await check_membership(bot, voter_id)
    if not m["channel"]:
        return {
            "status": "no_channel",
            "message": "You must join our channel before voting. Join the channel and press Vote Me again.",
        }

    # 4. Vote history check
    #    - Active vote → block
    #    - Revoked vote (left group) → allow ONLY for the same participant
    from database import get_vote_record
    record = await get_vote_record(giveaway_id, voter_id)

    if record and record["status"] == "active":
        return {
            "status": "already_voted",
            "message": "You have already used your vote in this giveaway.",
        }

    if record and record["status"] == "revoked":
        # Can only re-vote for the SAME participant they originally voted for
        if record["participant_id"] != participant_id:
            return {
                "status": "wrong_participant",
                "message": "You can only vote for the same participant you voted for before.",
            }
        # Same participant — allow re-vote (will reactivate the existing row)

    # 5. Cast vote (atomic, DB-level unique constraint)
    success = await cast_vote(giveaway_id, participant_id, voter_id)
    if not success:
        # Race condition — someone else voted at the same time
        return {
            "status": "already_voted",
            "message": "You have already used your vote in this giveaway.",
        }

    # 6. Update channel message
    fresh = await get_vote_participant_by_id(participant_id)
    total = await get_vote_total(participant_id)
    await update_channel_message(bot, fresh, giveaway_id)

    # Activity log → log channel
    await log_vote(bot, fresh, voter_id, total)

    return {
        "status": "success",
        "message": "Vote recorded.",
        "vote_count": total,
        "participant_name": fresh["participant_name"],
    }


# ─── Membership Reconciliation (Periodic) ─────────────────────────

async def reconcile_votes(bot: Bot, giveaway_id: int) -> list[int]:
    """Check all active voters' membership and revoke invalid votes.
    Returns list of participant_ids whose counts changed."""
    voter_ids = await get_all_active_voter_ids(giveaway_id)
    changed_pids = []

    for vid in voter_ids:
        try:
            m = await check_membership(bot, vid)
        except Exception as e:
            logger.error(f"Reconciliation check failed for {vid}: {e}")
            continue

        # If user left the required CHANNEL → revoke their vote
        # (group leave is ignored — group is not mandatory for voting)
        if not m["channel"]:
            pid = await revoke_vote_by_voter(giveaway_id, vid)
            if pid and pid not in changed_pids:
                changed_pids.append(pid)

    # Update channel messages for changed participants
    for pid in changed_pids:
        participant = await get_vote_participant_by_id(pid)
        if participant:
            await update_channel_message(bot, participant, giveaway_id)

    if changed_pids:
        logger.info(
            f"Vote reconciliation: revoked {len(changed_pids)} votes in giveaway {giveaway_id}"
        )
    return changed_pids


# ─── Live Membership Update Handler ───────────────────────────────

async def handle_membership_update(bot: Bot, update) -> list[int]:
    """Process a chat_member update. If user left required chat, revoke their vote.
    Returns list of participant_ids affected."""
    try:
        # ChatMemberHandler puts data in update.chat_member or update.my_chat_member
        member_update = getattr(update, "chat_member", None) or getattr(update, "my_chat_member", None)
        if not member_update:
            return []

        chat = member_update.chat
        new_status = member_update.new_chat_member.status
        user_id = member_update.new_chat_member.user.id

        # Only care about leaving the required CHANNEL
        # (group leave does not revoke votes — group not required)
        if chat.id != GIVEAWAY_CHANNEL_ID:
            return []

        left = new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, "left", "kicked")
        if not left:
            return []

        # Find active vote giveaway
        g = await get_active_vote_giveaway()
        if not g:
            return []

        gid = g["giveaway_id"]
        if await has_user_voted(gid, user_id):
            pid = await revoke_vote_by_voter(gid, user_id)
            if pid:
                participant = await get_vote_participant_by_id(pid)
                if participant:
                    await update_channel_message(bot, participant, gid)
                logger.info(
                    f"Vote revoked: user {user_id} left chat {chat.id} in giveaway {gid}"
                )
                return [pid]

        return []
    except Exception as e:
        logger.error(f"Error handling membership update: {e}")
        return []


# ─── Admin Vote Adjustments ───────────────────────────────────────

async def admin_adjust(bot: Bot, giveaway_id: int, telegram_user_id: int,
                       amount: int, admin_id: int, action: str) -> dict:
    """Add or remove admin votes for a participant linked to a Telegram user ID."""
    from emoji_packs import E
    participant = await get_participant_by_user_id(giveaway_id, telegram_user_id)
    if not participant:
        return {"success": False, "error": f"{E.CROSS} No active participant found with that user ID."}

    if amount <= 0:
        return {"success": False, "error": f"{E.CROSS} Amount must be a positive number."}

    if action == "add":
        await admin_add_votes(participant["id"], admin_id, giveaway_id, amount)
        removed = amount
    else:  # remove
        removed = await admin_remove_votes(participant["id"], admin_id, giveaway_id, amount)

    # Update channel message
    fresh = await get_vote_participant_by_id(participant["id"])
    await update_channel_message(bot, fresh, giveaway_id)

    total = await get_vote_total(participant["id"])
    return {
        "success": True,
        "participant": fresh,
        "amount": removed,
        "total": total,
    }


# ─── Winner Selection ─────────────────────────────────────────────

async def select_vote_winners(giveaway_id: int, winner_count: int) -> list[dict]:
    """Select winners: participants with the most total votes.
    Strict ordering: 1st has most, 2nd has fewer than 1st, 3rd fewer than 2nd.
    Ties: only the earliest registered wins that position; next goes to lower count.
    Returns list of {user_id, name, position, selection_method, votes}."""
    participants = await get_all_vote_participants(giveaway_id)
    if not participants:
        return []

    # Build ranked list — only participants with a real Telegram user ID
    ranked = []
    for p in participants:
        if not p["telegram_user_id"]:
            continue  # Skip owner-created entries with no real user
        total = await get_vote_total(p["id"])
        ranked.append({
            "participant_id": p["id"],
            "name": p["participant_name"],
            "telegram_user_id": p["telegram_user_id"],
            "total_votes": total,
        })

    if not ranked:
        return []

    # Sort: most votes first, earliest registration breaks ties
    ranked.sort(key=lambda x: (-x["total_votes"], x["participant_id"]))

    # Strict ordering: each winner must have FEWER votes than the previous
    winners = []
    prev_votes = None
    for entry in ranked:
        if len(winners) >= winner_count:
            break
        # Skip if same votes as previous winner (must be strictly less)
        if prev_votes is not None and entry["total_votes"] >= prev_votes:
            continue
        # Must have at least 1 vote to win
        if entry["total_votes"] <= 0:
            continue
        winners.append({
            "user_id": entry["telegram_user_id"],
            "name": entry["name"],
            "position": len(winners) + 1,
            "selection_method": "VOTE",
            "votes": entry["total_votes"],
        })
        prev_votes = entry["total_votes"]

    return winners


# ─── Participant Command Services ─────────────────────────────────
# Shared by /mystatus, /leaderboard, /mylink — always scoped to active giveaway.

async def get_user_participant(giveaway_id: int, telegram_user_id: int) -> Optional[dict]:
    """Resolve current giveaway participant by Telegram user ID only."""
    return await get_vote_participant_by_user(giveaway_id, telegram_user_id)


async def get_user_rank_info(giveaway_id: int, participant_id: int) -> dict:
    """Fresh competition rank + vote total for a participant."""
    votes = await get_vote_total(participant_id)
    rank_row = await get_participant_rank(giveaway_id, participant_id)
    rank = int(rank_row["rank_num"]) if rank_row and rank_row["rank_num"] is not None else 1
    return {"votes": votes, "rank": rank, "total_votes": votes}


async def get_leaderboard_page(giveaway_id: int, page: int = 1) -> dict:
    """Paginated leaderboard page with page metadata (fresh DB query)."""
    page_size = LEADERBOARD_PAGE_SIZE
    total_pages = await get_leaderboard_total_pages(giveaway_id, page_size)
    page = max(1, min(page, total_pages))
    rows = await get_vote_leaderboard_page(giveaway_id, page, page_size)
    total = await count_vote_participants(giveaway_id)
    return {
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_participants": total,
        "rows": rows,
    }


def build_participant_message_link(
    channel_id: int,
    message_id: Optional[int],
    channel_username: Optional[str] = None,
) -> Optional[str]:
    """Direct link to a participant's channel voting message.

    Public channel:  https://t.me/{username}/{message_id}
    Private channel: https://t.me/c/{internal_id}/{message_id}  (members only)
    Returns None if no usable link can be built.
    """
    if not message_id:
        return None
    if channel_username:
        uname = channel_username.lstrip("@")
        if uname:
            return f"https://t.me/{uname}/{message_id}"
    if channel_id is not None:
        sid = str(channel_id)
        # Telegram private chat form: -100<id> → t.me/c/<id>/<msg>
        if sid.startswith("-100"):
            return f"https://t.me/c/{sid[4:]}/{message_id}"
        if sid.startswith("-"):
            return f"https://t.me/c/{sid.lstrip('-')}/{message_id}"
    return None


async def generate_participant_message_link(bot: Bot, participant: dict) -> Optional[str]:
    """Resolve channel username via API, then build the participant message URL."""
    msg_id = None
    if participant:
        try:
            msg_id = participant["channel_message_id"]
        except (KeyError, IndexError, TypeError):
            msg_id = None
    if not msg_id:
        return None

    username = None
    try:
        chat = await bot.get_chat(GIVEAWAY_CHANNEL_ID)
        username = getattr(chat, "username", None)
    except TelegramError as e:
        logger.warning(f"get_chat for channel link failed: {e}")

    return build_participant_message_link(
        GIVEAWAY_CHANNEL_ID, msg_id, channel_username=username,
    )
