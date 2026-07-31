<div align="center">

# MyBuilder

**Compile AUR packages automatically without hassle**

</div>
<br/>

MyBuilder is a tool to automate the compilation of AUR packages, with addition of generation of index website.

## Configuration

Below is full configuration example:

```yaml
repo_name: my-repo
repo_url: https://mydehq.github.io/my-repo
project_url: https://github.com/mydehq/my-repo

builder:
  build_dir: build
  dist_dir: dist
  icon_file: src/icon.png

  templates:
    index: src/index.html
    installer: src/install.sh

packages:
  - myctl
  - mytm
  - name: aur-helper
    force: true # force compilation even if package is up-to-date
```
