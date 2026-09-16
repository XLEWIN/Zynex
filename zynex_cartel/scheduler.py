"""
ZYNEX CARTEL — Scheduler
Background task that auto-ends expired giveaways.
"""

import logging
import asyncio
from datetime import datetime, timezone

from telegram import Bot

from database import (
    get_scheduled_giveaways, get_active_giveaways, update_giveaway_status,
    get_all_participants, get_winners, add_winner, get_giveaway,
    add_audit_log, get_db, get_admin_winner_overrides
)
from config import GiveawayType
from utils import from_utc_iso, is_expired, is_started
from engines.vote_engine import VoteGiveawayEngine
from engines.random_engine import RandomGiveawayEngine
from engines.slot_engine import SlotGiveawayEngine
from utils.announcements import AnnouncementManager

logger = logging.getLogger("zynex.scheduler")


class GiveawayScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self._task = None
        self.vote_engine = VoteGiveawayEngine(bot)
        self.random_engine = RandomGiveawayEngine(bot)
        self.slot_engine = SlotGiveawayEngine(bot)
        self.announcer = AnnouncementManager(bot)

    async def start(self):
        """Start the scheduler background loop."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started.")

    async def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped.")

    async def _loop(self):
        """Main scheduler loop — checks every 30 seconds."""
        while self.running:
            try:
                await self._check_scheduled()
                await self._check_active()
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
            await asyncio.sleep(30)

    async def _check_scheduled(self):
        """Activate scheduled giveaways whose start time has arrived."""
        scheduled = await get_scheduled_giveaways()
        for g in scheduled:
            gid = g["giveaway_id"]
            try:
                if is_started(g["start_time"]):
                    # Activate
                    await update_giveaway_status(gid, "ACTIVE")
                    await add_audit_log(
                        action="giveaway_activated",
                        giveaway_id=gid,
                        new_state="ACTIVE",
                    )
                    logger.info(f"Giveaway {gid} activated (scheduled -> active)")

                    # Send announcement
                    await self.announcer.send_giveaway_announcement(g)
            except Exception as e:
                logger.error(f"Error activating giveaway {gid}: {e}")

    async def _check_active(self):
        """End active giveaways whose end time has passed."""
        active = await get_active_giveaways()
        for g in active:
            gid = g["giveaway_id"]
            try:
                if is_expired(g["end_time"]):
                    await self._end_giveaway(g)
            except Exception as e:
                logger.error(f"Error ending giveaway {gid}: {e}")

    async def _end_giveaway(self, giveaway: dict):
        """End a giveaway — select winners and announce."""
        gid = giveaway["giveaway_id"]
        gtype = giveaway["type"]

        # Mark as ENDING to prevent double processing
        await update_giveaway_status(gid, "ENDING")

        # Use a lock/transaction to prevent race conditions
        db = await get_db()
        cursor = await db.execute(
            "SELECT status FROM giveaways WHERE giveaway_id = ? AND status = 'ENDING'",
            (gid,),
        )
        row = await cursor.fetchone()
        if not row:
            # Already being processed by another worker
            logger.info(f"Giveaway {gid} already being processed, skipping.")
            return

        try:
            # First check for admin winner overrides — these take priority
            admin_overrides = await get_admin_winner_overrides(gid)

            if admin_overrides:
                # Use admin overrides as winners
                winners = []
                for i, override in enumerate(admin_overrides):
                    winners.append({
                        "user_id": override["target_user_id"],
                        "position": i + 1,
                        "selection_method": "ADMIN",
                    })
            else:
                # No admin overrides — select winners normally
                winners = []

                if gtype == GiveawayType.VOTE:
                    winners = await self.vote_engine.select_winners(gid)

                elif gtype == GiveawayType.RANDOM:
                    winners = await self.random_engine.select_winners(gid)

                elif gtype == GiveawayType.SLOT:
                    # Get slot winners from the database
                    slot_winners = await self.slot_engine.get_slot_winners(gid)
                    winners = [
                        {
                            "user_id": w["user_id"],
                            "position": i + 1,
                            "selection_method": "SLOT",
                        }
                        for i, w in enumerate(slot_winners)
                    ]

            # Save winners to database
            for w in winners:
                await add_winner(
                    giveaway_id=gid,
                    user_id=w["user_id"],
                    position=w["position"],
                    selection_method=w["selection_method"],
                )

            # Mark as ENDED
            await update_giveaway_status(gid, "ENDED")
            await add_audit_log(
                action="giveaway_ended",
                giveaway_id=gid,
                new_state="ENDED",
                metadata=f"winners={len(winners)}",
            )

            # Announce winners
            if winners:
                await self.announcer.send_winner_announcement(giveaway, winners)
            else:
                # No winners — announce that
                text = (
                    f"{E.INFO} <b>GIVEAWAY ENDED</b>\n\n"
                    f"{E.GIFT} {giveaway['name']}\n\n"
                    f"No eligible winners found."
                )
                for target_id in [giveaway["group_id"], giveaway["channel_id"]]:
                    if target_id:
                        try:
                            await self.bot.send_message(
                                chat_id=target_id,
                                text=text,
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

            logger.info(f"Giveaway {gid} ended with {len(winners)} winners.")

        except Exception as e:
            logger.error(f"Error ending giveaway {gid}: {e}", exc_info=True)
            # Revert to ACTIVE on failure
            await update_giveaway_status(gid, "ACTIVE")

    async def resume_on_restart(self):
        """Called on bot startup to resume any scheduled work."""
        logger.info("Checking for giveaways to resume...")
        await self._check_scheduled()
        await self._check_active()
        logger.info("Resume check complete.")
