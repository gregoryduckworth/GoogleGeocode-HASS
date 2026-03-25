"""
Tests for the update() method of GoogleGeocode in
custom_components/google_geocode/sensor.py

Covers all significant branches of update():
  - Early exits: no origin, same location, zone unchanged
  - Zone displayed (display_zone != 'hide', device in a named zone)
  - Zone hidden (display_zone == 'hide') — full address built from API
  - Address built when device is not_home
  - All display option keywords (street_number, street, city, county, state,
    postal_town, postal_code, country, formatted_address)
  - Fallbacks: unnamed road → alt_street, city from postal_town / county,
    empty display list → street
  - Error handling: API error_message, HTTP / network error, IndexError
  - URL construction: key vs no key, language/region params, latlng
  - Plain coordinate origin (not a trackable entity)
  - Multiple sensor instances are independent (regression for global vars)
"""

from unittest.mock import patch

# conftest.py inserts stubs onto sys.path before this module is imported.
from custom_components.google_geocode.sensor import (
    STATE_AWAITING_UPDATE,
)
from tests.conftest import (
    EMPTY_RESULTS_RESPONSE,
    ERROR_RESPONSE,
    FULL_API_RESPONSE,
    mock_api_response,
)


# ---------------------------------------------------------------------------
# update() — branch coverage
# ---------------------------------------------------------------------------

class TestUpdate:
    """Tests for the update() method under various conditions."""

    # ------------------------------------------------------------------
    # Early-exit branches
    # ------------------------------------------------------------------

    def test_no_update_when_origin_is_none(self, make_sensor, hass):
        """If _origin is None (entity not found), update returns early."""
        sensor = make_sensor(origin="device_tracker.missing")
        with patch("custom_components.google_geocode.sensor.requests.get") as mock_get:
            sensor.update()
        mock_get.assert_not_called()
        assert sensor._state == STATE_AWAITING_UPDATE

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
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Home"

    def test_zone_state_is_title_cased(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "work", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", display_zone="display")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Work"

    # ------------------------------------------------------------------
    # Zone hidden / not_home — address built from API response
    # ------------------------------------------------------------------

    def test_update_with_not_home_builds_address(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"

    def test_update_populates_all_address_attributes(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
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
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"

    # ------------------------------------------------------------------
    # Display options
    # ------------------------------------------------------------------

    def test_option_street_number(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street_number, street")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert "10" in sensor._state
        assert "Downing Street" in sensor._state

    def test_option_county(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="county")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Greater London"

    def test_option_state(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="state")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "England"

    def test_option_postal_town(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="postal_town")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "London"

    def test_option_postal_code(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="postal_code")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "SW1A 2AA"

    def test_option_country(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="country")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "United Kingdom"

    def test_option_formatted_address(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="formatted_address")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
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
                   return_value=mock_api_response(payload)):
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
                   return_value=mock_api_response(payload)):
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
                   return_value=mock_api_response(payload)):
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
                   return_value=mock_api_response(payload)):
            sensor.update()

        assert sensor._state == "Downing Street"

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_api_error_message_sets_state(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(ERROR_RESPONSE)):
            sensor.update()

        assert sensor._state == "The provided API key is invalid."

    def test_http_error_returns_early(self, make_sensor, hass):
        import requests as req
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   side_effect=req.exceptions.RequestException("timeout")):
            sensor.update()

        assert sensor._state == STATE_AWAITING_UPDATE

    def test_formatted_address_index_error_handled(self, make_sensor, hass):
        """IndexError on empty results list is swallowed."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(EMPTY_RESULTS_RESPONSE)):
            sensor.update()  # should not raise

        assert sensor._formatted_address is None

    # ------------------------------------------------------------------
    # URL construction
    # ------------------------------------------------------------------

    def test_url_without_api_key_uses_maps_google(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", api_key="no key")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("https://maps.google.com")
        assert "key=" not in called_url

    def test_url_with_api_key_uses_maps_googleapis(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", api_key="MY_API_KEY")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("https://maps.googleapis.com")
        assert "key=MY_API_KEY" in called_url

    def test_url_includes_language_and_region(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", language="fr", region="fr")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        called_url = mock_get.call_args[0][0]
        assert "language=fr" in called_url
        assert "region=fr" in called_url

    def test_url_includes_latlng(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
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
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert "latlng=51.5074,-0.1278" in called_url

    def test_plain_coord_origin_state_built_from_api(self, make_sensor, hass):
        sensor = make_sensor(origin="51.5074,-0.1278", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"

    # ------------------------------------------------------------------
    # Multiple sensors are independent (regression for global vars)
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
                   return_value=mock_api_response(response_a)):
            sensor_a.update()

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(response_b)):
            sensor_b.update()

        assert sensor_a._state == "Street A, City A"
        assert sensor_b._state == "Street B, City B"

    def test_current_location_updated_after_update(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._current_location == "51.5,-0.12"

    def test_zone_check_current_updated_after_update(self, make_sensor, hass):
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._zone_check_current == "not_home"

    def test_attributes_reset_on_each_update(self, make_sensor, hass):
        """Stale attributes from the previous location are cleared before a new geocode call."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        # First update with full response
        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
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
                   return_value=mock_api_response(minimal_payload)):
            sensor.update()

        # Street should have been reset then re-assigned to the fallback 'Unnamed Road'
        # (no route component in the second response, so the fallback applies)
        assert sensor._street == "Unnamed Road"
