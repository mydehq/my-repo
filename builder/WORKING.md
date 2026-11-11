# MyRepo Builder - The Spec

This document explains how to build a package-builder program in any language. It lists what goes in, what the program must do, what files it must create, how failures are handled, and how to test the result. You do not need this repository's source code to use it.

## Contents

- [MyRepo Builder - The Spec](#myrepo-builder---the-spec)
  - [Contents](#contents)
  - [Purpose and Scope](#purpose-and-scope)
  - [Key Terms](#key-terms)
  - [Tools Used](#tools-used)
  - [Settings](#settings)
  - [Commands](#commands)
  - [Build Steps](#build-steps)
  - [Getting Packages from AUR](#getting-packages-from-aur)
  - [Finding Required Packages](#finding-required-packages)
    - [Read dependency lists](#read-dependency-lists)
    - [Find and install missing packages](#find-and-install-missing-packages)
  - [Package Files and Repository](#package-files-and-repository)
  - [Website](#website)
  - [Automatic Builds](#automatic-builds)
    - [Current GitHub Actions Settings](#current-github-actions-settings)
  - [Errors and Saved Results](#errors-and-saved-results)
  - [Current Implementation Quirks](#current-implementation-quirks)
  - [Tests to Pass](#tests-to-pass)

## Purpose and Scope

The program has three jobs:

1. **Build packages:** check the settings, choose packages, compare versions, find required packages, and run Arch's build tools.
2. **Update the package repository:** add successfully built packages, remove old entries, and save a summary of the run.
3. **Publish results:** make a package-list website and let an automation service upload the files.

The PKGBUILD file and `makepkg` do the actual source build. `repo-add` and `repo-remove` update the package list that Arch clients use. Use these tools regardless of the programming language used for the builder.

```mermaid
flowchart TD
  A[Configuration] --> B[Select packages]
  B --> C[Get AUR package details]
  C --> D{Version changed or forced?}
  D -- no --> E[Keep published package]
  D -- yes --> F[Fetch PKGBUILD]
  F --> G[Parse and resolve dependencies]
  G --> H[Build configured package]
  H --> I[Update package repository]
  E --> J[Cleanup using full config]
  I --> J
  J --> K[Render site]
  K --> L[Publish changed package files]
```

## Key Terms

- **AUR:** a community site where Arch users share package build recipes.
- **PKGBUILD:** a shell script that tells Arch how to download, build, and package software.
- **Dependency:** another package needed to use, build, or test a package.
- **Package base:** one AUR source checkout that can create one or more installable packages.
- **Provider:** a package that says it can be used under another package name.
- **SRCINFO:** the dependency and package details printed by `makepkg --printsrcinfo`.
- **Repository database:** the index Arch uses to find packages in a package repository.
- **YAML:** the text format used for settings in `config.yml`.
- **JSON:** the text format used for package lists and run summaries.
- **CI:** an automated service that runs builds and publishes their results.

## Tools Used

| Tool                       | What it does                                                                                                                           |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| AUR web API, version 5     | Returns package details, versions, dependency lists, and search results for substitute packages                                        |
| Git                        | Downloads and updates AUR package bases and checks upstream commits for `-git` packages                                                |
| `makepkg`                  | Reads PKGBUILDs, prints package details, and creates installable package files                                                         |
| `pacman`                   | Checks installed packages, finds and installs packages from Arch repositories, inspects package files, and installs AUR-built packages |
| `vercmp`                   | Compare versions using Arch's version rules                                                                                            |
| `repo-add` / `repo-remove` | Add or remove packages from the repository database                                                                                    |
| GitHub Release             | Stores package files and the repository database between automated runs                                                                |
| Website hosting            | Serves the generated package list and install instructions                                                                             |

When starting another program, pass its arguments separately, check whether it succeeded, and show its error message. Put a time limit on network requests. PKGBUILD files can run commands on the machine, so build them only in a trusted Arch environment and avoid giving them unnecessary administrator access.

## Settings

Read a YAML settings file. The default name is `config.yml`; an explicit command-line path overrides it. Resolve relative paths from the folder where the program was started. Reject malformed YAML and wrong value types before changing the package repository.

Example:

```yaml
repo:
  name: my-repo
  url: https://github.com/OWNER/REPOSITORY
  architectures: [x86_64, aarch64]
  desc: Community Arch packages
  down_suffix: /releases/download/repo-{arch}
  output_dir: build
  clone_dir: aur
  # Optional: display_name, install_cmd, packager

aur:
  url: https://aur.archlinux.org
  pkg_base: /packages

site:
  url: https://OWNER.github.io/REPOSITORY
  name: My Repo
  desc: Community Arch packages
  input_dir: site-assets
  output_dir: dist

packages:
  - package-name
  - another-package:
      always: true
      extra_pkgs: [extra-build-tool]
```

`repo.name`, `repo.url`, and `site.url` are required. Supported native architectures are `x86_64` and `aarch64`; architecture is detected from the build machine, not set in YAML. The other defaults are repository description `Automated AUR package builds.`, display name equal to repository name, output folder `build`, site output folder `dist`, site input folder set to the bundled site files, release suffix `/releases/download/repo-{arch}`, and AUR base URL `https://aur.archlinux.org`. The AUR API address is the base URL plus `/rpc/`; the package-page base is `/packages`. The default install command is `curl -fSL {site_url}/setup | bash`. The site name and description default to the repository display name and description. Site URLs must start with `http://` or `https://`.

Each build runs on an Arch Linux machine. The builder detects the native architecture and does not accept a target-architecture override or cross-compile. CI chooses a native runner for each supported architecture in its matrix. A local run builds only for the current machine. Packages marked `arch = any` can be built on either supported machine when their PKGBUILD allows it.

Trim spaces around the repository name. Resolve the repository output and site input/output paths from the folder where the program was started. Build each database path as `<output_dir>/<arch>/<repo-name>.db.tar.gz`. Release URLs replace `{arch}` in `down_suffix` with `x86_64` or `aarch64`. Remove trailing slashes from the AUR base URL and package-page base before joining them. Use the configured clone folder; `aur` is the recommended default.

`packages` is an ordered list. Each item is either a package-name string or a mapping with exactly one package name and an options mapping. Supported package options are:

| Option       | Type                      | Default | Effect                                          |
| ------------ | ------------------------- | ------- | ----------------------------------------------- |
| `always`     | Boolean                   | `false` | Build even if its published version matches AUR |
| `extra_pkgs` | List of non-empty strings | `[]`    | Add packages to build requirements              |

Each package mapping must contain exactly one package name. Its options may be empty. `always` must be a Boolean and `extra_pkgs` must be a list of non-empty strings. Trim spaces around package names and extra package names. Map `always` to the package's force-build setting. Ignore unknown package option keys for compatibility, but a warning is helpful. A name such as `tool|always` is one literal package name, not a special form. Put the repository database at `<output_dir>/<architecture>/<repo-name>.db.tar.gz`.

## Commands

Provide commands equivalent to:

```text
builder [--config FILE] build [--package NAME ...] [--rebuild-missing]
builder [--config FILE] build-index
builder [--config FILE] --version
```

- `build` selects packages, checks versions, builds needed targets, updates the repository database, performs cleanup, and writes summaries.
- `--package NAME` may be repeated and selects only configured package names. An empty selection is an error.
- `BUILD_TARGETS` is used only when no command-line package was supplied. Accept either a JSON list or package names separated by spaces.
- `--rebuild-missing` rebuilds a version-matching package if its expected archive is absent.
- `build-index` only renders the site from an existing, valid repository database.
- `--version` prints the implementation version.

`--config` also has the short form `-c`, `--version` also has `-v`. Show help when no command is supplied, and allow help for each command. A package list given with repeated `--package` options overrides `BUILD_TARGETS`. If neither is supplied, build every configured package in configuration order. Parse `BUILD_TARGETS` as a JSON list first; if it is not valid JSON, split it into shell-style words. Reject an empty selection or names that do not match configured packages.

Return exit code `0` only if the requested operation succeeds. Return a failure code for bad settings, missing AUR packages, missing requirements, build problems, database problems, or website problems. Continue unrelated package builds after a failure when safe, but still return a failure code. Automation must never publish a failed build as successful.

## Build Steps

Perform a build in this order:

1. Verify required host tools are available. At minimum, building requires `makepkg`; dependency installation requires pacman; database changes require `repo-add` and sometimes `repo-remove`.
2. Load and validate configuration before mutating repository state.
3. Keep the full configured package set separate from the selected build set. Targeted cleanup must use the full set.
4. Prepare `<output_dir>/<arch>/` and remove only temporary result files from an earlier run. Check that the output folder can be written to.
5. If exactly one old-named repository database exists, rename it and its related files to the configured repository name. If there are several possible old databases, stop instead of guessing.
6. Query AUR versions for every selected target. If any selected name is absent, report all missing names and do not begin the selected package builds.
7. For each selected target, look up its published version and decide whether it needs rebuilding.
8. For each target that needs a build, fetch/update its AUR package base, extract dependencies, resolve them, and invoke `makepkg`.
9. Copy successful configured-target archives into the output directory and update the database for those archives.
10. Remove stale versions and packages no longer configured, without removing other configured packages during a targeted run.
11. Write summaries and change markers. Return a failure code if any selected package failed.

Before entering the package loop, query AUR versions for all selected packages in one info request. If the request fails, stop. If any selected package name is missing from the response, write all missing names to `missing-packages.json` and stop before building any of them.

For each package, read its version from the existing repository database. A package needs a build when `always` is true, it is not in the database, or its AUR version differs from the published version. With `--rebuild-missing`, also build when the version matches but no archive for that package and version is present. Log each decision as built or skipped.

For a package that needs a build, update its AUR checkout, check dependencies, and run `makepkg --noconfirm --nodeps --force --clean`. `--nodeps` means makepkg skips its own dependency check; the dependency resolver must finish first. Copy every produced archive for the configured package base into the output directory and record its actual package name, version, filename, and size. Catch a package's build error, report it, and continue with unrelated selected packages.

After the loop, write the build summary. Add all successfully built configured-package archives to the repository database in one `repo-add` call. Then clean up using the full configured package list, write any removal summary, and create `.db-updated` if the database changed. The final command result is failure if any package failed, even if other packages built successfully.

For a normal package, build when forced, when no repository version exists, or when the AUR and repository versions differ. For `-git` packages, inspect the PKGBUILD for `pkgver()`. If present, read Git sources from its evaluated source array and query the first Git source's selected ref with `git ls-remote`. If the remote short hash is already represented in the published version, treat it as unchanged; if it differs or there is no published version, build. If the remote query fails, retain the current published package rather than rebuilding solely because of a network failure. Without `pkgver()`, use the PKGBUILD's static epoch/version/release value.

Support Git source forms `git+https://...`, `git://...`, optional `name::` prefixes, and `#branch=`, `#tag=`, or `#commit=` fragments. Map branch and tag values to their corresponding `refs/heads/` and `refs/tags/` refs; use a supplied commit directly; use `HEAD` when no ref is specified.

## Getting Packages from AUR

Use the AUR version 5 web API. For package details, send `type=info` and one `arg[]` parameter for each name. For substitute packages, send `type=search`, `by=provides`, and `arg=<requested-name>`. A result uses these fields:

| API field      | Meaning                                 |
| -------------- | --------------------------------------- |
| `Name`         | Installable package name                |
| `PackageBase`  | Name of its AUR source repository       |
| `Version`      | Package version                         |
| `Depends`      | Packages needed to use it               |
| `MakeDepends`  | Packages needed to build it             |
| `CheckDepends` | Packages needed to test it              |
| `Provides`     | Other package names it can stand in for |

For multiple packages, repeat the `arg[]` parameter once per package. For example, the readable form is:

```url
https://aur.archlinux.org/rpc/?v=5&type=info&arg[]=package-one&arg[]=package-two
```

URL clients encode the square brackets when sending the request. The equivalent encoded URL is:

```text
https://aur.archlinux.org/rpc/?v=5&type=info&arg%5B%5D=package-one&arg%5B%5D=package-two
```

A provider search is needed when the required name is not the package's actual name.   
For example, a PKGBUILD may require `virtual-lib`, while an AUR package named `real-lib` lists `virtual-lib` in its `Provides` field.   
Search `https://aur.archlinux.org/rpc/?v=5&type=search&by=provides&arg=virtual-lib` to find such packages. Try an exact package name first, then search providers if no exact package can satisfy the requirement. Fetch full details for each result before choosing one. For a versioned requirement, the provider must list a version in `Provides` that meets the requested version rule. Treat network errors, timeouts, unsuccessful web responses, and unreadable responses as errors; do not treat an API failure as “no results.”

Keep one source copy per package base in a configurable cache. Clone it from `<git-base-url>/<package-base>.git` when missing; update an existing copy with `git pull` before use. Confirm that it contains a PKGBUILD file. Git source entries may use `git+https://...`, `git://...`, a `name::` prefix, or a `#branch=`, `#tag=`, or `#commit=` suffix.

## Finding Required Packages

### Read dependency lists

PKGBUILD is executable Bash, not a plain settings file. Do not try to understand its shell syntax with regular expressions or a custom parser.

For dependencies, run `makepkg --printsrcinfo` in the package checkout. `makepkg` evaluates the PKGBUILD and prints the package fields in SRCINFO format. Trim spaces and tabs from each output line, split it at ` = `, and read the field name and value. The output indents its fields. Collect:

- `depends`: packages needed when the built package is installed
- `makedepends`: packages needed to build it
- `checkdepends`: packages needed to run its tests
- generic fields and `x86_64` fields such as `depends_x86_64`. do not include fields for other architectures
- configured `extra_pkgs`, added to the build list.

Do not include fields for a different processor type or optional packages. Remove duplicates without changing the order. If the dependency list cannot be read, stop before building. An empty list is valid only when the PKGBUILD has no required packages.

For a `-git` version check, use Bash to source the PKGBUILD and print its expanded `source` array.   
Read only the values needed for the check; do not call the build or package functions. When a fixed version is needed, source the PKGBUILD and print `epoch`, `pkgver`, and `pkgrel` the same way. Sourcing a PKGBUILD runs its top-level shell commands, so do this only in the trusted, isolated Arch build environment described above.

### Find and install missing packages

For every required package, first ask pacman whether it is already installed. For a rule such as `thing>=2`, use Arch's version comparison rules. Do not compare version text alphabetically.

Use these commands for the checks and installs:

| Purpose                             | Command shape                                                   |
| ----------------------------------- | --------------------------------------------------------------- |
| Check installed packages            | `pacman -T 'thing>=2'`                                          |
| Check official repositories         | `pacman -Sp --print-format %n 'thing>=2'`                       |
| Install an official package         | `sudo pacman -S --noconfirm --needed 'thing>=2'`                |
| Read a package name from an archive | `pacman -Qp --print-format %n /path/to/file.pkg.tar.zst`        |
| Install a built AUR package         | `sudo pacman -U --noconfirm --needed /path/to/file.pkg.tar.zst` |
| Compare two Arch versions           | `vercmp 2.1 2.0`                                                |

Use the system's configured privilege helper in place of `sudo` if needed. After each install, check the original requirement again with `pacman -T`.

For a package that is not already installed:

1. Ask pacman whether one of the enabled Arch repositories can install the requested name. This also lets pacman find repository packages that provide another name.
2. If a repository package can satisfy it, install it and check the original requirement again.
3. If not, look in the AUR for a package with that exact name and a suitable version.
4. If there is no suitable exact match, look for AUR packages that list the requested name under `provides`. A plain requirement can use a plain provide. A versioned requirement needs a provide with a version that meets the same rule.
5. Prefer an exact name. If several AUR packages could work, choose them in a stable, documented order or ask the user in interactive mode. Never pick an arbitrary provider in an unattended build.
6. Before building an AUR dependency, read its own required package lists and resolve those first. Keep track of the current chain of packages; report and stop if a package depends on itself through that chain.
7. Build the dependency only after all of its requirements are installed. For a source package that makes several binary packages, inspect each archive to find the requested package by its recorded name.
8. Install that archive, then ask pacman again whether it satisfies the original requirement. Stop with an error if it does not.

If several requested packages come from the same package base, download and build that source only once. Install AUR dependencies on the build machine so later builds can use them, but do not add their package files to the hosted repository unless they are configured targets.

Build the configured target only after all packages it needs to run, build, and test are installed. The `--nodeps` option tells `makepkg` to skip its own dependency check, so use it only after this program has checked every requirement. If no installed package, Arch repository, or AUR package can meet a requirement, report it and fail that target.

## Package Files and Repository

Build the configured target only after its required packages are installed. Run `makepkg --noconfirm --nodeps --force --clean`; this skips makepkg's own dependency check, so the builder must have checked requirements first. Collect `*.pkg.tar.zst` archives and, if supported, `*.pkg.tar.xz` or `*.pkg.tar.gz` archives. Confirm that the target archive exists, copy it into `<output_dir>/<architecture>/`, then remove its temporary copy from the source folder.

Use `repo-add` to add successful configured-target archives to `<repo-name>.db.tar.gz`. Use `repo-remove` to remove packages no longer configured. The pacman database is the source of truth for published package versions and the package list shown on the site.

A pacman database is a compressed tar file. It contains one folder per package, with a `desc` text file in each folder. Each field starts with a marker such as `%NAME%`; its value appears on the following line or lines until the next marker. Blank lines can be ignored. Some fields have several values.

Read these fields when available: `NAME`, `FILENAME`, `BASE`, `VERSION`, `DESC`, `URL`, `LICENSE`, `ARCH`, `BUILDDATE`, `PACKAGER`, `CSIZE`, `ISIZE`, `SHA256`, `DEPENDS`, `OPTDEPENDS`, `MAKEDEPENDS`, `CHECKDEPENDS`, `PROVIDES`, `CONFLICTS`, `REPLACES`, and `GROUPS`.   
The package name and version are needed for build decisions; the name, description, version, architecture, filename, and URL are needed for the website. Treat missing optional fields as empty and invalid numeric fields as defaults. Use `repo-add` and `repo-remove` to write changes rather than editing this file format by hand.

When renaming a repository, rename its `<old>.db.tar.gz` to `<new>.db.tar.gz`. If matching `<old>.db` or `<old>.files` links exist, recreate them with the new name. Rename `<old>.files.tar.gz` as well when it exists. Only do this automatically when exactly one old database could be the source.

Before `repo-add`, remove a stale `<repo>.db.tar.gz.lck` lock only when no package operation is still running. After a successful update, remove `*.old` files left beside the database. If the repository database changes during the run, clear any in-memory copy before reading it again.

Before a build, automation may download the existing database and package files from release storage. After a successful build, upload changed package archives and database files. Keep package archives separate from database files; both are needed by clients of the repository.

Cleanup must use the full configured package list, even during a build of only one selected target. Remove an old archive only after its replacement was successfully built and added to the database. Do not remove a configured package because its build failed or it was skipped as current.

Write these state files under the output folder:

| File                    | Meaning                                                                                              |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| `build-summary.json`    | A list of built packages. Each item has `name`, `old_version`, `new_version`, `filename`, and `size` |
| `missing-packages.json` | Selected package names not found in AUR, when applicable                                             |
| `removed-packages.json` | Package names removed from the repository                                                            |
| `.db-updated`           | The repository database changed during this run                                                      |

Clear only state files that belong to a new run. Write JSON safely so an interrupted run does not leave a half-written file.

## Website

Render a static website from a configurable input folder into an output folder. Read its package list from the pacman database so the site shows what is actually published.

Replace text placeholders like `{{repo_name}}` with values from the configuration. The built-in page uses these names:

`builder_name`, `builder_version`, `builder_url`, `repo_name`, `repo_display_name`, `repo_url`, `repo_desc`, `repo_pkg_count`, `repo_down_suffix`, `repo_dwn_url`, `repo_install_cmd`, `repo_packager`, `last_updated`, `ci_run_url`, `ci_run_hash`, `site_url`, `site_name`, and `site_desc`.

Fail if a page uses a placeholder that has no value; do not publish a page with unresolved placeholders. Copy images and other non-text files unchanged, create output folders as needed, and keep useful file permissions.

Write a `packages.json` file in the site output folder. It is a list of package records with these fields:

| Field              | Meaning                                                     |
| ------------------ | ----------------------------------------------------------- |
| `pkg_name`         | Installable package name                                    |
| `pkg_desc`         | Short package description                                   |
| `pkg_version`      | Published version                                           |
| `pkg_aur_url`      | Link to the package's AUR page                              |
| `pkg_arch`         | Supported processor type, such as `x86_64` or `any`         |
| `pkg_filename`     | Package archive filename                                    |
| `pkg_download_url` | Full download link for the archive                          |
| `pkg_project_url`  | Upstream project link, or an empty value if invalid/missing |

The page can use this file to show package names, descriptions, versions, processor types, and links. The built-in page also supports searching, copying the install command, downloading a package, and opening its AUR or project page. The default install command is `curl -fSL {site_url}/setup | bash`.

Build each record from one package entry in the repository database. Set `pkg_aur_url` to `<aur-base>/packages/<pkg_name>`. Set `pkg_download_url` to `<repo-url><down_suffix>/<pkg_filename>`, joining the parts with one `/`. Keep `pkg_project_url` only when the package URL has an `http` or `https` scheme and a host; otherwise use an empty string. Write `packages.json` as UTF-8 JSON with one record per published package.

`last_updated` is the current time in Unix seconds. `ci_run_hash` is a short commit ID (up to seven characters), or `local` when no commit can be found. Use an explicitly supplied CI run URL when available; otherwise form one from the automation service or link to the repository's Actions page.

Fail if the input folder or a valid repository database is missing, or if the output path cannot be used as a folder. The generated website is an output; automation publishes it after a successful build.

## Automatic Builds

Run the builder in an Arch Linux environment with `base-devel`, Git, pacman, `makepkg`, repository database tools, and any build tools needed by the selected packages. Run PKGBUILDs as a build user that can install packages through the system's normal privilege helper.

A CI job is the wrapper around the builder. It starts builds after changes to settings or build code, on a schedule, or after a manual or external request. The current schedule is every 12 hours at minute 47. Manual requests may name packages and may ask for the website to be refreshed even if no package was rebuilt.

Use this order for each CI run:

1. Start a fresh Arch Linux environment, install system tools, check out the project, and install the builder. Create a non-root build user with permission to install needed packages.
2. Download the current repository database and package-list files from the release store into `<output_dir>/<architecture>/`. The builder needs this old database to compare versions and clean up correctly.
3. If the run names packages, pass them to the builder using `BUILD_TARGETS`. If no package list is supplied, let the builder use all configured packages.
4. Run `builder build`. Keep its exit code and output files. The builder writes package archives and the `.db-updated` marker when repository contents change.
5. If the build fails, do not upload packages or deploy the website. Still write a CI run summary that explains the failure.
6. If the build succeeds, run `builder build-index`. The builder reads the updated package database and writes the website to the configured site output folder.
7. Check for newly built package archives and `.db-updated`. If either shows a repository change, upload the new archives and database files to the release. Remove older release files for replaced package versions and files for packages no longer configured.
8. If there are no package changes, skip release uploads unless a site refresh was requested or site files/templates changed. Deploy the generated website only after the build succeeds.
9. Always write a run summary. Pass the CI run URL and short commit ID to the site builder so the page can link back to its build.

Do not let two jobs change the same repository at once; cancel an older run when a newer run replaces it. Keep release uploads, website publishing, credentials, and caches in the CI setup. Keep package selection, dependency handling, build decisions, summaries, and exit codes in the builder so it works the same locally and in CI.

### Current GitHub Actions Settings

The always-run job summary includes missing AUR package names, built package names with old and new versions and sizes, removed packages, or a note that no packages were built.

This is the current GitHub Actions setup. It is an example of how to connect CI to the language-independent builder contract above.

- Start on pushes to `main` that change the workflow file, `config.yml`, or anything under `builder/`.
- Also start every 12 hours at minute 47, on manual requests, or on a `repository_dispatch` event named `trigger-build`.
- Manual requests accept `packages` and `force_index`. Package names may be a JSON list or space-separated text. Dispatch events may pass package names in `client_payload.packages`.
- Run on Ubuntu with an `archlinux:latest` container. Install `base-devel`, Git, GitHub CLI, `jq`, and Meson. Install and run the builder as a non-root `builder` user. The current workflow installs the Python implementation with `uv` and Python 3.14; another implementation can replace this setup.
- Grant GitHub permissions `contents: write`, `pages: write`, and `id-token: write` for release uploads and Pages deployment. Cache `.cargo/registry`, `.cargo/git`, `.cargo/target`, `.go/cache`, and `.go/mod`. Allow only one job to update the repository at a time; a new run cancels the older one.
- Before building, download `*.db*` and `*.files*` assets from the GitHub Release named `repo` into `<output_dir>/x86_64`. Pass manual or dispatch package names through `BUILD_TARGETS`, then run `builder build` as the build user.
- If the build fails, do not upload packages or deploy the website. Still write the job summary.
- If the build succeeds, run `builder build-index`. Publish if package archives were built or `.db-updated` exists. Copy the database and files symlink targets to regular `.db` and `.files` files for upload. Remove older release archives for newly built package names and archives for packages no longer configured. Create the `repo` release if needed, then upload changed files with replacement enabled.
- If there are no new archives and `.db-updated` is absent, skip release changes unless `force_index` is true or site assets, site code, or `config.yml` changed. Deploy the site only when the release step reports that an update is needed.
- Pass the CI run URL and short commit ID to `build-index` so the page can link to the run. The job summary runs even after failure.

## Errors and Saved Results

Each error should say which step failed and name the affected package or requirement. Distinguish configuration problems, missing AUR packages, network errors, source download errors, unreadable dependency lists, missing dependencies, version mismatches, dependency cycles, install errors, build errors, missing output archives, database errors, and site errors.

Do not build a package after one of its required steps fails. Other selected packages may continue if they do not depend on the failed package. Always return a failure status if any requested package failed. Do not publish a package as successful until its archive is in the repository database.

Keep console logs useful in both a terminal and CI. Optionally write timestamped log files. For a dependency problem, report the requested name, whether it was checked as installed or searched in Arch repositories/AUR, the selected provider if any, and the failing tool's message. Never print credentials.

Write state so an interruption does not leave a partly written file. At the start of a run, remove only the previous run's summary and status files.

## Current Implementation Quirks

These notes describe behavior in the existing builder, not behavior a new implementation should copy. The clean-room requirements above describe the intended behavior.

| Current behavior                                                                                                                                          | What an independent implementation should do                                                                                                                                             |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The CLI and repository database path are fixed to `x86_64`.                                                                                               | Treat this version as native `x86_64` only. To add another arch, use a matching Arch build machine or implement and test cross-building; changing the folder name is not enough. |
| Configuration declares `repo.clone_dir` with default `.my-builder/clone`, but AUR clones are stored in the `aur/` folder relative to the starting folder. | Honor the configured clone folder; `aur` is the recommended clean-room default.                                                                                                          |
| Dependency parsing accepts every field beginning with `depends_`, `makedepends_`, or `checkdepends_`.                                                     | Include only generic fields and fields for the selected architecture.                                                                                                                    |
| A targeted build passes only the selected names to cleanup. Cleanup can therefore remove other configured packages from the repository.                   | Pass the complete configured package list to cleanup, separate from the selected build list.                                                                                             |
| Cleanup picks the newest archive for a package by file modification time and removes other package archives.                                              | Read package names and versions from each archive and keep the newest version; do not rely only on timestamps.                                                                           |
| Cleanup removes unrelated files from the architecture output folder unless they match its allow-list.                                                     | Remove only known stale package archives, temporary files, or state files. Preserve files the builder does not own.                                                                      |
| Unknown package option keys are ignored.                                                                                                                  | Keep this behavior for compatibility, but warn about unknown keys so misspellings are visible.                                                                                           |
| SRCINFO `options`, such as `!strip` and `!lto`, are not handled by the dependency resolver.                                                               | Leave these package build options to `makepkg`; they are not dependencies.                                                                                                               |

## Tests to Pass

Tests should check behavior without network access, administrator access, or real package installation. Use made-up AUR and pacman responses instead. At minimum, test:

1. Valid and invalid configuration, including both supported package-entry forms.
2. Indented SRCINFO fields, all three required dependency groups, architecture-specific fields, extra packages, and duplicate removal.
3. Already-installed dependencies, official repository packages, and repository packages that provide an alternate name.
4. Nested AUR dependencies are built and installed before the package that needs them.
5. Exact AUR matches, virtual providers, version rules, missing providers, and dependency cycles.
6. Split packages use one source checkout/build and select the correct archive by its recorded package name.
7. Build or install failures return failure and do not replace a previously published package.
8. A targeted build preserves every other configured package during cleanup.
9. Repository database changes and state files match the successful builds and removals.
10. Site placeholders, package rows, missing database behavior, and copying of images/binary files.
11. Command-line target precedence, missing-archive rebuilds, `-git` update checks, summaries, and exit codes.

Also run one real build in a temporary Arch Linux environment. Check that it installs packages, runs the PKGBUILD, creates an installable package file, updates the repository database, and builds the website. Tests with made-up tool responses cannot prove these real steps work.
