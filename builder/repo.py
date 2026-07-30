"""
Repository database (repo-add, repo-remove, db parsing, cleanup, migration) module using pathlib.
"""

import gzip
import shutil
import subprocess
import tarfile
from pathlib import Path

from .logger import log_error, log_info, log_msg, log_success, log_warn


def get_repo_version(db_file: Path | str, pkg_name: str) -> str:
    db_path = Path(db_file)
    if not db_path.exists():
        return ""

    prefix = f"{pkg_name}-"
    try:
        with (
            gzip.open(db_path, "rb") as gz,
            tarfile.open(fileobj=gz, mode="r:*") as tar,
        ):
            for member in tar.getmembers():
                parts = member.name.split("/")
                if len(parts) >= 2 and parts[1] == "desc":
                    dir_name = parts[0]
                    if dir_name.startswith(prefix):
                        rem = dir_name[len(prefix) :]
                        if rem.count("-") >= 1:
                            return rem
    except (gzip.BadGzipFile, tarfile.TarError, OSError):
        return ""

    return ""


def update_database(build_arch_dir: Path, db_name: str, packages: list[str]) -> None:
    if not packages:
        log_info("No new packages to add to database.")
        return

    log_info(f"Updating repository database with {len(packages)} new packages...")
    db_file = f"{db_name}.db.tar.gz"
    lock_file = build_arch_dir / f"{db_file}.lck"
    if lock_file.exists():
        log_warn(f"Removing stale lock file: {lock_file}")
        lock_file.unlink(missing_ok=True)

    res = subprocess.run(
        ["repo-add", db_file] + packages, cwd=build_arch_dir, check=False
    )
    if res.returncode != 0:
        log_error("Failed to update database")
        raise RuntimeError("repo-add failed")

    for f in build_arch_dir.glob("*.old"):
        f.unlink(missing_ok=True)

    log_msg("")
    log_success("Repository database updated")
    log_msg("")


def migrate_database(build_arch_dir: Path, repo_name: str) -> None:
    db_file = f"{repo_name}.db.tar.gz"
    if not build_arch_dir.exists():
        return

    existing_dbs = [
        f.name for f in build_arch_dir.glob("*.db.tar.gz") if f.name != db_file
    ]
    if len(existing_dbs) == 1:
        old_db = existing_dbs[0]
        old_base = old_db.removesuffix(".db.tar.gz")
        old_files = f"{old_base}.files.tar.gz"
        old_db_link = build_arch_dir / f"{old_base}.db"
        old_files_link = build_arch_dir / f"{old_base}.files"

        log_warn(f"Detected repository rename from '{old_base}' to '{repo_name}'\n")
        log_info("Migrating database files...")

        (build_arch_dir / old_db).rename(build_arch_dir / db_file)
        log_msg(f"Renamed DB: {old_db} -> {db_file}")

        if old_db_link.is_symlink() or old_db_link.exists():
            old_db_link.unlink()
            (build_arch_dir / f"{repo_name}.db").symlink_to(db_file)

        if (build_arch_dir / old_files).exists():
            new_files = f"{repo_name}.files.tar.gz"
            (build_arch_dir / old_files).rename(build_arch_dir / new_files)
            if old_files_link.is_symlink() or old_files_link.exists():
                old_files_link.unlink()
                (build_arch_dir / f"{repo_name}.files").symlink_to(new_files)

        log_success("Migration complete")
        log_msg("")


def cleanup(
    aur_clone_dir: Path,
    build_dir: Path,
    arch: str,
    repo_name: str,
    valid_pkgs: list[str],
) -> None:
    log_msg("")
    log_info("Cleaning up AUR cache...")
    if aur_clone_dir.exists():
        for item in aur_clone_dir.iterdir():
            if item.is_dir() and item.name not in valid_pkgs:
                log_warn(f"Removing unused AUR clone: {item.name}")
                shutil.rmtree(item, ignore_errors=True)

    log_info("Cleaning up repository database...")
    build_arch_dir = build_dir / arch

    if not build_arch_dir.exists():
        return

    latest_pkg_files: dict[str, str] = {}
    latest_pkg_times: dict[str, float] = {}

    for item in build_arch_dir.iterdir():
        if item.is_dir():
            continue
        name = item.name
        if name.endswith((".pkg.tar.zst", ".pkg.tar.xz")):
            ext = ".pkg.tar.zst" if name.endswith(".pkg.tar.zst") else ".pkg.tar.xz"
            base = name.removesuffix(ext)
            parts = base.split("-")
            if len(parts) >= 4:
                pkg_name = "-".join(parts[:-3])
                if pkg_name in valid_pkgs:
                    mtime = item.stat().st_mtime
                    if (
                        pkg_name not in latest_pkg_times
                        or mtime > latest_pkg_times[pkg_name]
                    ):
                        latest_pkg_files[pkg_name] = name
                        latest_pkg_times[pkg_name] = mtime

    pkgs_to_remove: set[str] = set()

    for item in build_arch_dir.iterdir():
        if item.is_dir():
            continue
        name = item.name

        if name.startswith((f"{repo_name}.db", f"{repo_name}.files")) or name in (
            "index.html",
            "install",
            "icon.png",
        ):
            continue

        is_pkg = name.endswith((".pkg.tar.zst", ".pkg.tar.xz"))
        extracted_name = ""
        if is_pkg:
            ext = ".pkg.tar.zst" if name.endswith(".pkg.tar.zst") else ".pkg.tar.xz"
            base = name.removesuffix(ext)
            parts = base.split("-")
            if len(parts) >= 4:
                extracted_name = "-".join(parts[:-3])

        is_valid = extracted_name in valid_pkgs if extracted_name else False
        is_latest = latest_pkg_files.get(extracted_name) == name

        if not is_valid or not is_latest:
            if is_pkg:
                if is_valid and not is_latest:
                    log_warn(f"Removing old version: {name}")
                else:
                    log_warn(f"Removing stale artifact: {name}")
                if extracted_name:
                    pkgs_to_remove.add(extracted_name)
            else:
                log_warn(f"Removing junk file: {name}")
            item.unlink(missing_ok=True)

    db_file = f"{repo_name}.db.tar.gz"

    for pkg_to_remove in pkgs_to_remove:
        subprocess.run(
            ["repo-remove", db_file, pkg_to_remove],
            cwd=build_arch_dir,
            capture_output=True,
            check=False,
        )
