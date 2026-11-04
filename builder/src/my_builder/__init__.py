"""AUR Package Builder"""

from importlib.metadata import PackageNotFoundError, metadata, version

__app__name__ = "my-builder"
__app_url__ = metadata(__app__name__).get("url")

try:
    __version__ = version(__app__name__)
except PackageNotFoundError:
    __version__ = "dev"
