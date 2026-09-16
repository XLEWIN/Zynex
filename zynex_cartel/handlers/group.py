"""
ZYNEX CARTEL — Group Message Handler
Handles random participation and slot attempts in giveaway groups.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

from config import GIVEAWAY_GROUP_ID, GiveawayType, GiveawayStatus, MANDATORY_CHANNELS
from database import (
    get_active_giveaways, get_giveaway, is_banned, is_participant,
    get_participant_count
)
from utils import E
from engines.random_engine import RandomGiveawayEngine
from engines.slot_engine import SlotGiveawayEngine
from utils.announcements import AnnouncementManager

logger = logging.getLogger("zynex.handlers.group")


class GroupMessageHandler:
    def __init__(self, bot):
        self.bot = bot
        self.random_engine = RandomGiveawayEngine(bot)
        self.slot_engine = SlotGiveawayEngine(bot)
        self.announcer = AnnouncementManager(bot)

    async def _check_membership(self, user_id: int) -> list[int]:
        """Check which mandatory channels the user has NOT joined.
        Returns list of channel IDs the user needs to join."""
        not_joined = []
        for channel_id in MANDATORY_CHANNELS:
            try:
                member = await self.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status in ["left", "kicked"]:
                    not_joined.append(channel_id)
            except Exception as e:
                logger.warning(f"Could not check membership for channel {channel_id}: {e}")
                # If we can't check, assume not joined
                not_joined.append(channel_id)
        return not_joined

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all non-command messages in the giveaway group."""
        message = update.effective_message
        if not message or not message.text:
            return

        chat = update.effective_chat
        user = update.effective_user

        # Only process in the configured giveaway group
        if chat.id != GIVEAWAY_GROUP_ID:
            return

        # Ignore bot messages
        if user and user.is_bot:
            return

        # Ignore commands
        if message.text.startswith("/"):
            return

        if not user:
            return

        user_id = user.id

        # Check banned
        if await is_banned(user_id):
            return

        # Get active giveaways for this group
        active = await get_active_giveaways(GIVEAWAY_GROUP_ID)
        if not active:
            return

        text = message.text.strip()

        for giveaway in active:
            gid = giveaway["giveaway_id"]
            gtype = giveaway["type"]
            status = giveaway["status"]

            if status != GiveawayStatus.ACTIVE:
                continue

            # ─── Slot Giveaway ──────────────────────────────
            if gtype == GiveawayType.SLOT:
                # Check for slot emoji or slot result
                if text in ["🎰", "slot"] or self._is_slot_result(text):
                    result = await self.slot_engine.process_attempt(
                        gid, user_id, message.message_id, chat.id, text
                    )

                    if result["is_winner"]:
                        await self.announcer.send_slot_result(
                            chat.id, user_id, result["result"], True
                        )

                        # Check if all winners found
                        from database import get_slot_winners_count
                        winner_count = await get_slot_winners_count(gid)
                        if winner_count >= giveaway["winner_count"]:
                            # Auto-end
                            from scheduler import GiveawayScheduler
                            scheduler = GiveawayScheduler(self.bot)
                            await scheduler._end_giveaway(giveaway)
                    elif result["result"] != "banned":
                        # Only react for non-banned, non-winning attempts
                        pass  # Don't spam for every attempt

                    return  # Slot messages are handled, don't also register as random

            # ─── Random Giveaway ────────────────────────────
            if gtype == GiveawayType.RANDOM:
                # Check mandatory channel membership FIRST
                not_joined = await self._check_membership(user_id)

                if not_joined:
                    # User hasn't joined all channels - tell them to join
                    channel_links = []
                    for ch_id in not_joined:
                        # Convert -100XXXXXXXXXX to t.me/c/XXXXXXXXXX
                        chat_id_str = str(ch_id).replace("-100", "")
                        channel_links.append(f"https://t.me/c/{chat_id_str}")

                    links_text = "\n".join([f"• {link}" for link in channel_links])
                    await message.reply_text(
                        f"{E.LOCK} You must join our channels first to participate!\n\n"
                        f"Join here:\n{links_text}\n\n"
                        f"{E.CHECK} Then send any message to register!",
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                    return

                # User is a member - register them
                result = await self.random_engine.register_participant(gid, user_id)

                if result["success"]:
                    # Send confirmation reply
                    try:
                        await message.reply_text(
                            f"{E.CHECK} You have been registered for <b>{giveaway['name']}</b>!\n"
                            f"Good luck! {E.FIRE}",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send registration confirmation: {e}")

                # Only register for the first active random giveaway
                return

    def _is_slot_result(self, text: str) -> bool:
        """Check if text looks like a slot game result."""
        import re
        # Common slot result patterns
        patterns = [
            r"7️⃣\s*7️⃣\s*7️⃣",
            r"[7🍒🍋🍊🍇💎🔔⭐]\s*[7🍒🍋🍊🍇💎🔔⭐]\s*[7🍒🍋🍊🍇💎🔔⭐]",
            r"7\s*7\s*7",
        ]
        for p in patterns:
            if re.search(p, text):
                return True
        return False

    def get_handlers(self):
        return [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.Chat(GIVEAWAY_GROUP_ID),
                self.handle_message,
            ),
        ]
