"""
ZYNEX CARTEL — Slot Giveaway Engine
Handles slot machine giveaway with triple-7 detection.
"""

import logging
import re
import secrets
from telegram import Bot

from database import (
    add_slot_attempt, get_slot_winners_count, has_slot_winner,
    add_winner, get_giveaway, is_banned, is_participant,
    add_participant, add_audit_log
)
from utils import E, mention_user

logger = logging.getLogger("zynex.engines.slot")

# Slot results: possible values from Telegram slot game
SLOT_SYMBOLS = ["7️⃣", "🍒", "🍋", "🍊", "🍇", "💎", "🔔", "⭐"]
WINNING_RESULT = "7️⃣ 7️⃣ 7️⃣"


class SlotGiveawayEngine:
    def __init__(self, bot: Bot):
        self.bot = bot

    def parse_slot_result(self, message_text: str) -> tuple[bool, str]:
        """
        Parse slot result from message text.
        Returns (is_triple_7, formatted_result).
        
        Detects various formats:
        - "7 7 7" (plain numbers)
        - "7️⃣ 7️⃣ 7️⃣" (emoji numbers)
        - "777" (combined)
        """
        if not message_text:
            return False, ""

        text = message_text.strip()

        # Check for triple 7 patterns
        patterns = [
            r"7️⃣\s*7️⃣\s*7️⃣",    # emoji seven
            r"7\s*7\s*7",            # plain seven
            r"777",                   # combined
        ]

        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True, "7️⃣ 7️⃣ 7️⃣"

        return False, text

    def is_slot_message(self, message_text: str) -> bool:
        """Check if a message is a slot emoji or slot game result."""
        if not message_text:
            return False
        text = message_text.strip()
        # Match slot emoji or common slot game patterns
        return text in ["🎰", "slot", "/slot"]

    async def process_attempt(
        self, giveaway_id: int, user_id: int, message_id: int,
        chat_id: int, message_text: str
    ) -> dict:
        """
        Process a slot attempt.
        Returns result dict: {"is_winner": bool, "result": str, "position": int|None}
        """
        # Check banned
        if await is_banned(user_id):
            return {"is_winner": False, "result": "banned", "position": None}

        # Auto-register for the giveaway if not already a participant
        if not await is_participant(giveaway_id, user_id):
            await add_participant(giveaway_id, user_id)

        # Parse the slot result
        is_triple_7, formatted = self.parse_slot_result(message_text)

        if not is_triple_7:
            # Record non-winning attempt
            await add_slot_attempt(
                giveaway_id, user_id, message_id, chat_id,
                formatted or message_text, is_winner=False
            )
            return {"is_winner": False, "result": formatted or message_text, "position": None}

        # Check if user already has a winning slot
        if await has_slot_winner(giveaway_id, user_id):
            await add_slot_attempt(
                giveaway_id, user_id, message_id, chat_id,
                WINNING_RESULT, is_winner=False
            )
            return {"is_winner": False, "result": WINNING_RESULT, "position": None}

        # Check how many winners already
        current_winners = await get_slot_winners_count(giveaway_id)
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway:
            return {"is_winner": False, "result": "error", "position": None}

        if current_winners >= giveaway["winner_count"]:
            # All winner slots filled
            await add_slot_attempt(
                giveaway_id, user_id, message_id, chat_id,
                WINNING_RESULT, is_winner=False
            )
            return {"is_winner": False, "result": WINNING_RESULT, "position": None}

        # This is a winner!
        position = current_winners + 1
        await add_slot_attempt(
            giveaway_id, user_id, message_id, chat_id,
            WINNING_RESULT, is_winner=True
        )

        await add_audit_log(
            action="slot_winner",
            giveaway_id=giveaway_id,
            target_user_id=user_id,
            metadata=f"position={position}",
        )

        return {
            "is_winner": True,
            "result": WINNING_RESULT,
            "position": position,
        }

    async def get_slot_winners(self, giveaway_id: int) -> list[dict]:
        """Get all slot winners for a giveaway."""
        from database import get_db
        db = await get_db()
        cursor = await db.execute(
            "SELECT user_id, created_at FROM slot_attempts WHERE giveaway_id = ? AND is_winner = 1 ORDER BY attempt_id",
            (giveaway_id,),
        )
        return await cursor.fetchall()
