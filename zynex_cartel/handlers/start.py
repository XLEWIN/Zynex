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

# Mandatory channels config — owner can modify
MANDATORY_CH = [
    {"id": GIVEAWAY_GROUP_ID, "name": "Zynex Cartel Group", "url": f"https://t.me/c/{str(GIVEAWAY_GROUP_ID).replace('-100', '')}"},
    {"id": GIVEAWAY_CHANNEL_ID, "name": "Zynex Cartel Channel", "url": f"https://t.me/c/{str(GIVEAWAY_CHANNEL_ID).replace('-100', '')}"},
]


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
            f"{E.SHIELD} You must join the following channels to participate:\n"
        )
        for ch in MANDATORY_CH:
            text += f"\n{E.GROUP} <b>{ch['name']}</b>"

        text += (
            f"\n\n{E.LOCK} Join all channels and press the button below."
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
            f"You haven't joined all required channels yet.\n"
            f"Please join all channels and try again."
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

    text = (
        f"{E.INFO} <b>ZYNEX CARTEL — Help</b>\n"
        f"\n"
        f"<b>User Commands:</b>\n"
        f"/start — Start the bot\n"
        f"/active — View active giveaways\n"
        f"/mystatus — Your vote status & rank\n"
        f"/leaderboard — Vote leaderboard (paginated)\n"
        f"/mylink — Direct link to your channel post\n"
        f"/join [name] — Register for the vote giveaway\n"
        f"/revoke — Leave the current vote giveaway\n"
        f"\n"
        f"<b>How to Participate:</b>\n"
        f"{E.GIVEAWAY} <b>Random:</b> Send any message in the giveaway group\n"
        f"{E.SLOT} <b>Slot:</b> Send the slot machine emoji in the giveaway group\n"
        f"{E.VOTE} <b>Vote:</b> Use the vote buttons\n"
        f"\n"
        f"<b>ZYNEX CARTEL</b> {E.CROWN}"
    )

    from utils.keyboards import main_menu_keyboard
    await query.edit_message_text(
        text=text,
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

    text = (
        f"{E.SHIELD} <b>ZYNEX CARTEL — Admin Commands</b>\n"
        f"\n"
        f"<b>Giveaway Management:</b>\n"
        f"/sgive [1/2/3] — Create giveaway (1=Vote, 2=Random, 3=Slot)\n"
        f"/end — End active giveaway\n"
        f"/winner [userid] — Override winner selection\n"
        f"\n"
        f"<b>Participant Management:</b>\n"
        f"/add [userid] — Add participant manually\n"
        f"/remove [userid] — Remove participant\n"
        f"/ban [userid] — Ban user from giveaways\n"
        f"/unban [userid] — Unban user\n"
        f"\n"
        f"<b>Access Control:</b>\n"
        f"/addsudo [userid] — Add sudo user\n"
        f"\n"
        f"<b>Process:</b>\n"
        f"/restart — Owner only: restart bot in terminal/Railway\n"
        f"\n"
        f"<b>ZYNEX CARTEL</b> {E.CROWN}"
    )

    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help — same content as the help button."""
    if not update.message:
        return
    from utils.keyboards import main_menu_keyboard

    text = (
        f"{E.INFO} <b>ZYNEX CARTEL — Help</b>\n"
        f"\n"
        f"<b>User Commands:</b>\n"
        f"/start — Start the bot\n"
        f"/active — View active giveaways\n"
        f"/mystatus — Your vote status & rank\n"
        f"/leaderboard — Vote leaderboard (paginated)\n"
        f"/mylink — Direct link to your channel post\n"
        f"/join [name] — Register for the vote giveaway\n"
        f"/revoke — Leave the current vote giveaway\n"
        f"\n"
        f"<b>How to Participate:</b>\n"
        f"{E.GIVEAWAY} <b>Random:</b> Send any message in the giveaway group\n"
        f"{E.SLOT} <b>Slot:</b> Send the slot machine emoji in the giveaway group\n"
        f"{E.VOTE} <b>Vote:</b> Use the vote buttons\n"
        f"\n"
        f"<b>ZYNEX CARTEL</b> {E.CROWN}"
    )
    await update.message.reply_text(
        text=text,
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
