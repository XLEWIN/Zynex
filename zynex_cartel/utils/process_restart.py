"""
ZYNEX CARTEL — Process restart + git change watch
Used by owner /restart and the auto-restart loop after git updates.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("zynex.process")


def _find_repo_root() -> Path:
    """Walk up from this file until .git is found (repo root)."""
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate
    # Fallback: zynex_cartel/utils → repo root is three levels up
    return here.parent.parent.parent


# Repo root (contains .git)
REPO_ROOT = _find_repo_root()

# Set to "0" to disable git-based auto-restart
GIT_AUTORESTART = os.getenv("GIT_AUTORESTART", "1").strip().lower() not in (
    "0", "false", "no", "off",
)

_restart_armed = False


def arm_restart(reason: str) -> bool:
    """Mark that a restart should run. Returns False if already armed."""
    global _restart_armed
    if _restart_armed:
        return False
    _restart_armed = True
    logger.info("Restart armed: %s", reason)
    return True


def is_restart_armed() -> bool:
    return _restart_armed


def reset_restart_arm() -> None:
    """Testing helper — clear the one-shot arm flag."""
    global _restart_armed
    _restart_armed = False


def get_git_head(repo_root: Optional[Path] = None) -> Optional[str]:
    """Current commit SHA, or None if git/repo unavailable."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("git rev-parse failed: %s", e)
        return None
    if proc.returncode != 0:
        return None
    sha = (proc.stdout or "").strip()
    return sha or None


def build_restart_argv(argv: Optional[list[str]] = None) -> list[str]:
    """Command argv for a fresh bot process."""
    base = list(argv) if argv is not None else list(sys.argv)
    if not base:
        base = ["zynex_cartel/main.py"]
    return [sys.executable or "python"] + base


def restart_self(reason: str = "manual", argv: Optional[list[str]] = None) -> None:
    """Replace the current process with a fresh bot process.

    - Linux / Railway: os.execv replaces the image in-place (same PID, container stays up).
    - Windows terminal: spawn a child on the same console, then exit this process.
    Never returns on success.
    """
    if not arm_restart(reason):
        logger.warning("Restart skipped (already armed): %s", reason)
        return

    cmd = build_restart_argv(argv)
    cwd = os.getcwd()
    logger.info("Restarting bot (%s): %s (cwd=%s)", reason, cmd, cwd)

    # Prefer in-place replace (Railway/Linux — seamless, no container exit)
    if os.name != "nt":
        try:
            os.execv(cmd[0], cmd)
        except OSError as e:
            logger.error("os.execv failed (%s); falling back to spawn+exit", e)

    # Windows (or execv failed): new process on same console, then this one exits
    try:
        subprocess.Popen(cmd, cwd=cwd)
    except OSError as e:
        logger.error("Failed to spawn restart process: %s", e)
        # Last resort: non-zero exit so Railway ON_FAILURE can recover
        os._exit(1)

    # Flush stdio so the spawn is visible in the terminal, then leave
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)


def schedule_restart(reason: str, delay: float = 1.5, argv: Optional[list[str]] = None) -> None:
    """Schedule an async restart after `delay` seconds (lets Telegram send first)."""
    import asyncio

    if not arm_restart(f"{reason} (scheduled)"):
        return

    async def _later():
        await asyncio.sleep(max(0.0, delay))
        # Already armed — call the low-level path without re-arming
        cmd = build_restart_argv(argv)
        cwd = os.getcwd()
        logger.info("Restarting bot (%s): %s", reason, cmd)
        if os.name != "nt":
            try:
                os.execv(cmd[0], cmd)
            except OSError as e:
                logger.error("os.execv failed (%s); falling back", e)
        try:
            subprocess.Popen(cmd, cwd=cwd)
        except OSError as e:
            logger.error("spawn failed: %s", e)
            os._exit(1)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(0)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_later())
    except RuntimeError:
        # No running loop — restart immediately
        restart_self(reason, argv=argv)
