from pathlib import Path

import snap
from snap import paths

REPO = Path(__file__).resolve().parents[1]


def test_version_is_set():
    assert snap.__version__.count(".") == 2


def test_resource_path_points_at_repo_assets():
    assert paths.resource_path("assets") == REPO / "assets"
    assert paths.resource_path("assets", "models", "selfie_segmenter.tflite").is_file()


def test_user_data_dir_honours_env_and_creates_it(tmp_path, monkeypatch):
    target = tmp_path / "data" / "Snap"
    monkeypatch.setenv("SNAP_DATA_DIR", str(target))
    assert paths.user_data_dir() == target
    assert target.is_dir()
