"""
ZYNEX CARTEL — Vote Giveaway Handlers
/join, /revoke (DM) · /register (owner) · /addvote, /rmvote (admin) · voting callback.
"""

import logging
import html
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
)
from telegram.constants import ParseMode, ChatType

from config import GIVEAWAY_CHANNEL_ID, GIVEAWAY_GROUP_ID, OWNER_ID
from database import (
    get_active_vote_giveaway,
    get_vote_participant_by_user,
    get_vote_participant_by_id,
    revoke_vote_participant,
    has_user_voted,
)
from utils.permissions import is_admin
from utils import E
from utils.keyboards import small_caps, BE
from engines.vote_giveaway_engine import (
    register_participant,
    process_vote,
    admin_adjust,
)

logger = logging.getLogger("zynex.handlers.vote_giveaway")


# ─── Helpers ──────────────────────────────────────────────────────

NO_GIVEAWAY = f"{E.CROSS} There is no active giveaway right now."

DM_ONLY = (
    f"{E.CROSS} This command can only be used in the bot's private messages.\n\n"
    "Open a chat with me and try again."
)


async def _require_active_giveaway() -> dict | None:
    return await get_active_vote_giveaway()


# ─── /join ────────────────────────────────────────────────────────

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register as a participant — DM only."""
    message = update.message
    if not message:
        return

    # DM only
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(DM_ONLY, parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    if not user:
        return

    # Active giveaway check
    giveaway = await _require_active_giveaway()
    if not giveaway:
        await message.reply_text(NO_GIVEAWAY, parse_mode=ParseMode.HTML)
        return

    # Argument check
    if not context.args:
        await message.reply_text(
            f"{E.CROSS} Usage: <code>/join [participant_name]</code>\n"
            f"{E.INFO} Name max: <b>10</b> characters.",
            parse_mode=ParseMode.HTML,
        )
        return

    participant_name = " ".join(context.args)
    gid = giveaway["giveaway_id"]

    bot = context.bot
    result = await register_participant(
        bot=bot,
        giveaway_id=gid,
        participant_name=participant_name,
        telegram_user_id=user.id,
        owner_registered=False,
    )

    if not result["success"]:
        if "errors" in result:
            for err in result["errors"]:
                await message.reply_text(err, parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(result["error"], parse_mode=ParseMode.HTML)
        return

    p = result["participant"]
    name = html.escape(p["participant_name"])

    reply = (
        f"{E.PARTY} <b>Giveaway Registration Successful!</b>\n\n"
        f"{E.PERSON} Participant: <b>{name}</b>\n"
        f"{E.VOTE} Votes: <code>0</code>\n\n"
        f"Your voting entry has been created successfully."
    )
    if not result.get("channel_ok"):
        reply += (
            f"\n\n{E.WARNING} Your channel post could not be created. "
            "An admin has been notified."
        )
        logger.warning(
            f"Channel message creation failed for participant {p['id']} "
            f"in giveaway {gid}"
        )

    await message.reply_text(reply, parse_mode=ParseMode.HTML)


# ─── /revoke ──────────────────────────────────────────────────────

async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove own participant registration — DM only. Does NOT remove votes."""
    message = update.message
    if not message:
        return

    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(DM_ONLY, parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    if not user:
        return

    giveaway = await _require_active_giveaway()
    if not giveaway:
        await message.reply_text(NO_GIVEAWAY, parse_mode=ParseMode.HTML)
        return

    gid = giveaway["giveaway_id"]
    participant = await get_vote_participant_by_user(gid, user.id)
    if not participant:
        await message.reply_text(
            f"{E.CROSS} You are not registered in this giveaway.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Revoke registration (vote history stays intact)
    await revoke_vote_participant(participant["id"])

    name = html.escape(participant["participant_name"])
    await message.reply_text(
        f"{E.CHECK} Your giveaway registration has been revoked.\n\n"
        f"Participant: <b>{name}</b>",
        parse_mode=ParseMode.HTML,
    )


# ─── /register (owner) ───────────────────────────────────────────

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: register participants directly. Unlimited."""
    message = update.message
    if not message:
        return

    user = update.effective_user
    if not user or user.id != OWNER_ID:
        return  # Silently ignore non-owners

    giveaway = await _require_active_giveaway()
    if not giveaway:
        await message.reply_text(NO_GIVEAWAY, parse_mode=ParseMode.HTML)
        return

    if not context.args:
        await message.reply_text(
            f"{E.CROSS} Usage: <code>/register [participant_name]</code>\n"
            f"{E.INFO} Name max: <b>10</b> characters.",
            parse_mode=ParseMode.HTML,
        )
        return

    participant_name = " ".join(context.args)
    gid = giveaway["giveaway_id"]

    result = await register_participant(
        bot=context.bot,
        giveaway_id=gid,
        participant_name=participant_name,
        telegram_user_id=None,
        owner_registered=True,
    )

    if not result["success"]:
        await message.reply_text(result["error"], parse_mode=ParseMode.HTML)
        return

    p = result["participant"]
    name = html.escape(p["participant_name"])
    await message.reply_text(
        f"{E.CHECK} Registered: <b>{name}</b>\n"
        f"{E.VOTE} Votes: <code>0</code>",
        parse_mode=ParseMode.HTML,
    )


# ─── /addvote ─────────────────────────────────────────────────────

async def addvote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: silently add votes to a participant. /addvote {userid} {amount}"""
    message = update.message
    if not message:
        return

    user = update.effective_user
    if not user or not is_admin(user.id):
        return  # Silently ignore

    if len(context.args) < 2:
        await message.reply_text(
            f"{E.CROSS} Usage: <code>/addvote [userid] [amount]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await message.reply_text(
            f"{E.CROSS} Both arguments must be numbers.",
            parse_mode=ParseMode.HTML,
        )
        return

    if amount <= 0:
        await message.reply_text(
            f"{E.CROSS} Amount must be a positive number.",
            parse_mode=ParseMode.HTML,
        )
        return

    giveaway = await _require_active_giveaway()
    if not giveaway:
        await message.reply_text(NO_GIVEAWAY, parse_mode=ParseMode.HTML)
        return

    result = await admin_adjust(
        bot=context.bot,
        giveaway_id=giveaway["giveaway_id"],
        telegram_user_id=target_id,
        amount=amount,
        admin_id=user.id,
        action="add",
    )

    if not result["success"]:
        await message.reply_text(result["error"], parse_mode=ParseMode.HTML)
        return

    name = html.escape(result["participant"]["participant_name"])
    await message.reply_text(
        f"{E.CHECK} Added <code>{result['amount']}</code> votes to <b>{name}</b>.\n"
        f"Total: <code>{result['total']}</code>",
        parse_mode=ParseMode.HTML,
    )


# ─── /rmvote ──────────────────────────────────────────────────────

async def rmvote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: silently remove votes from a participant. /rmvote {userid} {amount}"""
    message = update.message
    if not message:
        return

    user = update.effective_user
    if not user or not is_admin(user.id):
        return  # Silently ignore

    if len(context.args) < 2:
        await message.reply_text(
            f"{E.CROSS} Usage: <code>/rmvote [userid] [amount]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await message.reply_text(
            f"{E.CROSS} Both arguments must be numbers.",
            parse_mode=ParseMode.HTML,
        )
        return

    if amount <= 0:
        await message.reply_text(
            f"{E.CROSS} Amount must be a positive number.",
            parse_mode=ParseMode.HTML,
        )
        return

    giveaway = await _require_active_giveaway()
    if not giveaway:
        await message.reply_text(NO_GIVEAWAY, parse_mode=ParseMode.HTML)
        return

    result = await admin_adjust(
        bot=context.bot,
        giveaway_id=giveaway["giveaway_id"],
        telegram_user_id=target_id,
        amount=amount,
        admin_id=user.id,
        action="remove",
    )

    if not result["success"]:
        await message.reply_text(result["error"], parse_mode=ParseMode.HTML)
        return

    name = html.escape(result["participant"]["participant_name"])
    await message.reply_text(
        f"{E.CHECK} Removed <code>{result['amount']}</code> votes from <b>{name}</b>.\n"
        f"Total: <code>{result['total']}</code>",
        parse_mode=ParseMode.HTML,
    )


# ─── Vote Callback ────────────────────────────────────────────────

async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Vote Me inline button. Format: vgvote:{giveaway_id}:{participant_id}"""
    query = update.callback_query
    if not query:
        return

    data = query.data
    parts = data.split(":")
    if len(parts) != 3:
        await query.answer("Invalid callback data.", show_alert=True)
        return

    try:
        gid = int(parts[1])
        pid = int(parts[2])
    except ValueError:
        await query.answer("Invalid callback data.", show_alert=True)
        return

    voter_id = query.from_user.id

    # Process vote (validates everything)
    result = await process_vote(context.bot, gid, pid, voter_id)

    status = result["status"]

    if status == "success":
        # query.answer has no HTML — plain count only (no emojis per policy)
        await query.answer(
            f"Vote recorded. Count: {result['vote_count']}",
            show_alert=True,
        )
    elif status == "already_voted":
        # Spam protection — short answer, no alert spam on repeat
        await query.answer(result["message"], show_alert=True)
    else:
        await query.answer(result["message"], show_alert=True)


# ─── Registration ─────────────────────────────────────────────────

def register_vote_giveaway_handlers(app):
    """Register all vote giveaway handlers on the application."""
    app.add_handler(CommandHandler("join", join_command))
    app.add_handler(CommandHandler("revoke", revoke_command))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("addvote", addvote_command))
    app.add_handler(CommandHandler("rmvote", rmvote_command))
    app.add_handler(
        CallbackQueryHandler(vote_callback, pattern=r"^vgvote:\d+:\d+$")
    )
