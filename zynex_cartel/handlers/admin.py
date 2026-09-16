"""
ZYNEX CARTEL — Admin Commands Handler
/end, /winner, /add, /remove, /ban, /unban, /addsudo
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from config import OWNER_ID, GiveawayType, GiveawayStatus
from database import (
    get_active_giveaway_for_group, get_giveaway, update_giveaway_status,
    add_winner, add_participant, remove_participant, ban_user, unban_user,
    add_sudo, remove_sudo, add_admin_override, add_admin_winner_override,
    get_admin_winner_overrides, add_audit_log, is_banned, get_user,
    get_all_participants, clear_admin_winner_overrides
)
from utils import E, mention_user, user_display
from utils.permissions import sudo_only, is_admin, is_owner
from utils.announcements import AnnouncementManager
from engines.vote_engine import VoteGiveawayEngine
from engines.random_engine import RandomGiveawayEngine
from engines.slot_engine import SlotGiveawayEngine
from telegram import Bot

logger = logging.getLogger("zynex.handlers.admin")

# Global bot reference — set in main.py
_bot: Bot = None


def set_bot(bot: Bot):
    global _bot
    _bot = bot


async def _get_active_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the currently active giveaway for context."""
    # For DM commands, check if user has a selected giveaway
    if update.message.chat.type == "private":
        selected = context.user_data.get("selected_giveaway_id")
        if selected:
            return await get_giveaway(selected)
        # Try to find any active giveaway
        from database import get_active_giveaways
        active = await get_active_giveaways()
        return active[0] if active else None
    else:
        # Group context
        return await get_active_giveaway_for_group(update.message.chat.id)


@sudo_only
async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /end command — end the current active giveaway."""
    giveaway = await _get_active_giveaway(update, context)
    if not giveaway:
        await update.message.reply_text(
            f"{E.INFO} No active giveaway found."
        )
        return

    gid = giveaway["giveaway_id"]

    if giveaway["status"] == GiveawayStatus.ENDED:
        await update.message.reply_text(f"{E.INFO} This giveaway has already ended.")
        return

    # End the giveaway
    from scheduler import GiveawayScheduler
    scheduler = GiveawayScheduler(_bot)
    await scheduler._end_giveaway(giveaway)

    await update.message.reply_text(
        f"{E.CHECK} Giveaway <b>#{gid}</b> has been ended.",
        parse_mode=ParseMode.HTML,
    )


@sudo_only
async def winner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /winner [userid] — override a winner."""
    if not context.args:
        await update.message.reply_text(
            f"{E.INFO} Usage: <code>/winner [userid]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            f"{E.WARNING} Invalid user ID."
        )
        return

    giveaway = await _get_active_giveaway(update, context)
    if not giveaway:
        await update.message.reply_text(f"{E.INFO} No active giveaway found.")
        return

    gid = giveaway["giveaway_id"]

    # Check if target is banned
    if await is_banned(target_id):
        await update.message.reply_text(f"{E.WARNING} User is banned.")
        return

    # Check winner count limit
    winners = await get_admin_winner_overrides(gid)
    if len(winners) >= giveaway["winner_count"]:
        await update.message.reply_text(
            f"{E.WARNING} Winner count limit reached ({giveaway['winner_count']})."
        )
        return

    admin_id = update.effective_user.id

    # Add admin winner override
    await add_admin_winner_override(gid, admin_id, target_id)
    await add_audit_log(
        action="admin_winner_override",
        admin_id=admin_id,
        giveaway_id=gid,
        target_user_id=target_id,
    )

    # Also add as winner directly
    position = len(winners) + 1
    await add_winner(
        giveaway_id=gid,
        user_id=target_id,
        position=position,
        selection_method="ADMIN",
        selected_by=admin_id,
    )

    user = await get_user(target_id)
    display = user_display(target_id, user["username"] if user else None, user["first_name"] if user else None) if user else f"User {target_id}"

    await update.message.reply_text(
        f"{E.CHECK} {display} has been designated as <b>winner #{position}</b>.",
        parse_mode=ParseMode.HTML,
    )


@sudo_only
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add [userid] — add a participant."""
    if not context.args:
        await update.message.reply_text(
            f"{E.INFO} Usage: <code>/add [userid]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{E.WARNING} Invalid user ID.")
        return

    giveaway = await _get_active_giveaway(update, context)
    if not giveaway:
        await update.message.reply_text(f"{E.INFO} No active giveaway found.")
        return

    if await is_banned(target_id):
        await update.message.reply_text(f"{E.WARNING} User is banned.")
        return

    gid = giveaway["giveaway_id"]
    success = await add_participant(gid, target_id)

    if success:
        await add_audit_log(
            action="admin_add_participant",
            admin_id=update.effective_user.id,
            giveaway_id=gid,
            target_user_id=target_id,
        )
        await update.message.reply_text(
            f"{E.CHECK} User <code>{target_id}</code> added to giveaway <b>#{gid}</b>.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"{E.INFO} User is already participating."
        )


@sudo_only
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove [userid] — remove a participant."""
    if not context.args:
        await update.message.reply_text(
            f"{E.INFO} Usage: <code>/remove [userid]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{E.WARNING} Invalid user ID.")
        return

    giveaway = await _get_active_giveaway(update, context)
    if not giveaway:
        await update.message.reply_text(f"{E.INFO} No active giveaway found.")
        return

    gid = giveaway["giveaway_id"]
    admin_id = update.effective_user.id
    await remove_participant(gid, target_id, removed_by=admin_id)

    await add_audit_log(
        action="admin_remove_participant",
        admin_id=admin_id,
        giveaway_id=gid,
        target_user_id=target_id,
    )

    await update.message.reply_text(
        f"{E.CHECK} User <code>{target_id}</code> removed from giveaway <b>#{gid}</b>.",
        parse_mode=ParseMode.HTML,
    )


@sudo_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ban [userid] — permanently ban a user."""
    if not context.args:
        await update.message.reply_text(
            f"{E.INFO} Usage: <code>/ban [userid]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{E.WARNING} Invalid user ID.")
        return

    # Don't ban the owner
    if target_id == OWNER_ID:
        await update.message.reply_text(f"{E.WARNING} Cannot ban the bot owner.")
        return

    admin_id = update.effective_user.id
    await ban_user(target_id, admin_id)
    await add_audit_log(
        action="ban_user",
        admin_id=admin_id,
        target_user_id=target_id,
    )

    # Remove from active giveaways
    from database import get_active_giveaways
    active = await get_active_giveaways()
    for g in active:
        await remove_participant(g["giveaway_id"], target_id, removed_by=admin_id)

    await update.message.reply_text(
        f"{E.BAN} User <code>{target_id}</code> has been <b>permanently banned</b>.",
        parse_mode=ParseMode.HTML,
    )


@sudo_only
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unban [userid] — unban a user."""
    if not context.args:
        await update.message.reply_text(
            f"{E.INFO} Usage: <code>/unban [userid]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{E.WARNING} Invalid user ID.")
        return

    admin_id = update.effective_user.id
    await unban_user(target_id)
    await add_audit_log(
        action="unban_user",
        admin_id=admin_id,
        target_user_id=target_id,
    )

    await update.message.reply_text(
        f"{E.UNBAN} User <code>{target_id}</code> has been <b>unbanned</b>.",
        parse_mode=ParseMode.HTML,
    )


@sudo_only
async def addsudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addsudo [userid] — add a sudo user (owner only)."""
    if not is_owner(update.effective_user.id):
        return  # Silently ignore

    if not context.args:
        await update.message.reply_text(
            f"{E.INFO} Usage: <code>/addsudo [userid]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{E.WARNING} Invalid user ID.")
        return

    admin_id = update.effective_user.id
    await add_sudo(target_id, admin_id)
    await add_audit_log(
        action="add_sudo",
        admin_id=admin_id,
        target_user_id=target_id,
    )

    await update.message.reply_text(
        f"{E.SHIELD} User <code>{target_id}</code> has been added as <b>sudo</b>.",
        parse_mode=ParseMode.HTML,
    )


@sudo_only
async def removesudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removesudo [userid] — remove a sudo user (owner only)."""
    if not is_owner(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            f"{E.INFO} Usage: <code>/removesudo [userid]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{E.WARNING} Invalid user ID.")
        return

    admin_id = update.effective_user.id
    await remove_sudo(target_id)
    await add_audit_log(
        action="remove_sudo",
        admin_id=admin_id,
        target_user_id=target_id,
    )

    await update.message.reply_text(
        f"{E.SHIELD} User <code>{target_id}</code> has been removed from <b>sudo</b>.",
        parse_mode=ParseMode.HTML,
    )


@sudo_only
async def select_giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /select [giveaway_id] — select a giveaway for DM admin commands."""
    if update.message.chat.type != "private":
        return

    from database import get_all_active_giveaways
    active = await get_all_active_giveaways()

    if not active:
        await update.message.reply_text(f"{E.INFO} No active giveaways.")
        return

    if not context.args:
        # Show list
        text = f"{E.GIVEAWAY} <b>Select a giveaway:</b>\n\n"
        for g in active:
            text += f"/select <code>{g['giveaway_id']}</code> — {g['name']}\n"
        await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)
        return

    try:
        gid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{E.WARNING} Invalid ID.")
        return

    giveaway = await get_giveaway(gid)
    if not giveaway:
        await update.message.reply_text(f"{E.WARNING} Giveaway not found.")
        return

    context.user_data["selected_giveaway_id"] = gid
    await update.message.reply_text(
        f"{E.CHECK} Selected giveaway <b>#{gid}: {giveaway['name']}</b>",
        parse_mode=ParseMode.HTML,
    )


# Handler registration
def register_admin_handlers(app):
    app.add_handler(CommandHandler("end", end_command))
    app.add_handler(CommandHandler("winner", winner_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("remove", remove_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("addsudo", addsudo_command))
    app.add_handler(CommandHandler("removesudo", removesudo_command))
    app.add_handler(CommandHandler("select", select_giveaway_command))
