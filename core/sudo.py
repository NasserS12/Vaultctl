"""Sudo / privilege helpers."""
import os
import subprocess

from core.logging_setup import logger
from ui.colors import RED, RESET, YELLOW


def get_user_home():
    """Returns the home directory of the real user,
    even if running under sudo.

    NOTE: currently unused anywhere else in the codebase (dead code
    inherited from the original single-file version). Kept here in
    case a future feature (e.g. reading a user config file) needs it.
    """
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        try:
            import pwd
            return pwd.getpwnam(sudo_user).pw_dir
        except (ImportError, KeyError):
            return os.path.expanduser(f"~{sudo_user}")
    return os.path.expanduser("~")


def check_sudo():
    """Checks for root privileges. Returns True if authenticated."""
    has_sudo_cache = subprocess.run(
        ['sudo', '-n', 'true'], capture_output=True
    ).returncode == 0

    if os.getuid() == 0 or has_sudo_cache:
        return True
    print(
        f"{YELLOW}[!] This action requires root privileges. "
        f"Please authenticate...{RESET}")
    try:
        result = subprocess.run(['sudo', '-v'], check=False)
        success = result.returncode == 0
        if success:
            logger.info("sudo authentication successful.")
        else:
            logger.warning("sudo authentication failed.")
        return success
    except (KeyboardInterrupt, EOFError):
        print(f"\n{RED}[X] Authentication cancelled.{RESET}")
        logger.warning("sudo authentication cancelled by user.")
        return False
