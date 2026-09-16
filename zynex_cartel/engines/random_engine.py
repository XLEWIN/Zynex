"""
ZYNEX CARTEL — Random Giveaway Engine
Handles random giveaway participation and winner selection.
"""

import logging
import secrets
from telegram import Bot

from database import (
    add_participant, is_participant, get_all_participants,
    get_participant_count, get_giveaway, is_banned,
    add_winner, is_removed_from_giveaway, add_audit_log
)
from utils import E, mention_user

logger = logging.getLogger("zynex.engines.random")


class RandomGiveawayEngine:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def register_participant(self, giveaway_id: int, user_id: int) -> dict:
        """
        Register a user as participant.
        Returns result dict: {"success": bool, "reason": str}
        """
        # Check banned
        if await is_banned(user_id):
            return {"success": False, "reason": "banned"}

        # Check if removed by admin
        if await is_removed_from_giveaway(giveaway_id, user_id):
            return {"success": False, "reason": "removed"}

        # Check if already participating
        if await is_participant(giveaway_id, user_id):
            return {"success": False, "reason": "already_participating"}

        # Register
        success = await add_participant(giveaway_id, user_id)
        if success:
            await add_audit_log(
                action="participant_added_random",
                giveaway_id=giveaway_id,
                target_user_id=user_id,
            )
            return {"success": True, "reason": "registered"}
        else:
            return {"success": False, "reason": "already_participating"}

    async def select_winners(self, giveaway_id: int) -> list[dict]:
        """
        Select random winners using cryptographically secure randomness.
        Returns list of winner dicts.
        """
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway:
            return []

        winner_count = giveaway["winner_count"]

        # Get all active participants
        participants = await get_all_participants(giveaway_id)
        if not participants:
            return []

        user_ids = [p["user_id"] for p in participants]

        # Ensure we don't select more winners than participants
        actual_count = min(winner_count, len(user_ids))

        if actual_count == 0:
            return []

        # Cryptographically secure random selection
        selected_indices = set()
        winners = []

        for pos in range(1, actual_count + 1):
            # Keep selecting until we get a unique index
            while True:
                idx = secrets.randbelow(len(user_ids))
                if idx not in selected_indices:
                    selected_indices.add(idx)
                    winners.append({
                        "user_id": user_ids[idx],
                        "position": pos,
                        "selection_method": "RANDOM",
                    })
                    break

        return winners

    async def get_participant_count_display(self, giveaway_id: int) -> int:
        """Get the current participant count."""
        return await get_participant_count(giveaway_id)
