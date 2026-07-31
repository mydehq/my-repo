"""
makepkg execution & dependency management module using pathlib.
"""

import shutil
import subprocess
from pathlib import Path

from .logger import log_error, log_info, log_msg, log_success


def install_deps(pkg_dir: Path) -> None:
    log_info("Checking for build dependencies")
    res = subprocess.run(
        ["makepkg", "--printsrcinfo"],
        cwd=pkg_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"failed to extract makedepends: {res.stderr}")

    makedeps: list[str] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if line.startswith("makedepends = "):
            makedeps.append(line.removeprefix("makedepends = "))

    if not makedeps:
        log_info("No build dependencies found")
        return

    check_res = subprocess.run(
        ["pacman", "-T"] + makedeps, capture_output=True, check=False
    )

    if check_res.returncode == 0:
        log_info("Build dependencies already satisfied")
        return

    log_info(f"Installing missing dependencies: {' '.join(makedeps)}")

    inst_res = subprocess.run(
        ["sudo", "pacman", "-S", "--noconfirm", "--needed"] + makedeps, check=False
    )

    if inst_res.returncode != 0:
        raise RuntimeError("Failed to install build dependencies")


def build_package(pkg_dir: Path, build_dir: Path, arch: str) -> list[str]:
    install_deps(pkg_dir)

    log_info(f"Running makepkg in {pkg_dir}")

    res = subprocess.run(
        ["makepkg", "--noconfirm", "--nodeps", "--force", "--clean"],
        cwd=pkg_dir,
        check=False,
    )

    if res.returncode != 0:
        log_msg("")
        log_error("Build failed: Makepkg returned error.")
        raise RuntimeError("makepkg build failed")

    pkg_files: list[Path] = []
    for ext in ("*.pkg.tar.zst", "*.pkg.tar.xz"):
        pkg_files.extend(pkg_dir.glob(ext))

    if not pkg_files:
        log_error("No package files found after build")
        raise FileNotFoundError("No package files found")

    dest_dir = build_dir / arch
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for src in pkg_files:
        dest = dest_dir / src.name

        dest.unlink(missing_ok=True)
        shutil.copy2(src, dest)
        log_success(f"Packaged: {src.name}")

        copied.append(src.name)
        src.unlink(missing_ok=True)

    return copied
