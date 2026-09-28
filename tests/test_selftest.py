from snap import effects, selftest


def test_selftest_passes_and_logs_every_effect(tmp_path):
    log = tmp_path / "selftest.log"
    assert selftest.run(log) == 0
    text = log.read_text(encoding="utf-8")
    assert "RESULT PASS" in text
    for eid in effects.effect_ids():
        assert eid in text
