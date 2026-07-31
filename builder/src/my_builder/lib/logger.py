"""
Logger module with colored terminal output formatting. Disables color in CI environments.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from sys import stderr
from typing import Literal, TextIO, cast

from .colors import color

__all__ = ["CustomLogger", "LogError", "LogFileError", "LogLevelError", "log"]


class LogError(Exception):
    """Base exception for all logging module errors."""


class LogLevelError(LogError):
    """Raised when an invalid or unrecognized log level is specified."""

    def __init__(
        self,
        invalid_level: str,
        valid_levels: list[str] | tuple[str, ...],
        env: bool = False,
    ) -> None:

        self.invalid_level = invalid_level
        self.valid_levels = list(valid_levels)
        self.env = env

        levels_str = ", ".join(repr(lvl) for lvl in self.valid_levels)

        super().__init__(
            f"Invalid log level {'' if not env else '(env)'}: {invalid_level!r}. Expected one of: [{levels_str}]"
        )


class LogFileError(LogError):
    """Raised when a log file cannot be created, opened, or written to."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason

        super().__init__(
            f"Failed to write to log file at '{self.path.relative_to(Path.cwd())}': {reason}"
        )


LogLevel = Literal["error", "warn", "info", "success", "debug"]
LogConf = dict[LogLevel, tuple[int | float, str, str]]


class Logger:
    def __init__(
        self, log_level: LogLevel = "info", log_dir: Path | None = None
    ) -> None:

        LOG_CONF: LogConf = {
            "debug": (0, "gray", "[DEBUG]"),
            "info": (10, "blue", "i"),
            "success": (10, "green", "+"),
            "warn": (20, "yellow", "!"),
            "error": (30, "red", "x"),
        }

        if "LOG_LEVEL" in os.environ:
            env_level = os.environ["LOG_LEVEL"].strip().lower()

            if env_level not in LOG_CONF:
                raise LogLevelError(env_level, list(LOG_CONF), env=True)

            log_level = cast(LogLevel, env_level)

        log_file: Path | None = None
        log_stream: TextIO | None = None

        if log_dir:
            if not log_dir.is_absolute():
                log_dir = log_dir.resolve()

            if log_dir.is_file():
                raise LogFileError(log_dir, "Is a file")

            if not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

            try:
                log_stream = log_file.open("a", encoding="utf-8")

                log_stream.write(f"{'=' * 30} {Path.cwd()} {'=' * 30}\n")
                log_stream.flush()

            except OSError as e:
                try:
                    if log_stream is not None:
                        log_stream.close()
                except OSError:
                    pass

                print(
                    f"Warning: Failed to open log file '{log_file}': {e}", file=stderr
                )

        self.LEVELS: LogConf = LOG_CONF
        self.min_level: int | float = LOG_CONF[log_level][0]

        self.log_file = log_file
        self.log_stream = log_stream

    def __print_log(self, level_name: LogLevel, msg: str) -> None:

        if level_name not in self.LEVELS:
            raise LogLevelError(level_name, list(self.LEVELS))

        level, lcolor, prefix = self.LEVELS[level_name]

        if level < self.min_level:
            return

        clr = getattr(color, lcolor)

        print(
            f"{clr(prefix, bold=True)} {clr(msg)}",
            file=stderr if level_name == "error" else None,
        )

        current_time = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        if self.log_stream:
            try:
                self.log_stream.write(f"[{current_time}] {level_name.upper()}: {msg}\n")
                self.log_stream.flush()

            except OSError as e:
                try:
                    self.log_stream.close()
                except OSError:
                    pass

                print(
                    f"Warning: Failed to write log file '{self.log_file}': {e}",
                    file=stderr,
                )

                self.log_stream = None
                self.log_file = None

    def info(self, msg: str) -> None:
        self.__print_log("info", msg)

    def success(self, msg: str) -> None:
        self.__print_log("success", msg)

    def warn(self, msg: str) -> None:
        self.__print_log("warn", msg)

    def error(self, msg: str) -> None:
        self.__print_log("error", msg)

    def debug(self, msg: str) -> None:
        self.__print_log("debug", msg)


log: Logger = Logger()
"""logger instance"""


CustomLogger = Logger
"""
Create a custom logger instance

Options:
    log_level: str = Log level to use (default: "info")
    log_file: str = Log file to use (default: None)
"""
