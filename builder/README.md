<div align="center">

# MyBuilder

**Compile AUR packages automatically without hassle**

</div>
<br/>

MyBuilder is a command-line tool that builds configured AUR packages and generates the repository website.

## Installation

Install it with `uv`:

```bash
uv tool install /path/to/my-repo/builder
```

Or install it into an existing Python environment:

```bash
python -m pip install /path/to/my-repo/builder
```

After installation, the `my-builder` command is available.

## Usage

```bash
my-builder --config config.yml build
my-builder --config config.yml build-index
my-builder --config config.yml build --package myctl
```

Run `my-builder --help` for the complete command reference.

## Configuration

Below is full configuration example:

```yaml
repo:
  name: my-repo
  url: https://github.com/mydehq/my-repo

site:
  url: https://mydehq.github.io/my-repo

packages:
  - myctl
  - mytm
  - kireisakura-kit|always
```

The optional `|always` suffix forces a package to rebuild even when its version is unchanged.
