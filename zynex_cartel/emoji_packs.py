"""
ZYNEX CARTEL — Emoji Pack System
Uses the Robin-style custom Telegram emoji display:
<tg-emoji emoji-id="CUSTOM_EMOJI_ID">fallback</tg-emoji>

Custom emoji IDs provided:
- 6237533282599180408
- 5447410659077661506
- 5193035865147849172
- 5285350148451344065
- 5039667320356603311
- 6269557701219456424
- 6271797509484450259
- 6219549292458150316
- 6255685257501083955
- 6296508771325707891
- 6296367896398399651
- 6231051773222586793
- 6219525412439984045
- 6222029992553875665
- 6131931813590864308
- 6132092002986103018
- 6132099940085665914
"""

import random
import logging
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger("zynex.emoji_packs")

# ========== CUSTOM EMOJI IDS ==========
CUSTOM_EMOJI_IDS = [
    "6237533282599180408",
    "5447410659077661506",
    "5193035865147849172",
    "5285350148451344065",
    "5039667320356603311",
    "6269557701219456424",
    "6271797509484450259",
    "6219549292458150316",
    "6255685257501083955",
    "6296508771325707891",
    "6296367896398399651",
    "6231051773222586793",
    "6219525412439984045",
    "6222029992553875665",
    "6131931813590864308",
    "6132092002986103018",
    "6132099940085665914",
]

# ========== EMOJI CATEGORY MAPPING ==========
# Maps category -> list of (fallback_emoji, custom_emoji_id) tuples
# Categories are themed for the Zynex Cartel giveaway bot

EMOJI_MAP: Dict[str, List[Tuple[str, str]]] = {
    # ─── Giveaway Core ────────────────────────────────────────
    "giveaway": [
        ("🎉", "6237533282599180408"),   # Party/celebration
        ("🎁", "6269557701219456424"),   # Gift
        ("🎫", "6271797509484450259"),   # Ticket
        ("🎰", "6219549292458150316"),   # Slot machine
        ("🎲", "6222029992553875665"),   # Dice
    ],
    "winner": [
        ("🏆", "5039667320356603311"),   # Trophy
        ("👑", "6237533282599180408"),   # Crown
        ("🥇", "6255685257501083955"),   # Gold medal
        ("🥈", "6296508771325707891"),   # Silver medal
        ("🥉", "6296367896398399651"),   # Bronze medal
    ],
    "success": [
        ("✅", "6231051773222586793"),   # Check mark
        ("🔥", "5447410659077661506"),   # Fire
        ("⭐", "5193035865147849172"),   # Star
        ("💎", "5285350148451344065"),   # Diamond
        ("🎉", "6222029992553875665"),   # Party
    ],
    "error": [
        ("❌", "6219525412439984045"),   # Cross mark
        ("🚫", "6296508771325707891"),   # Prohibited
        ("⛔", "6219525412439984045"),   # Stop
        ("💀", "6132099940085665914"),   # Skull
    ],
    "warning": [
        ("⚠️", "6296367896398399651"),   # Warning
        ("⚡", "6131931813590864308"),   # Lightning
        ("🔔", "6271797509484450259"),   # Bell
        ("📌", "6255685257501083955"),   # Pin
    ],
    "info": [
        ("ℹ️", "5193035865147849172"),   # Info
        ("📊", "6255685257501083955"),   # Chart
        ("📋", "6271797509484450259"),   # Clipboard
        ("💬", "6132092002986103018"),   # Speech bubble
    ],
    "shield": [
        ("🛡️", "6296508771325707891"),   # Shield
        ("🔒", "6296367896398399651"),   # Lock
        ("🔓", "6231051773222586793"),   # Unlock
        ("⚜️", "5285350148451344065"),   # Fleur-de-lis
    ],
    "action": [
        ("🚀", "6131931813590864308"),   # Rocket
        ("💎", "5285350148451344065"),   # Diamond
        ("🔥", "5447410659077661506"),   # Fire
        ("⚡", "6131931813590864308"),   # Lightning
        ("✨", "6222029992553875665"),   # Sparkle
    ],
    "vote": [
        ("🗳️", "6271797509484450259"),   # Ballot box
        ("🗳", "6271797509484450259"),   # Ballot box alt
        ("✅", "6231051773222586793"),   # Check
        ("👤", "6132092002986103018"),   # Person
    ],
    "slot": [
        ("🎰", "6219549292458150316"),   # Slot machine
        ("7️⃣", "5447410659077661506"),   # Seven
        ("💎", "5285350148451344065"),   # Diamond
        ("🔔", "6271797509484450259"),   # Bell
    ],
    "crown": [
        ("👑", "6237533282599180408"),   # Crown
        ("💎", "5285350148451344065"),   # Diamond
        ("⭐", "5193035865147849172"),   # Star
        ("🏆", "5039667320356603311"),   # Trophy
    ],
    "time": [
        ("⏰", "6271797509484450259"),   # Clock
        ("⏳", "6255685257501083955"),   # Hourglass
        ("🕐", "6131931813590864308"),   # Clock one
    ],
    "people": [
        ("👤", "6132092002986103018"),   # Person
        ("👥", "6132092002986103018"),   # People
        ("🤝", "6132092002986103018"),   # Handshake
    ],
    "admin": [
        ("🛡️", "6296508771325707891"),   # Shield
        ("⚙️", "6296367896398399651"),   # Gear
        ("🔧", "6255685257501083955"),   # Wrench
    ],
    "start": [
        ("🎉", "6237533282599180408"),   # Party
        ("✨", "6222029992553875665"),   # Sparkle
        ("🚀", "6131931813590864308"),   # Rocket
        ("👋", "6132092002986103018"),   # Wave
    ],
    "ban": [
        ("🚫", "6219525412439984045"),   # Prohibited
        ("⛔", "6219525412439984045"),   # Stop
        ("💀", "6132099940085665914"),   # Skull
    ],
    "unban": [
        ("♻️", "6231051773222586793"),   # Recycle
        ("✅", "6231051773222586793"),   # Check
        ("🔓", "6231051773222586793"),   # Unlock
    ],
    "add": [
        ("➕", "6231051773222586793"),   # Plus
        ("✅", "6231051773222586793"),   # Check
        ("📝", "6271797509484450259"),   # Memo
    ],
    "remove": [
        ("➖", "6219525412439984045"),   # Minus
        ("❌", "6219525412439984045"),   # Cross
        ("🗑️", "6219525412439984045"),   # Trash
    ],
    "end": [
        ("⏹️", "6296367896398399651"),   # Stop button
        ("🔴", "6219525412439984045"),   # Red circle
        ("🏁", "6222029992553875665"),   # Checkered flag
    ],
    "medal_1": [
        ("🥇", "6255685257501083955"),   # Gold medal
    ],
    "medal_2": [
        ("🥈", "6296508771325707891"),   # Silver medal
    ],
    "medal_3": [
        ("🥉", "6296367896398399651"),   # Bronze medal
    ],
    "heart": [
        ("❤️", "6132092002986103018"),   # Heart
        ("💕", "6132092002986103018"),   # Two hearts
        ("💖", "6222029992553875665"),   # Sparkling heart
    ],
    "sparkle": [
        ("✨", "6222029992553875665"),   # Sparkle
        ("⭐", "5193035865147849172"),   # Star
        ("🌟", "5285350148451344065"),   # Glowing star
    ],
}


def custom_emoji(emoji_char: str, custom_emoji_id: str) -> str:
    """
    Format a custom emoji in HTML format for Telegram.
    
    Format: <tg-emoji emoji-id="CUSTOM_EMOJI_ID">fallback</tg-emoji>
    
    Args:
        emoji_char: The fallback emoji character
        custom_emoji_id: The custom_emoji_id from Telegram
    
    Returns:
        Formatted HTML string
    """
    if not custom_emoji_id:
        return emoji_char
    return f'<tg-emoji emoji-id="{custom_emoji_id}">{emoji_char}</tg-emoji>'


def get_emoji_from_category(category: str) -> Tuple[str, str]:
    """
    Get a random (fallback_emoji, custom_emoji_id) tuple from a category.
    
    Args:
        category: Category name from EMOJI_MAP
    
    Returns:
        Tuple of (fallback_emoji, custom_emoji_id)
    """
    if category in EMOJI_MAP and EMOJI_MAP[category]:
        return random.choice(EMOJI_MAP[category])
    
    # Default fallback
    return ("✨", "6222029992553875665")


def get_emoji(category: str = None) -> str:
    """
    Get a formatted custom emoji in HTML format.
    
    Args:
        category: Optional category name. If None, returns random from all.
    
    Returns:
        HTML formatted custom emoji string
    """
    if category:
        fallback, custom_id = get_emoji_from_category(category)
    else:
        categories = list(EMOJI_MAP.keys())
        cat = random.choice(categories)
        fallback, custom_id = get_emoji_from_category(cat)
    
    return custom_emoji(fallback, custom_id)


def get_emoji_text(category: str = None) -> str:
    """
    Get just the fallback emoji text (no custom formatting).
    
    Args:
        category: Optional category name
    
    Returns:
        Plain emoji character
    """
    if category:
        fallback, _ = get_emoji_from_category(category)
    else:
        categories = list(EMOJI_MAP.keys())
        cat = random.choice(categories)
        fallback, _ = get_emoji_from_category(cat)
    
    return fallback


# ========== QUICK ACCESS FUNCTIONS ==========
# Each returns the formatted custom emoji for that category

def giveaway() -> str:
    """Random giveaway emoji."""
    return get_emoji("giveaway")

def winner() -> str:
    """Random winner emoji."""
    return get_emoji("winner")

def success() -> str:
    """Random success emoji."""
    return get_emoji("success")

def error() -> str:
    """Random error emoji."""
    return get_emoji("error")

def warning() -> str:
    """Random warning emoji."""
    return get_emoji("warning")

def info() -> str:
    """Random info emoji."""
    return get_emoji("info")

def shield() -> str:
    """Random shield emoji."""
    return get_emoji("shield")

def action() -> str:
    """Random action emoji."""
    return get_emoji("action")

def vote() -> str:
    """Random vote emoji."""
    return get_emoji("vote")

def slot() -> str:
    """Random slot emoji."""
    return get_emoji("slot")

def crown() -> str:
    """Crown emoji."""
    return get_emoji("crown")

def clock() -> str:
    """Random time emoji."""
    return get_emoji("time")

def hourglass() -> str:
    """Hourglass emoji."""
    return custom_emoji("⏳", "6255685257501083955")

def people() -> str:
    """Random people emoji."""
    return get_emoji("people")

def admin() -> str:
    """Random admin emoji."""
    return get_emoji("admin")

def start() -> str:
    """Start emoji."""
    return get_emoji("start")

def ban() -> str:
    """Ban emoji."""
    return get_emoji("ban")

def unban() -> str:
    """Unban emoji."""
    return get_emoji("unban")

def add() -> str:
    """Add emoji."""
    return get_emoji("add")

def remove() -> str:
    """Remove emoji."""
    return get_emoji("remove")

def end() -> str:
    """End emoji."""
    return get_emoji("end")

def medal_1() -> str:
    """Gold medal."""
    return custom_emoji("🥇", "6255685257501083955")

def medal_2() -> str:
    """Silver medal."""
    return custom_emoji("🥈", "6296508771325707891")

def medal_3() -> str:
    """Bronze medal."""
    return custom_emoji("🥉", "6296367896398399651")

def heart() -> str:
    """Random heart emoji."""
    return get_emoji("heart")

def sparkle() -> str:
    """Random sparkle emoji."""
    return get_emoji("sparkle")

def name_tag() -> str:
    """Name tag emoji."""
    return custom_emoji("📛", "6271797509484450259")

def group() -> str:
    """Group/location emoji."""
    return custom_emoji("📍", "6255685257501083955")

def channel() -> str:
    """Channel emoji."""
    return custom_emoji("📢", "6271797509484450259")

def bullet() -> str:
    """Separator line."""
    return "━━━━━━━━━━━━━━"

def arrow() -> str:
    """Arrow emoji."""
    return custom_emoji("➡️", "6231051773222586793")

def question() -> str:
    """Question emoji."""
    return custom_emoji("❓", "6296367896398399651")

def check() -> str:
    """Check mark emoji."""
    return custom_emoji("✅", "6231051773222586793")

def cross() -> str:
    """Cross mark emoji."""
    return custom_emoji("❌", "6219525412439984045")

def fire() -> str:
    """Fire emoji."""
    return custom_emoji("🔥", "5447410659077661506")

def diamond() -> str:
    """Diamond emoji."""
    return custom_emoji("💎", "5285350148451344065")

def star() -> str:
    """Star emoji."""
    return custom_emoji("⭐", "5193035865147849172")

def rocket() -> str:
    """Rocket emoji."""
    return custom_emoji("🚀", "6131931813590864308")

def trophy() -> str:
    """Trophy emoji."""
    return custom_emoji("🏆", "5039667320356603311")

def gift() -> str:
    """Gift emoji."""
    return custom_emoji("🎁", "6269557701219456424")

def lightning() -> str:
    """Lightning emoji."""
    return custom_emoji("⚡", "6131931813590864308")

def skull() -> str:
    """Skull emoji."""
    return custom_emoji("💀", "6132099940085665914")

def pin() -> str:
    """Pin emoji."""
    return custom_emoji("📌", "6255685257501083955")

def lock() -> str:
    """Lock emoji."""
    return custom_emoji("🔒", "6296367896398399651")

def unlock() -> str:
    """Unlock emoji."""
    return custom_emoji("🔓", "6231051773222586793")

def chart() -> str:
    """Chart emoji."""
    return custom_emoji("📊", "6255685257501083955")

def ticket() -> str:
    """Ticket emoji."""
    return custom_emoji("🎫", "6271797509484450259")


# ========== EMOJI CLASS (for E.XXX access) ==========

class E:
    """
    Emoji constants class for consistent bot branding.
    Uses custom Telegram emojis via <tg-emoji> tags.
    
    Usage:
        f"{E.CROWN} Hello!"
        f"{E.FIRE} Giveaway active!"
    """
    # Core
    CROWN       = crown()
    FIRE        = fire()
    STAR        = star()
    DIAMOND     = diamond()
    TROPHY      = trophy()
    GIFT        = gift()
    TICKET      = ticket()
    SLOT        = slot()
    CHART       = chart()
    SHIELD      = shield()
    LIGHTNING   = lightning()
    CHECK       = check()
    CROSS       = cross()
    PARTY       = giveaway()
    ROCKET      = rocket()
    HEART       = heart()
    SKULL       = skull()
    SPARKLE     = sparkle()

    # Giveaway specific
    NAME_TAG    = name_tag()
    CLOCK       = clock()
    HOURGLASS   = hourglass()
    WINNER      = winner()
    MEDAL_1     = medal_1()
    MEDAL_2     = medal_2()
    MEDAL_3     = medal_3()
    GIVEAWAY    = giveaway()
    SLOT_MACHINE= slot()
    VOTE        = vote()
    GROUP       = group()
    CHANNEL     = channel()
    BULLET      = bullet()
    ARROW       = arrow()
    PERSON      = people()
    USERS       = people()
    PIN         = pin()
    LOCK        = lock()
    UNLOCK      = unlock()
    BAN         = ban()
    UNBAN       = unban()
    ADD         = add()
    REMOVE      = remove()
    END         = end()
    START       = start()
    WARNING     = warning()
    INFO        = info()
    QUESTION    = question()
