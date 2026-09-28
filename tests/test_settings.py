import json

from snap.core.settings import RESOLUTIONS, Settings


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(camera="Cam A", microphone="Mic B", effect="dust", duration=3.0, sensitivity=8.5)
    s.save(path)
    assert Settings.load(path) == s


def test_default_location_is_user_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAP_DATA_DIR", str(tmp_path))
    Settings(camera="X").save()
    assert (tmp_path / "settings.json").is_file()
    assert Settings.load().camera == "X"


def test_missing_file_gives_defaults(tmp_path):
    assert Settings.load(tmp_path / "nope.json") == Settings()


def test_unknown_keys_ignored_and_missing_defaulted(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"camera": "Cam", "bogus": 1}), encoding="utf-8")
    s = Settings.load(path)
    assert s.camera == "Cam"
    assert s.effect == Settings().effect


def test_wrong_types_and_out_of_range_values_are_repaired(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "camera": 5, "snap_enabled": "yes", "sensitivity": 99, "duration": 0.1,
        "resolution": "3x3", "backend": "magic", "theme": "neon", "language": "de",
    }), encoding="utf-8")
    s = Settings.load(path)
    d = Settings()
    assert s.camera == d.camera
    assert s.snap_enabled == d.snap_enabled
    assert s.sensitivity == 10.0
    assert s.duration == 1.0
    assert s.resolution == d.resolution
    assert s.backend == d.backend
    assert s.theme == d.theme
    assert s.language == ""


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path) == Settings()
    assert (tmp_path / "settings.json.bak").read_text(encoding="utf-8") == "{not json"


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "settings.json"
    Settings().save(path)
    Settings(camera="again").save(path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


def test_size_matches_resolution():
    assert Settings(resolution="960x540").size == (960, 540)
    assert set(RESOLUTIONS) == {"1280x720", "960x540", "640x480"}
