"""Module [4]: SSH Security Hardening.

11-point sshd_config audit, Fail2Ban/CrowdSec detection, Google
Authenticator 2FA check, and inline remediation recommendations.
"""
import os
import re
import subprocess
import time

from core.logging_setup import logger
from core.sudo import check_sudo
from ui.colors import CYAN, DIM, GREEN, OK, RED, RESET, TERMINAL_WIDTH, WHITE, YELLOW
from ui.terminal import (
    clear_screen,
    footer_prompt,
    section_header,
    terminal_manager,
)


def get_smart_val(content, key):
    """Parse an sshd_config-style directive out of `content`.

    Returns (value, is_active):
      - value: the first ACTIVE (uncommented) occurrence if present,
        otherwise the first COMMENTED occurrence (as a hint of intended
        default), otherwise None.
      - is_active: True only if an uncommented occurrence was found.

    NOTE: this is a pure function now (content/key are explicit
    parameters instead of relying on closures), which makes it directly
    unit-testable — see the upcoming tests session.
    """
    active, comment = None, None
    pattern = re.compile(rf"^\s*(#?)\s*({key})\s+([^\s#]+)", re.I | re.M)
    for m in pattern.finditer(content):
        val = m.group(3).lower()
        if m.group(1) == '':
            active = val
            break  # SSH uses the FIRST active occurrence
        elif comment is None:
            comment = val
    return active or comment, active is not None


def is_2fa_ssh_ready(v_kbd, v_chall):
    """True if EITHER `KbdInteractiveAuthentication` or
    `ChallengeResponseAuthentication` is set to 'yes'.

    Extracted as a small, pure, directly-testable function after a bug
    was found in the inline expression that used to live in
    `audit_ssh_security`:

        is_ssh_ready = (v_kbd or v_chall) == 'yes'

    `or` between two strings returns the first *truthy* value, so if
    `v_kbd` is a non-empty string like 'no', it is returned as-is and
    `v_chall` is never even inspected -- silently ignoring a 'yes' on
    the other directive. The fix checks membership instead of relying
    on short-circuit `or`.
    """
    return 'yes' in (v_kbd, v_chall)


def audit_ssh_security():
    clear_screen()
    section_header("SSH DEEP SECURITY & HARDENING AUDIT")
    print()
    if not check_sudo():
        print(f"\n{RED}[!] Audit Aborted.{RESET}")
        time.sleep(1.5)
        return

    # 1. Check Service Status
    print(f"{CYAN}[*] Checking SSH Service Status...{RESET}")
    try:
        status_check = subprocess.run(
            ['systemctl', 'is-active', 'ssh'],
            stdout=subprocess.PIPE, text=True)
        if status_check.stdout.strip() != "active":
            print(
                f"Service Status: {RED}[INACTIVE] "
                f"(Offline / Secured from Network){RESET}")
            print(
                f"{YELLOW}[!] Notice: Analyzing configuration for "
                f"future risk mitigation...{RESET}")
        else:
            print(
                f"Service Status: {GREEN}[ACTIVE] "
                f"(Listening for connections){RESET}")
    except Exception as e:
        logger.debug(f"SSH service status check failed: {e}")
        print(f"Service Status: {RED}Unknown.{RESET}")

    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")

    # 2. Analyze Configuration
    with terminal_manager(echo=False):
        print(f"{CYAN}[*] Analyzing SSH configuration files...{RESET}")
        try:
            # Precedence: Settings in Include files (like .d/*.conf) usually
            # take effect first
            config_files = []
            config_d = '/etc/ssh/sshd_config.d/'
            if os.name == 'posix':
                if os.path.exists(config_d):
                    try:
                        for f in sorted(os.listdir(config_d)):
                            if f.endswith('.conf'):
                                config_files.append(os.path.join(config_d, f))
                    except OSError as e:
                        logger.debug(f"Could not list sshd_config.d: {e}")
            config_files.append('/etc/ssh/sshd_config')

            content = ""
            scanned = []
            res = subprocess.run(['sudo',
                                  'cat'] + config_files,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 text=True)
            if res.returncode == 0:
                content = res.stdout
                scanned = [os.path.basename(fp) for fp in config_files]
            else:
                for fp in config_files:
                    res = subprocess.run(
                        ['sudo', 'cat', fp],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True)
                    if res.returncode == 0:
                        content += f"\n# --- FILE: {fp} ---\n" + res.stdout
                        scanned.append(os.path.basename(fp))

            if scanned:
                print(
                    f"{OK} Scanned {len(scanned)} config file(s).")

                v_port, a_port = get_smart_val(content, "Port")
                v_root, a_root = get_smart_val(content, "PermitRootLogin")
                v_pwd, a_pwd = get_smart_val(content, "PasswordAuthentication")
                v_empty, a_empty = get_smart_val(content, "PermitEmptyPasswords")
                v_tries, a_tries = get_smart_val(content, "MaxAuthTries")
                v_x11, a_x11 = get_smart_val(content, "X11Forwarding")
                v_idle, a_idle = get_smart_val(content, "ClientAliveInterval")
                v_strict, a_strict = get_smart_val(content, "StrictModes")
                v_grace, a_grace = get_smart_val(content, "LoginGraceTime")
                v_rhosts, a_rhosts = get_smart_val(content, "IgnoreRhosts")
                v_sess, a_sess = get_smart_val(content, "MaxSessions")

                print(f"{'CHECK':<25} | {'VALUE':<20} | {'STATUS'}")
                print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")

                def print_audit_row(label, value, status, recommendation=None):
                    print(f"{label:<25} | {str(value):<20} | {status}")
                    if recommendation and "[ SECURE  ]" not in status:
                        print(
                            f"  {YELLOW}→{RESET} {WHITE}"
                            f"{recommendation}{RESET}")

                p_val = v_port or "22"
                p_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if p_val != '22'
                    else f"{YELLOW}[ WARNING ]{RESET}")
                print_audit_row(
                    "SSH Port", p_val, p_status,
                    "Use a non-standard port (e.g., 2222) "
                    "to avoid automated brute-force bots.")

                r_val = v_root or 'prohibit-password'
                r_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if r_val == 'no'
                    else f"{YELLOW}[ WARNING ]{RESET}")
                print_audit_row(
                    "Permit Root Login", r_val, r_status,
                    "Set to 'no' to force login via a standard user and sudo.")

                pw_val = v_pwd or 'yes'
                pw_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if pw_val == 'no'
                    else f"{YELLOW}[  RISK   ]{RESET}")
                print_audit_row(
                    "Password Auth", pw_val, pw_status,
                    "Disable password auth and use SSH Keys "
                    "(Ed25519) for much higher security.")

                e_val = v_empty or "no"
                e_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if e_val == 'no'
                    else f"{RED}[  RISK   ]{RESET}")
                print_audit_row(
                    "Empty Passwords", e_val, e_status,
                    "CRITICAL: Set to 'no' immediately "
                    "to prevent passwordless entry.")

                rh_val = v_rhosts or "no"
                rh_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if rh_val == 'yes'
                    else f"{RED}[  RISK   ]{RESET}")
                print_audit_row(
                    "Ignore Rhosts", rh_val, rh_status,
                    "Set to 'yes' to ignore legacy insecure .rhosts files.")

                s_val = int(v_sess) if (v_sess and v_sess.isdigit()) else 10
                if s_val <= 2:
                    s_status = f"{GREEN}[ SECURE  ]{RESET}"
                elif s_val <= 10:
                    s_status = f"{YELLOW}[ WARNING ]{RESET}"
                else:
                    s_status = f"{RED}[  RISK   ]{RESET}"
                print_audit_row(
                    "Max Sessions", str(s_val), s_status,
                    "Reduce to 2 to prevent "
                    "connection exhaustion attacks.")

                x_val = v_x11 or 'no'
                x_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if x_val == 'no'
                    else f"{YELLOW}[  RISK   ]{RESET}")
                print_audit_row(
                    "X11 Forwarding", x_val, x_status,
                    "Set to 'no' unless you specifically "
                    "need remote GUI applications.")

                idle_timeout_str = v_idle or "0"
                idle_val = int(
                    idle_timeout_str) if idle_timeout_str.isdigit() else 0
                idle_status = f"{GREEN}[ SECURE  ]{RESET}" if (
                    0 < idle_val <= 300) else f"{YELLOW}[ WARNING ]{RESET}"
                print_audit_row(
                    "Idle Timeout (Sec)", idle_timeout_str, idle_status,
                    "Set ClientAliveInterval to 300 (5 mins) "
                    "to auto-kick idle users.")

                m_val = v_strict or 'yes'
                m_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if m_val == 'yes'
                    else f"{RED}[  RISK   ]{RESET}")
                print_audit_row(
                    "Strict Modes", m_val, m_status,
                    "Set to 'yes' to ensure SSH checks "
                    "directory permissions before login.")

                g_val = int(v_grace) if v_grace and v_grace.isdigit() else 120
                g_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if g_val <= 60
                    else f"{YELLOW}[ WARNING ]{RESET}")
                print_audit_row(
                    "Login Grace Time", str(g_val), g_status,
                    "Reduce to 60 seconds to stop "
                    "unauthenticated connection hangs.")

                t_val = int(v_tries) if v_tries and v_tries.isdigit() else 6
                t_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if t_val <= 4
                    else f"{YELLOW}[ MODERATE ]{RESET}")
                print_audit_row(
                    "Max Auth Tries", str(t_val), t_status,
                    "Set to 3 or 4 to quickly "
                    "lock out brute-force attempts.")

                print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")

                # --- Brute-Force Protection Detection ---
                print(
                    f"{CYAN}[*] Checking for Brute-Force Protection "
                    f"(Fail2Ban/CrowdSec)...{RESET}")

                def check_svc_active(svc_name):
                    try:
                        r = subprocess.run(
                            ['systemctl', 'is-active', svc_name],
                            capture_output=True, text=True, timeout=2)
                        return r.stdout.strip() == 'active'
                    except Exception:
                        return False

                f2b_active = check_svc_active('fail2ban')
                cs_active = check_svc_active('crowdsec')

                if f2b_active:
                    print(
                        f"{'Fail2Ban Service':<25} | "
                        f"{GREEN}[ACTIVE]{RESET}             | "
                        f"{GREEN}[ SECURE  ]{RESET}")
                elif cs_active:
                    print(
                        f"{'CrowdSec Service':<25} | "
                        f"{GREEN}[ACTIVE]{RESET}             | "
                        f"{GREEN}[ SECURE  ]{RESET}")
                else:
                    print(
                        f"{'Brute-Force Prot.':<25} | "
                        f"{RED}[NOT DETECTED]{RESET}       | "
                        f"{RED}[  RISK   ]{RESET}")
                    print(
                        f"  {YELLOW}→{RESET} {WHITE}Install Fail2Ban "
                        f"to auto-block brute-force bots.{RESET}")
                    print(
                        f"     {DIM}Quick: sudo apt install fail2ban{RESET}")

                # --- Two-Factor Authentication Detection ---
                print(
                    f"{CYAN}[*] Checking for "
                    f"Two-Factor Authentication (2FA)...{RESET}")

                two_fa_active = False
                try:
                    pam_res = subprocess.run(
                        ['sudo', 'grep', '-q',
                         'pam_google_authenticator.so', '/etc/pam.d/sshd'],
                        timeout=2)
                    v_kbd, a_kbd = get_smart_val(
                        content, "KbdInteractiveAuthentication")
                    v_chall, a_chall = get_smart_val(
                        content, "ChallengeResponseAuthentication")
                    is_pam_ready = pam_res.returncode == 0
                    is_ssh_ready = is_2fa_ssh_ready(v_kbd, v_chall)
                    two_fa_active = is_pam_ready and is_ssh_ready
                except Exception:
                    pass

                if two_fa_active:
                    print(
                        f"{'Two-Factor Auth':<25} | "
                        f"{GREEN}[CONFIGURED]{RESET}         | "
                        f"{GREEN}[ SECURE  ]{RESET}")
                else:
                    print(
                        f"{'Two-Factor Auth':<25} | "
                        f"{RED}[NOT CONFIGURED]{RESET}     | "
                        f"{RED}[  RISK   ]{RESET}")
                    print(
                        f"  {YELLOW}→{RESET} {WHITE}Enable 2FA "
                        f"(e.g., Google Authenticator) "
                        f"for a major security boost.{RESET}")

                # --- Summary ---
                print(f"\n{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
                all_secure = all(
                    "[ SECURE  ]" in s
                    for s in [p_status, r_status, pw_status, e_status,
                              rh_status, s_status, x_status, idle_status,
                              m_status, g_status, t_status]
                ) and (f2b_active or cs_active) and two_fa_active
                if all_secure:
                    print(
                        f"{OK} {GREEN}Excellent! SSH configuration "
                        f"meets high security standards.{RESET}")
                else:
                    print(
                        f"{YELLOW}[!] Audit complete. Follow "
                        f"recommendations above to harden "
                        f"your SSH service.{RESET}")

            else:
                print(f"{RED}[!] Error reading config file.{RESET}")
        except Exception as e:
            print(f"{RED}[X] Error: {e}{RESET}")

    footer_prompt("return to menu")
