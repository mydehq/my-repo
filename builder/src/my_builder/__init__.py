"""AUR Package Builder"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("my-builder")
except PackageNotFoundError:
    __version__ = "dev"
