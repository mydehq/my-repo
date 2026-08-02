"""AUR Package Builder"""

from importlib.metadata import PackageNotFoundError, version

__app__name__ = "my-builder"

try:
    __version__ = version(__app__name__)
except PackageNotFoundError:
    __version__ = "dev"
