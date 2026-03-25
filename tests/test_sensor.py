"""
Tests for custom_components/google_geocode/sensor.py

Covers:
  - Sensor initialisation (entity tracker vs raw coords)
  - Properties: name, state, entity_picture, extra_state_attributes
  - _get_location_from_entity (found / missing / no location attrs)
  - _get_location_from_attributes
  - _reset_attributes
  - _append_to_user_display
  - _get_gravatar_for_email
  - _get_image_from_url

See test_translations.py for translation-helper tests and
test_update.py for update() branch coverage.
"""

import hashlib
from unittest.mock import patch

# conftest.py inserts stubs onto sys.path before this module is imported.
from custom_components.google_geocode.sensor import (
    GoogleGeocode,
    TRACKABLE_DOMAINS,
    ATTR_STREET_NUMBER,
    ATTR_STREET,
    ATTR_CITY,
    ATTR_POSTAL_TOWN,
    ATTR_POSTAL_CODE,
    ATTR_REGION,
    ATTR_COUNTRY,
    ATTR_COUNTY,
    ATTR_FORMATTED_ADDRESS,
    CONF_ATTRIBUTION,
    STATE_AWAITING_UPDATE
)
from tests.conftest import (
    FULL_API_RESPONSE,
    FakeState,
    mock_api_response,
)

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_entity_tracker_origin_stored_as_entity_id(self, make_sensor):
        sensor = make_sensor(origin="device_tracker.phone")
        assert sensor._origin_entity_id == "device_tracker.phone"
        assert not hasattr(sensor, "_origin")

    def test_sensor_origin_stored_as_entity_id(self, make_sensor):
        sensor = make_sensor(origin="sensor.gps")
        assert sensor._origin_entity_id == "sensor.gps"

    def test_person_origin_stored_as_entity_id(self, make_sensor):
        sensor = make_sensor(origin="person.john")
        assert sensor._origin_entity_id == "person.john"

    def test_raw_coord_origin_stored_as_origin(self, make_sensor):
        sensor = make_sensor(origin="51.5074,-0.1278")
        assert sensor._origin == "51.5074,-0.1278"
        assert not hasattr(sensor, "_origin_entity_id")

    def test_options_lowercased(self, make_sensor):
        sensor = make_sensor(options="Street, City")
        assert sensor._options == "street, city"

    def test_language_lowercased(self, make_sensor):
        sensor = make_sensor(language="EN-GB")
        assert sensor._google_language == "en-gb"

    def test_region_lowercased(self, make_sensor):
        sensor = make_sensor(region="GB")
        assert sensor._google_region == "gb"

    def test_display_zone_lowercased(self, make_sensor):
        sensor = make_sensor(display_zone="Display")
        assert sensor._display_zone == "display"

    def test_initial_state_is_awaiting_update(self, make_sensor):
        sensor = make_sensor()
        assert sensor._state == STATE_AWAITING_UPDATE

    def test_all_address_attributes_start_as_none(self, make_sensor):
        sensor = make_sensor()
        for attr in [
            "_street_number", "_street", "_city", "_postal_town",
            "_postal_code", "_region", "_country", "_county",
            "_formatted_address",
        ]:
            assert getattr(sensor, attr) is None, f"{attr} should start as None"

    def test_no_duplicate_city_attribute(self, make_sensor):
        """Regression: _city was initialised twice in the original code."""
        sensor = make_sensor()
        assert sensor._city is None  # only once, no side-effect from duplication

    def test_gravatar_sets_picture(self, make_sensor):
        sensor = make_sensor(gravatar="test@example.com")
        expected = hashlib.md5(b"test@example.com").hexdigest()
        assert expected in sensor._picture

    def test_image_sets_picture(self, make_sensor):
        sensor = make_sensor(image="https://example.com/pic.jpg")
        assert sensor._picture == "https://example.com/pic.jpg"

    def test_no_gravatar_no_image_picture_is_none(self, make_sensor):
        sensor = make_sensor()
        assert sensor._picture is None

    def test_instance_tracking_vars_initialised(self, make_sensor):
        """Regression: globals replaced by per-instance variables."""
        sensor = make_sensor()
        assert sensor._current_location == "0,0"
        assert sensor._zone_check == "a"

    def test_two_sensors_have_independent_tracking_vars(self, make_sensor):
        s1 = make_sensor(origin="device_tracker.a")
        s2 = make_sensor(origin="device_tracker.b")
        s1._current_location = "1,1"
        assert s2._current_location == "0,0"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_name_property(self, make_sensor):
        sensor = make_sensor(name="My Sensor")
        assert sensor.name == "My Sensor"

    def test_state_property(self, make_sensor):
        """Raw address/zone strings stored in _state are returned as-is by state."""
        sensor = make_sensor()
        sensor._state = "London"
        assert sensor.state == "London"

    def test_state_property_translates_known_keys(self, make_sensor):
        """Known stable keys stored in _state are translated by the state property."""
        sensor = make_sensor(language='en')
        sensor._state = STATE_AWAITING_UPDATE
        assert sensor.state == 'Awaiting Update'

    def test_state_property_passes_through_error_message_unchanged(self, make_sensor):
        """API error messages must not be mangled by the title-case fallback.

        _get_state_label's fallback applies .title() to unknown snake_case keys,
        but a string like 'The provided API key is invalid.' contains spaces and
        punctuation — it must be returned verbatim, not title-cased.
        """
        sensor = make_sensor()
        error_msg = "The provided API key is invalid."
        sensor._state = error_msg
        assert sensor.state == error_msg

    def test_state_property_passes_through_zone_with_underscores_unchanged(self, make_sensor, hass):
        """Multi-word zone names (underscores) must be rendered correctly end-to-end.

        update() stores zone names as ``zone_check[0].upper() + zone_check[1:]``
        (e.g. 'work_office' → 'Work_office').  _get_state_label's fallback then
        converts that to 'Work Office' via the snake_case title-case path.
        Verify both that _state holds the half-formatted key and that the public
        state property delivers the fully human-readable label.
        """
        hass.set_state("device_tracker.phone", "work_office", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", display_zone="display")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        # _state holds the half-capitalised form produced by update()
        assert sensor._state == "Work_office"
        # state property finishes the formatting to a readable label
        assert sensor.state == "Work Office"

    def test_state_property_passes_through_address_string_unchanged(self, make_sensor):
        """Multi-word address strings must be returned exactly as set by update()."""
        sensor = make_sensor()
        sensor._state = "10 Downing Street, London"
        assert sensor.state == "10 Downing Street, London"

    def test_entity_picture_property(self, make_sensor):
        sensor = make_sensor()
        sensor._picture = "https://example.com/pic.jpg"
        assert sensor.entity_picture == "https://example.com/pic.jpg"

    def test_extra_state_attributes_keys(self, make_sensor):
        sensor = make_sensor()
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
        assert "attribution" in attrs

    def test_extra_state_attributes_attribution(self, make_sensor):
        sensor = make_sensor()
        assert sensor.extra_state_attributes["attribution"] == CONF_ATTRIBUTION

    def test_extra_state_attributes_values_after_update(self, make_sensor):
        sensor = make_sensor()
        sensor._street_number = "10"
        sensor._street = "Downing Street"
        sensor._city = "London"
        attrs = sensor.extra_state_attributes
        assert attrs[ATTR_STREET_NUMBER] == "10"
        assert attrs[ATTR_STREET] == "Downing Street"
        assert attrs[ATTR_CITY] == "London"


# ---------------------------------------------------------------------------
# Trackable domains
# ---------------------------------------------------------------------------

class TestTrackableDomains:
    def test_device_tracker_is_trackable(self):
        assert "device_tracker" in TRACKABLE_DOMAINS

    def test_sensor_is_trackable(self):
        assert "sensor" in TRACKABLE_DOMAINS

    def test_person_is_trackable(self):
        assert "person" in TRACKABLE_DOMAINS


# ---------------------------------------------------------------------------
# _get_location_from_attributes
# ---------------------------------------------------------------------------

class TestGetLocationFromAttributes:
    def test_returns_lat_lon_string(self, make_sensor):
        sensor = make_sensor()
        entity = FakeState("home", {"latitude": 51.5, "longitude": -0.12})
        result = GoogleGeocode._get_location_from_attributes(entity)
        assert result == "51.5,-0.12"

    def test_returns_zero_when_missing(self, make_sensor):
        sensor = make_sensor()
        entity = FakeState("home", {"latitude": 0.0, "longitude": 0.0})
        result = GoogleGeocode._get_location_from_attributes(entity)
        assert result == "0.0,0.0"


# ---------------------------------------------------------------------------
# _get_location_from_entity
# ---------------------------------------------------------------------------

class TestGetLocationFromEntity:
    def test_returns_none_when_entity_missing(self, make_sensor, hass):
        sensor = make_sensor()
        result = sensor._get_location_from_entity("device_tracker.ghost")
        assert result is None

    def test_returns_coords_when_entity_has_location(self, make_sensor, hass):
        hass.set_state(
            "device_tracker.phone", "not_home",
            {"latitude": 51.5, "longitude": -0.12}
        )
        sensor = make_sensor(origin="device_tracker.phone")
        result = sensor._get_location_from_entity("device_tracker.phone")
        assert result == "51.5,-0.12"

    def test_returns_none_when_entity_has_no_location(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "home", {})
        sensor = make_sensor(origin="device_tracker.phone")
        result = sensor._get_location_from_entity("device_tracker.phone")
        assert result is None


# ---------------------------------------------------------------------------
# _reset_attributes
# ---------------------------------------------------------------------------

class TestResetAttributes:
    def test_all_attributes_set_to_none(self, make_sensor):
        sensor = make_sensor()
        sensor._street = "Downing Street"
        sensor._city = "London"
        sensor._reset_attributes()
        for attr in [
            "_street_number", "_street", "_city", "_postal_town",
            "_postal_code", "_region", "_country", "_county",
            "_formatted_address",
        ]:
            assert getattr(sensor, attr) is None, f"{attr} should be None after reset"


# ---------------------------------------------------------------------------
# _append_to_user_display
# ---------------------------------------------------------------------------

class TestAppendToUserDisplay:
    def test_appends_non_empty_value(self, make_sensor):
        sensor = make_sensor()
        lst = []
        sensor._append_to_user_display(lst, "London")
        assert lst == ["London"]

    def test_does_not_append_empty_string(self, make_sensor):
        sensor = make_sensor()
        lst = []
        sensor._append_to_user_display(lst, "")
        assert lst == []

    def test_multiple_values(self, make_sensor):
        sensor = make_sensor()
        lst = []
        sensor._append_to_user_display(lst, "10")
        sensor._append_to_user_display(lst, "")
        sensor._append_to_user_display(lst, "London")
        assert lst == ["10", "London"]


# ---------------------------------------------------------------------------
# _get_gravatar_for_email
# ---------------------------------------------------------------------------

class TestGetGravatarForEmail:
    def test_returns_gravatar_url(self, make_sensor):
        sensor = make_sensor()
        url = sensor._get_gravatar_for_email("Test@Example.COM")
        # Email bytes are hashed as-is (encode then lower on bytes is same as lower on str)
        expected_hash = hashlib.md5("Test@Example.COM".encode("utf-8").lower()).hexdigest()
        assert url == f"https://www.gravatar.com/avatar/{expected_hash}.jpg?s=80&d=wavatar"

    def test_different_emails_give_different_urls(self, make_sensor):
        sensor = make_sensor()
        assert sensor._get_gravatar_for_email("a@a.com") != sensor._get_gravatar_for_email("b@b.com")


# ---------------------------------------------------------------------------
# _get_image_from_url
# ---------------------------------------------------------------------------

class TestGetImageFromUrl:
    def test_returns_url_unchanged(self, make_sensor):
        sensor = make_sensor()
        url = "https://example.com/avatar.jpg"
        assert GoogleGeocode._get_image_from_url(url) == url

    def test_returns_url_with_query_string_unchanged(self, make_sensor):
        url = "https://example.com/avatar.jpg?size=80"
        assert GoogleGeocode._get_image_from_url(url) == url

