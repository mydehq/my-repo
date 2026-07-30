"""
Logger module with colored terminal output formatting.
"""

import os
import sys

COLOR_RED = "\033[0;31m"
COLOR_GREEN = "\033[0;32m"
COLOR_YELLOW = "\033[1;33m"
COLOR_BLUE = "\033[0;34m"
COLOR_RESET = "\033[0m"

IS_CI = bool(os.environ.get("CI"))


def log_msg(msg: str) -> None:
    if IS_CI:
        print(f"{COLOR_BLUE}-{COLOR_RESET} {msg}")
    else:
        print(f"  {msg}")


def log_info(msg: str) -> None:
    print(f"{COLOR_BLUE}i {msg} {COLOR_RESET}")


def log_success(msg: str) -> None:
    print(f"{COLOR_GREEN}+ {msg} {COLOR_RESET}")


def log_warn(msg: str) -> None:
    print(f"{COLOR_YELLOW}! {msg} {COLOR_RESET}")


def log_error(msg: str) -> None:
    print(f"{COLOR_RED}x {msg} {COLOR_RESET}", file=sys.stderr)
