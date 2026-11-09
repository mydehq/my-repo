"""Process website templates and generate the repo index page."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2, copymode

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
    """Render a template by replacing {var_name} placeholders."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)

        try:
            return str(variables[name])
        except KeyError as exc:
            if strict:
                raise TemplateError(f"Unknown template variable {name!r}") from exc
            return f"{{{name}}}"

    return _VAR_RE.sub(replace, content)


def get_pkg_template(content: str) -> str:
    inside = False
    found_start = False
    lines: list[str] = []

    for line in content.splitlines(keepends=True):
        if defaults.pkg_template_start in line:
            if found_start:
                raise TemplateError("Multiple package template blocks found")

            found_start = True
            inside = True
            continue

        if defaults.pkg_template_end in line:
            if not inside:
                raise TemplateError("Found end marker before start marker")

            return "".join(lines)

        if inside:
            lines.append(line)

    if found_start:
        raise TemplateError("Missing package template end marker")

    return ""


def gen_pkg_list(pkg_template: str, cfg: Config) -> str:
    """Generate the HTML for all package entries."""

    entries: list[str] = []
    pkgs = get_repo_pkgs(cfg.repo.db_file)
    repo_dwn_base = f"{cfg.repo.url.rstrip('/')}{cfg.repo.down_suffix}".rstrip("/")

    for pkg in pkgs.packages:
        entries.append(
            render_template(
                pkg_template,
                {
                    "pkg_name": pkg.name,
                    "pkg_desc": pkg.desc,
                    "pkg_version": pkg.version,
                    "pkg_url": pkg.url,
                    "pkg_aur_url": f"{defaults.aur_pkg_url}/{pkg.name}",
                    "pkg_arch": pkg.arch,
                    "pkg_filename": pkg.filename,
                    "pkg_dwn_url": f"{repo_dwn_base}/{pkg.filename}",
                },
                strict=False,
            )
        )

    if not entries:
        return ""

    return "\n".join(entries)


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
        server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
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
            pkg_template = get_pkg_template(content)
        except TemplateError as e:
            raise SiteGenerationError(f"{e} in {path.relative_to(Path.cwd())}: ") from e

        if pkg_template:
            try:
                pkg_rows = gen_pkg_list(pkg_template, cfg)
            except TemplateError as e:
                raise SiteGenerationError(f"{path.relative_to(Path.cwd())}: {e}") from e

            content = content.replace(pkg_template, pkg_rows)

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

    return 0
