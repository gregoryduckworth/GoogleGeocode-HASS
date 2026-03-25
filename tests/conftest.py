"""Pytest configuration — installs HA stubs and provides shared fixtures."""
import json
import sys
import os
import types

# ---------------------------------------------------------------------------
# Insert the stubs directory so that `import homeassistant.*` resolves to our
# lightweight stubs instead of requiring a real HA installation.
# ---------------------------------------------------------------------------
STUBS_DIR = os.path.join(os.path.dirname(__file__), "stubs")
sys.path.insert(0, STUBS_DIR)

# Also make the repo root importable so custom_components can be found.
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)

import pytest


# ---------------------------------------------------------------------------
# Minimal Home-Assistant state / hass stubs used across tests
# ---------------------------------------------------------------------------

class FakeState:
    """Minimal stub for a HA state object."""

    def __init__(self, state: str, attributes: dict | None = None):
        self.state = state
        self.attributes = attributes or {}


class FakeHass:
    """Minimal stub for the HA `hass` object.

    Exposes a ``states`` attribute that mimics ``hass.states.get(entity_id)``
    so that sensor code under test can look up entity states without a real
    Home Assistant instance.
    """

    class _StatesProxy:
        """Proxy that forwards ``.get()`` calls to the internal state registry."""

        def __init__(self, registry):
            self._registry = registry

        def get(self, entity_id):
            return self._registry.get(entity_id)

    def __init__(self):
        self._registry: dict[str, FakeState] = {}
        self.states = self._StatesProxy(self._registry)

    def set_state(self, entity_id: str, state: str, attributes: dict | None = None):
        self._registry[entity_id] = FakeState(state, attributes)


@pytest.fixture
def hass():
    """Return a fresh FakeHass instance."""
    return FakeHass()


@pytest.fixture
def make_sensor(hass):
    """Factory fixture — returns a GoogleGeocode instance without calling update()."""
    from custom_components.google_geocode.sensor import GoogleGeocode

    def _factory(
        origin="device_tracker.phone",
        name="Google Geocode",
        api_key="no key",
        options="street, city",
        language="en-gb",
        region="gb",
        display_zone="display",
        gravatar=None,
        image=None,
    ):
        sensor = GoogleGeocode(
            hass,
            origin,
            name,
            api_key,
            options,
            language,
            region,
            display_zone,
            gravatar,
            image,
        )
        sensor.hass = hass
        return sensor

    return _factory


# ---------------------------------------------------------------------------
# Reusable mock Google API responses
# ---------------------------------------------------------------------------

FULL_API_RESPONSE = {
    "results": [
        {
            "formatted_address": "10 Downing St, London SW1A 2AA, UK",
            "address_components": [
                {"long_name": "10", "types": ["street_number"]},
                {"long_name": "Downing Street", "types": ["route"]},
                {"long_name": "Westminster", "types": ["sublocality_level_1"]},
                {"long_name": "London", "types": ["postal_town"]},
                {"long_name": "London", "types": ["locality"]},
                {"long_name": "England", "types": ["administrative_area_level_1"]},
                {"long_name": "Greater London", "types": ["administrative_area_level_2"]},
                {"long_name": "United Kingdom", "types": ["country"]},
                {"long_name": "SW1A 2AA", "types": ["postal_code"]},
            ],
        }
    ]
}

EMPTY_RESULTS_RESPONSE = {"results": []}

ERROR_RESPONSE = {
    "results": [],
    "error_message": "The provided API key is invalid.",
    "status": "REQUEST_DENIED",
}


# ---------------------------------------------------------------------------
# Shared HTTP mock helper
# ---------------------------------------------------------------------------

def mock_api_response(payload: dict, status_code: int = 200, raise_for_status=None):
    """Return a mock requests.Response-like object.

    Used by test_sensor.py, test_update.py, and any other test module that
    needs to simulate a Google Geocode API response without making a real
    HTTP request.
    """
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.text = json.dumps(payload)
    mock.status_code = status_code
    if raise_for_status is not None:
        mock.raise_for_status.side_effect = raise_for_status
    else:
        mock.raise_for_status.return_value = None
    return mock
