"""
ZYNEX CARTEL — Broadcast Handler
/bd — Owner only: reply to a DM message to broadcast it to the
giveaway channel + group with a Participate Now deep-link button.
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from config import GIVEAWAY_CHANNEL_ID, GIVEAWAY_GROUP_ID
from utils import E
from utils.permissions import owner_only
from utils.keyboards import small_caps, BE, btn_url

logger = logging.getLogger("zynex.handlers.broadcast")


# ─── Deep link ────────────────────────────────────────────────────

def build_join_url(bot_username: str) -> str:
    """Direct deep link that opens the bot and triggers /start join."""
    uname = (bot_username or "").lstrip("@")
    if not uname:
        return "https://t.me/"
    return f"https://t.me/{uname}?start=join"


def participate_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Participate Now URL button (plain Unicode — no premium HTML in buttons)."""
    url = build_join_url(bot_username)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{BE.GIVEAWAY} {small_caps('Participate Now')}", url=url)],
    ])


# ─── Message forwarding helpers ───────────────────────────────────

async def send_broadcast_copy(bot, source, chat_id: int, reply_markup) -> bool:
    """Re-send source message content to chat_id with the participate button.

    Uses entities (not parse_mode) so premium/custom emojis and formatting
    from the original message are preserved exactly.
    Returns True if a message was sent.
    """
    # Photo / video / animation with caption
    if source.photo or source.video or source.animation:
        caption = source.caption or ""
        caption_entities = source.caption_entities or None
        kwargs = {
            "chat_id": chat_id,
            "caption": caption,
            "caption_entities": caption_entities,
            "reply_markup": reply_markup,
        }
        if source.photo:
            await bot.send_photo(photo=source.photo[-1].file_id, **kwargs)
        elif source.video:
            await bot.send_video(video=source.video.file_id, **kwargs)
        else:
            await bot.send_animation(animation=source.animation.file_id, **kwargs)
        return True

    # Text message (primary path)
    if source.text:
        await bot.send_message(
            chat_id=chat_id,
            text=source.text,
            entities=source.entities or None,
            reply_markup=reply_markup,
        )
        return True

    # Document with caption
    if source.document and (source.caption or source.caption_entities):
        await bot.send_document(
            document=source.document.file_id,
            chat_id=chat_id,
            caption=source.caption or "",
            caption_entities=source.caption_entities or None,
            reply_markup=reply_markup,
        )
        return True

    return False


# ─── /bd ──────────────────────────────────────────────────────────

@owner_only
async def bd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: reply to a message with /bd to broadcast it to channel + group."""
    message = update.message
    if not message:
        return

    source = message.reply_to_message
    if not source:
        await message.reply_text(
            f"{E.CROSS} Reply to a message with <code>/bd</code> to broadcast it.\n\n"
            f"{E.INFO} The same content is sent to the giveaway channel and group "
            f"with a <b>Participate Now</b> button.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Collect a sendable payload (text, caption, or media+caption)
    has_payload = bool(
        source.text
        or source.caption
        or source.photo
        or source.video
        or source.animation
        or source.document
    )
    if not has_payload:
        await message.reply_text(
            f"{E.CROSS} That message type cannot be broadcast. "
            f"Reply to text or media with a caption.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        me = await context.bot.get_me()
        bot_username = me.username
    except Exception as e:
        logger.warning(f"get_me failed for /bd: {e}")
        bot_username = ""

    kb = participate_keyboard(bot_username)

    results = []
    for label, chat_id in (
        ("channel", GIVEAWAY_CHANNEL_ID),
        ("group", GIVEAWAY_GROUP_ID),
    ):
        try:
            ok = await send_broadcast_copy(context.bot, source, chat_id, kb)
            results.append((label, chat_id, ok, None))
        except Exception as e:
            logger.error(f"/bd send to {label} {chat_id} failed: {e}", exc_info=True)
            results.append((label, chat_id, False, str(e)))

    # Summarize for the owner
    lines = []
    ok_count = 0
    for label, chat_id, ok, err in results:
        if ok:
            ok_count += 1
            lines.append(f"{E.CHECK} <b>{label.title()}</b>: <code>{chat_id}</code>")
        else:
            lines.append(
                f"{E.CROSS} <b>{label.title()}</b>: <code>{chat_id}</code> — {err or 'unsupported'}"
            )

    join_url = build_join_url(bot_username)
    summary = (
        f"{E.CHANNEL} <b>Broadcast {'complete' if ok_count == len(results) else 'partial'}</b>\n"
        f"\n"
        + "\n".join(lines)
        + f"\n\n"
        f"{E.VOTE} Participate link: <a href=\"{join_url}\">open bot</a>\n"
        f"{E.INFO} Button: <b>Participate Now</b> → deep link <code>?start=join</code>"
    )
    await message.reply_text(
        summary,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    logger.info(
        "Owner /bd broadcast by %s → %s/%s ok=%s",
        update.effective_user.id if update.effective_user else "?",
        GIVEAWAY_CHANNEL_ID,
        GIVEAWAY_GROUP_ID,
        ok_count,
    )


def register_broadcast_handlers(app):
    app.add_handler(CommandHandler("bd", bd_command))
