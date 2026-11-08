"""AUR Package Builder"""

from importlib.metadata import PackageNotFoundError, metadata, version

__app__name__ = "my-builder"
__app_url__ = metadata(__app__name__).get("Project-URL", "")

if __app_url__:
    __app_url__ = __app_url__.split(", ", 1)[-1]

try:
    __version__ = version(__app__name__)
except PackageNotFoundError:
    __version__ = "dev"
