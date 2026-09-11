"""ANSI color codes and unified status icons used across the whole app."""

RESET = "\033[0m"
WHITE = "\033[97m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
DIM = "\033[2m"
BOLD = "\033[1m"

# Unified status badges (ASCII bracket tags — one vocabulary used by
# every module, safe to render over any terminal/SSH session).
OK = f"{GREEN}[ OK ]{RESET}"
WARN = f"{YELLOW}[WARNING]{RESET}"
FAIL = f"{RED}[ RISK ]{RESET}"
INFO = f"{CYAN}[i]{RESET}"

TERMINAL_WIDTH = 65
