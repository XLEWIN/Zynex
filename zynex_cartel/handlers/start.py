"""
ZYNEX CARTEL — /start Handler
Welcome, mandatory channel verification, registration.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from config import OWNER_ID, SUDO_USERS, GIVEAWAY_GROUP_ID, GIVEAWAY_CHANNEL_ID, MANDATORY_CHANNELS
from database import upsert_user, is_banned
from utils import E
from utils.keyboards import start_keyboard, verified_keyboard, main_menu_keyboard

logger = logging.getLogger("zynex.handlers.start")

# Mandatory channels — CHANNEL ONLY for voting (group not required)
MANDATORY_CH = [
    {"id": GIVEAWAY_CHANNEL_ID, "name": "Zynex Cartel Channel", "url": f"https://t.me/c/{str(GIVEAWAY_CHANNEL_ID).replace('-100', '')}"},
]


# ─── Help texts (shared by /help button + /help + /adminhelp) ────

def user_help_text() -> str:
    """Full user help — how to join and enter each giveaway type."""
    return (
        f"{E.INFO} <b>ZYNEX CARTEL — Help</b>\n"
        f"\n"
        f"{E.CROWN} <b>1. How to join</b>\n"
        f"• Open a private chat with this bot\n"
        f"• Send <code>/start</code>\n"
        f"• Join the required channel, then tap "
        f"<b>I've Joined</b>\n"
        f"• Wait for <b>Verification Successful</b>\n"
        f"\n"
        f"{E.GIFT} <b>2. Find a giveaway</b>\n"
        f"• <code>/active</code> — list live giveaways\n"
        f"• Watch the giveaway group for announcements\n"
        f"\n"
        f"{E.VOTE} <b>3. Enter — by type</b>\n"
        f"\n"
        f"<b>Vote giveaway</b> (DM only):\n"
        f"1. <code>/join [name]</code> — register your entry (max 10 chars)\n"
        f"2. Your post is created in the channel\n"
        f"3. Others press <b>Vote</b> on your post\n"
        f"4. Track yourself:\n"
        f"   • <code>/mystatus</code> — votes &amp; rank\n"
        f"   • <code>/leaderboard</code> — standings\n"
        f"   • <code>/mylink</code> — share your voting post\n"
        f"5. <code>/revoke</code> — leave (keeps existing votes)\n"
        f"\n"
        f"<b>Random giveaway:</b>\n"
        f"• Send any message in the giveaway group while it is live\n"
        f"\n"
        f"<b>Slot giveaway:</b>\n"
        f"• Send <code>🎰</code> (or the slot result) in the group\n"
        f"• Match <b>7 7 7</b> to win\n"
        f"\n"
        f"{E.SHIELD} <b>Rules</b>\n"
        f"• Stay in the required channel or votes may be removed\n"
        f"• One vote per user per giveaway\n"
        f"• Leaving and rejoining only re-votes for the same entry\n"
        f"\n"
        f"{E.INFO} <b>Commands</b>\n"
        f"<code>/start</code> — verify &amp; open menu\n"
        f"<code>/help</code> — this guide\n"
        f"<code>/active</code> — active giveaways\n"
        f"<code>/join [name]</code> — enter vote giveaway\n"
        f"<code>/revoke</code> — leave vote giveaway\n"
        f"<code>/mystatus</code> — your status &amp; rank\n"
        f"<code>/leaderboard</code> — vote rankings\n"
        f"<code>/mylink</code> — your channel voting link\n"
        f"\n"
        f"<b>ZYNEX CARTEL</b> {E.CROWN}"
    )


def admin_help_text() -> str:
    """Admin guide — how to create, run, and finish a giveaway."""
    return (
        f"{E.SHIELD} <b>ZYNEX CARTEL — Admin Guide</b>\n"
        f"\n"
        f"{E.GIVEAWAY} <b>Create a giveaway</b> (DM the bot)\n"
        f"1. <code>/sgive 1</code> — Vote\n"
        f"   <code>/sgive 2</code> — Random\n"
        f"   <code>/sgive 3</code> — Slot\n"
        f"2. Enter <b>name</b>\n"
        f"3. Enter <b>winner count</b>\n"
        f"4. Enter <b>start – end</b> times (IST)\n"
        f"   Example: <code>24/09/2026 18:00 - 20:00</code>\n"
        f"5. Tap <b>Confirm</b>\n"
        f"→ Auto-announces when it starts; auto-ends at finish\n"
        f"\n"
        f"{E.TROPHY} <b>Run &amp; finish</b>\n"
        f"<code>/active</code> — see what is live\n"
        f"<code>/select [id]</code> — target a giveaway (DM)\n"
        f"<code>/end</code> — end now &amp; pick winners\n"
        f"<code>/winner [userid]</code> — force a winner\n"
        f"<code>/cancel</code> — abort the /sgive wizard\n"
        f"\n"
        f"{E.VOTE} <b>Vote giveaway tools</b>\n"
        f"<code>/register [name]</code> — owner: add an entry\n"
        f"<code>/addvote [userid] [n]</code> — add votes\n"
        f"<code>/rmvote [userid] [n]</code> — remove votes\n"
        f"\n"
        f"{E.USERS} <b>Participants</b>\n"
        f"<code>/add [userid]</code> — add to giveaway\n"
        f"<code>/remove [userid]</code> — remove entry\n"
        f"<code>/ban [userid]</code> / <code>/unban [userid]</code>\n"
        f"\n"
        f"{E.LOCK} <b>Access &amp; process</b>\n"
        f"<code>/addsudo [userid]</code> / <code>/removesudo [userid]</code>\n"
        f"<code>/restart</code> — owner: restart bot process\n"
        f"<code>/adminhelp</code> — this guide\n"
        f"\n"
        f"{E.INFO} <b>Tips</b>\n"
        f"• Use Vote when members should campaign for entries\n"
        f"• Random = any group message while live\n"
        f"• Slot = send 🎰; triple 7 wins\n"
        f"• Winners are announced in the group + channel\n"
        f"\n"
        f"<b>ZYNEX CARTEL</b> {E.CROWN}"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    if not user:
        return

    user_id = user.id

    # Register user
    await upsert_user(
        user_id=user_id,
        username=user.username,
        first_name=user.first_name,
    )

    # Check ban
    if await is_banned(user_id):
        return  # Silently ignore banned users

    # Check mandatory channels
    not_joined = await _check_mandatory_channels(context.bot, user_id)

    if not_joined:
        # Show required channels
        text = (
            f"{E.CROWN} <b>Welcome to ZYNEX CARTEL!</b>\n"
            f"\n"
            f"{E.SHIELD} You must join the following channel to participate:\n"
        )
        for ch in MANDATORY_CH:
            text += f"\n{E.GROUP} <b>{ch['name']}</b>"

        text += (
            f"\n\n{E.LOCK} Join the channel and press the button below."
        )

        keyboard = start_keyboard(MANDATORY_CH)
    else:
        text = (
            f"{E.CROWN} <b>Welcome to ZYNEX CARTEL!</b>\n"
            f"\n"
            f"{E.SPARKLE} Your gateway to exciting giveaways!\n"
            f"\n"
            f"Choose an option below:"
        )
        keyboard = verified_keyboard()

    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def verify_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'I've Joined' button press."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    not_joined = await _check_mandatory_channels(context.bot, user_id)

    if not_joined:
        # Still missing channels
        text = (
            f"{E.WARNING} <b>Verification Failed</b>\n"
            f"\n"
            f"You haven't joined the required channel yet.\n"
            f"Please join the channel and try again."
        )
        await query.edit_message_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=start_keyboard(MANDATORY_CH),
        )
    else:
        # Verified!
        text = (
            f"{E.CHECK} <b>Verification Successful!</b>\n"
            f"\n"
            f"{E.SPARKLE} Welcome to ZYNEX CARTEL!\n"
            f"You now have access to all giveaways.\n"
            f"\n"
            f"Choose an option below:"
        )
        await query.edit_message_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=verified_keyboard(),
        )


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help button."""
    query = update.callback_query
    await query.answer()

    from utils.keyboards import main_menu_keyboard
    await query.edit_message_text(
        text=user_help_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )


async def show_active_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Active Giveaways' button."""
    query = update.callback_query
    await query.answer()

    # Redirect to /active command
    from handlers.active import active_command
    # We need to fake an update-like object
    await query.edit_message_text(
        text=f"{E.LIGHTNING} Loading active giveaways...",
        parse_mode=ParseMode.HTML,
    )
    # Actually fetch and display
    from database import get_all_active_giveaways
    from utils import format_ist, from_utc_iso, giveaway_type_name, giveaway_type_emoji, status_emoji
    from utils.keyboards import active_giveaways_keyboard

    giveaways = await get_all_active_giveaways()

    if not giveaways:
        await query.edit_message_text(
            text=f"{E.INFO} There are currently <b>no active giveaways</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(),
        )
        return

    text = f"{E.PARTY} <b>ACTIVE GIVEAWAYS</b>\n\n"
    for g in giveaways:
        gtype_emoji = giveaway_type_emoji(g["type"])
        status = status_emoji(g["status"])
        start = format_ist(from_utc_iso(g["start_time"]))
        end = format_ist(from_utc_iso(g["end_time"]))

        text += (
            f"{E.GIFT} <b>{g['name']}</b>\n"
            f"Type: {gtype_emoji} {giveaway_type_name(g['type'])}\n"
            f"Winners: {g['winner_count']}\n"
            f"Started: {start}\n"
            f"Ends: {end}\n"
            f"Status: {status} {g['status']}\n\n"
        )

    keyboard = active_giveaways_keyboard(giveaways)
    await query.edit_message_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def _check_mandatory_channels(bot, user_id: int) -> list:
    """Check which mandatory channels the user hasn't joined."""
    not_joined = []
    for ch in MANDATORY_CH:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ["left", "kicked", "banned"]:
                not_joined.append(ch)
        except Exception:
            # If we can't check, assume not joined
            not_joined.append(ch)
    return not_joined


async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /adminhelp command — admin only."""
    user_id = update.effective_user.id
    from utils.permissions import is_admin
    if not is_admin(user_id):
        return  # Silently ignore

    await update.message.reply_text(
        text=admin_help_text(),
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help — same content as the help button."""
    if not update.message:
        return
    from utils.keyboards import main_menu_keyboard

    await update.message.reply_text(
        text=user_help_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )


# Handler registration
def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("adminhelp", adminhelp_command))
    app.add_handler(CallbackQueryHandler(verify_membership_callback, pattern="^verify_membership$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^show_help$"))
    app.add_handler(CallbackQueryHandler(show_active_callback, pattern="^show_active$"))
