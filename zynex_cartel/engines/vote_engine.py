"""
ZYNEX CARTEL — Vote Giveaway Engine
Handles vote-based giveaway logic.
"""

import logging
from telegram import Bot
from telegram.constants import ParseMode

from database import (
    add_vote, has_voted, get_vote_leaderboard, get_vote_count,
    get_all_participants, get_participant_count, add_winner,
    get_giveaway, admin_adjust_votes, add_audit_log,
    is_participant, is_banned
)
from utils import E, mention_user, user_display, from_utc_iso
from utils.announcements import AnnouncementManager

logger = logging.getLogger("zynex.engines.vote")


class VoteGiveawayEngine:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.announcer = AnnouncementManager(bot)

    async def cast_vote(self, giveaway_id: int, voter_id: int, target_id: int) -> dict:
        """
        Cast a vote. Returns result dict:
        {"success": bool, "reason": str}
        """
        # Check voter not banned
        if await is_banned(voter_id):
            return {"success": False, "reason": "banned"}

        # Check voter is a participant
        if not await is_participant(giveaway_id, voter_id):
            return {"success": False, "reason": "not_participant"}

        # Check target is a participant
        if not await is_participant(giveaway_id, target_id):
            return {"success": False, "reason": "target_not_participant"}

        # Check voter hasn't already voted
        if await has_voted(giveaway_id, voter_id):
            return {"success": False, "reason": "already_voted"}

        # Record vote
        success = await add_vote(giveaway_id, voter_id, target_id)
        if success:
            await add_audit_log(
                action="vote_cast",
                admin_id=voter_id,
                giveaway_id=giveaway_id,
                target_user_id=target_id,
            )
            return {"success": True, "reason": "voted"}
        else:
            return {"success": False, "reason": "already_voted"}

    async def select_winners(self, giveaway_id: int) -> list[dict]:
        """
        Select winners based on vote counts.
        Returns list of winner dicts.
        """
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway:
            return []

        winner_count = giveaway["winner_count"]
        leaderboard = await get_vote_leaderboard(giveaway_id, limit=winner_count + 10)

        if not leaderboard:
            return []

        # Group by vote count for tie detection
        winners = []
        position = 1

        for i, row in enumerate(leaderboard):
            if position > winner_count:
                break

            uid = row["target_id"]
            vote_count = row["vote_count"]

            # Check for ties
            tied_users = []
            for j in range(i, len(leaderboard)):
                if leaderboard[j]["vote_count"] == vote_count:
                    tied_users.append(leaderboard[j]["target_id"])
                else:
                    break

            if len(tied_users) > 1:
                # Tie: select randomly from tied users
                import random
                random.shuffle(tied_users)
                for tu in tied_users:
                    if position > winner_count:
                        break
                    winners.append({
                        "user_id": tu,
                        "position": position,
                        "selection_method": "VOTE",
                    })
                    position += 1
                # Skip already processed tied users
                i += len(tied_users) - 1
            else:
                winners.append({
                    "user_id": uid,
                    "position": position,
                    "selection_method": "VOTE",
                })
                position += 1

        return winners[:winner_count]

    async def get_leaderboard_display(self, giveaway_id: int, limit: int = 10) -> str:
        """Get formatted leaderboard text."""
        leaderboard = await get_vote_leaderboard(giveaway_id, limit)

        if not leaderboard:
            return f"{E.INFO} No votes yet."

        medals = [E.MEDAL_1, E.MEDAL_2, E.MEDAL_3]
        lines = []
        for i, row in enumerate(leaderboard):
            medal = medals[i] if i < 3 else f"#{i+1}"
            uid = row["target_id"]
            count = row["vote_count"]
            lines.append(f"{medal} {mention_user(uid)} — <b>{count}</b> votes")

        return "\n".join(lines)
