"""
AUR RPC API interaction & git cloning module using pathlib.
"""

import json
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

from .logger import log_error, log_msg

AUR_BASE_URL = "https://aur.archlinux.org"
AUR_CLONE_DIR = Path("aur")


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
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        log_error(f"Failed to query AUR RPC API: {e}")

    return {}


def clone_package(pkg_name: str) -> Path:
    pkg_dir = AUR_CLONE_DIR / pkg_name
    if pkg_dir.exists():
        log_msg("Updating cache")
        res = subprocess.run(
            ["git", "-C", str(pkg_dir), "pull", "--quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git pull failed: {res.stderr}")
    else:
        log_msg("Cloning from AUR")
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


def get_actual_git_version(pkg_name: str) -> str:
    if not pkg_name.endswith("-git"):
        return ""

    try:
        pkg_dir = clone_package(pkg_name)
    except (RuntimeError, FileNotFoundError, subprocess.SubprocessError):
        return ""

    pkgbuild = pkg_dir / "PKGBUILD"
    if not pkgbuild.exists():
        return ""

    bash_cmd = f'source {pkgbuild} && if [ -n "${{epoch:-}}" ]; then echo "${{epoch}}:${{pkgver}}-${{pkgrel}}"; else echo "${{pkgver}}-${{pkgrel}}"; fi'
    try:
        out = subprocess.check_output(["bash", "-c", bash_cmd], text=True).strip()
        return out
    except (subprocess.SubprocessError, OSError):
        return ""
