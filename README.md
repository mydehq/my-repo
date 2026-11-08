<div align="center">
    <img src="builder/my_builder/assets/icon.png" alt="MyRepo Logo" width="80">
    <h1>My Repo</h1>
    <p>
        <b>Automated AUR package building and repository hosting.</b>
    </p>
</div>

<br />

## Installation

> [!WARNING]
> This repository is x86_64/any only.

Run the following command to add the repository:

```sh
curl -sL https://mydehq.github.io/my-repo/install | bash
```

## Package Information

For Package list, Update time; view [Dashboard](https://mydehq.github.io/my-repo)

## Adding Packages in repo

- Simply edit `config.yml` and add desired AUR package names:

    ```yml
    packages:
      aur:
        - name: myctl
        - name: vicinae-bin
        - name: catppuccin-cursors-macchiato
    ```

- Then Open a pr.
- Once merged, CI will auto detect changes, build the packages, update the repository.

---


## Related Resources

- **Main Repository**: [mydehq/MyDE](https://github.com/mydehq/myde)
- **Wiki Repository**: [mydehq/MyWiki](https://github.com/mydehq/mydehq.github.io)

---

<div align="center">
    <b>Made with ❤️ by the <a href="https://github.com/mydehq">MyDE Team</a></b>
</div>
