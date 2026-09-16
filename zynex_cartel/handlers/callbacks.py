"""
ZYNEX CARTEL — Callback Handlers
Handle inline keyboard interactions for giveaway participation.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

from config import GiveawayType, GiveawayStatus
from database import (
    get_giveaway, get_all_participants, is_banned,
    get_participant_count, get_vote_leaderboard
)
from utils import E, mention_user, user_display
from utils.keyboards import (
    vote_keyboard, giveaway_info_keyboard, main_menu_keyboard
)
from engines.vote_engine import VoteGiveawayEngine
from engines.random_engine import RandomGiveawayEngine
from engines.slot_engine import SlotGiveawayEngine
from utils.announcements import AnnouncementManager

logger = logging.getLogger("zynex.handlers.callbacks")


class CallbackManager:
    def __init__(self, bot):
        self.bot = bot
        self.vote_engine = VoteGiveawayEngine(bot)
        self.random_engine = RandomGiveawayEngine(bot)
        self.slot_engine = SlotGiveawayEngine(bot)
        self.announcer = AnnouncementManager(bot)

    def get_handlers(self):
        return [
            CallbackQueryHandler(self._noop, pattern="^noop$"),
            CallbackQueryHandler(self._vote_start, pattern=r"^vote_start_\d+$"),
            CallbackQueryHandler(self._vote_cast, pattern=r"^vote_\d+_\d+$"),
            CallbackQueryHandler(self._vote_confirm, pattern=r"^vote_confirm_\d+_\d+$"),
            CallbackQueryHandler(self._vote_cancel, pattern=r"^vote_cancel_\d+$"),
            CallbackQueryHandler(self._join_random, pattern=r"^join_random_\d+$"),
            CallbackQueryHandler(self._info_slot, pattern=r"^info_slot_\d+$"),
            CallbackQueryHandler(self._leaderboard, pattern=r"^leaderboard_\d+$"),
            CallbackQueryHandler(self._admin_end, pattern=r"^admin_end_\d+$"),
            CallbackQueryHandler(self._admin_winner_prompt, pattern=r"^admin_winner_\d+$"),
            CallbackQueryHandler(self._admin_add_prompt, pattern=r"^admin_add_\d+$"),
            CallbackQueryHandler(self._admin_remove_prompt, pattern=r"^admin_remove_\d+$"),
            CallbackQueryHandler(self._admin_ban_prompt, pattern=r"^admin_ban_\d+$"),
            CallbackQueryHandler(self._admin_unban_prompt, pattern=r"^admin_unban_\d+$"),
        ]

    async def _noop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()

    async def _vote_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show vote buttons for a vote giveaway."""
        query = update.callback_query
        await query.answer()

        data = query.data
        try:
            gid = int(data.split("_")[-1])
        except (ValueError, IndexError):
            return

        giveaway = await get_giveaway(gid)
        if not giveaway or giveaway["status"] != GiveawayStatus.ACTIVE:
            await query.answer("Giveaway is not active.", show_alert=True)
            return

        user_id = query.from_user.id
        if await is_banned(user_id):
            await query.answer("You are banned.", show_alert=True)
            return

        # Get participants as candidates
        participants = await get_all_participants(gid)
        if not participants:
            await query.answer("No participants yet.", show_alert=True)
            return

        # Build candidate list with vote counts
        candidates = []
        for p in participants:
            uid = p["user_id"]
            vote_count = 0
            # Get vote count from leaderboard
            from database import get_vote_count
            vote_count = await get_vote_count(gid, uid)
            candidates.append({
                "user_id": uid,
                "display_name": f"User {uid}",
                "vote_count": vote_count,
            })

        # Sort by vote count descending
        candidates.sort(key=lambda x: x["vote_count"], reverse=True)

        keyboard = vote_keyboard(gid, candidates)
        await query.edit_message_reply_markup(reply_markup=keyboard)

    async def _vote_cast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle vote button press (show confirmation)."""
        query = update.callback_query
        await query.answer()

        data = query.data
        # Pattern: vote_{gid}_{target_id}
        parts = data.split("_")
        try:
            gid = int(parts[1])
            target_id = int(parts[2])
        except (ValueError, IndexError):
            return

        voter_id = query.from_user.id

        if await is_banned(voter_id):
            await query.answer("You are banned.", show_alert=True)
            return

        # Check if already voted
        from database import has_voted
        if await has_voted(gid, voter_id):
            await query.answer("You already voted.", show_alert=True)
            return

        # Show confirmation
        from utils.keyboards import vote_confirm_keyboard
        keyboard = vote_confirm_keyboard(gid, target_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)

    async def _vote_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm and cast vote."""
        query = update.callback_query

        data = query.data
        parts = data.split("_")
        try:
            gid = int(parts[2])
            target_id = int(parts[3])
        except (ValueError, IndexError):
            await query.answer("Invalid callback data.")
            return

        voter_id = query.from_user.id

        result = await self.vote_engine.cast_vote(gid, voter_id, target_id)

        if result["success"]:
            await query.answer("Vote recorded!", show_alert=True)
            # Update the keyboard
            participants = await get_all_participants(gid)
            candidates = []
            for p in participants:
                uid = p["user_id"]
                from database import get_vote_count
                vote_count = await get_vote_count(gid, uid)
                candidates.append({
                    "user_id": uid,
                    "display_name": f"User {uid}",
                    "vote_count": vote_count,
                })
            candidates.sort(key=lambda x: x["vote_count"], reverse=True)
            keyboard = vote_keyboard(gid, candidates)
            await query.edit_message_reply_markup(reply_markup=keyboard)
        else:
            reason = result["reason"]
            if reason == "already_voted":
                await query.answer("You already voted.", show_alert=True)
            elif reason == "banned":
                await query.answer("You are banned.", show_alert=True)
            elif reason == "not_participant":
                await query.answer("You must join first.", show_alert=True)
            else:
                await query.answer("Could not record vote.", show_alert=True)

    async def _vote_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel vote and go back to vote list."""
        query = update.callback_query
        await query.answer()

        data = query.data
        try:
            gid = int(data.split("_")[-1])
        except (ValueError, IndexError):
            return

        # Rebuild vote keyboard
        participants = await get_all_participants(gid)
        candidates = []
        for p in participants:
            uid = p["user_id"]
            from database import get_vote_count
            vote_count = await get_vote_count(gid, uid)
            candidates.append({
                "user_id": uid,
                "display_name": f"User {uid}",
                "vote_count": vote_count,
            })
        candidates.sort(key=lambda x: x["vote_count"], reverse=True)
        keyboard = vote_keyboard(gid, candidates)
        await query.edit_message_reply_markup(reply_markup=keyboard)

    async def _join_random(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle random giveaway participation button."""
        query = update.callback_query

        data = query.data
        try:
            gid = int(data.split("_")[-1])
        except (ValueError, IndexError):
            await query.answer("Invalid.")
            return

        user_id = query.from_user.id
        giveaway = await get_giveaway(gid)

        if not giveaway or giveaway["status"] != GiveawayStatus.ACTIVE:
            await query.answer("Giveaway not active.", show_alert=True)
            return

        result = await self.random_engine.register_participant(gid, user_id)

        if result["success"]:
            await query.answer(
                f"You are registered for {giveaway['name']}!",
                show_alert=True,
            )
        elif result["reason"] == "already_participating":
            await query.answer("Already participating.", show_alert=True)
        elif result["reason"] == "banned":
            await query.answer("You are banned.", show_alert=True)
        elif result["reason"] == "removed":
            await query.answer("You were removed by an admin.", show_alert=True)
        else:
            await query.answer("Could not register.", show_alert=True)

    async def _info_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show slot giveaway instructions."""
        query = update.callback_query
        await query.answer()

        data = query.data
        try:
            gid = int(data.split("_")[-1])
        except (ValueError, IndexError):
            return

        giveaway = await get_giveaway(gid)
        if not giveaway:
            return

        text = (
            f"SLOT GIVEAWAY\n\n"
            f"{giveaway['name']}\n\n"
            f"How to play:\n"
            f"Send the slot emoji in the giveaway group.\n"
            f"Match 7 7 7 to win!\n\n"
            f"Winners: {giveaway['winner_count']}\n\n"
            f"First triple-7 result wins!"
        )

        await query.answer(text, show_alert=True)

    async def _leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show vote leaderboard."""
        query = update.callback_query
        await query.answer()

        data = query.data
        try:
            gid = int(data.split("_")[-1])
        except (ValueError, IndexError):
            return

        leaderboard = await get_vote_leaderboard(gid, limit=10)

        if not leaderboard:
            await query.answer("No votes yet.", show_alert=True)
            return

        medals = ["1.", "2.", "3."]
        lines = []
        for i, row in enumerate(leaderboard):
            medal = medals[i] if i < 3 else f"#{i+1}"
            uid = row["target_id"]
            count = row["vote_count"]
            lines.append(f"{medal} User {uid} - {count} votes")

        text = "\n".join(lines)
        await query.answer(text, show_alert=True)

    # ─── Admin Callbacks ──────────────────────────────────────

    async def _admin_end(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin end giveaway button."""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        from utils.permissions import is_admin as check_admin
        if not check_admin(user_id):
            return

        data = query.data
        try:
            gid = int(data.split("_")[-1])
        except (ValueError, IndexError):
            return

        giveaway = await get_giveaway(gid)
        if not giveaway:
            return

        from scheduler import GiveawayScheduler
        scheduler = GiveawayScheduler(self.bot)
        await scheduler._end_giveaway(giveaway)

        await query.edit_message_text(
            f"Giveaway #{gid} has been ended.",
            parse_mode=ParseMode.HTML,
        )

    async def _admin_winner_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for admin winner override."""
        query = update.callback_query
        user_id = query.from_user.id
        from utils.permissions import is_admin as check_admin
        if not check_admin(user_id):
            await query.answer()
            return
        await query.answer("Send: /winner [userid]", show_alert=True)

    async def _admin_add_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for admin add."""
        query = update.callback_query
        user_id = query.from_user.id
        from utils.permissions import is_admin as check_admin
        if not check_admin(user_id):
            await query.answer()
            return
        await query.answer("Send: /add [userid]", show_alert=True)

    async def _admin_remove_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for admin remove."""
        query = update.callback_query
        user_id = query.from_user.id
        from utils.permissions import is_admin as check_admin
        if not check_admin(user_id):
            await query.answer()
            return
        await query.answer("Send: /remove [userid]", show_alert=True)

    async def _admin_ban_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for admin ban."""
        query = update.callback_query
        user_id = query.from_user.id
        from utils.permissions import is_admin as check_admin
        if not check_admin(user_id):
            await query.answer()
            return
        await query.answer("Send: /ban [userid]", show_alert=True)

    async def _admin_unban_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for admin unban."""
        query = update.callback_query
        user_id = query.from_user.id
        from utils.permissions import is_admin as check_admin
        if not check_admin(user_id):
            await query.answer()
            return
        await query.answer("Send: /unban [userid]", show_alert=True)
