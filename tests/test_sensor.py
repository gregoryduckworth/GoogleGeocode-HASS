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
  - update() — all significant branches:
      * no origin (None)
      * same location (no duplicate request)
      * zone unchanged (not not_home) — skipped
      * zone displayed (display_zone != 'hide', in a zone)
      * zone hidden (display_zone == 'hide') — full address built
      * device not in HA states → zone_check = 'not_home'
      * plain coordinate origin (not a trackable entity)
      * API error_message in response
      * HTTP / network error
      * all display option keywords
      * fallbacks: unnamed road → alt_street, city from postal_town / county
      * formatted_address IndexError handled gracefully
"""

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

# conftest.py inserts stubs onto sys.path before this module is imported.
from custom_components.google_geocode.sensor import (
    DEFAULT_KEY,
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
)
from tests.conftest import (
    FULL_API_RESPONSE,
    EMPTY_RESULTS_RESPONSE,
    ERROR_RESPONSE,
    FakeState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(payload: dict, status_code: int = 200, raise_for_status=None):
    """Return a mock requests.Response-like object."""
    mock = MagicMock()
    mock.text = json.dumps(payload)
    mock.status_code = status_code
    if raise_for_status is not None:
        mock.raise_for_status.side_effect = raise_for_status
    else:
        mock.raise_for_status.return_value = None
    return mock


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
        assert sensor._state == "Awaiting Update"

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
        sensor = make_sensor()
        sensor._state = "London"
        assert sensor.state == "London"

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


# ---------------------------------------------------------------------------
# update() — branch coverage
# ---------------------------------------------------------------------------

class TestUpdate:
    """Tests for the update() method under various conditions."""

    def _make_patched_sensor(self, make_sensor, hass, response_payload,
                              origin="device_tracker.phone",
                              state="not_home",
                              lat=51.5, lon=-0.12,
                              display_zone="display",
                              options="street, city",
                              api_key="no key"):
        """Helper: creates sensor, sets entity state, patches requests.get."""
        hass.set_state(origin, state, {"latitude": lat, "longitude": lon})
        sensor = make_sensor(
            origin=origin,
            display_zone=display_zone,
            options=options,
            api_key=api_key,
        )
        return sensor

    # ------------------------------------------------------------------
    # Early-exit branches
    # ------------------------------------------------------------------

    def test_no_update_when_origin_is_none(self, make_sensor, hass):
        """If _origin is None (entity not found), update returns early."""
        sensor = make_sensor(origin="device_tracker.missing")
        with patch("custom_components.google_geocode.sensor.requests.get") as mock_get:
            sensor.update()
        mock_get.assert_not_called()
        assert sensor._state == "Awaiting Update"

    def test_no_update_when_location_unchanged(self, make_sensor, hass):
        """If location hasn't changed, no HTTP request is made."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")
        sensor._current_location = "51.5,-0.12"  # pre-set to same location

        with patch("custom_components.google_geocode.sensor.requests.get") as mock_get:
            sensor.update()
        mock_get.assert_not_called()

    def test_no_update_when_zone_unchanged_and_not_home(self, make_sensor, hass):
        """If zone is unchanged and is a named zone (not not_home), skip update."""
        hass.set_state("device_tracker.phone", "home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")
        sensor._zone_check_current = "home"  # already in this zone

        with patch("custom_components.google_geocode.sensor.requests.get") as mock_get:
            sensor.update()
        mock_get.assert_not_called()

    # ------------------------------------------------------------------
    # Zone displayed (in a named zone, display_zone != 'hide')
    # ------------------------------------------------------------------

    def test_state_shows_zone_when_in_zone_and_display_not_hidden(self, make_sensor, hass):
        """When device is in a named zone and display_zone is 'display', show zone name."""
        hass.set_state("device_tracker.phone", "home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", display_zone="display")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Home"

    def test_zone_state_is_title_cased(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "work", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", display_zone="display")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Work"

    # ------------------------------------------------------------------
    # Zone hidden / not_home — address built from API response
    # ------------------------------------------------------------------

    def test_update_with_not_home_builds_address(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"

    def test_update_populates_all_address_attributes(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._street_number == "10"
        assert sensor._street == "Downing Street"
        assert sensor._city == "London"
        assert sensor._postal_town == "London"
        assert sensor._region == "England"
        assert sensor._county == "Greater London"
        assert sensor._country == "United Kingdom"
        assert sensor._postal_code == "SW1A 2AA"
        assert sensor._formatted_address == "10 Downing St, London SW1A 2AA, UK"

    def test_update_with_display_zone_hide_builds_address(self, make_sensor, hass):
        """display_zone='hide' forces address display even when in a zone."""
        hass.set_state("device_tracker.phone", "home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            display_zone="hide",
            options="street, city",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"

    # ------------------------------------------------------------------
    # Display options
    # ------------------------------------------------------------------

    def test_option_street_number(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street_number, street")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert "10" in sensor._state
        assert "Downing Street" in sensor._state

    def test_option_county(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="county")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Greater London"

    def test_option_state(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="state")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "England"

    def test_option_postal_town(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="postal_town")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "London"

    def test_option_postal_code(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="postal_code")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "SW1A 2AA"

    def test_option_country(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="country")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "United Kingdom"

    def test_option_formatted_address(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="formatted_address")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "10 Downing St, London SW1A 2AA, UK"

    # ------------------------------------------------------------------
    # Fallbacks
    # ------------------------------------------------------------------

    def test_fallback_unnamed_road_to_alt_street(self, make_sensor, hass):
        """When route is missing, street falls back to sublocality_level_1."""
        payload = {
            "results": [{
                "formatted_address": "Westminster, London",
                "address_components": [
                    {"long_name": "Westminster", "types": ["sublocality_level_1"]},
                    {"long_name": "London", "types": ["locality"]},
                ],
            }]
        }
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(payload)):
            sensor.update()

        assert sensor._street == "Westminster"
        assert "Westminster" in sensor._state

    def test_fallback_city_to_postal_town(self, make_sensor, hass):
        """When locality is absent, city falls back to postal_town."""
        payload = {
            "results": [{
                "formatted_address": "Downing Street, London",
                "address_components": [
                    {"long_name": "Downing Street", "types": ["route"]},
                    {"long_name": "London", "types": ["postal_town"]},
                ],
            }]
        }
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(payload)):
            sensor.update()

        assert "London" in sensor._state

    def test_fallback_city_to_county(self, make_sensor, hass):
        """When locality and postal_town are absent, city falls back to county."""
        payload = {
            "results": [{
                "formatted_address": "Downing Street, Greater London",
                "address_components": [
                    {"long_name": "Downing Street", "types": ["route"]},
                    {"long_name": "Greater London", "types": ["administrative_area_level_2"]},
                ],
            }]
        }
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(payload)):
            sensor.update()

        assert "Greater London" in sensor._state

    def test_fallback_to_street_when_all_display_empty(self, make_sensor, hass):
        """When the display list is empty (e.g. options='city' but no city), falls back to street."""
        payload = {
            "results": [{
                "formatted_address": "Downing Street",
                "address_components": [
                    {"long_name": "Downing Street", "types": ["route"]},
                ],
            }]
        }
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(payload)):
            sensor.update()

        assert sensor._state == "Downing Street"

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_api_error_message_sets_state(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(ERROR_RESPONSE)):
            sensor.update()

        assert sensor._state == "The provided API key is invalid."

    def test_http_error_returns_early(self, make_sensor, hass):
        import requests as req
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   side_effect=req.exceptions.RequestException("timeout")):
            sensor.update()

        assert sensor._state == "Awaiting Update"

    def test_formatted_address_index_error_handled(self, make_sensor, hass):
        """IndexError on empty results list is swallowed."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(EMPTY_RESULTS_RESPONSE)):
            sensor.update()  # should not raise

        assert sensor._formatted_address is None

    # ------------------------------------------------------------------
    # URL construction
    # ------------------------------------------------------------------

    def test_url_without_api_key_uses_maps_google(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", api_key="no key")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("https://maps.google.com")
        assert "key=" not in called_url

    def test_url_with_api_key_uses_maps_googleapis(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", api_key="MY_API_KEY")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("https://maps.googleapis.com")
        assert "key=MY_API_KEY" in called_url

    def test_url_includes_language_and_region(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", language="fr", region="fr")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        called_url = mock_get.call_args[0][0]
        assert "language=fr" in called_url
        assert "region=fr" in called_url

    def test_url_includes_latlng(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        called_url = mock_get.call_args[0][0]
        assert "latlng=51.5,-0.12" in called_url

    # ------------------------------------------------------------------
    # Plain coordinate origin (not a trackable entity)
    # ------------------------------------------------------------------

    def test_plain_coord_origin_triggers_api(self, make_sensor, hass):
        """A raw lat/lon string (not an entity) still triggers a geocode request."""
        sensor = make_sensor(origin="51.5074,-0.1278")
        # For plain coord there's no entity, zone_check defaults to not_home
        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert "latlng=51.5074,-0.1278" in called_url

    def test_plain_coord_origin_state_built_from_api(self, make_sensor, hass):
        sensor = make_sensor(origin="51.5074,-0.1278", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"

    # ------------------------------------------------------------------
    # Second sensors are independent (regression for global vars)
    # ------------------------------------------------------------------

    def test_two_sensors_update_independently(self, make_sensor, hass):
        hass.set_state("device_tracker.a", "not_home", {"latitude": 51.0, "longitude": -0.1})
        hass.set_state("device_tracker.b", "not_home", {"latitude": 52.0, "longitude": -1.0})

        response_a = {
            "results": [{
                "formatted_address": "Street A",
                "address_components": [
                    {"long_name": "Street A", "types": ["route"]},
                    {"long_name": "City A", "types": ["locality"]},
                ],
            }]
        }
        response_b = {
            "results": [{
                "formatted_address": "Street B",
                "address_components": [
                    {"long_name": "Street B", "types": ["route"]},
                    {"long_name": "City B", "types": ["locality"]},
                ],
            }]
        }

        sensor_a = make_sensor(origin="device_tracker.a", options="street, city")
        sensor_b = make_sensor(origin="device_tracker.b", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(response_a)):
            sensor_a.update()

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(response_b)):
            sensor_b.update()

        assert sensor_a._state == "Street A, City A"
        assert sensor_b._state == "Street B, City B"

    def test_current_location_updated_after_update(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._current_location == "51.5,-0.12"

    def test_zone_check_current_updated_after_update(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._zone_check_current == "not_home"

    def test_attributes_reset_on_each_update(self, make_sensor, hass):
        """Stale attributes from the previous location are cleared before a new geocode call."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        # First update with full response
        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(FULL_API_RESPONSE)):
            sensor.update()
        assert sensor._street == "Downing Street"

        # Move to a new location with no street in the response
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 52.0, "longitude": -1.0})
        sensor._current_location = "old"  # force update

        minimal_payload = {
            "results": [{
                "formatted_address": "Somewhere",
                "address_components": [
                    {"long_name": "Somewhere", "types": ["locality"]},
                ],
            }]
        }
        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=_mock_response(minimal_payload)):
            sensor.update()

        # Street should have been reset then re-assigned to the fallback 'Unnamed Road'
        # (no route component in the second response, so the fallback applies)
        assert sensor._street == "Unnamed Road"
