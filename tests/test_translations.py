"""
Tests for the translation helpers in custom_components/google_geocode/sensor.py

Covers:
  - _load_translations: English baseline, region-suffix fallback, unknown language
    fallback, underscore/hyphen locale normalisation
  - _get_state_label: translated state labels, title-case fallback
  - Integration: sensor loads translations on init, extra_state_attributes uses
    stable keys (not translated labels), initial _state is a stable key
"""

import json
from unittest.mock import mock_open, patch

import pytest

# conftest.py inserts stubs onto sys.path before this module is imported.
from custom_components.google_geocode.sensor import (
    ATTR_CITY,
    ATTR_COUNTRY,
    ATTR_COUNTY,
    ATTR_FORMATTED_ADDRESS,
    ATTR_POSTAL_CODE,
    ATTR_POSTAL_TOWN,
    ATTR_REGION,
    ATTR_STREET,
    ATTR_STREET_NUMBER,
    STATE_AWAITING_UPDATE,
    _build_translations_index,
    _get_state_label,
    _load_translations,
)


# ---------------------------------------------------------------------------
# _load_translations
# ---------------------------------------------------------------------------

class TestLoadTranslations:
    """Tests for the translation file loader."""

    @pytest.fixture(autouse=True)
    def clear_translation_caches(self):
        """Clear lru_cache on both helpers before and after every test.

        The three patched tests supply fake os.listdir / open results.  Without
        clearing the cache a real result cached by an earlier test would be
        served instead of the patched one (and the patched result would then
        leak into later tests that expect real file I/O).
        """
        _build_translations_index.cache_clear()
        _load_translations.cache_clear()
        yield
        _build_translations_index.cache_clear()
        _load_translations.cache_clear()

    def test_load_english_translations(self):
        t = _load_translations('en')
        assert isinstance(t, dict)
        assert t['entity']['sensor']['google_geocode']['state']['awaiting_update'] == 'Awaiting Update'

    def test_load_translations_with_region_suffix_falls_back_to_base(self):
        """e.g. 'en-GB' should resolve to 'en.json' when 'en-GB.json' doesn't exist."""
        t = _load_translations('en-GB')
        assert t['entity']['sensor']['google_geocode']['state']['awaiting_update'] == 'Awaiting Update'

    def test_load_translations_unknown_language_falls_back_to_english(self):
        """An unknown language code should return the English translations."""
        t = _load_translations('xx-UNKNOWN')
        assert 'entity' in t

    def test_load_translations_underscore_locale_finds_uppercase_region_file(self):
        """pt_BR input must find pt-BR.json — the casing HA translators actually use.

        The directory is scanned case-insensitively, so pt-BR.json is resolved
        from the lower-cased candidate stem 'pt-br' regardless of the file's
        actual on-disk casing.
        """
        fake_data = {'entity': {'sensor': {'google_geocode': {'state': {'awaiting_update': 'Aguardando'}}}}}
        fake_json = json.dumps(fake_data)

        with patch('os.listdir', return_value=['pt-BR.json', 'en.json']), \
             patch('builtins.open', mock_open(read_data=fake_json)):
            t = _load_translations('pt_BR')

        assert t['entity']['sensor']['google_geocode']['state']['awaiting_update'] == 'Aguardando'

    def test_load_translations_hyphen_locale_finds_uppercase_region_file(self):
        """pt-BR input must also find pt-BR.json."""
        fake_data = {'entity': {'sensor': {'google_geocode': {'state': {'awaiting_update': 'Aguardando'}}}}}
        fake_json = json.dumps(fake_data)

        with patch('os.listdir', return_value=['pt-BR.json', 'en.json']), \
             patch('builtins.open', mock_open(read_data=fake_json)):
            t = _load_translations('pt-BR')

        assert t['entity']['sensor']['google_geocode']['state']['awaiting_update'] == 'Aguardando'

    def test_load_translations_lowercase_hyphen_file_still_found(self):
        """pt_BR input must also find pt-br.json (lowercase, the older convention)."""
        fake_data = {'entity': {'sensor': {'google_geocode': {'state': {'awaiting_update': 'Aguardando'}}}}}
        fake_json = json.dumps(fake_data)

        with patch('os.listdir', return_value=['pt-br.json', 'en.json']), \
             patch('builtins.open', mock_open(read_data=fake_json)):
            t = _load_translations('pt_BR')

        assert t['entity']['sensor']['google_geocode']['state']['awaiting_update'] == 'Aguardando'


# ---------------------------------------------------------------------------
# _get_state_label
# ---------------------------------------------------------------------------

class TestGetStateLabel:
    """Tests for the state label helper."""

    def test_returns_awaiting_update(self):
        t = _load_translations('en')
        assert _get_state_label(t, STATE_AWAITING_UPDATE) == 'Awaiting Update'

    def test_falls_back_to_title_cased_key(self):
        assert _get_state_label({}, 'some_state') == 'Some State'


# ---------------------------------------------------------------------------
# Integration: sensor + translations
# ---------------------------------------------------------------------------

class TestSensorTranslationIntegration:
    """Tests that verify the sensor class integrates correctly with translations."""

    def test_sensor_loads_translations_on_init(self, make_sensor):
        sensor = make_sensor(language='en')
        assert sensor._translations != {}

    def test_sensor_extra_attrs_use_stable_keys(self, make_sensor):
        """Attribute keys must be stable snake_case identifiers, not translated labels.

        Translations affect UI display only; changing the language must never
        change the dict keys returned by extra_state_attributes.
        """
        sensor = make_sensor(language='en')
        attrs = sensor.extra_state_attributes
        assert ATTR_STREET_NUMBER in attrs
        assert ATTR_STREET in attrs
        assert ATTR_CITY in attrs
        assert ATTR_POSTAL_TOWN in attrs
        assert ATTR_POSTAL_CODE in attrs
        assert ATTR_REGION in attrs
        assert ATTR_COUNTRY in attrs
        assert ATTR_COUNTY in attrs
        assert ATTR_FORMATTED_ADDRESS in attrs
        # Translated labels must NOT appear as keys
        assert 'Street' not in attrs   # translated label must not be a key
        assert 'City' not in attrs     # translated label must not be a key

    def test_sensor_initial_state_is_stable_key(self, make_sensor):
        """_state stores the stable key; the state property renders the translation.

        The internal ``_state`` field is always a stable, language-independent
        key or a raw user-facing string (address / zone name).  The public
        ``state`` property translates known keys through the loaded translations
        so that the UI and automations always see a localised, human-readable
        value.
        """
        sensor = make_sensor(language='en')
        # Internal field: stable key
        assert sensor._state == STATE_AWAITING_UPDATE
        # Public property: translated label rendered from that key
        t = _load_translations('en')
        assert sensor.state == _get_state_label(t, STATE_AWAITING_UPDATE)
