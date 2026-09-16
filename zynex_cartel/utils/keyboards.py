"""
ZYNEX CARTEL — Keyboard Builder
Premium inline buttons with small caps text styling.
Uses the same approach as the Robin bot.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ─── Small Caps Conversion (Robin-style) ─────────────────────────
# Converts regular text to Unicode small caps for premium button look.

SMALL_CAPS_MAP = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
    "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
    "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
    "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
}

BOLD_CAPS = {
    "A": "𝐀", "B": "𝐁", "C": "𝐂", "D": "𝐃", "E": "𝐄", "F": "𝐅",
    "G": "𝐆", "H": "𝐇", "I": "𝐈", "J": "𝐉", "K": "𝐊", "L": "𝐋",
    "M": "𝐌", "N": "𝐍", "O": "𝐎", "P": "𝐏", "Q": "𝐐", "R": "𝐑",
    "S": "𝐒", "T": "𝐓", "U": "𝐔", "V": "𝐕", "W": "𝐖", "X": "𝐗",
    "Y": "𝐘", "Z": "𝐙",
}


def small_caps(text: str) -> str:
    """Convert text to Unicode small caps for premium button styling."""
    if not text:
        return ""
    result = []
    for char in text:
        if char.isupper():
            result.append(BOLD_CAPS.get(char, char))
        elif char.islower():
            result.append(SMALL_CAPS_MAP.get(char, char))
        else:
            result.append(char)
    return "".join(result)


# ─── Button Emojis (Plain Unicode — works in all buttons) ────────

class BE:
    """Button Emojis — Plain Unicode for inline keyboard buttons."""
    # Core
    CROWN       = "👑"
    FIRE        = "🔥"
    STAR        = "⭐"
    DIAMOND     = "💎"
    TROPHY      = "🏆"
    GIFT        = "🎁"
    TICKET      = "🎫"
    SLOT        = "🎰"
    CHART       = "📊"
    SHIELD      = "🛡️"
    LIGHTNING   = "⚡"
    CHECK       = "✅"
    CROSS       = "❌"
    PARTY       = "🎉"
    ROCKET      = "🚀"
    HEART       = "❤️"
    SKULL       = "💀"
    SPARKLE     = "✨"

    # Giveaway
    NAME_TAG    = "📛"
    CLOCK       = "⏰"
    HOURGLASS   = "⏳"
    WINNER      = "🏆"
    MEDAL_1     = "🥇"
    MEDAL_2     = "🥈"
    MEDAL_3     = "🥉"
    GIVEAWAY    = "🎲"
    SLOT_MACHINE= "🎰"
    VOTE        = "🗳️"
    GROUP       = "📍"
    CHANNEL     = "📢"
    PERSON      = "👤"
    USERS       = "👥"
    PIN         = "📌"
    LOCK        = "🔒"
    UNLOCK      = "🔓"
    BAN         = "🚫"
    UNBAN       = "♻️"
    ADD         = "➕"
    REMOVE      = "➖"
    END         = "⏹️"
    START       = "▶️"
    WARNING     = "⚠️"
    INFO        = "ℹ️"
    QUESTION    = "❓"
    ARROW       = "➡️"
    BACK        = "◀️"
    HOME        = "🏠"


# ─── Colored Button Builders (Robin-style with small caps) ────────

def btn_green(text: str, callback_data: str) -> InlineKeyboardButton:
    """Green-themed button — affirmative/confirm actions."""
    return InlineKeyboardButton(f"🟩 {small_caps(text)}", callback_data=callback_data)

def btn_red(text: str, callback_data: str) -> InlineKeyboardButton:
    """Red-themed button — negative/cancel/danger actions."""
    return InlineKeyboardButton(f"🟥 {small_caps(text)}", callback_data=callback_data)

def btn_blue(text: str, callback_data: str) -> InlineKeyboardButton:
    """Blue-themed button — informational/neutral actions."""
    return InlineKeyboardButton(f"🟦 {small_caps(text)}", callback_data=callback_data)

def btn_yellow(text: str, callback_data: str) -> InlineKeyboardButton:
    """Yellow-themed button — warning/pending actions."""
    return InlineKeyboardButton(f"🟨 {small_caps(text)}", callback_data=callback_data)

def btn_purple(text: str, callback_data: str) -> InlineKeyboardButton:
    """Purple-themed button — special/admin actions."""
    return InlineKeyboardButton(f"🟪 {small_caps(text)}", callback_data=callback_data)

def btn_orange(text: str, callback_data: str) -> InlineKeyboardButton:
    """Orange-themed button — moderate actions."""
    return InlineKeyboardButton(f"🟧 {small_caps(text)}", callback_data=callback_data)

def btn(text: str, callback_data: str) -> InlineKeyboardButton:
    """Plain button with small caps text, no color prefix."""
    return InlineKeyboardButton(small_caps(text), callback_data=callback_data)

def btn_icon(emoji: str, text: str, callback_data: str) -> InlineKeyboardButton:
    """Button with icon emoji + small caps text."""
    return InlineKeyboardButton(f"{emoji} {small_caps(text)}", callback_data=callback_data)


# ─── Start / Welcome ──────────────────────────────────────────────

def start_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    """Build mandatory channel check keyboard."""
    buttons = []
    for ch in channels:
        ch_id = ch.get("id", "")
        ch_name = ch.get("name", f"Channel {ch_id}")
        url = ch.get("url", f"https://t.me/c/{str(ch_id).replace('-100', '')}")
        buttons.append([InlineKeyboardButton(f"📍 {ch_name}", url=url)])
    buttons.append([btn_icon(BE.CHECK, "I've Joined", "verify_membership")])
    return InlineKeyboardMarkup(buttons)


def verified_keyboard() -> InlineKeyboardMarkup:
    """After verification success."""
    return InlineKeyboardMarkup([
        [btn_icon(BE.GIVEAWAY, "Active Giveaways", "show_active")],
        [btn_icon(BE.INFO, "Help", "show_help")],
    ])


# ─── Active Giveaways ────────────────────────────────────────────

def active_giveaways_keyboard(giveaways: list[dict]) -> InlineKeyboardMarkup:
    """Show list of active giveaways with join buttons."""
    buttons = []
    for g in giveaways:
        gid = g["giveaway_id"]
        name = g["name"]
        gtype = g["type"]
        from utils import giveaway_type_emoji
        emoji = giveaway_type_emoji(gtype)
        buttons.append([
            InlineKeyboardButton(
                f"{emoji} {name}",
                callback_data=f"giveaway_info_{gid}"
            )
        ])
    if not buttons:
        buttons.append([btn_icon(BE.INFO, "No Active Giveaways", "noop")])
    return InlineKeyboardMarkup(buttons)


def giveaway_info_keyboard(giveaway_id: int, gtype: int) -> InlineKeyboardMarkup:
    """Actions for a specific giveaway."""
    buttons = []
    if gtype == 1:  # Vote
        buttons.append([btn_icon(BE.VOTE, "Vote Now", f"vote_start_{giveaway_id}")])
        buttons.append([btn_icon(BE.CHART, "Leaderboard", f"leaderboard_{giveaway_id}")])
    elif gtype == 2:  # Random — no button, participate by sending message in group
        pass
    elif gtype == 3:  # Slot
        buttons.append([btn_icon(BE.SLOT, "Spin to Win!", f"info_slot_{giveaway_id}")])
    buttons.append([btn_icon(BE.USERS, "Participants", f"participant_count_{giveaway_id}")])
    return InlineKeyboardMarkup(buttons)


# ─── Vote Giveaway ───────────────────────────────────────────────

def vote_keyboard(giveaway_id: int, candidates: list[dict]) -> InlineKeyboardMarkup:
    """Vote buttons for each candidate."""
    buttons = []
    for c in candidates:
        uid = c["user_id"]
        name = c.get("display_name", f"User {uid}")
        vote_count = c.get("vote_count", 0)
        buttons.append([
            InlineKeyboardButton(
                f"👤 {name} — {vote_count} votes",
                callback_data=f"vote_{giveaway_id}_{uid}"
            )
        ])
    return InlineKeyboardMarkup(buttons)


def vote_confirm_keyboard(giveaway_id: int, target_id: int) -> InlineKeyboardMarkup:
    """Single vote confirm button."""
    return InlineKeyboardMarkup([
        [btn_icon(BE.CHECK, "Confirm Vote", f"vote_confirm_{giveaway_id}_{target_id}")],
        [btn_icon(BE.CROSS, "Cancel", f"vote_cancel_{giveaway_id}")],
    ])


# ─── Giveaway Creation Wizard ────────────────────────────────────

def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn_icon(BE.CROSS, "Cancel Setup", "cancel_setup")]
    ])


def confirm_giveaway_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn_green("CONFIRM", f"confirm_giveaway_{giveaway_id}")],
        [btn_red("CANCEL", f"cancel_giveaway_{giveaway_id}")],
    ])


# ─── Admin Controls ──────────────────────────────────────────────

def admin_giveaway_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    """Admin controls for an active giveaway."""
    return InlineKeyboardMarkup([
        [
            btn_icon(BE.TROPHY, "Set Winner", f"admin_winner_{giveaway_id}"),
            btn_icon(BE.END, "End", f"admin_end_{giveaway_id}"),
        ],
        [
            btn_icon(BE.ADD, "Add User", f"admin_add_{giveaway_id}"),
            btn_icon(BE.REMOVE, "Remove", f"admin_remove_{giveaway_id}"),
        ],
        [
            btn_icon(BE.BAN, "Ban User", f"admin_ban_{giveaway_id}"),
            btn_icon(BE.UNBAN, "Unban", f"admin_unban_{giveaway_id}"),
        ],
    ])


# ─── Confirmation ────────────────────────────────────────────────

def confirm_keyboard(action: str, target: str = "") -> InlineKeyboardMarkup:
    prefix = f"{action}_{target}" if target else action
    return InlineKeyboardMarkup([
        [btn_green("Yes", f"confirm_{prefix}")],
        [btn_red("No", f"deny_{prefix}")],
    ])


# ─── Navigation ──────────────────────────────────────────────────

def back_keyboard(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn_icon(BE.BACK, "Back", callback_data)]
    ])


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn_icon(BE.GIVEAWAY, "Active Giveaways", "show_active")],
        [btn_icon(BE.INFO, "Help", "show_help")],
    ])
