<div align="center">
    <img src="./builder/src/my_builder/assets/icon.png" alt="MyRepo Logo" width="80">
    <h1>My Repo</h1>
    <p>
        <b>Automated AUR package building and repository hosting.</b>
    </p>
</div>

<br />

## Installation

> [!WARNING]
> This repository is x86_64 only.

Run the following command to add the repository:

```sh
curl -sL https://mydehq.github.io/my-repo/install | bash
```

## Adding Packages in repo

Simply edit `config.yml` and add desired AUR package names:

```yml
packages:
  aur:
    - name: myctl
    - name: vicinae-bin
    - name: catppuccin-cursors-macchiato
```

The GitHub Action will automatically detect changes, build the packages, update the repository index, and regenerate the dashboard.

---

## Repository Structure

```text
my-repo/
├── src/
│   ├── builder              # Core build logic & site generator
│   ├── index.html           # Dashboard template
│   ├── repo-README.md       # Repo branch README
│   ├── install.sh           # Repository installer script
│   └── icon.png             # Repository icon
├── config.yml               # Declarative package list
├── .github/
│   └── workflows/
│       └── build.yml        # Automation pipeline
└── README.md
```

## Technical Specification

- **Build Environment**: Native Arch Linux (`archlinux:latest`) container.
- **Build Logic**: Uses `makepkg` with dependency handling.

## Related Resources

- **Main Repository**: [mydehq/MyDE](https://github.com/mydehq/myde)
- **Wiki Repository**: [mydehq/MyWiki](https://github.com/mydehq/mydehq.github.io)

---

<div align="center">
    <b>Made with ❤️ by the <a href="https://github.com/mydehq">MyDE Team</a></b>
</div>
