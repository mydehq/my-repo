"""
Config parsing module for config.json using Python dataclasses and pathlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import yaml

from ..defaults import defaults


@dataclass(slots=True)
class RepoConfig:
    name: str
    url: str
    display_name: str = ""
    desc: str = "Automated AUR package builds."
    down_suffix: str = "/releases/download/repo"
    install_cmd: str = defaults.install_cmd
    output_dir: Path = Path("build")
    clone_dir: Path = Path(defaults.data_dir) / "clone"
    packager: str | None = None

    db_file: Path = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.name.strip()

        if not self.display_name:
            self.display_name = self.name

        self.output_dir = self.output_dir.expanduser().resolve()
        self.db_file = self.output_dir / "x86_64" / f"{self.name}.db.tar.gz"


@dataclass(slots=True)
class AURConfig:
    url: str = defaults.aur_url
    pkg_base: str = defaults.aur_pkg_url

    pkg_url: str = field(init=False)  # do not initialize

    def __post_init__(self) -> None:
        self.url = self.url.rstrip("/")
        self.pkg_base = self.pkg_base.rstrip("/")

        self.pkg_url = f"{self.url}/{self.pkg_base}"


@dataclass(slots=True)
class SiteConfig:
    url: str
    name: str = ""
    desc: str = ""
    input_dir: Path = defaults.site_input_dir
    output_dir: Path = Path("dist")

    def __post_init__(self) -> None:
        if self.url and not self.url.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")

        self.input_dir = self.input_dir.expanduser().resolve()
        self.output_dir = self.output_dir.expanduser().resolve()


@dataclass(slots=True)
class PackageSpec:
    name: str
    force: bool = False
    extra_pkgs: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Self:
        if len(raw) != 1:
            raise ValueError("package mapping must contain exactly one package name")

        name, options = next(iter(raw.items()))
        if not isinstance(name, str):
            raise TypeError("package name must be a string")
        if not name.strip():
            raise ValueError("package name must be a non-empty string")
        if options is None:
            options = {}
        if not isinstance(options, dict):
            raise TypeError(f"options for package {name!r} must be a mapping")

        force = options.get("always", False)
        if not isinstance(force, bool):
            raise TypeError(f"always for package {name!r} must be a boolean")

        extra_pkgs = options.get("extra_pkgs", [])
        if not isinstance(extra_pkgs, list):
            raise TypeError(f"extra_pkgs for package {name!r} must be a list")
        if any(not isinstance(pkg, str) for pkg in extra_pkgs):
            raise TypeError(f"extra_pkgs for package {name!r} must contain strings")
        if any(not pkg.strip() for pkg in extra_pkgs):
            raise ValueError(f"extra_pkgs for package {name!r} must be a list of names")

        return cls(
            name=name.strip(),
            force=force,
            extra_pkgs=[pkg.strip() for pkg in extra_pkgs],
        )

    @classmethod
    def parse_list(cls, pkgs: list[Any]) -> list[Self]:
        parsed: list[Self] = []
        for pkg in pkgs:
            if isinstance(pkg, str):
                parsed.append(cls(name=pkg.strip()))
            elif isinstance(pkg, dict):
                parsed.append(cls.from_mapping(pkg))
            else:
                raise TypeError("each package must be a string or a package mapping")
        return parsed


@dataclass(slots=True)
class Config:
    repo: RepoConfig
    aur: AURConfig
    site: SiteConfig
    packages: list[PackageSpec]

    def __post_init__(self) -> None:
        if not self.site.name:
            self.site.name = self.repo.display_name

        if not self.site.desc:
            self.site.desc = self.repo.desc

        self.repo.install_cmd = self.repo.install_cmd.format(
            site_url=self.site.url,
            repo_url=self.repo.url,
            packageer=self.repo.packager if self.repo.packager else None,
        )


class ConfigError(Exception):
    """Raised when configuration loading fails."""


def load_config(conf_file: Path) -> Config:
    """
    Load and parse a configuration file.
    """

    if not isinstance(conf_file, Path):
        raise ConfigError("conf_file must be a Path")

    conf_file = conf_file.expanduser().resolve()

    if not conf_file.exists():
        raise ConfigError(f"Config file not found: {conf_file}")

    if not conf_file.is_file():
        raise ConfigError(f"Not a file: {conf_file}")

    try:
        raw_config: dict[str, Any] = yaml.safe_load(
            conf_file.read_text(encoding="utf-8")
        )
    except OSError as exc:
        raise ConfigError(f"Failed to read config: {conf_file}") from exc

    repo: RepoConfig = RepoConfig(**raw_config.get("repo", {}))
    site: SiteConfig = SiteConfig(**raw_config.get("site", {}))
    aur: AURConfig = AURConfig(**raw_config.get("aur", {}))
    try:
        packages = PackageSpec.parse_list(raw_config.get("packages", []))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid packages configuration: {exc}") from exc

    return Config(
        repo=repo,
        aur=aur,
        site=site,
        packages=packages,
    )
