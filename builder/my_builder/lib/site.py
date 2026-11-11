"""Process website templates and generate the repo index page."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2, copymode
from urllib.parse import urlsplit

from .. import __app__name__, __app_url__, __version__
from ..defaults import defaults
from .config import Config
from .logger import log
from .repo import get_repo_pkg_count, get_repo_pkgs

_VAR_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


class SiteGenerationError(Exception):
    """Raised when the site generation fails."""


class TemplateError(SiteGenerationError):
    """Raised when the template rendering fails."""


def render_template(
    content: str,
    variables: Mapping[str, object],
    strict: bool = True,
) -> str:
    """Render {{name}} placeholders."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)

        try:
            return str(variables[name])
        except KeyError as exc:
            if strict:
                raise TemplateError(f"Unknown template variable {name!r}") from exc
            return f"{{{name}}}"

    return _VAR_RE.sub(replace, content)


def _validate_project_url(raw_url: str) -> str:
    project_url = raw_url.strip()
    try:
        parsed_url = urlsplit(project_url)
    except ValueError:
        return ""

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return ""

    return project_url


def gen_pkg_data(cfg: Config) -> list[dict[str, str]]:
    """Generate package data for the client-rendered package list."""
    packages = get_repo_pkgs(cfg.repo.db_file)
    repo_dwn_base = f"{cfg.repo.url.rstrip('/')}{cfg.repo.down_suffix}".rstrip("/")

    return [
        {
            "pkg_name": pkg.name,
            "pkg_desc": pkg.desc,
            "pkg_version": pkg.version,
            "pkg_aur_url": f"{defaults.aur_pkg_url}/{pkg.name}",
            "pkg_arch": pkg.arch,
            "pkg_filename": pkg.filename,
            "pkg_download_url": f"{repo_dwn_base}/{pkg.filename}",
            "pkg_project_url": _validate_project_url(pkg.url),
        }
        for pkg in packages.packages
    ]


def generate_site(cfg: Config) -> int:
    """Generate the repository website."""

    if not cfg.site.input_dir.exists():
        raise SiteGenerationError(f"input_dir does not exist: {cfg.site.input_dir}")

    if not cfg.site.input_dir.is_dir():
        raise SiteGenerationError(f"input_dir is not a directory: {cfg.site.input_dir}")

    if cfg.site.output_dir.is_file():
        raise SiteGenerationError(
            f"output_dir is not a directory: {cfg.site.output_dir}"
        )

    cfg.site.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        repo_pkg_count = get_repo_pkg_count(cfg.repo.db_file)
    except FileNotFoundError as e:
        raise SiteGenerationError(
            f"Database file not found: {cfg.repo.db_file}, Have You bulit repo?"
        ) from e

    package_data = gen_pkg_data(cfg)

    ci_run_url = os.environ.get("CI_RUN_URL", "").strip()
    ci_run_hash = os.environ.get("CI_RUN_HASH", "").strip()

    if not ci_run_hash:
        ci_run_hash = os.environ.get("GITHUB_SHA", "").strip()

    if not ci_run_hash:
        try:
            ci_run_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
        except (subprocess.SubprocessError, OSError, TimeoutError):
            ci_run_hash = "local"

    ci_run_hash = ci_run_hash[:7]

    if not ci_run_url:
        server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip(
            "/"
        )
        repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
        run_id = os.environ.get("GITHUB_RUN_ID", "").strip()

        if repository and run_id:
            ci_run_url = f"{server_url}/{repository}/actions/runs/{run_id}"
        elif run_id and cfg.repo.url:
            ci_run_url = f"{cfg.repo.url.rstrip('/')}/actions/runs/{run_id}"
        elif cfg.repo.url:
            ci_run_url = f"{cfg.repo.url.rstrip('/')}/actions"

    variables = {
        "builder_name": __app__name__,
        "builder_version": __version__,
        "builder_url": __app_url__,
        "repo_name": cfg.repo.name,
        "repo_display_name": cfg.repo.display_name,
        "repo_url": cfg.repo.url,
        "repo_desc": cfg.repo.desc,
        "repo_pkg_count": repo_pkg_count,
        "repo_down_suffix": cfg.repo.down_suffix,
        "repo_dwn_url": f"{cfg.repo.url.rstrip('/')}{cfg.repo.down_suffix}",
        "repo_install_cmd": cfg.repo.install_cmd,
        "repo_packager": cfg.repo.packager,
        "last_updated": datetime.now(UTC).timestamp(),
        "ci_run_url": ci_run_url,
        "ci_run_hash": ci_run_hash,
        "site_url": cfg.site.url,
        "site_name": cfg.site.name,
        "site_desc": cfg.site.desc,
    }

    for path in cfg.site.input_dir.rglob("*"):
        if not path.is_file():
            continue

        out_path = cfg.site.output_dir / path.relative_to(cfg.site.input_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            copy2(path, out_path)
            continue
        except OSError as e:
            raise SiteGenerationError(f"Failed to read template: {path}") from e

        try:
            content = render_template(content, variables)
        except TemplateError as e:
            raise SiteGenerationError(f"{path.relative_to(Path.cwd())}: {e}") from e

        try:
            out_path.write_text(content, encoding="utf-8")
            copymode(path, out_path)
        except OSError as e:
            raise SiteGenerationError(f"Failed to write output file: {out_path}") from e

        log.info(f"Processed {path.relative_to(cfg.site.input_dir)}")

    try:
        (cfg.site.output_dir / "packages.json").write_text(
            json.dumps(package_data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    except OSError as e:
        raise SiteGenerationError(
            f"Failed to write package data: {cfg.site.output_dir / 'packages.json'}"
        ) from e

    return 0
