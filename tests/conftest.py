import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Never touch the real %APPDATA%\\Snap from tests."""
    monkeypatch.setenv("SNAP_DATA_DIR", str(tmp_path / "snap-data"))
