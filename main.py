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

from ui.colors import RESET, WHITE, CYAN, GREEN, YELLOW, RED, DIM, BOLD, FAIL, TERMINAL_WIDTH
from ui.terminal import (
    set_echo, clear_screen, flush_input, get_confirmation, terminal_manager,
    wait_for_enter,
)

from modules.system_scan import run_full_scan
from modules.process_manager import manage_processes_live
from modules.network_audit import show_network_audit
from modules.ssh_audit import audit_ssh_security
from modules.service_optimizer import optimize_services


def print_startup_message():
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
                f"{pad}  {CYAN}❯{RESET} Enable root? "
                f"{DIM}(y/N){RESET}: ")

            if user_agreed:
                print(f"\n{pad}  {DIM}Authenticating...{RESET}")
                subprocess.run(['sudo', '-v'], check=False)

            clear_screen()
            has_cache_final = subprocess.run(
                ['sudo', '-n', 'true'], capture_output=True
            ).returncode == 0

            print(f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")
            if has_cache_final:
                if user_agreed:
                    print(
                        f"{pad}  {GREEN}✓{RESET}  {WHITE}"
                        f"Authenticated — Full access enabled{RESET}")
                    logger.info("Session started: authenticated with sudo.")
                else:
                    print(
                        f"{pad}  {GREEN}✓{RESET}  {WHITE}"
                        f"Active sudo session detected — "
                        f"Full access available{RESET}")
                    logger.info(
                        "Session started: pre-existing sudo cache detected.")
            else:
                print(
                    f"{pad}  {YELLOW}⚠{RESET}  {WHITE}"
                    f"Standard user mode{RESET}  {DIM}"
                    f"— Some features restricted{RESET}")
                logger.info(
                    "Session started: standard user mode (no sudo cache).")
            print(
                f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")

        else:
            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)
            print(
                f"\n{pad}  {GREEN}✓{RESET}  {WHITE}"
                f"Running as Root (UID 0) — Full access{RESET}")
            logger.info("Session started: running as real root (UID 0).")
    else:
        print(f"\n  {YELLOW}⚠{RESET}  {WHITE}Standard user mode{RESET}")
        logger.info("Session started: non-POSIX system, standard user mode.")
    time.sleep(2.0)
    flush_input()
    clear_screen()
    set_echo(True)


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

    tool_name = '[ VAULTCTL — Secure System Control ]\n'
    slogan = 'Know Your System. Own Your Security.\n'
    credits = '(Developed by Nasser)'
    bar = '-' * min(columns, 70)

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


def main():
    logger.info("=== Diagnostic Tool started ===")
    print_startup_message()
    try:
        while True:
            clear_screen()
            header()

            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)

            print(f"{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}")
            print(f"{pad}{'MAIN MENU':^{TERMINAL_WIDTH}}")
            print(f"{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[1]{RESET}  {WHITE}"
                f"Full System Scan{RESET}              "
                f"{DIM}CPU · RAM · Disk · Battery · +More{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[2]{RESET}  {WHITE}"
                f"Live Process Manager{RESET}          "
                f"{DIM}Monitor & Kill Processes{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[3]{RESET}  {WHITE}"
                f"Network & Firewall Audit{RESET}      "
                f"{DIM}Ports · UFW · Connections{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[4]{RESET}  {WHITE}"
                f"SSH Security Hardening{RESET}        "
                f"{DIM}Config · Keys · Risk Audit{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[5]{RESET}  {WHITE}"
                f"Service Optimizer{RESET}             "
                f"{DIM}Manage & Neutralize Services{RESET}")
            print()
            print(f"{pad}  {RED}[6]{RESET}  {WHITE}Exit{RESET}")
            print()
            print(f"{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")

            flush_input()
            choice = input(f"{pad}  {CYAN}❯{RESET} ").strip()

            if choice == "1":
                logger.info("User selected: Full System Scan")
                with terminal_manager(echo=False):
                    clear_screen()
                    run_full_scan()
                    print(
                        f"\n{YELLOW}Press [Enter] to return "
                        f"to Main Menu...{RESET}",
                        end="",
                        flush=True)
                    wait_for_enter()
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
                print(f"\n{pad}  {FAIL}  Invalid choice — press [1-6]{RESET}")
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
