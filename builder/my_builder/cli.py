"""
CLI routing & subcommand handler module using Python 3.14 pattern matching, dataclasses, and pathlib.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from . import __app__name__, __version__
from .defaults import defaults
from .lib.aur import (
    AUR_CLONE_DIR,
    clone_package,
    fetch_aur_versions,
    get_actual_git_version,
)
from .lib.colors import color
from .lib.config import ConfigError, load_config
from .lib.logger import log
from .lib.pkgbuild import build_package
from .lib.repo import cleanup, get_pkg_info, migrate_database, update_database
from .lib.site import SiteGenerationError, generate_site

ARCH = "x86_64"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__app__name__,
        description="Build AUR packages and generate the repository website.",
    )
    parser.add_argument(
        '-v', "--version",
        action="version",
        version=f"Builder {__version__}",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=defaults.config_file,
        help="Path to the YAML configuration file (default: config.yml)",
    )

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    build_command = commands.add_parser("build", help="Build configured AUR packages")
    build_command.add_argument(
        '-p', "--package",
        action="append",
        dest="packages",
        metavar="NAME",
        help="Build only this configured package; may be repeated",
    )
    build_command.add_argument(
        '-r', "--rebuild-missing",
        action="store_true",
        help="Rebuild package if binary file is missing from build directory",
    )
    commands.add_parser("build-index", help="Generate the repository website")
    help_command = commands.add_parser("help", help="Show help message and exit")
    help_command.add_argument("topic", nargs="?", help=argparse.SUPPRESS)

    return parser


def run_build_index(config_path: Path) -> int:
    try:
        config = load_config(config_path)
    except ConfigError as e:
        log.error(f"Failed to load config: {e}")
        return 1

    log.info(
        f"Generating site from {'default' if config.site.input_dir == defaults.site_input_dir else config.site.input_dir.relative_to(Path.cwd())}..."
    )
    try:
        generate_site(config)
    except SiteGenerationError as e:
        log.error(color.bold("Failed to generate site"), str(e))
        return 1

    log.success(
        f"\nSite generated successfully in {config.site.output_dir.relative_to(Path.cwd())}"
    )

    return 0


def run_build(
    config_path: Path,
    target_names: list[str] | None = None,
    rebuild_missing: bool = False,
) -> int:
    if not shutil.which("makepkg"):
        log.error("makepkg is required but not installed")
        return 1

    try:
        config = load_config(config_path)
    except ConfigError as e:
        log.error(f"Failed to load config: {e}")
        return 1

    build_dir = config.repo.output_dir
    build_arch_dir = build_dir / ARCH
    build_arch_dir.mkdir(parents=True, exist_ok=True)

    if not os.access(build_arch_dir, os.W_OK):
        log.error(f"Build directory is not writable: {build_arch_dir}")
        return 1

    target_text = os.environ.get("BUILD_TARGETS", "").strip()
    if target_names is None and target_text:
        try:
            parsed_targets = json.loads(target_text)
            target_names = parsed_targets if isinstance(parsed_targets, list) else []
        except json.JSONDecodeError:
            target_names = shlex.split(target_text)

    if target_names is not None:
        packages = [pkg for pkg in config.packages if pkg.name in target_names]
        if not packages:
            requested = ", ".join(target_names)
            log.error(f"No configured packages matched: {requested}")
            return 1
    else:
        packages = config.packages

    repo_name = config.repo.name
    db_file = build_arch_dir / f"{repo_name}.db.tar.gz"
    migrate_database(build_arch_dir, repo_name)

    package_names = [pkg.name for pkg in packages]
    remote_versions = fetch_aur_versions(package_names)
    built_pkg_files: list[str] = []
    skipped_count = 0
    failed_count = 0

    AUR_CLONE_DIR.mkdir(parents=True, exist_ok=True)

    for package in packages:
        log.info(f"Processing package: {color.yellow(package.name)}")
        repo_info = get_pkg_info(db_file, package.name)
        repo_version = repo_info.version if repo_info else ""
        aur_version = remote_versions.get(package.name, "")

        if package.name.endswith("-git"):
            actual_version = get_actual_git_version(package.name)
            if actual_version:
                aur_version = actual_version

        needs_build = package.force or not repo_version or repo_version != aur_version
        if not needs_build and rebuild_missing:
            existing = list(build_arch_dir.glob(f"{package.name}-{repo_version}-*.pkg.tar.*"))
            if not existing:
                needs_build = True

        if not needs_build:
            skipped_count += 1
            log.info("Up-to-date, skipping")
            continue

        try:
            package_dir = clone_package(package.name)
            built_pkg_files.extend(build_package(package_dir, build_dir, ARCH))
        except (FileNotFoundError, RuntimeError, subprocess.SubprocessError, OSError) as e:
            log.error(f"Build failed for {package.name}: {e}")
            failed_count += 1

    if built_pkg_files:
        update_database(build_arch_dir, repo_name, built_pkg_files)

    cleanup(AUR_CLONE_DIR, build_dir, ARCH, repo_name, package_names)
    log.success(f"Built: {len(built_pkg_files)}; skipped: {skipped_count}; failed: {failed_count}")
    return 1 if failed_count else 0


"""
Why use return codes and SystemExit?

To allow the CLI to return a specific exit code to the caller.
Makes program flow explicit:
    1. Run main().
    2. Get its exit code.
    3. Exit the process with that code.
"""


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "help"):
        topic = getattr(args, "topic", None)
        subparsers_action = next(
            (action for action in parser._actions if isinstance(action, argparse._SubParsersAction)),
            None,
        )
        if topic and subparsers_action and topic in subparsers_action.choices:
            subparsers_action.choices[topic].print_help()
        else:
            parser.print_help()
        return 0
    if args.command == "build":
        return run_build(args.config, args.packages, args.rebuild_missing)
    if args.command == "build-index":
        return run_build_index(args.config)

    parser.error(f"unknown command: {args.command}")
    return 2


def cli() -> None:
    """Entrypoint for the command-line interface."""
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log.error("Interrupted by user!")
        raise SystemExit(130)


if __name__ == "__main__":
    cli()
