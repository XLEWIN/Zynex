"""
ZYNEX CARTEL — /active Handler
Show currently active giveaways.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from database import get_all_active_giveaways, get_participant_count
from utils import (
    E, format_ist, from_utc_iso, giveaway_type_name,
    giveaway_type_emoji, status_emoji, time_remaining
)
from utils.keyboards import active_giveaways_keyboard, giveaway_info_keyboard, main_menu_keyboard

logger = logging.getLogger("zynex.handlers.active")


async def active_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /active command."""
    giveaways = await get_all_active_giveaways()

    if not giveaways:
        text = f"{E.INFO} There are currently <b>no active giveaways</b>."
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
        )
        return

    text = f"{E.PARTY} <b>ZYNEX CARTEL — ACTIVE GIVEAWAYS</b>\n\n"

    for g in giveaways:
        gid = g["giveaway_id"]
        name = g["name"]
        gtype = g["type"]
        winners = g["winner_count"]
        start = format_ist(from_utc_iso(g["start_time"]))
        end = format_ist(from_utc_iso(g["end_time"]))
        status = g["status"]
        remaining = time_remaining(g["end_time"])

        count = await get_participant_count(gid)

        text += (
            f"{E.BULLET}\n"
            f"\n"
            f"{E.GIFT} <b>{name}</b>\n"
            f"\n"
            f"{giveaway_type_emoji(gtype)} Type: <b>{giveaway_type_name(gtype)}</b>\n"
            f"{E.WINNER} Winners: <code>{winners}</code>\n"
            f"{E.USERS} Participants: <code>{count}</code>\n"
            f"{E.CLOCK} Started: <b>{start}</b>\n"
            f"{E.HOURGLASS} Ends: <b>{end}</b>\n"
            f"\n"
            f"Status: {status_emoji(status)} <b>{status}</b>\n"
            f"Remaining: <b>{remaining}</b>\n"
        )

    text += f"\n{E.BULLET}\n"

    keyboard = active_giveaways_keyboard(giveaways)
    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def giveaway_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle giveaway info button press."""
    query = update.callback_query
    await query.answer()

    data = query.data
    # Pattern: giveaway_info_{gid}
    try:
        gid = int(data.split("_")[-1])
    except (ValueError, IndexError):
        return

    from database import get_giveaway
    giveaway = await get_giveaway(gid)
    if not giveaway:
        await query.edit_message_text(text=f"{E.CROSS} Giveaway not found.")
        return

    name = giveaway["name"]
    gtype = giveaway["type"]
    winners = giveaway["winner_count"]
    start = format_ist(from_utc_iso(giveaway["start_time"]))
    end = format_ist(from_utc_iso(giveaway["end_time"]))
    remaining = time_remaining(giveaway["end_time"])
    count = await get_participant_count(gid)

    text = (
        f"{E.GIFT} <b>{name}</b>\n"
        f"\n"
        f"{giveaway_type_emoji(gtype)} Type: <b>{giveaway_type_name(gtype)}</b>\n"
        f"{E.WINNER} Winners: <code>{winners}</code>\n"
        f"{E.USERS} Participants: <code>{count}</code>\n"
        f"{E.CLOCK} Started: <b>{start}</b>\n"
        f"{E.HOURGLASS} Ends: <b>{end}</b>\n"
        f"Remaining: <b>{remaining}</b>\n"
    )

    keyboard = giveaway_info_keyboard(gid, gtype)
    await query.edit_message_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def participant_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle participant count button."""
    query = update.callback_query
    await query.answer()

    data = query.data
    try:
        gid = int(data.split("_")[-1])
    except (ValueError, IndexError):
        return

    from database import get_giveaway
    giveaway = await get_giveaway(gid)
    if not giveaway:
        await query.answer("Giveaway not found.", show_alert=True)
        return

    count = await get_participant_count(gid)
    await query.answer(
        f"{giveaway['name']}: {count} participants",
        show_alert=True,
    )


# Handler registration
def register_active_handlers(app):
    app.add_handler(CommandHandler("active", active_command))
    app.add_handler(CallbackQueryHandler(giveaway_info_callback, pattern=r"^giveaway_info_\d+$"))
    app.add_handler(CallbackQueryHandler(participant_count_callback, pattern=r"^participant_count_\d+$"))
