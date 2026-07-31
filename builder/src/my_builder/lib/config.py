"""
Config parsing module for config.json using Python dataclasses and pathlib.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logger import log_error

CONFIG_FILE = Path("config.json")


class ConfigError(Exception):
    """Raised when configuration loading or parsing fails."""


@dataclass
class MetaConfig:
    repo_name: str = ""
    repo_url: str = ""
    project_url: str = ""


@dataclass
class TemplatesConfig:
    index: Path = Path("src/index.html")
    installer: Path = Path("src/install.sh")

    def __post_init__(self) -> None:
        self.index = Path(self.index)
        self.installer = Path(self.installer)


@dataclass
class BuilderConfig:
    build_dir: Path = Path("build")
    dist_dir: Path = Path("dist")
    icon_file: Path = Path("src/icon.png")
    templates: TemplatesConfig = field(default_factory=TemplatesConfig)

    def __post_init__(self) -> None:
        self.build_dir = Path(self.build_dir)
        self.dist_dir = Path(self.dist_dir)
        self.icon_file = Path(self.icon_file)

        if isinstance(self.templates, dict):
            self.templates = TemplatesConfig(**self.templates)


@dataclass
class PackageSpec:
    name: str
    force: bool = False
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    meta: MetaConfig
    builder: BuilderConfig
    packages: list[PackageSpec]


def parse_package_item(item: Any) -> PackageSpec | None:
    match item:
        case str(name):
            return PackageSpec(name=name)

        case {"name": str(name), **opts}:
            opts_copy = dict(opts)
            force = bool(opts_copy.pop("force", False))

            return PackageSpec(name=name, force=force, options=opts_copy)

        case dict() as d if len(d) == 1:
            name, opts = next(iter(d.items()))

            if isinstance(opts, dict):
                opts_copy = dict(opts)
                force = bool(opts_copy.pop("force", False))

                return PackageSpec(name=name, force=force, options=opts_copy)

            return PackageSpec(name=name)

        case _:
            return None


def parse_packages(raw_packages: Any) -> list[PackageSpec]:
    packages: list[PackageSpec] = []

    if isinstance(raw_packages, list):
        for item in raw_packages:
            spec = parse_package_item(item)
            if spec:
                packages.append(spec)

    elif isinstance(raw_packages, dict):
        for name, val in raw_packages.items():
            match val:
                case True | False:
                    packages.append(PackageSpec(name=name))

                case dict() as opts:
                    opts_copy = dict(opts)
                    force = bool(opts_copy.pop("force", False))
                    packages.append(
                        PackageSpec(name=name, force=force, options=opts_copy)
                    )

                case _:
                    packages.append(PackageSpec(name=name))

    return packages


def load_config(path: Path | str = CONFIG_FILE) -> Config:
    config_path = Path(path)

    try:
        data: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log_error(f"Config file not found: {config_path}")
        raise ConfigError(f"File not found: {config_path}")
    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in config file: {e}")
        raise ConfigError(f"Invalid JSON: {e}")
    except OSError as e:
        log_error(f"Failed to load config file: {config_path}")
        raise ConfigError(f"OS error reading file: {e}")

    meta = MetaConfig(**data.get("meta", {}))
    builder = BuilderConfig(**data.get("builder", {}))
    packages = parse_packages(data.get("packages", []))

    return Config(meta=meta, builder=builder, packages=packages)
