"""
ZYNEX CARTEL — Participant Commands
/mystatus · /leaderboard · /mylink — active vote giveaway only.
Identity is numeric user_id; no user-supplied participant IDs.
"""

import logging
import html
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
)
from telegram.constants import ParseMode, ChatType
from telegram.error import BadRequest

from utils import E
from utils.keyboards import small_caps, BE, btn_success, btn_primary, btn_default, btn_url
from engines.vote_giveaway_engine import (
    get_user_participant,
    get_user_rank_info,
    get_leaderboard_page,
    generate_participant_message_link,
)
from database import get_active_vote_giveaway

logger = logging.getLogger("zynex.handlers.participant")


# ─── Shared messages ──────────────────────────────────────────────

NO_GIVEAWAY_MSG = (
    f"{E.GIFT} <b>Zynex Giveaways</b>\n\n"
    "There is currently no active giveaway."
)

DM_ONLY_MSG = (
    f"{E.CROSS} This command can only be used in the bot's private messages.\n\n"
    "Open a chat with me and try again."
)

NOT_REGISTERED_MSG = (
    f"{E.CROSS} You are not registered in this giveaway.\n\n"
    "Send <code>/join [name]</code> to register."
)

STALE_LEADERBOARD = "This leaderboard is no longer active."


async def _require_active_vote_giveaway(message) -> dict | None:
    giveaway = await get_active_vote_giveaway()
    if not giveaway:
        await message.reply_text(NO_GIVEAWAY_MSG, parse_mode=ParseMode.HTML)
        return None
    return giveaway


# ─── Keyboard builders ────────────────────────────────────────────

def mystatus_keyboard() -> InlineKeyboardMarkup:
    """Buttons after /mystatus: Leaderboard + My Link (plain BE emoji)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{BE.TROPHY} {small_caps('Leaderboard')}",
                callback_data="pui:lb",
            ),
            InlineKeyboardButton(
                f"🔗 {small_caps('My Link')}",
                callback_data="pui:link",
            ),
        ],
    ])


def leaderboard_keyboard(giveaway_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """[◀][1/N][▶] + optional Refresh."""
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(
            f"{BE.BACK}",
            callback_data=f"lb:{giveaway_id}:{page - 1}",
        ))
    else:
        nav.append(InlineKeyboardButton(" ", callback_data="noop"))
    nav.append(InlineKeyboardButton(
        f"{page}/{total_pages}",
        callback_data="noop",
    ))
    if page < total_pages:
        nav.append(InlineKeyboardButton(
            f"➡️",
            callback_data=f"lb:{giveaway_id}:{page + 1}",
        ))
    else:
        nav.append(InlineKeyboardButton(" ", callback_data="noop"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(
        f"🔄 {small_caps('Refresh')}",
        callback_data=f"lb:{giveaway_id}:{page}",
    )])
    rows.append([InlineKeyboardButton(
        f"{BE.PERSON} {small_caps('My Status')}",
        callback_data="pui:status",
    )])
    return InlineKeyboardMarkup(rows)


def mylink_keyboard(link: str | None) -> InlineKeyboardMarkup:
    """Post-/mylink: Vote for Me URL button when a usable link exists."""
    rows = []
    if link:
        rows.append([btn_url(f"{BE.VOTE} {small_caps('Vote for Me')}", link)])
    rows.append([InlineKeyboardButton(
        f"{BE.TROPHY} {small_caps('Leaderboard')}",
        callback_data="pui:lb",
    )])
    rows.append([InlineKeyboardButton(
        f"{BE.PERSON} {small_caps('My Status')}",
        callback_data="pui:status",
    )])
    return InlineKeyboardMarkup(rows)


# ─── Content builders ─────────────────────────────────────────────

def _rank_display(rank: int) -> str:
    return f"#{rank}"


def _giveaway_name(giveaway) -> str:
    try:
        return str(giveaway["name"] or "Vote Giveaway")
    except (KeyError, IndexError, TypeError):
        return "Vote Giveaway"


def _status_registered_text(giveaway: dict, participant: dict, rank_info: dict) -> str:
    gname = html.escape(_giveaway_name(giveaway))
    pname = html.escape(str(participant["participant_name"]))
    votes = rank_info["votes"]
    rank = rank_info["rank"]
    return (
        f"╭━━━ {E.TROPHY} <b>ZYNEX GIVEAWAYS</b> ━━━╮\n"
        f"│ {E.GIFT} Vote Giveaway: <b>{gname}</b>\n"
        f"│ {E.PERSON} Participant: <b>{pname}</b>\n"
        f"│ {E.VOTE} Votes: <code>{votes}</code>\n"
        f"│ {E.TROPHY} Rank: <code>{_rank_display(rank)}</code>\n"
        f"│ {E.CHECK} Status: <b>Participating</b>\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━╯"
    )


def _status_not_registered_text(giveaway: dict) -> str:
    gname = html.escape(_giveaway_name(giveaway))
    return (
        f"╭━━━ {E.TROPHY} <b>ZYNEX GIVEAWAYS</b> ━━━╮\n"
        f"│ {E.GIFT} Vote Giveaway: <b>{gname}</b>\n"
        f"│ {E.CROSS} Status: <b>Not registered</b>\n"
        f"\n"
        f"Send <code>/join [name]</code> to participate.\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━╯"
    )


def _medal_for_rank(rank: int) -> str:
    if rank == 1:
        return E.MEDAL_1
    if rank == 2:
        return E.MEDAL_2
    if rank == 3:
        return E.MEDAL_3
    return f"<code>#{rank}</code>"


def _leaderboard_text(giveaway: dict, board: dict) -> str:
    gname = html.escape(_giveaway_name(giveaway))
    page = board["page"]
    total_pages = board["total_pages"]
    total = board["total_participants"]
    rows = board["rows"]

    lines = [
        f"╭━━━ {E.CHART} <b>LEADERBOARD</b> ━━━╮",
        f"│ {E.GIFT} {gname}",
        f"│ {E.USERS} Participants: <code>{total}</code>",
        f"│ Page <code>{page}/{total_pages}</code>",
        "╰━━━━━━━━━━━━━━━━━━━━━━╯",
        "",
    ]
    if not rows:
        lines.append(f"{E.INFO} No participants yet.")
    else:
        for row in rows:
            rank = int(row["rank_num"])
            name = html.escape(row["participant_name"])
            votes = int(row["total_votes"])
            medal = _medal_for_rank(rank)
            lines.append(
                f"{medal} <b>{name}</b> — <code>{votes}</code> votes"
            )
    return "\n".join(lines)


def _mylink_text(
    giveaway: dict,
    participant: dict,
    rank_info: dict,
    link: str | None,
    has_message: bool,
) -> str:
    gname = html.escape(_giveaway_name(giveaway))
    pname = html.escape(str(participant["participant_name"]))
    votes = rank_info["votes"]
    rank = rank_info["rank"]
    if link:
        link_line = (
            f"{E.ARROW} Link: "
            f"<a href=\"{html.escape(link)}\">Open voting message</a>"
        )
    elif has_message:
        link_line = f"{E.WARNING} Direct link unavailable — open the channel and find your post."
    else:
        link_line = f"{E.WARNING} Your channel message is not ready yet."
    return (
        f"╭━━━ {E.TROPHY} <b>ZYNEX GIVEAWAYS</b> ━━━╮\n"
        f"│ {E.GIFT} Vote Giveaway: <b>{gname}</b>\n"
        f"│ {E.PERSON} Participant: <b>{pname}</b>\n"
        f"│ {E.VOTE} Votes: <code>{votes}</code>\n"
        f"│ {E.TROPHY} Rank: <code>{_rank_display(rank)}</code>\n"
        f"│ {E.CHECK} Status: <b>Participating</b>\n"
        f"│\n"
        f"│ {link_line}\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━╯"
    )


# ─── /mystatus ────────────────────────────────────────────────────

async def mystatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(DM_ONLY_MSG, parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    if not user:
        return

    giveaway = await _require_active_vote_giveaway(message)
    if not giveaway:
        return

    gid = giveaway["giveaway_id"]
    participant = await get_user_participant(gid, user.id)
    if not participant:
        await message.reply_text(
            _status_not_registered_text(giveaway),
            parse_mode=ParseMode.HTML,
            reply_markup=mystatus_keyboard(),
        )
        return

    rank_info = await get_user_rank_info(gid, participant["id"])
    await message.reply_text(
        _status_registered_text(giveaway, participant, rank_info),
        parse_mode=ParseMode.HTML,
        reply_markup=mystatus_keyboard(),
    )


# ─── /leaderboard ─────────────────────────────────────────────────

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(DM_ONLY_MSG, parse_mode=ParseMode.HTML)
        return

    giveaway = await _require_active_vote_giveaway(message)
    if not giveaway:
        return

    gid = giveaway["giveaway_id"]
    board = await get_leaderboard_page(gid, page=1)
    await message.reply_text(
        _leaderboard_text(giveaway, board),
        parse_mode=ParseMode.HTML,
        reply_markup=leaderboard_keyboard(gid, board["page"], board["total_pages"]),
    )


# ─── /mylink ──────────────────────────────────────────────────────

async def mylink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(DM_ONLY_MSG, parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    if not user:
        return

    giveaway = await _require_active_vote_giveaway(message)
    if not giveaway:
        return

    gid = giveaway["giveaway_id"]
    participant = await get_user_participant(gid, user.id)
    if not participant:
        await message.reply_text(NOT_REGISTERED_MSG, parse_mode=ParseMode.HTML)
        return

    rank_info = await get_user_rank_info(gid, participant["id"])
    link = await generate_participant_message_link(context.bot, participant)
    has_message = _has_channel_message(participant)
    await message.reply_text(
        _mylink_text(giveaway, participant, rank_info, link, has_message),
        parse_mode=ParseMode.HTML,
        reply_markup=mylink_keyboard(link),
        disable_web_page_preview=True,
    )


# ─── Callbacks ────────────────────────────────────────────────────

def _row_get(row, key, default=None):
    """Read a column from sqlite3.Row or dict without AttributeError."""
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _has_channel_message(participant) -> bool:
    return bool(_row_get(participant, "channel_message_id"))


async def _edit_or_reply(query, text: str, reply_markup: InlineKeyboardMarkup | None) -> bool:
    """Edit existing message when possible. Returns False if unchanged."""
    try:
        await query.edit_message_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return True
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return False
        raise


async def _answer_nav(query, changed: bool):
    if changed:
        await query.answer()
    else:
        await query.answer("Already up to date.")


async def participant_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """pui:status | pui:lb | pui:link — navigate between participant views."""
    query = update.callback_query
    if not query or not query.data:
        return

    action = query.data.split(":", 1)[-1]
    user = query.from_user

    giveaway = await get_active_vote_giveaway()
    if not giveaway:
        await query.answer(STALE_LEADERBOARD, show_alert=True)
        return

    gid = giveaway["giveaway_id"]
    changed = True

    if action == "lb":
        board = await get_leaderboard_page(gid, page=1)
        changed = await _edit_or_reply(
            query,
            _leaderboard_text(giveaway, board),
            leaderboard_keyboard(gid, board["page"], board["total_pages"]),
        )
    elif action == "link":
        participant = await get_user_participant(gid, user.id)
        if not participant:
            await query.answer("Not registered in this giveaway.", show_alert=True)
            return
        rank_info = await get_user_rank_info(gid, participant["id"])
        link = await generate_participant_message_link(context.bot, participant)
        has_message = _has_channel_message(participant)
        changed = await _edit_or_reply(
            query,
            _mylink_text(giveaway, participant, rank_info, link, has_message),
            mylink_keyboard(link),
        )
    else:  # pui:status
        participant = await get_user_participant(gid, user.id)
        if not participant:
            changed = await _edit_or_reply(
                query, _status_not_registered_text(giveaway), mystatus_keyboard(),
            )
        else:
            rank_info = await get_user_rank_info(gid, participant["id"])
            changed = await _edit_or_reply(
                query,
                _status_registered_text(giveaway, participant, rank_info),
                mystatus_keyboard(),
            )

    await _answer_nav(query, changed)


async def leaderboard_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """lb:{giveaway_id}:{page} — paginated leaderboard; validates active giveaway."""
    query = update.callback_query
    if not query or not query.data:
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer("Invalid callback data.", show_alert=True)
        return
    try:
        gid = int(parts[1])
        page = max(1, int(parts[2]))
    except ValueError:
        await query.answer("Invalid callback data.", show_alert=True)
        return

    active = await get_active_vote_giveaway()
    if not active or active["giveaway_id"] != gid:
        # No emojis in query.answer popups (policy)
        await query.answer(STALE_LEADERBOARD, show_alert=True)
        return

    board = await get_leaderboard_page(gid, page=page)
    changed = await _edit_or_reply(
        query,
        _leaderboard_text(active, board),
        leaderboard_keyboard(gid, board["page"], board["total_pages"]),
    )
    await _answer_nav(query, changed)


# ─── Registration ─────────────────────────────────────────────────

def register_participant_handlers(app):
    """Register /mystatus, /leaderboard, /mylink + their callbacks."""
    app.add_handler(CommandHandler("mystatus", mystatus_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("mylink", mylink_command))
    app.add_handler(
        CallbackQueryHandler(participant_nav_callback, pattern=r"^pui:(status|lb|link)$")
    )
    app.add_handler(
        CallbackQueryHandler(leaderboard_page_callback, pattern=r"^lb:\d+:\d+$")
    )
