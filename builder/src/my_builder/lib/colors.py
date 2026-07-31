"""Colors for the terminal. Disabled by default in CI environments."""

import os
import sys

# Only export the color object
__all__ = ["color"]


_NO_COLOR: bool = (
    "CI" in os.environ
    or "NO_COLOR" in os.environ
    or not getattr(sys.stdout, "isatty", lambda: False)()
)


class Colors:
    """A palette of terminal color codes."""

    def __init__(self) -> None:
        self.color_codes: dict[str, str] = {
            "red": "31",
            "green": "32",
            "yellow": "33",
            "blue": "34",
            "magenta": "35",
            "cyan": "36",
            "white": "37",
            "gray": "90",
        }

    def get(self, color: str) -> str:
        """Get the color code for the given color."""

        if color not in self.color_codes:
            raise ValueError(
                f"Unknown color: {color}, expected one of {list(self.color_codes.keys())}"
            )

        return self.color_codes[color]

    def __color(self, color: str, msg: str, bold: bool = False) -> str:
        if _NO_COLOR:
            return msg

        prefix = (
            f"\033[1;{self.color_codes[color]}m"
            if bold
            else f"\033[0;{self.color_codes[color]}m"
        )

        return f"{prefix}{msg}\033[0m"

    # Standalone formatting
    def bold(self, msg: str) -> str:
        if _NO_COLOR:
            return msg
        return f"\033[1m{msg}\033[0m"

    def dim(self, msg: str) -> str:
        if _NO_COLOR:
            return msg
        return f"\033[2m{msg}\033[0m"

    # Base Colors (supports bold=True)
    def red(self, msg: str, bold: bool = False) -> str:
        return self.__color("red", msg, bold)

    def green(self, msg: str, bold: bool = False) -> str:
        return self.__color("green", msg, bold)

    def yellow(self, msg: str, bold: bool = False) -> str:
        return self.__color("yellow", msg, bold)

    def blue(self, msg: str, bold: bool = False) -> str:
        return self.__color("blue", msg, bold)

    def magenta(self, msg: str, bold: bool = False) -> str:
        return self.__color("magenta", msg, bold)

    def cyan(self, msg: str, bold: bool = False) -> str:
        return self.__color("cyan", msg, bold)

    def white(self, msg: str, bold: bool = False) -> str:
        return self.__color("white", msg, bold)

    def gray(self, msg: str, bold: bool = False) -> str:
        return self.__color("gray", msg, bold)


color = Colors()
