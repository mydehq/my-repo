<div align="center">
    <img src="./src/icon.png" alt="MyTM" width="80">
    <h1>arch-repo</h1>
    <p>
        <b>Automated building repo for AUR packages</b>
    </p>
</div>

## Installation

- Add the repo to `pacman.conf`:

    ```sh
    sudo bash -c 'printf "\n[mydehq]\nSigLevel = Optional TrustAll\nServer = https://mydehq.github.io/arch-repo/\$arch\n" >> /etc/pacman.conf'
    ```

- Update the system:

   ```sh
    pacman -Sy
   ```

<br>

<!--
    For LLM:
        Follow the specification below **exactly**. Do not invent features that are explicitly excluded.
        The gh repo name is arch-repo
        The arch repo's name should be mydehq
-->

## Project Architecture

### Goal

- AUR packages are declared declaratively in packages.json
- Only changed packages are rebuilt
- Builds run in clean Arch chroots
- Built artifacts are published via GitHub Pages (deployed from repo branch)
- Build logic and publishing logic are strictly separated

### Scope (Hard Constraints)

#### Supported

- AUR packages only
- Incremental builds
- `force` rebuild flag (optional, per package)
- YAML for package list (packages.yml)
- `go-yq` for parsing
- GitHub Actions for CI
- Separate branch for binaries (repo)

#### Explicitly NOT supported

- Direct git PKGBUILD repos
- Auto-generated PKGBUILDs
- Dependency-triggered rebuilds
- Parallel builds
- Package signing (for now)

---

### Repository Structure

- main branch:

```text
arch-repo/
├── src/
│   └── builder              # build-only script
├── packages.yml             # declarative package list
├── build/                   # build output (gitignored)
│   └── x86_64/
├── .github/
│   └── workflows/
│       └── build.yml        # CI pipeline
└── README.md
```

### Package Lists

Package lists are store in `packages.yml` in project root.
It looks like this:

```yml
# Format:
#    - name: <package_name>
#      force: <true|false>  # Optional, Force rebuild ignoring version. defaults to false
packages:
  - name: myctl
  - name: vicinae-bin
  - name: catppuccin-cursors-macchiato
  - name: goog-git
    force: true
```

### CI Responsibilities (build.yml)

- CI must:
    1. Check out main
    2. Check out repo branch in build/
    3. If it doesn't exist, make.
    3. Run `src/builder`
    5. Commit changes & push
    6. It should keep only one commit in repo branch. History should be deleted else the repo will become too big over time.
    7. Let GitHub Pages serve it

- CI environment:
  - Arch Linux container
  - Installed tools:
        1. base-devel
        2. git
        3. yq (go-yq)
        4. jq

### Build Script (builder)

- What builder MUST do:
    1. Read packages.yml
    2. Clone AUR repos
    3. Decide which packages to build by checking build/ dir
    4. Build using makepkg
    5. Use repo-add to index repo
    6. any other steps needed
    7. Output artifacts to build directory

- What builder should NOT do
    1. Switch git branches
    2. Commit or push anything
    3. Know about GitHub Pages
    4. Perform uploading or deployment

- `builder` outputs one dir:

    ```
    build/
    └── x86_64/
        ├── mydehq.db.tar.gz
        ├── mydehq.files.tar.gz
        └── *.pkg.tar.zst
    ```

- For each package:

    ```sh
    if repo dont have package
        build
    elif repo version != aur version
        build
    elif repo version == aur version but force = true
        build
    else
        skip
    
    ```

### pacman.conf entry

`pacman.conf` will look like this:

```ini
[mydehq]
SigLevel = Optional TrustAll
Server = https://mydehq.github.io/arch-repo/$arch
```

---

<br>

## Related Resources

- **Main Repository**: [mydehq/MyDE](https://github.com/mydehq/myde)
- **Wiki Repository**: [mydehq/MyWiki](https://github.com/mydehq/mydehq.github.io)
- **Dependency Library**: [soymadip/KireiSakura Kit](https://soymadip.github.io/KireiSakura-Kit)

---

<div align="center">

**Made with ❤️ by the MyDE Team**

</div>
