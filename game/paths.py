"""Central place for filesystem locations (works from any working directory)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DATA = ROOT / "data"


def asset(*parts: str) -> Path:
    """Return the absolute path of a file inside the assets folder."""
    return ASSETS.joinpath(*parts)
