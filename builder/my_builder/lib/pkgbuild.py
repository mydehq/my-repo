"""
makepkg execution & dependency management module using pathlib.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .aur import (
    AurPackageInfo,
    AurRpcError,
    clone_package,
    fetch_aur_packages,
    fetch_aur_providers,
)
from .logger import log


@dataclass(frozen=True, slots=True)
class PackageDependencies:
    depends: tuple[str, ...] = ()
    make_depends: tuple[str, ...] = ()
    check_depends: tuple[str, ...] = ()


def get_package_dependencies(
    pkg_dir: Path,
    extra_pkgs: list[str] | None = None,
) -> PackageDependencies:
    res = subprocess.run(
        ["makepkg", "--printsrcinfo"],
        cwd=pkg_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"failed to extract package dependencies: {res.stderr}")

    depends: list[str] = []
    make_depends: list[str] = []
    check_depends: list[str] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        key, separator, value = line.partition(" = ")
        if not separator:
            continue
        if key == "depends" or key.startswith("depends_"):
            depends.append(value)
        elif key == "makedepends" or key.startswith("makedepends_"):
            make_depends.append(value)
        elif key == "checkdepends" or key.startswith("checkdepends_"):
            check_depends.append(value)

    make_depends.extend(extra_pkgs or [])
    return PackageDependencies(
        depends=tuple(
            dict.fromkeys(dependency for dependency in depends if dependency)
        ),
        make_depends=tuple(
            dict.fromkeys(dependency for dependency in make_depends if dependency)
        ),
        check_depends=tuple(
            dict.fromkeys(dependency for dependency in check_depends if dependency)
        ),
    )


def _dependency_parts(dependency: str) -> tuple[str, str, str]:
    match = re.fullmatch(r"([A-Za-z0-9@._+-]+)(?:(>=|<=|=|>|<)(.+))?", dependency)
    if not match:
        raise RuntimeError(f"Unsupported package dependency: {dependency}")
    return match.group(1), match.group(2) or "", match.group(3) or ""


def _version_satisfies(version: str, operator: str, required: str) -> bool:
    if not operator:
        return True
    result = subprocess.run(
        ["vercmp", version, required], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to compare package versions: {result.stderr}")
    comparison = int(result.stdout.strip())
    return {
        "=": comparison == 0,
        ">": comparison > 0,
        ">=": comparison >= 0,
        "<": comparison < 0,
        "<=": comparison <= 0,
    }[operator]


def _aur_candidate_matches(
    package: AurPackageInfo, name: str, operator: str, required: str
) -> bool:
    if package.name == name and _version_satisfies(package.version, operator, required):
        return True

    for provided in package.provides:
        provided_name, provided_operator, provided_version = _dependency_parts(provided)
        if provided_name != name:
            continue
        if not operator:
            return True
        if provided_operator and _version_satisfies(
            provided_version, operator, required
        ):
            return True
    return False


def _find_aur_candidate(dependency: str) -> AurPackageInfo | None:
    name, operator, required = _dependency_parts(dependency)
    try:
        candidates = fetch_aur_packages([name])
        package = candidates.get(name)
        if package and _aur_candidate_matches(package, name, operator, required):
            return package

        providers = fetch_aur_providers(name)
    except AurRpcError as error:
        raise RuntimeError(str(error)) from error

    return next(
        (
            provider
            for provider in providers
            if _aur_candidate_matches(provider, name, operator, required)
        ),
        None,
    )


def _resolve_dependency(
    dependency: str,
    visiting: set[str],
    built_bases: dict[str, dict[str, Path]],
) -> None:
    if (
        subprocess.run(
            ["pacman", "-T", dependency], capture_output=True, check=False
        ).returncode
        == 0
    ):
        return

    sync_check = subprocess.run(
        ["pacman", "-Sp", "--print-format", "%n", dependency],
        capture_output=True,
        check=False,
    )
    if sync_check.returncode == 0:
        install_result = subprocess.run(
            ["sudo", "pacman", "-S", "--noconfirm", "--needed", dependency],
            check=False,
        )
        if install_result.returncode != 0:
            raise RuntimeError(f"Failed to install repository dependency: {dependency}")
        if (
            subprocess.run(
                ["pacman", "-T", dependency], capture_output=True, check=False
            ).returncode
            != 0
        ):
            raise RuntimeError(f"Installed package does not satisfy: {dependency}")
        return

    package = _find_aur_candidate(dependency)
    if package is None:
        raise RuntimeError(f"No AUR package provides dependency: {dependency}")
    if package.name in visiting:
        chain = " -> ".join((*visiting, package.name))
        raise RuntimeError(f"Circular AUR dependency detected: {chain}")

    artifact = built_bases.get(package.package_base, {}).get(package.name)
    if artifact is None:
        visiting.add(package.name)
        package_dir = clone_package(package.name, package.package_base)
        dependencies = get_package_dependencies(package_dir)
        for child in dict.fromkeys(
            (
                *dependencies.depends,
                *dependencies.make_depends,
                *dependencies.check_depends,
            )
        ):
            _resolve_dependency(child, visiting, built_bases)

        build_result = subprocess.run(
            ["makepkg", "--noconfirm", "--nodeps", "--force", "--clean"],
            cwd=package_dir,
            check=False,
        )
        if build_result.returncode != 0:
            raise RuntimeError(f"Failed to build AUR dependency: {package.name}")

        artifacts: dict[str, Path] = {}
        for pattern in ("*.pkg.tar.zst", "*.pkg.tar.xz", "*.pkg.tar.gz"):
            for path in package_dir.glob(pattern):
                query = subprocess.run(
                    ["pacman", "-Qp", "--print-format", "%n", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if query.returncode == 0 and query.stdout.strip():
                    artifacts[query.stdout.strip()] = path
        built_bases[package.package_base] = artifacts
        artifact = artifacts.get(package.name)
        if artifact is None:
            raise RuntimeError(f"AUR build did not produce package: {package.name}")
        visiting.remove(package.name)

    install_result = subprocess.run(
        ["sudo", "pacman", "-U", "--noconfirm", "--needed", str(artifact)],
        check=False,
    )
    if install_result.returncode != 0:
        raise RuntimeError(f"Failed to install AUR dependency: {package.name}")
    if (
        subprocess.run(
            ["pacman", "-T", dependency], capture_output=True, check=False
        ).returncode
        != 0
    ):
        raise RuntimeError(f"Installed AUR package does not satisfy: {dependency}")


def install_deps(pkg_dir: Path, extra_pkgs: list[str] | None = None) -> None:
    log.info("Checking for package dependencies")

    pkg_dependencies = get_package_dependencies(pkg_dir, extra_pkgs)
    dependencies = list(
        dict.fromkeys(
            (
                *pkg_dependencies.depends,
                *pkg_dependencies.make_depends,
                *pkg_dependencies.check_depends,
            )
        )
    )

    if not dependencies:
        log.info("No package dependencies found")
        return

    missing = [
        dependency
        for dependency in dependencies
        if subprocess.run(
            ["pacman", "-T", dependency], capture_output=True, check=False
        ).returncode
        != 0
    ]
    if not missing:
        log.info("Package dependencies already satisfied")
        return

    log.info(f"Resolving missing dependencies: {' '.join(missing)}")
    visiting: set[str] = set()
    built_bases: dict[str, dict[str, Path]] = {}
    for dependency in missing:
        _resolve_dependency(dependency, visiting, built_bases)


# TODO: Add packager support. Warn if not set.
def build_package(
    pkg_dir: Path,
    build_dir: Path,
    arch: str,
    extra_pkgs: list[str] | None = None,
) -> list[str]:
    install_deps(pkg_dir, extra_pkgs)

    log.info(f"Running makepkg in {pkg_dir}")

    res = subprocess.run(
        ["makepkg", "--noconfirm", "--nodeps", "--force", "--clean"],
        cwd=pkg_dir,
        check=False,
    )

    if res.returncode != 0:
        log.info("")
        log.error("Build failed: Makepkg returned error.")
        raise RuntimeError("makepkg build failed")

    pkg_files: list[Path] = []
    for ext in ("*.pkg.tar.zst", "*.pkg.tar.xz"):
        pkg_files.extend(pkg_dir.glob(ext))

    if not pkg_files:
        log.error("No package files found after build")
        raise FileNotFoundError("No package files found")

    dest_dir = build_dir / arch
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for src in pkg_files:
        dest = dest_dir / src.name

        dest.unlink(missing_ok=True)
        shutil.copy2(src, dest)
        log.success(f"Packaged: {src.name}")

        copied.append(src.name)
        src.unlink(missing_ok=True)

    return copied
