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
    install_cmd: str = "{repo_url}/setup"
    output_dir: Path = Path("build")
    clone_dir: Path = Path(defaults.data_dir) / "clone"
    packager: str | None = None

    db_file: Path = field(init=False)

    def __post_init__(self) -> None:

        self.name = self.name.strip()

        if not self.display_name:
            self.display_name = self.name

        self.db_file = self.output_dir / f"{self.name}.tar.gz"

        self.output_dir = self.output_dir.expanduser().resolve()

        if "{repo_url}" in self.install_cmd:
            self.install_cmd = self.install_cmd.replace("{repo_url}", self.url)


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
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_str(cls, raw: str) -> Self:
        parts = raw.split("|")

        return cls(
            name=parts[0].strip(),
            force=len(parts) > 1 and parts[1].strip() == "always",
        )

    @classmethod
    def parse_list(cls, pkgs: list[str]) -> list[Self]:
        return [cls.from_str(pkg) for pkg in pkgs]


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
    packages: list[PackageSpec] = PackageSpec.parse_list(raw_config.get("packages", []))

    return Config(
        repo=repo,
        aur=aur,
        site=site,
        packages=packages,
    )
