import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from my_builder.lib import pkgbuild
from my_builder.lib.aur import AurPackageInfo


class AurResolutionTests(unittest.TestCase):
    def test_extracts_dependencies_from_indented_srcinfo(self) -> None:
        srcinfo = "\tpkgbase = demo\n\tdepends = runtime-lib\n\tmakedepends = meson\n\tcheckdepends = test-runner\n"
        result = subprocess.CompletedProcess(
            ["makepkg", "--printsrcinfo"], 0, stdout=srcinfo, stderr=""
        )

        with patch.object(pkgbuild.subprocess, "run", return_value=result):
            dependencies = pkgbuild.get_package_dependencies(Path("/demo"))

        self.assertEqual(dependencies.depends, ("runtime-lib",))
        self.assertEqual(dependencies.make_depends, ("meson",))
        self.assertEqual(dependencies.check_depends, ("test-runner",))

    def run_resolution(
        self,
        root_dependency: str,
        packages: dict[str, AurPackageInfo],
    ) -> tuple[list[str], dict[str, str]]:
        installed: dict[str, tuple[str, tuple[str, ...]]] = {}
        build_order: list[str] = []

        def version_key(version: str) -> tuple[int, ...]:
            return tuple(int(part) for part in version.split("."))

        def satisfies(dependency: str) -> bool:
            name, operator, required = pkgbuild._dependency_parts(dependency)
            for package_name, (version, provides) in installed.items():
                candidates = [
                    (package_name, "=", version),
                    *(pkgbuild._dependency_parts(provided) for provided in provides),
                ]
                for candidate_name, candidate_operator, candidate_version in candidates:
                    if candidate_name != name:
                        continue
                    if not operator:
                        return True
                    if (
                        candidate_operator
                        and {
                            "=": version_key(candidate_version)
                            == version_key(required),
                            ">": version_key(candidate_version) > version_key(required),
                            ">=": version_key(candidate_version)
                            >= version_key(required),
                            "<": version_key(candidate_version) < version_key(required),
                            "<=": version_key(candidate_version)
                            <= version_key(required),
                        }[operator]
                    ):
                        return True
            return False

        def fake_run(
            args: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["pacman", "-T"]:
                return subprocess.CompletedProcess(
                    args, 0 if satisfies(args[2]) else 1, stdout="", stderr=""
                )
            if args[:2] == ["pacman", "-Sp"]:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
            if args[0] == "vercmp":
                left, right = version_key(args[1]), version_key(args[2])
                result = (left > right) - (left < right)
                return subprocess.CompletedProcess(
                    args, 0, stdout=f"{result}\n", stderr=""
                )
            if args[0] == "makepkg":
                build_order.append(Path(kwargs["cwd"]).name)
                return subprocess.CompletedProcess(args, 0)
            if args[:4] == ["pacman", "-Qp", "--print-format", "%n"]:
                return subprocess.CompletedProcess(
                    args, 0, stdout=f"{Path(args[-1]).parent.name}\n", stderr=""
                )
            if args[:3] == ["sudo", "pacman", "-U"]:
                package_name = Path(args[-1]).parent.name
                package = packages[package_name]
                installed[package_name] = (package.version, package.provides)
                return subprocess.CompletedProcess(args, 0)
            raise AssertionError(f"Unexpected command: {args}")

        def package_dependencies(
            package_dir: Path,
            extra_pkgs: list[str] | None = None,
        ) -> pkgbuild.PackageDependencies:
            if package_dir.name == "target":
                return pkgbuild.PackageDependencies(depends=(root_dependency,))
            package = packages[package_dir.name]
            return pkgbuild.PackageDependencies(
                depends=package.depends,
                make_depends=package.make_depends,
                check_depends=package.check_depends,
            )

        def fetch_packages(names: list[str]) -> dict[str, AurPackageInfo]:
            return {name: packages[name] for name in names if name in packages}

        def fetch_providers(name: str) -> list[AurPackageInfo]:
            return [
                package
                for package in packages.values()
                if any(
                    pkgbuild._dependency_parts(provided)[0] == name
                    for provided in package.provides
                )
            ]

        def package_artifacts(
            package_dir: Path,
            pattern: str,
        ) -> list[Path]:
            if pattern == "*.pkg.tar.zst":
                return [package_dir / f"{package_dir.name}-1-1-x86_64.pkg.tar.zst"]
            return []

        with (
            patch.object(pkgbuild, "get_package_dependencies", package_dependencies),
            patch.object(
                pkgbuild,
                "clone_package",
                side_effect=lambda name, base=None: Path("/aur") / (base or name),
            ),
            patch.object(pkgbuild, "fetch_aur_packages", fetch_packages),
            patch.object(pkgbuild, "fetch_aur_providers", fetch_providers),
            patch.object(pkgbuild.subprocess, "run", fake_run),
            patch.object(Path, "glob", package_artifacts),
        ):
            pkgbuild.install_deps(Path("/target"))

        return build_order, {name: info[0] for name, info in installed.items()}

    def test_builds_nested_runtime_make_and_check_dependencies_first(self) -> None:
        packages = {
            "app-lib": AurPackageInfo(
                "app-lib",
                "app-lib",
                "2.1",
                depends=("runtime-lib",),
                make_depends=("build-tool",),
                provides=(),
                check_depends=("test-tool",),
            ),
            "runtime-lib": AurPackageInfo(
                "runtime-lib", "runtime-lib", "1.0", (), (), ()
            ),
            "build-tool": AurPackageInfo("build-tool", "build-tool", "1.0", (), (), ()),
            "test-tool": AurPackageInfo("test-tool", "test-tool", "1.0", (), (), ()),
        }

        build_order, installed = self.run_resolution("app-lib=2.1", packages)

        self.assertEqual(
            build_order,
            ["runtime-lib", "build-tool", "test-tool", "app-lib"],
        )
        self.assertEqual(
            installed,
            {
                "runtime-lib": "1.0",
                "build-tool": "1.0",
                "test-tool": "1.0",
                "app-lib": "2.1",
            },
        )

    def test_resolves_versioned_virtual_dependency_from_aur_provider(self) -> None:
        packages = {
            "virtual-provider": AurPackageInfo(
                "virtual-provider",
                "virtual-provider",
                "1.2",
                (),
                (),
                ("virtual-lib=1.2",),
            )
        }

        build_order, installed = self.run_resolution("virtual-lib>=1.0", packages)

        self.assertEqual(build_order, ["virtual-provider"])
        self.assertEqual(installed, {"virtual-provider": "1.2"})


if __name__ == "__main__":
    unittest.main()
