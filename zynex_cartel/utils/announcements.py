"""
ZYNEX CARTEL — Announcement Manager
Giveaway and winner announcement formatting.
"""

import logging
from telegram import Bot
from telegram.constants import ParseMode

from config import GiveawayType
from utils import (
    E, format_ist, giveaway_type_name, giveaway_type_emoji, mention_user,
    user_display, from_utc_iso, time_remaining, status_emoji
)
from utils.keyboards import giveaway_info_keyboard

logger = logging.getLogger("zynex.announcements")


class AnnouncementManager:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_giveaway_announcement(self, giveaway: dict, participants: int = 0):
        """Send the initial giveaway announcement to group and channel."""
        gid = giveaway["giveaway_id"]
        name = giveaway["name"]
        gtype = giveaway["type"]
        winners = giveaway["winner_count"]
        start = format_ist(from_utc_iso(giveaway["start_time"]))
        end = format_ist(from_utc_iso(giveaway["end_time"]))
        group_id = giveaway["group_id"]
        channel_id = giveaway["channel_id"]

        type_emoji = giveaway_type_emoji(gtype)
        type_name = giveaway_type_name(gtype)

        # Type-specific instructions
        instructions = self._get_participation_instructions(gtype)

        text = (
            f"{E.PARTY} <b>ZYNEX CARTEL GIVEAWAY</b>\n"
            f"\n"
            f"{E.BULLET}\n"
            f"\n"
            f"{E.GIFT} <b>{name}</b>\n"
            f"\n"
            f"{E.WINNER} Winners: <code>{winners}</code>\n"
            f"{type_emoji} Type: <b>{type_name}</b>\n"
            f"{E.CLOCK} Starts: <b>{start}</b>\n"
            f"{E.HOURGLASS} Ends: <b>{end}</b>\n"
            f"\n"
            f"{E.BULLET}\n"
            f"\n"
            f"<b>How to participate</b>\n"
            f"{instructions}\n"
            f"\n"
            f"Good luck everyone! {E.DIAMOND}"
        )

        keyboard = giveaway_info_keyboard(gid, gtype)

        # Send to group
        if group_id:
            try:
                await self.bot.send_message(
                    chat_id=group_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                logger.info(f"Announcement sent to group {group_id} for giveaway {gid}")
            except Exception as e:
                logger.error(f"Failed to send group announcement for giveaway {gid}: {e}")

        # Send to channel
        if channel_id:
            try:
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
                logger.info(f"Announcement sent to channel {channel_id} for giveaway {gid}")
            except Exception as e:
                logger.error(f"Failed to send channel announcement for giveaway {gid}: {e}")

    async def send_winner_announcement(self, giveaway: dict, winners: list[dict]):
        """Send winner announcement to group and channel."""
        name = giveaway["name"]
        group_id = giveaway["group_id"]
        channel_id = giveaway["channel_id"]

        medals = [E.MEDAL_1, E.MEDAL_2, E.MEDAL_3]
        winner_lines = []
        for i, w in enumerate(winners):
            medal = medals[i] if i < 3 else f"#{i+1}"
            uid = w["user_id"]
            winner_lines.append(f"{medal} {mention_user(uid)}")

        winners_text = "\n".join(winner_lines) if winner_lines else "<i>No winners</i>"

        text = (
            f"{E.TROPHY} <b>ZYNEX CARTEL — GIVEAWAY ENDED</b>\n"
            f"\n"
            f"{E.BULLET}\n"
            f"\n"
            f"{E.GIFT} <b>{name}</b>\n"
            f"\n"
            f"{E.WINNER} <b>WINNERS</b>\n"
            f"\n"
            f"{winners_text}\n"
            f"\n"
            f"{E.BULLET}\n"
            f"\n"
            f"{E.PARTY} Congratulations!\n"
            f"Thank you to everyone who participated.\n"
            f"\n"
            f"<b>ZYNEX CARTEL</b> {E.CROWN}"
        )

        for target_id in [group_id, channel_id]:
            if target_id:
                try:
                    await self.bot.send_message(
                        chat_id=target_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                    )
                    logger.info(f"Winner announcement sent to {target_id}")
                except Exception as e:
                    logger.error(f"Failed to send winner announcement to {target_id}: {e}")

    async def send_vote_leaderboard(self, chat_id: int, giveaway: dict, leaderboard: list):
        """Send the current vote leaderboard."""
        name = giveaway["name"]

        medals = [E.MEDAL_1, E.MEDAL_2, E.MEDAL_3]
        lines = []
        for i, row in enumerate(leaderboard):
            medal = medals[i] if i < 3 else f"#{i+1}"
            uid = row["target_id"]
            count = row["vote_count"]
            lines.append(f"{medal} {mention_user(uid)} — <b>{count}</b> votes")

        if not lines:
            lines.append("<i>No votes yet.</i>")

        lb_text = "\n".join(lines)

        text = (
            f"{E.CHART} <b>CURRENT LEADERBOARD</b>\n"
            f"\n"
            f"{E.GIFT} {name}\n"
            f"\n"
            f"{E.BULLET}\n"
            f"\n"
            f"{lb_text}\n"
            f"\n"
            f"{E.BULLET}\n"
        )

        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_confirmation_message(self, chat_id: int, giveaway: dict):
        """Send admin confirmation before creating giveaway."""
        name = giveaway["name"]
        gtype = giveaway["type"]
        winners = giveaway["winner_count"]
        start = format_ist(from_utc_iso(giveaway["start_time"]))
        end = format_ist(from_utc_iso(giveaway["end_time"]))

        type_emoji = giveaway_type_emoji(gtype)
        type_name = giveaway_type_name(gtype)

        text = (
            f"{E.GIVEAWAY} <b>GIVEAWAY CONFIRMATION</b>\n"
            f"\n"
            f"{E.BULLET}\n"
            f"\n"
            f"{E.NAME_TAG} Name:\n<b>{name}</b>\n"
            f"\n"
            f"{E.GIFT} Type:\n{type_emoji} <b>{type_name}</b>\n"
            f"\n"
            f"{E.WINNER} Winners:\n<b>{winners}</b>\n"
            f"\n"
            f"{E.CLOCK} Starts:\n<b>{start}</b>\n"
            f"\n"
            f"{E.HOURGLASS} Ends:\n<b>{end}</b>\n"
            f"\n"
            f"{E.GROUP} Announcement Group:\n<code>{giveaway.get('group_id', 'Not configured')}</code>\n"
            f"\n"
            f"{E.CHANNEL} Announcement Channel:\n<code>{giveaway.get('channel_id', 'Not configured')}</code>\n"
            f"\n"
            f"{E.BULLET}\n"
            f"\n"
            f"Are you sure you want to start this giveaway?"
        )

        return text

    async def send_dm_only_error(self, chat_id: int):
        """Send a DM-only notice."""
        text = (
            f"{E.SHIELD} This command can only be used in my <b>private chat</b>.\n"
            f"Please message me directly."
        )
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_no_active_giveaways(self, chat_id: int):
        """Send message when no giveaways are active."""
        text = (
            f"{E.INFO} There are currently <b>no active giveaways</b>.\n"
            f"\n"
            f"Check back later! {E.SPARKLE}"
        )
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_giveaway_ended_already(self, chat_id: int):
        """Send message when giveaway already ended."""
        text = f"{E.INFO} This giveaway has <b>already ended</b>."
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_participation_registered(self, chat_id: int, giveaway_name: str):
        """Confirm participation registration."""
        text = (
            f"{E.CHECK} You are registered for <b>{giveaway_name}</b>!\n"
            f"Good luck! {E.FIRE}"
        )
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_already_participated(self, chat_id: int):
        """User already in giveaway."""
        text = f"{E.INFO} You are <b>already participating</b> in this giveaway."
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_banned_notice(self, chat_id: int):
        """User is banned."""
        text = f"{E.BAN} You are <b>permanently banned</b> from participating in giveaways."
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_vote_recorded(self, chat_id: int, voter_name: str, target_name: str):
        """Vote confirmation."""
        text = (
            f"{E.CHECK} <b>Vote recorded!</b>\n"
            f"\n"
            f"{voter_name} voted for {target_name}\n"
            f"{E.FIRE} Your vote has been counted."
        )
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_already_voted(self, chat_id: int):
        """User already voted."""
        text = f"{E.INFO} You have <b>already voted</b> in this giveaway."
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_slot_result(self, chat_id: int, user_id: int, result: str, is_winner: bool):
        """Send slot spin result."""
        if is_winner:
            text = (
                f"{E.SLOT} <b>SLOT RESULT</b>\n"
                f"\n"
                f"<code>{result}</code>\n"
                f"\n"
                f"{E.TROPHY} <b>JACKPOT! TRIPLE 7!</b>\n"
                f"{mention_user(user_id)} wins!"
            )
        else:
            text = (
                f"{E.SLOT} <b>SLOT RESULT</b>\n"
                f"\n"
                f"<code>{result}</code>\n"
                f"\n"
                f"{E.INFO} No qualifying result. Try again!"
            )
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_generic_error(self, chat_id: int, message: str = None):
        """Generic error message."""
        text = f"{E.WARNING} An error occurred."
        if message:
            text += f"\n{message}"
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def send_admin_action(self, chat_id: int, action: str, details: str = ""):
        """Confirm an admin action."""
        text = f"{E.SHIELD} <b>Admin Action</b>\n{action}"
        if details:
            text += f"\n{details}"
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    def _get_participation_instructions(self, gtype: int) -> str:
        """Get type-specific participation instructions."""
        if gtype == GiveawayType.VOTE:
            return (
                f"{E.VOTE} <b>Vote Giveaway</b>\n"
                f"Use the buttons below to cast your vote.\n"
                f"One vote per user. You can vote for yourself!\n"
                f"The most voted user wins."
            )
        elif gtype == GiveawayType.RANDOM:
            return (
                f"{E.GIVEAWAY} <b>Random Giveaway</b>\n"
                f"Just send any message in this group during the giveaway.\n"
                f"You'll be automatically registered!\n"
                f"Winners are selected randomly."
            )
        elif gtype == GiveawayType.SLOT:
            return (
                f"{E.SLOT} <b>Slot Giveaway</b>\n"
                f"Send the slot emoji <b>🎰</b> in this group.\n"
                f"Match <b>7 7 7</b> to win!\n"
                f"First triple-7 result wins."
            )
        return "Participate now!"
