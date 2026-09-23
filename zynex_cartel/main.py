"""
ZYNEX CARTEL — Main Entry Point
Production-ready Telegram giveaway bot.
"""

import asyncio
import logging
import sys
from telegram.ext import ApplicationBuilder, Application
from telegram import Update
from telegram.ext import ContextTypes

from config import BOT_TOKEN, LOG_LEVEL, LOG_FILE
from database import init_db, close_db
from scheduler import GiveawayScheduler

# ─── Logging Setup ────────────────────────────────────────────────

def setup_logging():
    """Configure structured logging."""
    fmt = "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
    )

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    return logging.getLogger("zynex.main")


# ─── Bot Setup ───────────────────────────────────────────────────

async def post_init(app: Application):
    """Called after the application is initialized."""
    logger = logging.getLogger("zynex.main")

    # Delete any active webhook before polling
    try:
        await app.bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook deleted successfully.")
    except Exception as e:
        logger.warning(f"Could not delete webhook: {e}")

    # Initialize database
    await init_db()
    logger.info("Database initialized.")

    # Start scheduler
    scheduler = GiveawayScheduler(app.bot)
    app.bot_data["scheduler"] = scheduler
    await scheduler.start()
    await scheduler.resume_on_restart()
    logger.info("Scheduler started and resumed.")

    # Start periodic vote reconciliation loop (fallback for missed chat_member updates)
    from engines.vote_giveaway_engine import reconcile_votes
    from database import get_active_vote_giveaway

    async def _reconcile_loop():
        while True:
            try:
                await asyncio.sleep(300)  # every 5 minutes
                g = await get_active_vote_giveaway()
                if g:
                    await reconcile_votes(app.bot, g["giveaway_id"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Vote reconciliation error: {e}")
                await asyncio.sleep(60)

    reconcile_task = asyncio.create_task(_reconcile_loop())
    app.bot_data["reconcile_task"] = reconcile_task
    logger.info("Vote reconciliation loop started (every 5 min).")

    # Auto-restart when git HEAD changes (local terminal after commit/push)
    from utils.process_restart import (
        get_git_head, schedule_restart, GIT_AUTORESTART,
    )

    baseline_head = get_git_head()
    if baseline_head:
        logger.info("Git HEAD baseline: %s", baseline_head[:12])
    else:
        logger.info("Git HEAD unavailable — auto-restart on push disabled for this run.")

    async def _git_watch_loop(interval: float = 20.0):
        """Poll git HEAD; restart once when the commit changes while running."""
        last = baseline_head
        while True:
            try:
                await asyncio.sleep(interval)
                if not GIT_AUTORESTART:
                    continue
                current = get_git_head()
                if not current or not last:
                    # First successful read establishes baseline
                    if current and not last:
                        last = current
                    continue
                if current != last:
                    logger.info(
                        "Git change detected (%s → %s) — restarting bot…",
                        last[:12], current[:12],
                    )
                    schedule_restart("git HEAD changed", delay=2.0)
                    return
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Git watch error: {e}")
                await asyncio.sleep(60)

    if baseline_head:
        git_task = asyncio.create_task(_git_watch_loop())
        app.bot_data["git_watch_task"] = git_task
        logger.info("Git auto-restart watcher started (every 20s).")
    else:
        app.bot_data["git_watch_task"] = None


async def post_shutdown(app: Application):
    """Called when the application is shutting down."""
    logger = logging.getLogger("zynex.main")

    # Cancel reconciliation loop
    reconcile_task = app.bot_data.get("reconcile_task")
    if reconcile_task:
        reconcile_task.cancel()
        logger.info("Vote reconciliation stopped.")

    git_task = app.bot_data.get("git_watch_task")
    if git_task:
        git_task.cancel()
        logger.info("Git auto-restart watcher stopped.")

    # Stop scheduler
    scheduler = app.bot_data.get("scheduler")
    if scheduler:
        await scheduler.stop()
        logger.info("Scheduler stopped.")

    # Close database
    await close_db()
    logger.info("Database closed.")


def main():
    """Main function to start the bot."""
    logger = setup_logging()
    logger.info("Starting ZYNEX CARTEL bot...")

    # Build application
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers
    from handlers.start import register_start_handlers
    from handlers.active import register_active_handlers
    from handlers.sgive import register_sgive_handlers
    from handlers.admin import register_admin_handlers, set_bot
    from handlers.vote_giveaway import register_vote_giveaway_handlers
    from handlers.participant import register_participant_handlers
    from handlers.callbacks import CallbackManager
    from handlers.group import GroupMessageHandler

    # Set bot reference for admin handlers
    set_bot(app.bot)

    # Register all handler groups
    register_start_handlers(app)
    register_active_handlers(app)
    register_sgive_handlers(app)
    register_admin_handlers(app)
    register_vote_giveaway_handlers(app)
    register_participant_handlers(app)

    # Callback manager
    callback_manager = CallbackManager(app.bot)
    for handler in callback_manager.get_handlers():
        app.add_handler(handler)

    # Group message handler
    group_handler = GroupMessageHandler(app.bot)
    for handler in group_handler.get_handlers():
        app.add_handler(handler)

    # Membership monitoring — chat_member updates for live vote revocation
    from telegram.ext import ChatMemberHandler
    from engines.vote_giveaway_engine import handle_membership_update

    async def _membership_watcher(update, context):
        await handle_membership_update(context.bot, update)

    app.add_handler(ChatMemberHandler(_membership_watcher, ChatMemberHandler.CHAT_MEMBER))

    # Global error handler — log full traceback; never crash the poller
    async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        err_logger = logging.getLogger("zynex.errors")
        if isinstance(context.error, Exception):
            err_logger.exception(
                "Unhandled exception while processing update %s",
                getattr(update, "update_id", update),
                exc_info=context.error,
            )
        else:
            err_logger.error("Unhandled error: %s", context.error)

    app.add_error_handler(_error_handler)

    logger.info("All handlers registered.")
    logger.info("ZYNEX CARTEL is now running!")
    logger.info("Press Ctrl+C to stop.")

    # Run the bot
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=[
            "message", "callback_query", "my_chat_member",
            "chat_member", "chat_join_request",
        ],
    )


if __name__ == "__main__":
    main()
