"""User settings, stored as JSON in the per-user data dir."""
import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from snap.paths import user_data_dir

RESOLUTIONS = {"1280x720": (1280, 720), "960x540": (960, 540), "640x480": (640, 480)}
BACKENDS = ("auto", "unitycapture", "obs")
THEMES = ("auto", "light", "dark")
LANGUAGES = ("", "tr", "en")  # "" = follow Windows

SENSITIVITY_RANGE = (1.0, 10.0)
DURATION_RANGE = (1.0, 4.0)

_CHOICES = {"resolution": tuple(RESOLUTIONS), "backend": BACKENDS, "theme": THEMES,
            "language": LANGUAGES}
_RANGES = {"sensitivity": SENSITIVITY_RANGE, "duration": DURATION_RANGE}


@dataclass
class Settings:
    camera: str = ""
    microphone: str = ""
    resolution: str = "1280x720"
    backend: str = "auto"
    snap_enabled: bool = True
    sensitivity: float = 6.0
    effect: str = "cloud"
    duration: float = 2.0
    theme: str = "auto"
    language: str = ""
    close_to_tray: bool = True
    preview: bool = True

    @property
    def size(self) -> tuple[int, int]:
        return RESOLUTIONS[self.resolution]

    @staticmethod
    def default_path() -> Path:
        return user_data_dir() / "settings.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = Path(path) if path else cls.default_path()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return cls()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("settings root is not an object")
        except ValueError:
            try:
                path.with_name(path.name + ".bak").write_text(raw, encoding="utf-8")
            except OSError:
                pass
            return cls()
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> "Settings":
        defaults = cls()
        values = {}
        for f in fields(cls):
            default = getattr(defaults, f.name)
            value = data.get(f.name, default)
            values[f.name] = _clean(f.name, value, default)
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        path = Path(path) if path else self.default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(asdict(self), fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _clean(name: str, value, default):
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        lo, hi = _RANGES.get(name, (float("-inf"), float("inf")))
        return float(min(hi, max(lo, value)))
    if isinstance(default, str):
        if not isinstance(value, str):
            return default
        choices = _CHOICES.get(name)
        if choices is not None and value not in choices:
            return default
        return value
    return default
