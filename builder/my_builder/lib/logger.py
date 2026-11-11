"""
Logger module with colored terminal output formatting. Disables color in CI environments.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from sys import stderr
from typing import Any, Literal, TextIO, TypedDict, Unpack

from ..defaults import defaults
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

        self.invalid_level: str = invalid_level
        self.valid_levels: list[str] = list(valid_levels)
        self.env: bool = env

        levels_str: str = ", ".join(repr(lvl) for lvl in self.valid_levels)

        super().__init__(
            f"Invalid log level {'' if not env else '(env)'}: {invalid_level!r}. Expected one of: [{levels_str}]"
        )


class LogFileError(LogError):
    """Raised when a log file cannot be created, opened, or written to."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path: Path = path
        self.reason: str = reason

        super().__init__(
            f"Failed to write to log file at '{self.path.relative_to(Path.cwd())}': {reason}"
        )


LogLevel = Literal["error", "warn", "info", "success", "debug"]
LogConf = dict[LogLevel, tuple[int | float, str, str]]


class Logger:
    def __init__(
        self,
        log_level: LogLevel = "info",
        log_dir: Path | None = defaults.data_dir / "logs",
    ) -> None:

        LOG_CONF: LogConf = {
            "debug": (0, "gray", "[DEBUG]"),
            "info": (10, "blue", "i"),
            "success": (10, "green", "✓"),
            "warn": (20, "yellow", "!"),
            "error": (30, "red", "x"),
        }

        if "LOG_LEVEL" in os.environ:
            env_level = os.environ["LOG_LEVEL"].strip().lower()

            if env_level not in LOG_CONF:
                raise LogLevelError(env_level, list(LOG_CONF), env=True)

            log_level = env_level

        log_file: Path | None = None
        log_stream: TextIO | None = None

        if log_dir:
            if not log_dir.is_absolute():
                log_dir = log_dir.resolve()

            if log_dir.is_file():
                raise LogFileError(log_dir, "Is a file")

            if not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f"{datetime.now().astimezone():%Y-%m-%d_%H-%M-%S}.log"

            try:
                log_stream = log_file.open("a", encoding="utf-8")

                header = f" Started in: {Path.cwd()} ".center(80, "=")

                _ = log_stream.write(f"{header}\n\n")
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
        self.max_level_width: int = max(len(lvl) for lvl in self.LEVELS)

        self.log_file: Path | None = log_file
        self.log_stream: TextIO | None = log_stream

    class LogOptions(TypedDict, total=False):
        bold: bool
        sep: str
        end: str | None
        file: TextIO | None
        log_file_only: bool

    def __print_log(
        self,
        lvl: LogLevel,
        *msgs: Any,
        **opts: Unpack[LogOptions],
    ) -> None:

        bold = opts.get("bold", False)
        sep = opts.get("sep", " ")
        end = opts.get("end", "\n")
        file = opts.get("file", None)
        log_file_only = opts.get("log_file_only", False)

        if lvl not in self.LEVELS:
            raise LogLevelError(lvl, list(self.LEVELS))

        level, lcolor, prefix = self.LEVELS[lvl]

        msg: str = sep.join(str(m) for m in msgs)

        # don't print if level is below min level or explicitly log-file-only
        if level >= self.min_level and not log_file_only:
            clr = getattr(color, lcolor)
            colored_prefix = clr(prefix, bold=True)

            if bold:
                msg = f"{colored_prefix} {color.bold(msg)}"
            else:
                msg = f"{colored_prefix} {msg}"

            print(msg, end=end, file=file)

        current_time: str = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        if self.log_stream:
            try:
                self.log_stream.write(  # pyright: ignore[reportUnusedCallResult]
                    f"[{current_time}] {lvl.upper():<{self.max_level_width}} {msg}\n"
                )
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

    # Define log level methods

    def debug(self, *msg: Any, **opts: Unpack[LogOptions]) -> None:
        self.__print_log("debug", *msg, **opts)

    def info(self, *msgs: Any, **opts: Unpack[LogOptions]) -> None:
        self.__print_log("info", *msgs, **opts)

    def success(self, *msgs: str, **opts: Unpack[LogOptions]) -> None:
        self.__print_log("success", *msgs, **opts)

    def warn(self, *msgs: str, **opts: Unpack[LogOptions]) -> None:
        self.__print_log("warn", *msgs, **opts)

    def error(self, *msgs: str, **opts: Unpack[LogOptions]) -> None:
        opts.setdefault("file", stderr)
        self.__print_log("error", *msgs, **opts)


log: Logger = Logger()
"""logger instance"""


CustomLogger = Logger
"""
Create a custom logger instance

Options:
    log_level: str = Log level to use (default: "info")
    log_file: str = Log file to use (default: None)
"""


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    return globals()[name]
