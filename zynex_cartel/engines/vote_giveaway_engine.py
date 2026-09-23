"""
ZYNEX CARTEL — Vote Giveaway Engine
Complete vote giveaway system: registration, voting, anti-cheat, membership monitoring.
"""

import logging
import html
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import TelegramError

from config import GIVEAWAY_CHANNEL_ID, GIVEAWAY_GROUP_ID
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
)

logger = logging.getLogger("zynex.vote_engine")

# ─── Name Validation ──────────────────────────────────────────────

MAX_NAME_LEN = 32


def validate_name(raw: str) -> tuple[bool, str]:
    """Validate a participant name. Returns (ok, name_or_error)."""
    name = raw.strip()
    if not name:
        return False, "❌ Participant name cannot be empty."
    if len(name) > MAX_NAME_LEN:
        return False, f"❌ Name must be {MAX_NAME_LEN} characters or fewer."
    # Block control characters
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return False, "❌ Name contains invalid characters."
    # Escape HTML for safe rendering later
    return True, name


# ─── Membership Checker ───────────────────────────────────────────

async def check_membership(bot: Bot, user_id: int) -> dict:
    """Check channel and group membership. Never trusts API failures as 'member'.
    Returns {channel: bool, group: bool, channel_error: bool, group_error: bool}
    """
    result = {
        "channel": False, "group": False,
        "channel_error": False, "group_error": False,
    }

    # Channel check
    try:
        member = await bot.get_chat_member(chat_id=GIVEAWAY_CHANNEL_ID, user_id=user_id)
        result["channel"] = member.status not in (
            ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, "left", "kicked",
        )
    except TelegramError as e:
        logger.warning(f"Channel membership check failed for {user_id}: {e}")
        result["channel_error"] = True
        result["channel"] = False  # Fail safe

    # Group check
    try:
        member = await bot.get_chat_member(chat_id=GIVEAWAY_GROUP_ID, user_id=user_id)
        result["group"] = member.status not in (
            ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, "left", "kicked",
        )
    except TelegramError as e:
        logger.warning(f"Group membership check failed for {user_id}: {e}")
        result["group_error"] = True
        result["group"] = False  # Fail safe

    return result


def membership_messages(m: dict) -> list[str]:
    """Build user-facing membership error messages."""
    msgs = []
    if m["channel_error"]:
        msgs.append("❌ Could not verify channel membership. Please try again later.")
    elif not m["channel"]:
        msgs.append(
            "❌ You must join our channel before joining the giveaway.\n\n"
            "Please join the channel and try again."
        )
    if m["group_error"]:
        msgs.append("❌ Could not verify group membership. Please try again later.")
    elif not m["group"]:
        msgs.append(
            "❌ You must join our group before joining the giveaway.\n\n"
            "Please join the group and try again."
        )
    if not m["channel"] and not m["group"] and not m["channel_error"] and not m["group_error"]:
        msgs = [
            "❌ You must join both our channel and group before joining the giveaway.\n\n"
            "Please join both and try again."
        ]
    return msgs


# ─── Channel Message Builder ──────────────────────────────────────

def build_vote_button(participant_id: int, giveaway_id: int) -> InlineKeyboardMarkup:
    """Colored inline vote button."""
    from utils.keyboards import small_caps, BE
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🗳️ {small_caps('Vote Me')}",
            callback_data=f"vgvote:{giveaway_id}:{participant_id}",
        )],
    ])


def build_channel_message_text(name: str, total_votes: int) -> str:
    """Format the public voting message."""
    safe_name = html.escape(name)
    return f"👤 <b>{safe_name}</b> : <code>{total_votes}</code>"


async def update_channel_message(bot: Bot, participant: dict, giveaway_id: int) -> bool:
    """Edit the participant's channel message with the current vote count."""
    pid = participant["id"]
    msg_id = participant["channel_message_id"]
    if not msg_id:
        return False

    total = await get_vote_total(pid)
    text = build_channel_message_text(participant["participant_name"], total)

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
    text = build_channel_message_text(participant["participant_name"], 0)
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
    # Validate name
    ok, name_or_err = validate_name(participant_name)
    if not ok:
        return {"success": False, "error": name_or_err}

    name = name_or_err

    # Membership check (only for self-registration, not owner)
    if not owner_registered and telegram_user_id:
        m = await check_membership(bot, telegram_user_id)
        if not m["channel"] or not m["group"]:
            return {"success": False, "errors": membership_messages(m)}

    # Already registered check (by Telegram user ID)
    if telegram_user_id and not owner_registered:
        existing = await get_vote_participant_by_user(giveaway_id, telegram_user_id)
        if existing:
            return {
                "success": False,
                "error": (
                    "⚠️ You are already registered in this giveaway.\n\n"
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
                "❌ This participant name is already being used.\n"
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
                "❌ This participant name is already being used.\n"
                "Please choose another name."
            ),
        }

    participant = await get_vote_participant_by_id(pid)

    # Send channel message
    msg_ok = await create_channel_message(bot, participant, giveaway_id)

    return {
        "success": True,
        "participant": participant,
        "channel_ok": msg_ok,
    }


# ─── Vote Casting ─────────────────────────────────────────────────

async def process_vote(bot: Bot, giveaway_id: int, participant_id: int, voter_id: int) -> dict:
    """Process a vote with all validations. Returns {status, message, ...}."""
    # 1. Giveaway active?
    g = await get_active_vote_giveaway()
    if not g or g["giveaway_id"] != giveaway_id:
        return {"status": "ended", "message": "❌ This giveaway has ended."}

    # 2. Participant exists?
    participant = await get_vote_participant_by_id(participant_id)
    if not participant or participant["revoked"] or participant["giveaway_id"] != giveaway_id:
        return {"status": "invalid", "message": "❌ This participant no longer exists."}

    # 3. Membership check
    m = await check_membership(bot, voter_id)
    if m["channel_error"] or m["group_error"]:
        return {
            "status": "error",
            "message": "❌ Could not verify your membership. Please try again.",
        }
    if not m["channel"]:
        return {
            "status": "no_channel",
            "message": (
                "❌ You must join our channel before voting.\n\n"
                "Join the channel and then press Vote Me again."
            ),
        }
    if not m["group"]:
        return {
            "status": "no_group",
            "message": (
                "❌ You must join our group before voting.\n\n"
                "Join the group and then press Vote Me again."
            ),
        }

    # 4. Already voted? (checks active AND revoked — anti-cheat)
    if await has_user_voted(giveaway_id, voter_id):
        return {
            "status": "already_voted",
            "message": "⚠️ You have already used your vote in this giveaway.",
        }

    # 5. Cast vote (atomic, DB-level unique constraint)
    success = await cast_vote(giveaway_id, participant_id, voter_id)
    if not success:
        # Race condition — someone else voted at the same time
        return {
            "status": "already_voted",
            "message": "⚠️ You have already used your vote in this giveaway.",
        }

    # 6. Update channel message
    fresh = await get_vote_participant_by_id(participant_id)
    total = await get_vote_total(participant_id)
    await update_channel_message(bot, fresh, giveaway_id)

    safe_name = html.escape(fresh["participant_name"])
    return {
        "status": "success",
        "message": f"✅ You Have Successfully Voted {safe_name}!",
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

        # If user left channel OR group → revoke their vote
        if not m["channel"] or not m["group"]:
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
        result = update.chat_member or update.my_chat_member
        if not result:
            return []

        chat_id = update.chat.id
        user_id = result.new_chat_member.user.id
        new_status = result.new_chat_member.status

        # Only care about leaving the required channel or group
        relevant_chat = chat_id in (GIVEAWAY_CHANNEL_ID, GIVEAWAY_GROUP_ID)
        if not relevant_chat:
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
                    f"Vote revoked: user {user_id} left chat {chat_id} in giveaway {gid}"
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
    participant = await get_participant_by_user_id(giveaway_id, telegram_user_id)
    if not participant:
        return {"success": False, "error": "❌ No active participant found with that user ID."}

    if amount <= 0:
        return {"success": False, "error": "❌ Amount must be a positive number."}

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
