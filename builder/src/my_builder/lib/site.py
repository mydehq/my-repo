"""
Static website generation (landing page HTML, installer, icon) module using pathlib.
"""

import shutil
from datetime import datetime, timezone

from .config import Config
from .logger import log_info, log_msg, log_success, log_warn
from .repo import get_repo_version

ARCH = "x86_64"


def generate_site(cfg: Config) -> None:
    dist_dir = cfg.builder.dist_dir
    build_dir = cfg.builder.build_dir
    templates = cfg.builder.templates
    meta = cfg.meta

    index_template = templates.index
    installer_template = templates.installer
    icon_file = cfg.builder.icon_file

    if not index_template.exists():
        log_warn(
            f"Landing page template not found: {index_template}. Skipping generation."
        )
        return

    log_msg("")
    log_info("Generating landing pages...")
    dist_dir.mkdir(parents=True, exist_ok=True)

    db_file = build_dir / ARCH / f"{meta.repo_name}.db.tar.gz"

    rendered_rows: list[str] = []
    valid_count = 0

    for pkg in cfg.packages:
        version = get_repo_version(db_file, pkg.name)
        if not version:
            continue
        valid_count += 1
        row = (
            f"<tr>\n"
            f"    <td class='ps-3'><a href='https://aur.archlinux.org/packages/{pkg.name}' target='_blank' class='package-name text-decoration-none'>{pkg.name}</a></td>\n"
            f"    <td class='text-center'><span class='badge rounded-pill badge-version'>{version}</span></td>\n"
            f"    <td class='text-end pe-3 text-secondary'>{ARCH}</td>\n"
            f"</tr>"
        )
        rendered_rows.append(row)

    package_rows = "\n".join(rendered_rows)
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Read and render index.html
    html_content = index_template.read_text(encoding="utf-8")

    replacements = {
        "{repo_name}": meta.repo_name,
        "{repo_url}": meta.repo_url,
        "{project_url}": meta.project_url,
        "{package_count}": str(valid_count),
        "{last_updated}": last_updated,
        "{package_rows}": package_rows,
    }

    for key, val in replacements.items():
        html_content = html_content.replace(key, val)

    index_out = dist_dir / "index.html"
    index_out.write_text(html_content, encoding="utf-8")
    log_success("   Generated: Landing page.")

    # Copy Icon if present
    if icon_file.exists():
        shutil.copy2(icon_file, dist_dir / "icon.png")
        log_success("   Copied icon.png")

    # Generate Installer
    if installer_template.exists():
        inst_content = installer_template.read_text(encoding="utf-8")

        inst_replacements = {
            "{repo_name}": meta.repo_name,
            "{repo_url}": meta.repo_url,
            "{project_url}": meta.project_url,
        }
        for key, val in inst_replacements.items():
            inst_content = inst_content.replace(key, val)

        inst_out = dist_dir / "install"
        inst_out.write_text(inst_content, encoding="utf-8")
        inst_out.chmod(0o755)
        log_success("   Generated: installer\n")
