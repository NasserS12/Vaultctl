#!/usr/bin/env python3
"""VAULTCTL — Linux System Diagnostic & Security Hardening.

Entry point only. All feature logic lives in modules/; shared UI and
core helpers live in ui/ and core/. See README.md for the module map.
"""
import os
import sys
import subprocess
import shutil
import time

# --- Logging must be configured before anything else touches it ---
from core.logging_setup import logger

# --- ABSOLUTE TOP PRIORITY: LOCK TERMINAL IMMEDIATELY ---
from ui.terminal import early_lock_terminal
early_lock_terminal()

from ui.colors import RESET, WHITE, CYAN, GREEN, YELLOW, RED, DIM, BOLD, TERMINAL_WIDTH
from ui.terminal import (
    set_echo, clear_screen, flush_input, get_confirmation, terminal_manager,
    footer_prompt,
)
from core.version import VERSION

from modules.system_scan import run_full_scan
from modules.process_manager import manage_processes_live
from modules.network_audit import show_network_audit
from modules.ssh_audit import audit_ssh_security
from modules.service_optimizer import optimize_services


def print_startup_message():
    """Runs the privilege-setup flow and returns whether the session
    ends up with root/sudo access (used later for the menu status line)."""
    root_enabled = False
    if os.name == 'posix':
        if os.getuid() != 0:
            set_echo(True)

            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)

            print(f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}")
            print(f"\n{pad}  {CYAN}{BOLD}VAULTCTL — Privilege Setup{RESET}")
            print(
                f"{pad}  {DIM}Root access unlocks: "
                f"SSH Audit · Firewall · Service Control{RESET}\n")
            user_agreed = get_confirmation(
                f"{pad}  {CYAN}>{RESET} Enable root? "
                f"{DIM}(y/N){RESET}: ")

            if user_agreed:
                print(f"\n{pad}  {DIM}Authenticating...{RESET}")
                subprocess.run(['sudo', '-v'], check=False)

            clear_screen()
            has_cache_final = subprocess.run(
                ['sudo', '-n', 'true'], capture_output=True
            ).returncode == 0

            print(f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")
            root_enabled = has_cache_final
            if has_cache_final:
                if user_agreed:
                    print(
                        f"{pad}  {GREEN}[ OK ]{RESET}  {WHITE}"
                        f"Authenticated — Full access enabled{RESET}")
                    logger.info("Session started: authenticated with sudo.")
                else:
                    print(
                        f"{pad}  {GREEN}[ OK ]{RESET}  {WHITE}"
                        f"Active sudo session detected — "
                        f"Full access available{RESET}")
                    logger.info(
                        "Session started: pre-existing sudo cache detected.")
            else:
                print(
                    f"{pad}  {YELLOW}[WARNING]{RESET}  {WHITE}"
                    f"Standard user mode{RESET}  {DIM}"
                    f"— Some features restricted{RESET}")
                logger.info(
                    "Session started: standard user mode (no sudo cache).")
            print(
                f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")

        else:
            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)
            root_enabled = True
            print(
                f"\n{pad}  {GREEN}[ OK ]{RESET}  {WHITE}"
                f"Running as Root (UID 0) — Full access{RESET}")
            logger.info("Session started: running as real root (UID 0).")
    else:
        print(f"\n  {YELLOW}[WARNING]{RESET}  {WHITE}Standard user mode{RESET}")
        logger.info("Session started: non-POSIX system, standard user mode.")
    time.sleep(2.0)
    flush_input()
    clear_screen()
    set_echo(True)
    return root_enabled


def header():
    columns = shutil.get_terminal_size().columns
    LOGO_WIDTH = 65

    logo_lines = [
        '██╗   ██╗ █████╗ ██╗   ██╗██╗  ████████╗ ██████╗████████╗██╗',
        '██║   ██║██╔══██╗██║   ██║██║  ╚══██╔══╝██╔════╝╚══██╔══╝██║',
        '██║   ██║███████║██║   ██║██║     ██║   ██║        ██║   ██║',
        '╚██╗ ██╔╝██╔══██║██║   ██║██║     ██║   ██║        ██║   ██║',
        ' ╚████╔╝ ██║  ██║╚██████╔╝███████╗██║   ╚██████╗   ██║   ███████╗',
        '  ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝    ╚═════╝   ╚═╝   ╚══════╝',
    ]

    tool_name = f'[ VAULTCTL — Secure System Control ]  [ v{VERSION} ]\n'
    slogan = 'Know Your System. Own Your Security.\n'
    credits = '(Developed by Nasser)'
    bar = '=' * min(columns, 70)

    def center(text):
        text = text[:columns]
        pad = max(0, (columns - len(text)) // 2)
        return ' ' * pad + text

    print(f"{RED}")

    if columns >= LOGO_WIDTH:
        pad = ' ' * (max(0, (columns - LOGO_WIDTH) // 2) + 2)
        for line in logo_lines:
            print(f"{pad}{line}")
    else:
        print(center('[ VAULTCTL ]'))

    print(f"{RESET}")
    print(f"{CYAN}{center(tool_name)}{RESET}")
    print(f"{YELLOW}{center(slogan)}{RESET}")
    print(f"{WHITE}{center(credits)}{RESET}")
    print(f"{RED}{center(bar)}{RESET}\n")


def menu_row(pad, num, label, desc, num_color=CYAN):
    """Prints one main-menu entry with a dotted leader between the
    label and its description, so columns stay aligned regardless of
    label length."""
    LEADER_COL = 34
    dots = '.' * max(2, LEADER_COL - len(label))
    print(
        f"{pad}  {num_color}[{num}]{RESET} {WHITE}{label}{RESET}"
        f"{DIM}{dots}{RESET} {DIM}{desc}{RESET}")


def get_load_avg_text():
    try:
        return f"{os.getloadavg()[0]:.2f}"
    except (OSError, AttributeError):
        return "N/A"


def main():
    logger.info("=== Diagnostic Tool started ===")
    root_enabled = print_startup_message()
    try:
        while True:
            clear_screen()
            header()

            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)

            title_txt = " [ MAIN MENU ]"
            status_txt = (
                f"root: {'YES' if root_enabled else 'NO'}  |  "
                f"load: {get_load_avg_text()}")
            gap = max(2, TERMINAL_WIDTH - len(title_txt) - len(status_txt))

            print(
                f"{pad}{CYAN}{BOLD}{title_txt}{RESET}"
                f"{' ' * gap}{DIM}{status_txt}{RESET}")
            print(f"{pad}{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
            print()
            menu_row(pad, 1, "Full System Scan",
                     "CPU . RAM . Disk . Battery . +More")
            menu_row(pad, 2, "Live Process Manager",
                     "Monitor & Kill Processes")
            menu_row(pad, 3, "Network & Firewall Audit",
                     "Ports . UFW . Connections")
            menu_row(pad, 4, "SSH Security Hardening",
                     "Config . Keys . Risk Audit")
            menu_row(pad, 5, "Service Optimizer",
                     "Manage & Neutralize Services")
            print()
            print(f"{pad}  {RED}[6]{RESET} {WHITE}Exit{RESET}")
            print()
            print(f"{pad}{DIM}{'-' * TERMINAL_WIDTH}{RESET}\n")

            flush_input()
            choice = input(f"{pad}  {CYAN}>{RESET} ").strip()

            if choice == "1":
                logger.info("User selected: Full System Scan")
                with terminal_manager(echo=False):
                    clear_screen()
                    run_full_scan()
                    footer_prompt("return to menu")
            elif choice == "2":
                logger.info("User selected: Live Process Manager")
                with terminal_manager(echo=True):
                    manage_processes_live()
            elif choice == "3":
                logger.info("User selected: Network Diagnostics")
                with terminal_manager(echo=True):
                    show_network_audit()
            elif choice == "4":
                logger.info("User selected: SSH Security Audit")
                with terminal_manager(echo=True):
                    audit_ssh_security()
            elif choice == "5":
                logger.info("User selected: Service Optimizer")
                with terminal_manager(echo=True):
                    optimize_services()
            elif choice == "6":
                logger.info("=== Diagnostic Tool exited by user ===")
                clear_screen()
                print(f"\n{CYAN}{'VAULTCTL':^{cols}}{RESET}")
                print(
                    f"{DIM}{
                        'Session terminated. Stay secure.':^{cols}}{RESET}\n")
                sys.exit(0)
            else:
                print(f"\n{pad}  {RED}[!] Invalid choice — press [1-6]{RESET}")
                time.sleep(1.5)
    except KeyboardInterrupt:
        set_echo(True)
        logger.info("=== Diagnostic Tool terminated via Ctrl+C ===")
        clear_screen()
        cols = shutil.get_terminal_size().columns
        print(f"\n{CYAN}{'VAULTCTL':^{cols}}{RESET}")
        print(f"{DIM}{'Session terminated. Stay secure.':^{cols}}{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
