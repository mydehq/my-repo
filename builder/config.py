"""
Config parsing module for config.json using Python dataclasses and pathlib.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logger import log_error

CONFIG_FILE = Path("config.json")


@dataclass
class MetaConfig:
    repo_name: str = ""
    repo_url: str = ""
    project_url: str = ""


@dataclass
class TemplatesConfig:
    index: Path = Path("src/index.html")
    installer: Path = Path("src/install.sh")


@dataclass
class BuilderConfig:
    build_dir: Path = Path("build")
    dist_dir: Path = Path("dist")
    icon_file: Path = Path("src/icon.png")
    templates: TemplatesConfig = field(default_factory=TemplatesConfig)


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
            force = bool(opts.get("force", False))
            return PackageSpec(name=name, force=force, options=opts)
        case dict() as d if len(d) == 1:
            name, opts = next(iter(d.items()))
            if isinstance(opts, dict):
                force = bool(opts.get("force", False))
                return PackageSpec(name=name, force=force, options=opts)
            return PackageSpec(name=name)
        case _:
            return None


def load_config(path: Path | str = CONFIG_FILE) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        log_error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    raw_meta = data.get("meta", {})
    meta = MetaConfig(
        repo_name=raw_meta.get("repo-name", ""),
        repo_url=raw_meta.get("repo-url", ""),
        project_url=raw_meta.get("project-url", ""),
    )

    raw_builder = data.get("builder", {})
    raw_templates = raw_builder.get("templates", {})
    templates = TemplatesConfig(
        index=Path(raw_templates.get("index", "src/index.html")),
        installer=Path(raw_templates.get("installer", "src/install.sh")),
    )
    builder = BuilderConfig(
        build_dir=Path(raw_builder.get("build-dir", "build")),
        dist_dir=Path(raw_builder.get("dist-dir", "dist")),
        icon_file=Path(raw_builder.get("icon-file", "src/icon.png")),
        templates=templates,
    )

    packages: list[PackageSpec] = []
    raw_packages = data.get("packages", [])

    if isinstance(raw_packages, list):
        for item in raw_packages:
            spec = parse_package_item(item)
            if spec:
                packages.append(spec)
    elif isinstance(raw_packages, dict):
        for name, val in raw_packages.items():
            match val:
                case bool() if val is True:
                    packages.append(PackageSpec(name=name))
                case dict() as opts:
                    force = bool(opts.get("force", False))
                    packages.append(PackageSpec(name=name, force=force, options=opts))
                case _:
                    packages.append(PackageSpec(name=name))

    return Config(meta=meta, builder=builder, packages=packages)
