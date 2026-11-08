from dataclasses import dataclass, field
from pathlib import Path

from . import __app__name__


@dataclass(slots=True)
class Defaults:
    config_file: Path = Path("config.yml")
    data_dir: Path = Path(f".{__app__name__}")
    site_input_dir: Path = Path(__file__).parent / "assets"

    install_cmd: str = "curl -fSL {site_url}/setup | bash"

    aur_url: str = "https://aur.archlinux.org"
    aur_pkg_url: str = field(init=False)

    pkg_template_start: str = "ROW_TEMPLATE_START"
    pkg_template_end: str = "ROW_TEMPLATE_END"

    def __post_init__(self) -> None:
        self.aur_url = self.aur_url.rstrip("/")
        self.aur_pkg_url = f"{self.aur_url}/packages"


defaults = Defaults()
