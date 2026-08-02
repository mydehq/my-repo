"""
Repository database (repo-add, repo-remove, db parsing, cleanup, migration) module using pathlib.
"""

import gzip
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from .logger import log


class PKGError(Exception):
    """Raised when a package is not found in the repository."""


@dataclass(slots=True, frozen=True)
class PkgInfo:
    name: str
    base: str
    version: str
    desc: str

    url: str
    licenses: list[str]
    arch: str

    build_date: int
    packager: str

    compressed_size: int
    installed_size: int
    sha256: str

    dependencies: list[str]
    optional_dependencies: list[str]
    make_dependencies: list[str]
    check_dependencies: list[str]

    provides: list[str]
    conflicts: list[str]
    replaces: list[str]

    groups: list[str]

    @property
    def compressed_size_mb(self) -> float:
        return self.compressed_size / (1024 * 1024)

    @property
    def installed_size_mb(self) -> float:
        return self.installed_size / (1024 * 1024)

    @property
    def build_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.build_date, tz=UTC)


def _parse_desc(desc: IO[bytes]) -> dict[str, list[str]]:
    """Parse a pacman desc file."""

    fields: dict[str, list[str]] = {}
    current: str | None = None

    for line in desc.read().decode("utf-8", errors="replace").splitlines():
        if not line:
            continue

        if line.startswith("%") and line.endswith("%"):
            current = line[1:-1]
            fields[current] = []
        elif current is not None:
            fields[current].append(line)

    return fields


def get_pkg_info(db_file: Path, pkg_name: str) -> PkgInfo:
    """Return package information from a pacman repository database."""

    if not db_file.is_file():
        raise ValueError(f"Invalid database file: {db_file}")

    prefix = f"{pkg_name}-"

    try:
        with (
            gzip.open(db_file, "rb") as gz,
            tarfile.open(fileobj=gz, mode="r:*") as tar,
        ):
            for member in tar:
                parts = member.name.split("/")

                if (
                    len(parts) != 2
                    or parts[1] != "desc"
                    or not parts[0].startswith(prefix)
                ):
                    continue

                desc = tar.extractfile(member)

                if desc is None:
                    continue

                fields = _parse_desc(desc)

                return PkgInfo(
                    name=fields["NAME"][0],
                    base=fields.get("BASE", [""])[0],
                    version=fields["VERSION"][0],
                    desc=fields.get("DESC", [""])[0],
                    url=fields.get("URL", [""])[0],
                    licenses=fields.get("LICENSE", []),
                    arch=fields["ARCH"][0],
                    build_date=int(fields["BUILDDATE"][0]),
                    packager=fields.get("PACKAGER", [""])[0],
                    compressed_size=int(fields.get("CSIZE", ["0"])[0]),
                    installed_size=int(fields.get("ISIZE", ["0"])[0]),
                    sha256=fields.get("SHA256SUM", [""])[0],
                    dependencies=fields.get("DEPENDS", []),
                    optional_dependencies=fields.get("OPTDEPENDS", []),
                    make_dependencies=fields.get("MAKEDEPENDS", []),
                    check_dependencies=fields.get("CHECKDEPENDS", []),
                    provides=fields.get("PROVIDES", []),
                    conflicts=fields.get("CONFLICTS", []),
                    replaces=fields.get("REPLACES", []),
                    groups=fields.get("GROUPS", []),
                )

    except (gzip.BadGzipFile, tarfile.TarError, OSError) as e:
        raise RuntimeError(f"Failed to read '{db_file}': {e}") from e

    raise LookupError(
        f"Package '{pkg_name}' not found in repository database '{db_file}'."
    )


def update_database(build_arch_dir: Path, db_name: str, packages: list[str]) -> None:
    if not packages:
        log.info("No new packages to add to database.")
        return

    log.info(f"Updating repository database with {len(packages)} new packages...")

    db_file = f"{db_name}.db.tar.gz"
    lock_file = build_arch_dir / f"{db_file}.lck"

    if lock_file.exists():
        log.warn(f"Removing stale lock file: {lock_file}")
        lock_file.unlink(missing_ok=True)

    res = subprocess.run(
        ["repo-add", db_file] + packages, cwd=build_arch_dir, check=False
    )

    if res.returncode != 0:
        log.error("Failed to update database")
        raise RuntimeError("repo-add failed")

    for f in build_arch_dir.glob("*.old"):
        f.unlink(missing_ok=True)

    log.info("")
    log.success("Repository database updated")
    log.info("")


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

        log.warn(f"Detected repository rename from '{old_base}' to '{repo_name}'\n")
        log.info("Migrating database files...")

        (build_arch_dir / old_db).rename(build_arch_dir / db_file)

        log.success(f"Renamed DB: {old_db} -> {db_file}")

        if old_db_link.is_symlink() or old_db_link.exists():
            old_db_link.unlink()
            (build_arch_dir / f"{repo_name}.db").symlink_to(db_file)

        if (build_arch_dir / old_files).exists():
            new_files = f"{repo_name}.files.tar.gz"
            (build_arch_dir / old_files).rename(build_arch_dir / new_files)
            if old_files_link.is_symlink() or old_files_link.exists():
                old_files_link.unlink()
                (build_arch_dir / f"{repo_name}.files").symlink_to(new_files)

        log.success("Migration complete")
        log.info("")


def cleanup(
    aur_clone_dir: Path,
    build_dir: Path,
    arch: str,
    repo_name: str,
    valid_pkgs: list[str],
) -> None:

    log.info("")
    log.info("Cleaning up AUR cache...")
    if aur_clone_dir.exists():
        for item in aur_clone_dir.iterdir():
            if item.is_dir() and item.name not in valid_pkgs:
                log.warn(f"Removing unused AUR clone: {item.name}")
                shutil.rmtree(item, ignore_errors=True)

    log.info("Cleaning up repository database...")
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
                    log.warn(f"Removing old version: {name}")
                else:
                    log.warn(f"Removing stale artifact: {name}")
                if extracted_name:
                    pkgs_to_remove.add(extracted_name)
            else:
                log.warn(f"Removing junk file: {name}")

            item.unlink(missing_ok=True)

    db_file = f"{repo_name}.db.tar.gz"

    for pkg_to_remove in pkgs_to_remove:
        subprocess.run(
            ["repo-remove", db_file, pkg_to_remove],
            cwd=build_arch_dir,
            capture_output=True,
            check=False,
        )
