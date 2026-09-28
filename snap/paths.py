"""Where bundled resources and per-user data live, both in dev and in the frozen exe."""
import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return _base_dir().joinpath(*parts)


def user_data_dir() -> Path:
    override = os.environ.get("SNAP_DATA_DIR")
    if override:
        path = Path(override)
    else:
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(root) / "Snap"
    path.mkdir(parents=True, exist_ok=True)
    return path
