"""
AUR RPC API interaction & git cloning module using pathlib.
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .logger import log

AUR_BASE_URL = "https://aur.archlinux.org"
AUR_CLONE_DIR = Path("aur")


class AurRpcError(Exception):
    """Raised when the AUR RPC query fails."""


def fetch_aur_versions(package_names: list[str]) -> dict[str, str]:
    if not package_names:
        return {}

    query_args = [("v", "5"), ("type", "info")]
    for pkg in package_names:
        query_args.append(("arg[]", pkg))

    url = f"{AUR_BASE_URL}/rpc/?{urllib.parse.urlencode(query_args)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MyRepoBuilder/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])

                return {item["Name"]: item["Version"] for item in results}
            raise AurRpcError(f"AUR RPC returned HTTP status {resp.status}")

    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        raise AurRpcError(f"Failed to query AUR RPC API: {e}") from e


def clone_package(pkg_name: str) -> Path:
    pkg_dir = AUR_CLONE_DIR / pkg_name

    if pkg_dir.exists():
        log.info("Updating cache")
        res = subprocess.run(
            ["git", "-C", str(pkg_dir), "pull", "--quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git pull failed: {res.stderr}")
    else:
        log.info("Cloning from AUR")

        url = f"{AUR_BASE_URL}/{pkg_name}.git"
        res = subprocess.run(
            ["git", "clone", "--quiet", url, str(pkg_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git clone failed: {res.stderr}")

    if not (pkg_dir / "PKGBUILD").exists():
        raise FileNotFoundError(f"PKGBUILD not found for {pkg_name}")

    return pkg_dir


def _parse_git_source(entry: str) -> tuple[str, str] | None:
    """Parse a PKGBUILD source entry into (url, git_ref) if it's a git source.

    Handles formats like:
        git+https://github.com/user/repo.git
        name::git+https://github.com/user/repo.git#branch=dev
    """
    # Strip name:: prefix
    if "::" in entry:
        entry = entry.split("::", 1)[1]

    if not entry.startswith(("git+", "git://")):
        return None

    entry = entry.removeprefix("git+")

    ref = "HEAD"
    if "#" in entry:
        url, fragment = entry.rsplit("#", 1)
        if "=" in fragment:
            key, value = fragment.split("=", 1)
            match key:
                case "branch":
                    ref = f"refs/heads/{value}"
                case "tag":
                    ref = f"refs/tags/{value}"
                case "commit":
                    ref = value
    else:
        url = entry

    return url.rstrip("/"), ref


def _get_pkgbuild_sources(pkgbuild: Path) -> list[str]:
    """Extract the source array entries from a PKGBUILD."""
    bash_cmd = f'source {pkgbuild} && printf "%s\\n" "${{source[@]}}"'
    try:
        out = subprocess.check_output(
            ["bash", "-c", bash_cmd],
            text=True,
            timeout=10,
        ).strip()
        return out.splitlines() if out else []
    except (subprocess.SubprocessError, OSError, TimeoutError):
        return []


def _get_remote_head(url: str, ref: str = "HEAD") -> str:
    """Get the latest commit hash from a remote git repo via ls-remote."""
    try:
        out = subprocess.check_output(
            ["git", "ls-remote", url, ref],
            text=True,
            timeout=15,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return out.split()[0]
    except (subprocess.SubprocessError, OSError, TimeoutError):
        pass
    return ""


def get_actual_git_version(pkg_name: str, repo_version: str = "") -> str:
    """Get version for a -git package, checking upstream for new commits.

    For PKGBUILDs with a ``pkgver()`` function:
      - Uses ``git ls-remote`` to check if upstream HEAD has changed.
      - Returns *repo_version* if the upstream hash already appears in it
        (no new commits, safe to skip).
      - Returns ``""`` if new commits are detected or the check fails
        (triggers a rebuild).

    For PKGBUILDs without ``pkgver()``:
      - Returns the static ``pkgver-pkgrel`` sourced from the PKGBUILD.
    """
    if not pkg_name.endswith("-git"):
        return ""

    try:
        pkg_dir = clone_package(pkg_name)
    except (RuntimeError, FileNotFoundError, subprocess.SubprocessError):
        return ""

    pkgbuild = pkg_dir / "PKGBUILD"
    if not pkgbuild.exists():
        return ""

    try:
        content = pkgbuild.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    if "pkgver()" in content:
        if not repo_version:
            log.info("First build of -git package")
            return ""

        # Extract git source URLs and check upstream for new commits.
        sources = _get_pkgbuild_sources(pkgbuild)
        git_sources = [_parse_git_source(s) for s in sources]
        git_sources = [gs for gs in git_sources if gs is not None]

        if not git_sources:
            log.warn("No git sources found in PKGBUILD, can't check for updates")
            return repo_version

        url, ref = git_sources[0]
        commit = _get_remote_head(url, ref)

        if not commit:
            log.warn(f"Failed to query upstream: {url}")
            return repo_version

        short_hash = commit[:7]
        if short_hash in repo_version:
            log.info(f"Upstream unchanged (HEAD: {short_hash})")
            return repo_version

        log.info(
            f"New upstream commits detected (HEAD: {short_hash},"
            f" repo has: {repo_version})"
        )
        return ""

    # Static version (no pkgver())
    bash_cmd = f'source {pkgbuild} && if [ -n "${{epoch:-}}" ]; then echo "${{epoch}}:${{pkgver}}-${{pkgrel}}"; else echo "${{pkgver}}-${{pkgrel}}"; fi'
    try:
        out = subprocess.check_output(["bash", "-c", bash_cmd], text=True).strip()
        return out
    except (subprocess.SubprocessError, OSError):
        return ""
