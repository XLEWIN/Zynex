"""
ZYNEX CARTEL — /sgive Handler
Interactive giveaway creation wizard.
"""

import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ConversationHandler
)
from telegram.constants import ParseMode

from config import GiveawayType, GIVEAWAY_GROUP_ID, GIVEAWAY_CHANNEL_ID, MAX_WINNERS, MAX_GIVEAWAY_NAME_LEN
from database import create_giveaway, get_giveaway, update_giveaway_status, add_audit_log, is_banned
from utils import E, parse_ist_datetime, to_utc_iso, format_ist, giveaway_type_name, giveaway_type_emoji
from utils.keyboards import cancel_keyboard, confirm_giveaway_keyboard
from utils.permissions import sudo_only
from utils.announcements import AnnouncementManager
from config import GiveawayStatus

logger = logging.getLogger("zynex.handlers.sgive")

# Conversation states
(SGIVE_TYPE, SGIVE_NAME, SGIVE_WINNERS, SGIVE_TIME, SGIVE_CONFIRM) = range(5)


async def sgive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sgive command — DM only, start wizard."""
    user_id = update.effective_user.id

    # DM only check
    if update.message.chat.type != "private":
        await update.message.reply_text(
            f"{E.SHIELD} This command can only be used in my <b>private chat</b>.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    # Parse type argument
    args = context.args
    if not args or len(args) != 1:
        text = (
            f"{E.GIVEAWAY} <b>Create a Giveaway</b>\n"
            f"\n"
            f"Usage: <code>/sgive [type]</code>\n"
            f"\n"
            f"Types:\n"
            f"1 — {E.VOTE} Vote Giveaway\n"
            f"2 — {E.GIVEAWAY} Random Giveaway\n"
            f"3 — {E.SLOT} Slot Giveaway\n"
            f"\n"
            f"Example: <code>/sgive 2</code>"
        )
        await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    try:
        gtype = int(args[0])
        if gtype not in [1, 2, 3]:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"{E.WARNING} Invalid type. Use 1, 2, or 3.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    # Store type in context
    context.user_data["sgive_type"] = gtype
    context.user_data["sgive_step"] = "name"

    type_emoji = giveaway_type_emoji(gtype)
    type_name = giveaway_type_name(gtype)

    text = (
        f"{E.PARTY} <b>Creating {type_emoji} {type_name}</b>\n"
        f"\n"
        f"Step 1/4: {E.NAME_TAG} <b>Enter the name of the giveaway.</b>\n"
        f"\n"
        f"Max length: {MAX_GIVEAWAY_NAME_LEN} characters.\n"
        f"\n"
        f"Send the giveaway name:"
    )

    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )

    return SGIVE_NAME


async def sgive_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle giveaway name input."""
    query = update.callback_query
    if query:
        await query.answer()
        if query.data == "cancel_setup":
            await query.edit_message_text(f"{E.CROSS} Giveaway setup cancelled.")
            return ConversationHandler.END
        return

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text(
            f"{E.WARNING} Name cannot be empty. Please enter a name:",
        )
        return SGIVE_NAME

    if len(text) > MAX_GIVEAWAY_NAME_LEN:
        await update.message.reply_text(
            f"{E.WARNING} Name too long ({len(text)}/{MAX_GIVEAWAY_NAME_LEN}). Enter a shorter name:",
        )
        return SGIVE_NAME

    context.user_data["sgive_name"] = text
    context.user_data["sgive_step"] = "winners"

    reply = (
        f"{E.WINNER} <b>Step 2/4: How many winners should this giveaway have?</b>\n"
        f"\n"
        f"Current name: <b>{text}</b>\n"
        f"\n"
        f"Enter a positive integer (max {MAX_WINNERS}):"
    )

    await update.message.reply_text(
        text=reply,
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )

    return SGIVE_WINNERS


async def sgive_winners_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle winner count input."""
    query = update.callback_query
    if query:
        await query.answer()
        if query.data == "cancel_setup":
            await query.edit_message_text(f"{E.CROSS} Giveaway setup cancelled.")
            return ConversationHandler.END
        return

    text = update.message.text.strip()
    try:
        count = int(text)
        if count < 1 or count > MAX_WINNERS:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"{E.WARNING} Invalid number. Enter an integer between 1 and {MAX_WINNERS}:",
        )
        return SGIVE_WINNERS

    context.user_data["sgive_winners"] = count
    context.user_data["sgive_step"] = "time"

    # Get current IST time for helpful example
    from datetime import datetime, timezone, timedelta
    from utils import IST
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST)
    # Round up to next 5 minutes for example
    next_hour = (now_ist + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    example_start = now_ist.strftime("%d/%m/%Y %H:%M")
    example_end = next_hour.strftime("%d/%m/%Y %H:%M")

    reply = (
        f"{E.CLOCK} <b>Step 3/4: Enter start and end time in IST (24-hour format).</b>\n"
        f"\n"
        f"Name: <b>{context.user_data['sgive_name']}</b>\n"
        f"Winners: <code>{count}</code>\n"
        f"\n"
        f"Current IST time: <b>{now_ist.strftime('%H:%M')}</b>\n"
        f"\n"
        f"Format: <code>DD/MM/YYYY HH:MM - DD/MM/YYYY HH:MM</code>\n"
        f"\n"
        f"Example: <code>{example_start} - {example_end}</code>\n"
        f"\n"
        f"All times are in IST (Asia/Kolkata).\n"
        f"You can use a time close to now for immediate start."
    )

    await update.message.reply_text(
        text=reply,
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )

    return SGIVE_TIME


async def sgive_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle start/end time input."""
    query = update.callback_query
    if query:
        await query.answer()
        if query.data == "cancel_setup":
            await query.edit_message_text(f"{E.CROSS} Giveaway setup cancelled.")
            return ConversationHandler.END
        return

    text = update.message.text.strip()

    # Parse time range
    parts = text.split("-")
    if len(parts) != 2:
        await update.message.reply_text(
            f"{E.WARNING} Invalid format. Use: <code>DD/MM/YYYY HH:MM - DD/MM/YYYY HH:MM</code>",
            parse_mode=ParseMode.HTML,
        )
        return SGIVE_TIME

    start_str = parts[0].strip()
    end_str = parts[1].strip()

    start_dt = parse_ist_datetime(start_str)
    end_dt = parse_ist_datetime(end_str)

    if not start_dt:
        await update.message.reply_text(
            f"{E.WARNING} Invalid start time format.\nUse: <code>DD/MM/YYYY HH:MM</code>",
            parse_mode=ParseMode.HTML,
        )
        return SGIVE_TIME

    if not end_dt:
        await update.message.reply_text(
            f"{E.WARNING} Invalid end time format.\nUse: <code>DD/MM/YYYY HH:MM</code>",
            parse_mode=ParseMode.HTML,
        )
        return SGIVE_TIME

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)

    # Allow start time up to 5 minutes in the past (grace period for testing)
    grace_period = timedelta(minutes=5)
    start_with_grace = start_utc + grace_period

    if start_with_grace < now:
        # Get current IST time for the error message
        from utils import IST
        now_ist = now.astimezone(IST)
        current_time_str = now_ist.strftime("%H:%M")
        await update.message.reply_text(
            f"{E.WARNING} Start time <code>{start_str}</code> is too far in the past.\n"
            f"\n"
            f"Current IST time: <b>{current_time_str}</b>\n"
            f"\n"
            f"Enter a future time or use a time close to now.\n"
            f"Example: <code>12/09/2026 {current_time_str}</code>",
            parse_mode=ParseMode.HTML,
        )
        return SGIVE_TIME

    if end_utc <= start_utc:
        await update.message.reply_text(
            f"{E.WARNING} End time must be after start time.",
        )
        return SGIVE_TIME

    context.user_data["sgive_start"] = to_utc_iso(start_dt)
    context.user_data["sgive_end"] = to_utc_iso(end_dt)
    context.user_data["sgive_step"] = "confirm"

    # Show confirmation
    gtype = context.user_data["sgive_type"]
    type_emoji = giveaway_type_emoji(gtype)
    type_name = giveaway_type_name(gtype)

    confirm_text = (
        f"{E.GIVEAWAY} <b>GIVEAWAY CONFIRMATION</b>\n"
        f"\n"
        f"{E.BULLET}\n"
        f"\n"
        f"{E.NAME_TAG} Name:\n<b>{context.user_data['sgive_name']}</b>\n"
        f"\n"
        f"{E.GIFT} Type:\n{type_emoji} <b>{type_name}</b>\n"
        f"\n"
        f"{E.WINNER} Winners:\n<b>{context.user_data['sgive_winners']}</b>\n"
        f"\n"
        f"{E.CLOCK} Starts:\n<b>{format_ist(start_dt)}</b>\n"
        f"\n"
        f"{E.HOURGLASS} Ends:\n<b>{format_ist(end_dt)}</b>\n"
        f"\n"
        f"{E.GROUP} Announcement Group:\n<code>{GIVEAWAY_GROUP_ID}</code>\n"
        f"\n"
        f"{E.CHANNEL} Announcement Channel:\n<code>{GIVEAWAY_CHANNEL_ID}</code>\n"
        f"\n"
        f"{E.BULLET}\n"
        f"\n"
        f"Are you sure you want to start this giveaway?"
    )

    await update.message.reply_text(
        text=confirm_text,
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_giveaway_keyboard(0),  # 0 = not yet created
    )

    return SGIVE_CONFIRM


async def sgive_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation callback."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("cancel_giveaway_") or data == "cancel_setup":
        await query.edit_message_text(f"{E.CROSS} Giveaway setup cancelled.")
        return ConversationHandler.END

    if data.startswith("confirm_giveaway_"):
        user_id = query.from_user.id
        ud = context.user_data

        # Check if this is our wizard
        if "sgive_type" not in ud:
            return

        try:
            # Create the giveaway
            gid = await create_giveaway(
                name=ud["sgive_name"],
                giveaway_type=ud["sgive_type"],
                winner_count=ud["sgive_winners"],
                start_time=ud["sgive_start"],
                end_time=ud["sgive_end"],
                group_id=GIVEAWAY_GROUP_ID,
                channel_id=GIVEAWAY_CHANNEL_ID,
                created_by=user_id,
            )

            await add_audit_log(
                action="giveaway_created",
                admin_id=user_id,
                giveaway_id=gid,
                new_state=GiveawayStatus.SCHEDULED,
            )

            # Update confirmation message
            from utils import format_ist, from_utc_iso
            gtype = ud["sgive_type"]
            type_emoji = giveaway_type_emoji(gtype)
            type_name = giveaway_type_name(gtype)
            start_dt = from_utc_iso(ud["sgive_start"])
            end_dt = from_utc_iso(ud["sgive_end"])

            text = (
                f"{E.CHECK} <b>GIVEAWAY CREATED SUCCESSFULLY!</b>\n"
                f"\n"
                f"{E.BULLET}\n"
                f"\n"
                f"{E.NAME_TAG} Name: <b>{ud['sgive_name']}</b>\n"
                f"{E.GIFT} Type: {type_emoji} <b>{type_name}</b>\n"
                f"{E.WINNER} Winners: <code>{ud['sgive_winners']}</code>\n"
                f"{E.CLOCK} Starts: <b>{format_ist(start_dt)}</b>\n"
                f"{E.HOURGLASS} Ends: <b>{format_ist(end_dt)}</b>\n"
                f"{E.PIN} Giveaway ID: <code>#{gid}</code>\n"
                f"\n"
                f"{E.BULLET}\n"
                f"\n"
                f"{E.ROCKET} The giveaway will be announced when it starts!"
            )

            await query.edit_message_text(
                text=text,
                parse_mode=ParseMode.HTML,
            )

            # Clear user data
            context.user_data.clear()

            logger.info(f"Giveaway #{gid} created by admin {user_id}")

        except Exception as e:
            logger.error(f"Error creating giveaway: {e}", exc_info=True)
            await query.edit_message_text(
                f"{E.CROSS} Error creating giveaway. Please try again.",
            )

        return ConversationHandler.END

    return SGIVE_CONFIRM


# Handler registration
def register_sgive_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("sgive", sgive_command)],
        states={
            SGIVE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sgive_name_handler),
                CallbackQueryHandler(sgive_name_handler, pattern="^cancel_setup$"),
            ],
            SGIVE_WINNERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sgive_winners_handler),
                CallbackQueryHandler(sgive_winners_handler, pattern="^cancel_setup$"),
            ],
            SGIVE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sgive_time_handler),
                CallbackQueryHandler(sgive_time_handler, pattern="^cancel_setup$"),
            ],
            SGIVE_CONFIRM: [
                CallbackQueryHandler(sgive_confirm_handler, pattern=r"^(confirm_giveaway_|cancel_giveaway_|cancel_setup)"),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )
    app.add_handler(conv_handler)
