"""
CLI routing & subcommand handler module using Python 3.14 pattern matching, dataclasses, and pathlib.
"""

import glob
import os
import shutil
import subprocess
import sys

from . import __version__
from .lib.aur import (
    AUR_CLONE_DIR,
    clone_package,
    fetch_aur_versions,
    get_actual_git_version,
)
from .lib.colors import color
from .lib.config import CONFIG_FILE, load_config
from .lib.logger import log
from .lib.pkgbuild import build_package
from .lib.repo import cleanup, get_repo_version, migrate_database, update_database
from .lib.site import generate_site

ARCH = "x86_64"


def print_help() -> None:
    print("Usage: python -m builder <command> [flags]")
    print()
    print("Commands:")
    print(
        "  build        Build packages from config.json and update repository database"
    )
    print(
        "  build-index  Generate repository landing page and installer in dist directory"
    )
    print()
    print("Flags:")
    print("  -h, --help     Print this help message")
    print("  -v, --version  Print version information")


def run_build() -> None:
    log.info("")
    log.warn("Starting AUR package build process\n")

    if not shutil.which("makepkg"):
        log.error("makepkg is required but not installed")
        sys.exit(1)

    cfg = load_config()
    build_dir = cfg.builder.build_dir
    meta = cfg.meta

    if not meta.repo_name:
        log.error("meta.repo-name is required")
        sys.exit(1)

    target_dir = build_dir / ARCH
    target_dir.mkdir(parents=True, exist_ok=True)

    if not os.access(target_dir, os.W_OK):
        log.error(f"Build directory is not writable: {target_dir}")
        sys.exit(1)

    AUR_CLONE_DIR.mkdir(parents=True, exist_ok=True)

    migrate_database(target_dir, meta.repo_name)

    package_names = [p.name for p in cfg.packages]

    log.info(f"Found {len(cfg.packages)} packages in {CONFIG_FILE}")
    log.info("Fetching upstream versions from AUR...")

    remote_versions = fetch_aur_versions(package_names)

    skipped_count = 0
    failed_count = 0
    built_pkg_files: list[str] = []

    for pkg in cfg.packages:
        log.info("")
        log.info(f"Processing package: {color.yellow(pkg.name)}")

        db_file = build_dir / ARCH / f"{meta.repo_name}.db.tar.gz"
        repo_version = get_repo_version(db_file, pkg.name)
        aur_version = remote_versions.get(pkg.name, "")

        if pkg.name.endswith("-git"):
            actual_version = get_actual_git_version(pkg.name)
            if actual_version:
                aur_version = actual_version

        log.info(f"     AUR  version: {aur_version or '<unknown>'}")
        log.info(f"     Repo version: {repo_version or '<not in repo>'}")

        needs_build = False

        if not aur_version:
            if repo_version:
                log.warn("Could not get version from AUR API. Keeping repo version.")
            else:
                log.warn("Package not found in AUR API.")
                needs_build = True

        elif not repo_version:
            log.warn("Package not in repo, downloading...")
            needs_build = True

        elif repo_version != aur_version:
            log.warn("Version mismatch, updating...")
            needs_build = True

        elif pkg.force:
            log.warn("Force flag set, rebuilding...")
            needs_build = True

        else:
            pattern = str(build_dir / ARCH / f"{pkg.name}-{repo_version}-*.pkg.tar.*")
            matches = glob.glob(pattern)

            if not matches:
                log.warn("Package file missing, rebuilding...")
                needs_build = True
            else:
                log.info("Up-to-date, skipping")
                skipped_count += 1

        if needs_build:
            try:
                pkg_dir = clone_package(pkg.name)
                files = build_package(pkg_dir, build_dir, ARCH)
                built_pkg_files.extend(files)
            except (RuntimeError, FileNotFoundError, subprocess.SubprocessError) as e:
                log.error(f"Build failed for {pkg.name}: {e}")
                failed_count += 1

    log.info("")

    if built_pkg_files:
        update_database(build_dir / ARCH, meta.repo_name, built_pkg_files)
    else:
        log.info("Repository update not needed")

    cleanup(AUR_CLONE_DIR, build_dir, ARCH, meta.repo_name, package_names)

    log.info("")
    log.info("Build Summary:")
    log.success(f"   Built:   {len(built_pkg_files)}")
    log.info(f"   Skipped: {skipped_count}")
    log.error(f"   Failed:  {failed_count}")

    if failed_count > 0:
        log.error(f"Build failed for {failed_count} packages")
        sys.exit(1)
    else:
        log.success("Build completed successfully\n")


def run_build_index() -> None:
    cfg = load_config()
    generate_site(cfg)


def main() -> None:
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    arg = sys.argv[1]

    match arg:
        case "-h" | "--help" | "help":
            print_help()
            sys.exit(0)

        case "-v" | "--version" | "version":
            print(f"Builder v{__version__}")
            sys.exit(0)

        case "build":
            run_build()

        case "build-index":
            run_build_index()

        case _:
            print(f"Unknown command or flag: {arg}")
            print_help()
            sys.exit(1)
