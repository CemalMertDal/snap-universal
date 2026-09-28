from snap import i18n


def test_languages_have_identical_keys():
    assert set(i18n.STRINGS) == {"tr", "en"}
    assert set(i18n.STRINGS["tr"]) == set(i18n.STRINGS["en"])


def test_no_empty_strings():
    for lang, table in i18n.STRINGS.items():
        for key, value in table.items():
            assert value.strip(), f"{lang}:{key} is empty"


def test_translate_and_format():
    i18n.set_language("en")
    assert i18n.t("home.start") == "Start"
    i18n.set_language("tr")
    assert i18n.t("home.start") == "Başlat"
    assert "3" in i18n.t("home.countdown", n=3)


def test_fallbacks(monkeypatch):
    i18n.set_language("tr")
    monkeypatch.setitem(i18n.STRINGS["en"], "only.en", "English only")
    assert i18n.t("only.en") == "English only"
    assert i18n.t("does.not.exist") == "does.not.exist"


def test_unknown_language_falls_back_to_english():
    i18n.set_language("de")
    assert i18n.language() == "en"


def test_detect_language_returns_supported_code():
    assert i18n.detect_language() in ("tr", "en")
