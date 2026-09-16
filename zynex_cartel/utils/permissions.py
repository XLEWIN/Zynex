"""
ZYNEX CARTEL — Permissions Module
Role-based access control for bot commands.
"""

import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from config import OWNER_ID, SUDO_USERS
from database import is_sudo, is_banned

logger = logging.getLogger("zynex.permissions")


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_sudo_user(user_id: int) -> bool:
    return user_id in SUDO_USERS


def is_admin(user_id: int) -> bool:
    return is_owner(user_id) or is_sudo_user(user_id)


def owner_only(func):
    """Decorator: only the bot owner can use this."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else 0
        if not is_owner(user_id):
            # Silently ignore
            return
        return await func(update, context)
    return wrapper


def sudo_only(func):
    """Decorator: owner or sudo users only. Silently ignores others."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else 0
        if not is_admin(user_id):
            return
        return await func(update, context)
    return wrapper


def not_banned(func):
    """Decorator: banned users cannot use this."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else 0
        if await is_banned(user_id):
            return
        return await func(update, context)
    return wrapper


async def check_admin_silent(user_id: int) -> bool:
    """Silently check if user is admin. Returns True if admin."""
    return is_admin(user_id)


async def check_banned_silent(user_id: int) -> bool:
    """Silently check if user is banned. Returns True if banned."""
    return await is_banned(user_id)


async def get_user_role(user_id: int) -> str:
    """Get the role of a user."""
    if is_owner(user_id):
        return "owner"
    if is_sudo_user(user_id):
        return "sudo"
    return "user"
