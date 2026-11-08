"""
Repository database (repo-add, repo-remove, db parsing, cleanup, migration) module using pathlib.
"""

import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import IO, Self

from .logger import log


class PKGError(Exception):
    """Raised when a package is not found in the repository."""


@dataclass(slots=True, frozen=True)
class PkgInfo:
    name: str
    filename: str
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

    @classmethod
    def from_dict(cls, data: dict[str, list[str]]) -> Self:
        """Construct a PkgInfo from a dictionary."""

        def get_str(key: str, default: str = "") -> str:
            return data.get(key, [default])[0]

        def get_int(key: str, default: int = 0) -> int:
            val = data.get(key, ["0"])[0]
            return int(val) if val.isdigit() else default

        def get_list(key: str) -> list[str]:
            return data.get(key, [])

        return cls(
            name=get_str("NAME"),
            filename=get_str(
                "FILENAME",
                default=f"{get_str('NAME')}-{get_str('VERSION')}-{get_str('ARCH')}.pkg.tar.zst",
            ),
            base=get_str("BASE", default=get_str("NAME")),
            version=get_str("VERSION"),
            desc=get_str("DESC"),
            url=get_str("URL"),
            licenses=get_list("LICENSE"),
            arch=get_str("ARCH"),
            build_date=get_int("BUILDDATE"),
            packager=get_str("PACKAGER"),
            compressed_size=get_int("CSIZE"),
            installed_size=get_int("ISIZE"),
            sha256=get_str("SHA256"),
            dependencies=get_list("DEPENDS"),
            optional_dependencies=get_list("OPTDEPENDS"),
            make_dependencies=get_list("MAKEDEPENDS"),
            check_dependencies=get_list("CHECKDEPENDS"),
            provides=get_list("PROVIDES"),
            conflicts=get_list("CONFLICTS"),
            replaces=get_list("REPLACES"),
            groups=get_list("GROUPS"),
        )


@dataclass(slots=True)
class RepoInfo:
    packages: list[PkgInfo] = field(default_factory=list)

    @property
    def pkg_count(self) -> int:
        return len(self.packages)


def _parse_desc(desc: IO[bytes]) -> dict[str, list[str]]:
    """Parse a pacman desc file into key-value lists."""

    fields: dict[str, list[str]] = {}
    current: str | None = None

    for line in desc.read().decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("%") and line.endswith("%"):
            current = line[1:-1]
            fields[current] = []

        elif current is not None:
            fields[current].append(line)

    return fields


@cache
def get_repo_pkgs(db_file: Path) -> RepoInfo:
    """Parse pacman database archive (.db or .db.tar.gz) and return RepoInfo."""

    if not db_file.exists():
        return RepoInfo()

    packages: list[PkgInfo] = []

    with tarfile.open(db_file, "r:*") as tar:
        for member in tar.getmembers():
            if not member.name.endswith("/desc"):
                continue

            f = tar.extractfile(member)
            if f is not None:
                packages.append(PkgInfo.from_dict(_parse_desc(f)))

    return RepoInfo(packages=packages)


@cache
def get_pkg_info(db_file: Path, pkg_name: str) -> PkgInfo | None:
    """Return package information for a specific package from a pacman repository database.

    Returns None if the package is not found.
    """
    repo = get_repo_pkgs(db_file)

    for pkg in repo.packages:
        if pkg.name == pkg_name:
            return pkg

    return None


@cache
def get_repo_pkg_count(db_file: Path) -> int:
    """Count packages in a db file"""
    if not db_file.exists():
        raise FileNotFoundError(f"Database file '{db_file}' does not exist.")

    with tarfile.open(db_file, "r:*") as tar:
        return sum(1 for member in tar.getmembers() if member.name.endswith("/desc"))


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
) -> list[str]:
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
        return []

    pkgs_to_remove: set[str] = set()
    db_file = build_arch_dir / f"{repo_name}.db.tar.gz"
    valid_set = set(valid_pkgs)

    # Check for packages in repository DB that are no longer configured
    if db_file.exists():
        repo_info = get_repo_pkgs(db_file)
        for pkg in repo_info.packages:
            if pkg.name not in valid_set:
                log.warn(
                    f"Package '{pkg.name}' in repository DB is not in config, marking for removal"
                )
                pkgs_to_remove.add(pkg.name)

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
                if extracted_name and not is_valid:
                    pkgs_to_remove.add(extracted_name)
            else:
                log.warn(f"Removing junk file: {name}")

            item.unlink(missing_ok=True)

    db_file_name = f"{repo_name}.db.tar.gz"

    for pkg_to_remove in sorted(pkgs_to_remove):
        log.info(f"Removing '{pkg_to_remove}' from database...")
        subprocess.run(
            ["repo-remove", db_file_name, pkg_to_remove],
            cwd=build_arch_dir,
            capture_output=True,
            check=False,
        )

    for f in build_arch_dir.glob("*.old"):
        f.unlink(missing_ok=True)

    if pkgs_to_remove:
        get_repo_pkgs.cache_clear()
        get_pkg_info.cache_clear()

    return sorted(pkgs_to_remove)
