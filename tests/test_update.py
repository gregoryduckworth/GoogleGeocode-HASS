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
  - Field ordering via the order= config key
  - Misspelling / unknown token warnings for order= and options=
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
    NO_STREET_NUMBER_RESPONSE,
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


# ---------------------------------------------------------------------------
# paused_by — polling suppression based on a HA entity state
# ---------------------------------------------------------------------------

class TestUpdatePausedBy:
    """Tests for the paused_by feature: skip polling when a designated entity is 'on'."""

    def test_polling_skipped_when_paused_by_entity_is_on(self, make_sensor, hass):
        """No HTTP request is made when the paused_by entity state is 'on'."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        hass.set_state("input_boolean.vacation_mode", "on")
        sensor = make_sensor(
            origin="device_tracker.phone",
            paused_by="input_boolean.vacation_mode",
        )

        with patch("custom_components.google_geocode.sensor.requests.get") as mock_get:
            sensor.update()

        mock_get.assert_not_called()

    def test_state_unchanged_when_paused(self, make_sensor, hass):
        """Sensor state is left at awaiting_update when paused."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        hass.set_state("input_boolean.vacation_mode", "on")
        sensor = make_sensor(
            origin="device_tracker.phone",
            paused_by="input_boolean.vacation_mode",
        )

        with patch("custom_components.google_geocode.sensor.requests.get"):
            sensor.update()

        assert sensor._state == STATE_AWAITING_UPDATE

    def test_polling_resumes_when_paused_by_entity_is_off(self, make_sensor, hass):
        """HTTP request is made when the paused_by entity state is 'off'."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        hass.set_state("input_boolean.vacation_mode", "off")
        sensor = make_sensor(
            origin="device_tracker.phone",
            paused_by="input_boolean.vacation_mode",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        mock_get.assert_called_once()

    def test_polling_not_blocked_when_paused_by_entity_missing(self, make_sensor, hass):
        """When the paused_by entity does not exist in HA, polling is not blocked."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        # 'input_boolean.vacation_mode' is intentionally NOT registered in hass
        sensor = make_sensor(
            origin="device_tracker.phone",
            paused_by="input_boolean.vacation_mode",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        mock_get.assert_called_once()

    def test_no_paused_by_does_not_skip_polling(self, make_sensor, hass):
        """Default behaviour (no paused_by) is unaffected — polling proceeds normally."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)) as mock_get:
            sensor.update()

        mock_get.assert_called_once()

    def test_paused_then_resumed_updates_state(self, make_sensor, hass):
        """After being paused, a sensor resumes geocoding once the entity flips to 'off'."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        hass.set_state("input_boolean.vacation_mode", "on")
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street, city",
            paused_by="input_boolean.vacation_mode",
        )

        # While paused, no update
        with patch("custom_components.google_geocode.sensor.requests.get") as mock_get:
            sensor.update()
        mock_get.assert_not_called()
        assert sensor._state == STATE_AWAITING_UPDATE

        # Vacation mode turns off → polling resumes
        hass.set_state("input_boolean.vacation_mode", "off")
        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"


# ---------------------------------------------------------------------------
# Field ordering — _parse_order and order config key
# ---------------------------------------------------------------------------

class TestFieldOrdering:
    """Tests for the user-configurable field display order feature."""

    # ------------------------------------------------------------------
    # _parse_order unit tests
    # ------------------------------------------------------------------

    def test_parse_order_none_returns_none(self, make_sensor):
        sensor = make_sensor()
        assert sensor._parse_order(None) is None

    def test_parse_order_empty_string_returns_none(self, make_sensor):
        sensor = make_sensor()
        assert sensor._parse_order("") is None

    def test_parse_order_all_unknown_returns_none(self, make_sensor):
        sensor = make_sensor()
        assert sensor._parse_order("nonsense, garbage") is None

    def test_parse_order_valid_fields(self, make_sensor):
        sensor = make_sensor()
        result = sensor._parse_order("city, street")
        assert result == ["city", "street"]

    def test_parse_order_resolves_state_alias(self, make_sensor):
        sensor = make_sensor()
        result = sensor._parse_order("state")
        assert result == ["region"]

    def test_parse_order_strips_whitespace(self, make_sensor):
        sensor = make_sensor()
        result = sensor._parse_order("  city  ,  country  ")
        assert result == ["city", "country"]

    def test_parse_order_lowercases_tokens(self, make_sensor):
        sensor = make_sensor()
        result = sensor._parse_order("City, Country")
        assert result == ["city", "country"]

    def test_parse_order_deduplicates(self, make_sensor):
        sensor = make_sensor()
        result = sensor._parse_order("city, city, street")
        assert result == ["city", "street"]

    def test_parse_order_skips_empty_tokens_silently(self, make_sensor, caplog):
        """Empty tokens from trailing/double commas are skipped without warning.

        order='city,,street,' has two empty tokens (the double comma and the
        trailing comma); neither should produce a log warning.
        """
        import logging
        sensor = make_sensor()
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            result = sensor._parse_order("city,,street,")
        assert result == ["city", "street"]
        assert caplog.text == ""

    def test_parse_order_drops_unknown_tokens_and_warns(self, make_sensor, caplog):
        """Unknown tokens are dropped from the result AND a WARNING is emitted.

        The token 'TYPO' is invalid; it must be absent from the returned list
        and must appear in the log so the user can spot the mistake.
        """
        import logging
        sensor = make_sensor()
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            result = sensor._parse_order("city, TYPO, country")
        assert result == ["city", "country"]
        assert "TYPO" in caplog.text
        assert "order" in caplog.text

    # ------------------------------------------------------------------
    # No order specified → default DISPLAY_FIELDS order preserved
    # ------------------------------------------------------------------

    def test_no_order_uses_default_field_order(self, make_sensor, hass):
        """Without order= the output matches street then city (default order)."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(origin="device_tracker.phone", options="street, city")

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"

    def test_default_multi_field_order_matches_original_hardcoded_sequence(self, make_sensor, hass):
        """Regression: DISPLAY_FIELDS order must match the original hard-coded display
        sequence so existing configs without an explicit order= key are unaffected.

        Original sequence (from pre-DISPLAY_FIELDS code):
            street_number → street → city → county → region →
            postal_town → postal_code → country → formatted_address

        This test enables all fields and asserts the exact comma-separated output,
        locking in the order so any future reordering of DISPLAY_FIELDS is caught.
        """
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street_number, street, city, county, region, postal_town, postal_code, country, formatted_address",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == (
            "10, Downing Street, London, Greater London, England, "
            "London, SW1A 2AA, United Kingdom, 10 Downing St, London SW1A 2AA, UK"
        )



    def test_custom_order_city_before_street(self, make_sensor, hass):
        """order='city, street' should produce 'London, Downing Street'."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street, city",
            order="city, street",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "London, Downing Street"

    def test_custom_order_country_first(self, make_sensor, hass):
        """order='country, city, street' respects the user preference."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street, city, country",
            order="country, city, street",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "United Kingdom, London, Downing Street"

    def test_order_only_affects_enabled_fields(self, make_sensor, hass):
        """Fields in order= but NOT in options= are excluded from display."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        # options only enables 'city'; order requests 'country, city, street'
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="city",
            order="country, city, street",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "London"

    def test_order_with_state_alias(self, make_sensor, hass):
        """order='state' (alias for region) is resolved correctly."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="state, city",
            order="state, city",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "England, London"

    def test_order_reversed_state_alias(self, make_sensor, hass):
        """order='city, state' reverses the default region/city order."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="state, city",
            order="city, state",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "London, England"

    def test_order_partial_override_unmentioned_fields_appended(self, make_sensor, hass):
        """Fields enabled in options but absent from order still appear, appended
        after the explicitly ordered fields in their default DISPLAY_FIELDS sequence.

        Here options enables street, city, country.  order only mentions city.
        Expected output: city first (as ordered), then street and country in
        their default relative positions → 'London, Downing Street, United Kingdom'.
        """
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street, city, country",
            order="city",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "London, Downing Street, United Kingdom"

    def test_order_partial_override_preserves_default_sequence_for_remainder(self, make_sensor, hass):
        """Unmentioned options fields follow the default DISPLAY_FIELDS order,
        not the order they appeared in options.

        options enables country, street, city (deliberately out of default order).
        order pins country first.  The remaining two (street, city) must appear
        in their default relative order (street before city), not in the options
        declaration order.
        """
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="country, street, city",
            order="country",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "United Kingdom, Downing Street, London"

    def test_init_stores_parsed_order(self, make_sensor):
        """The constructor parses the order string and stores it on the instance."""
        sensor = make_sensor(order="city, country")
        assert sensor._order == ["city", "country"]

    def test_init_stores_none_when_no_order(self, make_sensor):
        """When order= is not supplied the instance stores None."""
        sensor = make_sensor()
        assert sensor._order is None

    # ------------------------------------------------------------------
    # Warning logs for misspelled / unknown fields
    # ------------------------------------------------------------------

    def test_parse_order_warns_on_unknown_token(self, make_sensor, caplog):
        """A misspelled field in order= emits a WARNING and is dropped."""
        import logging
        sensor = make_sensor()
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            result = sensor._parse_order("city, ciyt, country")
        assert result == ["city", "country"]
        assert "ciyt" in caplog.text
        assert "order" in caplog.text

    def test_parse_order_warns_preserves_valid_fields(self, make_sensor, caplog):
        """Valid fields are kept even when surrounded by invalid ones."""
        import logging
        sensor = make_sensor()
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            result = sensor._parse_order("badfield1, street, badfield2, city")
        assert result == ["street", "city"]
        assert "badfield1" in caplog.text
        assert "badfield2" in caplog.text

    def test_parse_order_no_warning_for_valid_fields(self, make_sensor, caplog):
        """No warning is emitted when all order= fields are valid."""
        import logging
        sensor = make_sensor()
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            sensor._parse_order("city, street, country")
        assert caplog.text == ""


# ---------------------------------------------------------------------------
# Options parsing — _parse_options and substring-match regression
# ---------------------------------------------------------------------------

class TestParseOptions:
    """Tests for _parse_options: token-based parsing, alias resolution, typo handling."""

    def test_parse_options_returns_set_of_canonical_keys(self, make_sensor):
        from custom_components.google_geocode.sensor import GoogleGeocode
        result = GoogleGeocode._parse_options("street, city, country")
        assert result == {"street", "city", "country"}

    def test_parse_options_resolves_state_alias(self, make_sensor):
        from custom_components.google_geocode.sensor import GoogleGeocode
        result = GoogleGeocode._parse_options("state, city")
        assert "region" in result
        assert "state" not in result

    def test_parse_options_strips_whitespace_and_lowercases(self, make_sensor):
        from custom_components.google_geocode.sensor import GoogleGeocode
        result = GoogleGeocode._parse_options("  Street  ,  CITY  ")
        assert result == {"street", "city"}

    def test_parse_options_drops_unknown_token(self, make_sensor, caplog):
        import logging
        from custom_components.google_geocode.sensor import GoogleGeocode
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            result = GoogleGeocode._parse_options("street, citty, country")
        assert result == {"street", "country"}
        assert "citty" in caplog.text

    def test_parse_options_multiple_unknown_tokens_each_warned(self, make_sensor, caplog):
        """Each unrecognised token generates its own warning."""
        import logging
        from custom_components.google_geocode.sensor import GoogleGeocode
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            result = GoogleGeocode._parse_options("sreet, ctiy")
        assert result == set()
        assert "sreet" in caplog.text
        assert "ctiy" in caplog.text

    def test_parse_options_valid_tokens_no_warning(self, make_sensor, caplog):
        """No warning is emitted when all tokens are valid."""
        import logging
        from custom_components.google_geocode.sensor import GoogleGeocode
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            GoogleGeocode._parse_options("street, city, country")
        assert caplog.text == ""

    def test_parse_options_state_alias_no_warning(self, make_sensor, caplog):
        """'state' (alias for region) is accepted without a warning."""
        import logging
        from custom_components.google_geocode.sensor import GoogleGeocode
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            GoogleGeocode._parse_options("state, city")
        assert caplog.text == ""

    def test_parse_options_empty_string_returns_empty_set(self, make_sensor):
        from custom_components.google_geocode.sensor import GoogleGeocode
        result = GoogleGeocode._parse_options("")
        assert result == set()

    def test_init_stores_options_set(self, make_sensor):
        """Constructor populates _options_set from the options string."""
        sensor = make_sensor(options="street, city")
        assert sensor._options_set == {"street", "city"}

    def test_init_warns_on_unknown_options_token(self, make_sensor, caplog):
        """Constructor warns at startup when options= contains an unrecognised token."""
        import logging
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            make_sensor(options="street, ciyt")
        assert "ciyt" in caplog.text
        assert "options" in caplog.text

    def test_init_no_warning_for_valid_options(self, make_sensor, caplog):
        """No warning when the options string is fully valid."""
        import logging
        with caplog.at_level(logging.WARNING, logger="custom_components.google_geocode.sensor"):
            make_sensor(options="street, city, country")
        assert caplog.text == ""


    # ------------------------------------------------------------------
    # Substring-match regression tests
    # ------------------------------------------------------------------

    def test_street_does_not_match_when_only_street_number_in_options(self, make_sensor, hass):
        """Regression: 'street' must NOT be shown when only 'street_number' is in options.

        With the old substring check, ``'street' in 'street_number'`` was True,
        causing the street name to bleed into the output even when the user
        only requested street_number.
        """
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street_number",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        # Only the street number (10) should appear, not the street name
        assert sensor._state == "10"

    def test_street_number_does_not_show_without_street_in_options(self, make_sensor, hass):
        """When only 'street' is in options, street_number must not appear."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street"
        assert "10" not in sensor._state

    def test_county_does_not_match_country_token(self, make_sensor, hass):
        """'country' option must not cause 'county' to appear.

        With substring matching, ``'count' in 'country'`` would be True if
        the token loop was reversed; token-set membership prevents this.
        """
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="country",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        assert sensor._state == "United Kingdom"

    def test_misspelled_option_produces_no_output_for_that_field(self, make_sensor, hass):
        """A typo in options= silently drops that field without crashing."""
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="streeet, city",  # 'streeet' is a typo
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(FULL_API_RESPONSE)):
            sensor.update()

        # Only city should appear; the typo'd field is ignored
        assert sensor._state == "London"

    def test_street_number_absent_in_response_no_leading_comma(self, make_sensor, hass):
        """Regression: when street_number is enabled but absent in the API response,
        the state must not start with a leading ', ' separator.

        Previously, street_number was always appended (even as an empty string)
        and ', '.join() did not filter falsy entries, producing ', Downing Street'
        instead of 'Downing Street' when no street_number component was returned.
        """
        hass.set_state("device_tracker.phone", "not_home", {"latitude": 51.5, "longitude": -0.12})
        sensor = make_sensor(
            origin="device_tracker.phone",
            options="street_number, street, city",
        )

        with patch("custom_components.google_geocode.sensor.requests.get",
                   return_value=mock_api_response(NO_STREET_NUMBER_RESPONSE)):
            sensor.update()

        assert sensor._state == "Downing Street, London"
        assert not sensor._state.startswith(",")
