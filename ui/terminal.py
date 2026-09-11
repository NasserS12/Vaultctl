"""Terminal I/O helpers: echo control, raw-mode Enter waiting,
screen clearing, and yes/no confirmation prompts.
"""
import os
import sys
import time
from contextlib import contextmanager

from core.logging_setup import logger
from ui.colors import RED, RESET, CYAN, BOLD, DIM, TERMINAL_WIDTH


def early_lock_terminal():
    """Disable terminal echo IMMEDIATELY at startup and flush any
    keystrokes typed while Python was still loading.

    Rationale: without this, characters the user mashes during the
    ~1s Python startup (e.g. hitting Enter impatiently) can leak into
    the first menu prompt and trigger an unintended selection. This
    must run before any other output/input happens, which is why
    main.py calls it as its very first statement.
    """
    if os.name == 'posix':
        try:
            import termios
            fd = sys.stdin.fileno()
            attr = termios.tcgetattr(fd)
            attr[3] = attr[3] & ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, attr)
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception as e:
            logger.debug(f"termios early-lock failed: {e}")


def flush_input():
    """Flushes the stdin buffer to prevent accidental keystrokes
    from skipping prompts."""
    if os.name == 'posix':
        try:
            import termios
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception as e:
            logger.debug(f"flush_input failed: {e}")


def set_echo(enable):
    """Enables or disables terminal echo on Linux."""
    if os.name == 'posix' and sys.stdin.isatty():
        try:
            import termios
            fd = sys.stdin.fileno()
            attr = termios.tcgetattr(fd)
            if enable:
                attr[3] = attr[3] | termios.ECHO
            else:
                attr[3] = attr[3] & ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, attr)
        except Exception as e:
            logger.debug(f"set_echo({enable}) failed: {e}")


@contextmanager
def terminal_manager(echo=True):
    """Context manager to safely manage terminal echo."""
    try:
        set_echo(echo)
        yield
    finally:
        set_echo(True)
        flush_input()


def wait_for_enter():
    """Waits for Enter key only. Ignores all other input except Ctrl+C."""
    if os.name == 'posix' and sys.stdin.isatty():
        try:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ('\r', '\n'):
                        break
                    elif ch == '\x03':  # Ctrl+C
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
                        raise KeyboardInterrupt
                    # Ignore everything else silently
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.debug(f"wait_for_enter raw mode failed: {e}")
            input("")  # fallback
    else:
        input("")  # Windows fallback


def section_header(title):
    """Prints the standard boxed section header used at the top of
    every module screen, e.g.:

        =================================================================
         [ TITLE ]
        =================================================================
    """
    bar = '=' * TERMINAL_WIDTH
    print(f"{CYAN}{bar}{RESET}")
    print(f"{CYAN}{BOLD} [ {title} ]{RESET}")
    print(f"{CYAN}{bar}{RESET}")


def footer_prompt(message="return to menu"):
    """Prints the standard footer and blocks until Enter is pressed."""
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
    print(
        f"\n {CYAN}[Enter]{RESET} {message}   {DIM}|{RESET}   "
        f"{CYAN}[Ctrl+C]{RESET} exit",
        end="", flush=True)
    wait_for_enter()


def clear_screen():
    """Clears the terminal screen and scrollback buffer
    using fast ANSI escape codes."""
    print("\033[H\033[2J\033[3J", end="", flush=True)


def get_confirmation(prompt_text):
    """Strictly captures a yes/no confirmation. Re-asks on invalid input."""
    while True:
        flush_input()
        try:
            ans = input(prompt_text).lower().strip()
            if ans in ['y', 'yes', '1']:
                return True
            if ans in ['n', 'no', '0', '']:
                return False
            print(f"{RED}  [!] Invalid input{RESET}", end="", flush=True)
            time.sleep(1.5)
            print("\r\033[K\033[A\r\033[K", end="", flush=True)
        except (KeyboardInterrupt, EOFError):
            return False
