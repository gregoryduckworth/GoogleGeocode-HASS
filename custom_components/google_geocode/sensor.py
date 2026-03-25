"""
Support for Google Geocode sensors.
For more details about this platform, please refer to the documentation at
https://github.com/gregoryduckworth/GoogleGeocode-HASS
"""
from datetime import timedelta
import functools
import hashlib
import logging
import json
import os
import requests

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_API_KEY, CONF_NAME, CONF_SCAN_INTERVAL, ATTR_ATTRIBUTION, ATTR_LATITUDE, ATTR_LONGITUDE)
import homeassistant.helpers.location as location
from homeassistant.util import Throttle
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_ORIGIN = 'origin'
CONF_OPTIONS = 'options'
CONF_DISPLAY_ZONE = 'display_zone'
CONF_ATTRIBUTION = "Data provided by maps.google.com"
CONF_GRAVATAR = 'gravatar'
CONF_IMAGE = 'image'
CONF_GOOGLE_LANGUAGE = 'language'
CONF_GOOGLE_REGION = 'region'
CONF_PAUSED_BY = 'paused_by'

# Stable snake_case keys used in extra_state_attributes.  These values are the
# dict keys returned to HA (automations, templates, etc.) and must never change.
# Human-readable labels come from the translation files and are used for UI
# display only — they do not appear as attribute keys.
ATTR_STREET_NUMBER = 'street_number'
ATTR_STREET = 'street'
ATTR_CITY = 'city'
ATTR_POSTAL_TOWN = 'postal_town'
ATTR_POSTAL_CODE = 'postal_code'
ATTR_REGION = 'region'
ATTR_COUNTRY = 'country'
ATTR_COUNTY = 'county'
ATTR_FORMATTED_ADDRESS = 'formatted_address'

# Translation key used as the sensor's initial state.
STATE_AWAITING_UPDATE = 'awaiting_update'

DEFAULT_NAME = 'Google Geocode'
DEFAULT_OPTION = 'street, city'
DEFAULT_LANGUAGE = 'en-GB'
DEFAULT_REGION = 'GB'
DEFAULT_DISPLAY_ZONE = 'display'
DEFAULT_KEY = 'no key'
SCAN_INTERVAL = timedelta(seconds=60)

# ---------------------------------------------------------------------------
# Translations helpers
#
# Translation files live in translations/<lang>.json (e.g. translations/fr.json).
# translations/en.json is the English baseline and the final fallback — there is
# no separate strings.json; en.json itself serves as the canonical string set.
# To add a new language, create translations/<lang>.json with the same structure.
#
# File lookup is case-insensitive: the directory is scanned once and a map of
# lowercased stem → actual path is built.  This means pt-BR.json, pt-br.json,
# and PT-BR.JSON are all found correctly regardless of the OS file-system
# case-sensitivity, matching the varied naming conventions used by HA translators.
# ---------------------------------------------------------------------------

_TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), "translations")


@functools.lru_cache(maxsize=None)
def _build_translations_index(directory: str) -> dict:
    """Return a ``{lowercased_stem: absolute_path}`` map for every .json file
    in *directory*.

    Cached at module scope so the ``os.listdir`` scan is performed at most once
    per unique *directory* path across all sensor instances and calls.  The
    first entry wins when two files differ only in case (unlikely in practice).
    """
    index: dict[str, str] = {}
    try:
        for filename in os.listdir(directory):
            if filename.lower().endswith('.json'):
                stem = filename[:-5]          # strip .json
                key  = stem.lower()
                if key not in index:          # first entry wins
                    index[key] = os.path.join(directory, filename)
    except OSError:
        pass
    return index


@functools.lru_cache(maxsize=None)
def _load_translations(language: str) -> dict:
    """Load the translation file for *language*, falling back to English.

    Cached at module scope so the ``os.listdir`` directory scan and JSON parse
    happen at most once per unique language string across all sensor instances.

    Candidate stems are tried in order:
    1. The input as-is, lower-cased          (e.g. ``pt_br``)
    2. Hyphen-normalised form                (e.g. ``pt-br`` from ``pt_BR``)
    3. Base-language prefix                  (e.g. ``pt`` from ``pt-BR``)
    4. ``en``                                (final fallback)

    Each stem is resolved against a case-insensitive index of the translations
    directory, so ``pt-BR.json``, ``pt-br.json``, and ``PT-BR.JSON`` are all
    found correctly on case-sensitive file systems.
    """
    normalised = language.lower()
    candidates = [normalised]
    if '-' in normalised or '_' in normalised:
        hyphenated = normalised.replace('_', '-')
        if hyphenated != normalised:
            candidates.append(hyphenated)
        candidates.append(hyphenated.split('-')[0])
    candidates.append('en')

    index = _build_translations_index(_TRANSLATIONS_DIR)

    for stem in candidates:
        path = index.get(stem)
        if path:
            try:
                with open(path, encoding='utf-8') as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError) as err:
                _LOGGER.warning("Failed to load translations from %s: %s", path, err)

    return {}


def _get_state_label(translations: dict, state_key: str) -> str:
    """Return the human-readable label for *state_key* from *translations*.

    Falls back to title-casing only when *state_key* looks like a snake_case
    identifier (no spaces, no punctuation other than underscores).  Free-form
    strings — API error messages, address strings, zone names — are returned
    exactly as-is so they are never mangled by the title-case transform.
    """
    try:
        return (
            translations['entity']['sensor']['google_geocode']
            ['state'][state_key]
        )
    except (KeyError, TypeError):
        # Only apply the cosmetic snake_case → Title Case transform for strings
        # that look like translation keys (all word-chars / underscores, no
        # spaces or punctuation).  Everything else is a raw user-facing value
        # (address string, zone name, API error message) and must be unchanged.
        if state_key.replace('_', '').isalnum():
            return state_key.replace('_', ' ').title()
        return state_key

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_ORIGIN): cv.string,
    vol.Optional(CONF_API_KEY, default=DEFAULT_KEY): cv.string,
    vol.Optional(CONF_OPTIONS, default=DEFAULT_OPTION): cv.string,
    vol.Optional(CONF_GOOGLE_LANGUAGE, default=DEFAULT_LANGUAGE): cv.string,
    vol.Optional(CONF_GOOGLE_REGION, default=DEFAULT_REGION): cv.string,
    vol.Optional(CONF_DISPLAY_ZONE, default=DEFAULT_DISPLAY_ZONE): cv.string,
    vol.Optional(CONF_GRAVATAR, default=None): vol.Any(None, cv.string),
    vol.Optional(CONF_IMAGE, default=None): vol.Any(None, cv.string),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL): cv.time_period,
    vol.Optional(CONF_PAUSED_BY, default=None): vol.Any(None, cv.entity_id),
})

TRACKABLE_DOMAINS = ['device_tracker', 'sensor', 'person']

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the sensor platform."""
    name = config.get(CONF_NAME)
    api_key = config.get(CONF_API_KEY)
    origin = config.get(CONF_ORIGIN)
    options = config.get(CONF_OPTIONS)
    google_language = config.get(CONF_GOOGLE_LANGUAGE)
    google_region = config.get(CONF_GOOGLE_REGION)
    display_zone = config.get(CONF_DISPLAY_ZONE)
    gravatar = config.get(CONF_GRAVATAR) 
    image = config.get(CONF_IMAGE)
    paused_by = config.get(CONF_PAUSED_BY)

    add_devices([GoogleGeocode(hass, origin, name, api_key, options, google_language, google_region, display_zone, gravatar, image, paused_by)])

class GoogleGeocode(Entity):
    """Representation of a Google Geocode Sensor."""

    def __init__(self, hass, origin, name, api_key, options, google_language, google_region, display_zone, gravatar, image, paused_by=None):
        """Initialize the sensor."""
        self._hass = hass
        self._name = name
        self._api_key = api_key
        self._options = options.lower()
        self._google_language = google_language.lower()
        self._google_region = google_region.lower()
        self._display_zone = display_zone.lower()
        self._gravatar = gravatar
        self._image = image
        self._paused_by_entity_id = paused_by

        # Load translations for the configured language (falls back to English).
        # Use the already-normalised self._google_language so the lookup is
        # consistent with the lower-cased value stored on the instance.
        self._translations = _load_translations(self._google_language)

        # _state holds a stable, language-independent value: either the
        # STATE_AWAITING_UPDATE key, a raw address string built from the API
        # response, or a zone name.  Translations are for UI rendering only and
        # must never be stored here so that automations comparing state strings
        # work regardless of the configured language.
        self._state = STATE_AWAITING_UPDATE

        self._street_number = None
        self._street = None
        self._city = None
        self._postal_town = None
        self._postal_code = None
        self._region = None
        self._country = None
        self._county = None
        self._formatted_address = None
        self._zone_check_current = None

        # Instance-level tracking variables (replacing module-level globals).
        # _current_location guards against re-geocoding the same coordinates.
        # _zone_check_current guards against re-geocoding the same named zone.
        # _zone_check is retained for backward-compatibility only and is not
        # read by any logic.
        self._current_location = '0,0'
        self._zone_check = 'a'

        # Check if origin is a trackable entity
        if origin.split('.', 1)[0] in TRACKABLE_DOMAINS:
            self._origin_entity_id = origin
        else:
            self._origin = origin

        if gravatar is not None:
            self._picture = self._get_gravatar_for_email(gravatar)
        elif image is not None:
            self._picture = self._get_image_from_url(image)
        else:
            self._picture = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor.

        Known stable keys (e.g. ``STATE_AWAITING_UPDATE``) are resolved to
        their translated, human-readable label so the UI and automations always
        see a localised string.  Address strings and zone names set during
        ``update()`` are already user-facing and are returned as-is.
        """
        return _get_state_label(self._translations, self._state)

    @property
    def entity_picture(self):
        """Return the picture of the device."""
        return self._picture

    @property
    def extra_state_attributes(self):
        """Return the state attributes.

        Keys are the stable snake_case ``ATTR_*`` identifiers so that
        automations, template sensors, and other consumers are unaffected by
        the configured display language.  Translation labels are used only for
        UI rendering (e.g. the Lovelace card), not as dict keys.
        """
        return {
            ATTR_STREET_NUMBER: self._street_number,
            ATTR_STREET: self._street,
            ATTR_CITY: self._city,
            ATTR_POSTAL_TOWN: self._postal_town,
            ATTR_POSTAL_CODE: self._postal_code,
            ATTR_REGION: self._region,
            ATTR_COUNTRY: self._country,
            ATTR_COUNTY: self._county,
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
            ATTR_FORMATTED_ADDRESS: self._formatted_address,
        }

    @Throttle(SCAN_INTERVAL)
    def update(self):
        """Get the latest data and updates the states."""

        # Skip polling if a paused_by entity is configured and its state is 'on'
        if self._paused_by_entity_id is not None:
            paused_by_state = self._hass.states.get(self._paused_by_entity_id)
            if paused_by_state is not None and paused_by_state.state == 'on':
                _LOGGER.debug(
                    "Polling paused: %s is 'on'", self._paused_by_entity_id
                )
                return

        if hasattr(self, '_origin_entity_id'):
            self._origin = self._get_location_from_entity(
                self._origin_entity_id
            )

        # Don't update anything if no origin location
        if self._origin is None:
            return

        # If location is still the same then do not update
        if self._current_location == self._origin:
            return

        if hasattr(self, '_origin_entity_id') and self.hass.states.get(self._origin_entity_id) is not None:
            zone_check = self.hass.states.get(self._origin_entity_id).state
        else:
            zone_check = 'not_home'

        # Do not update location if zone is still the same and defined (not not_home)
        if zone_check == self._zone_check_current and zone_check != 'not_home':
            return

        self._zone_check_current = zone_check
        self._current_location = self._origin
        self._reset_attributes()

        if self._api_key == DEFAULT_KEY:
            url = (
                f"https://maps.google.com/maps/api/geocode/json"
                f"?language={self._google_language}&region={self._google_region}&latlng={self._origin}"
            )
        else:
            url = (
                f"https://maps.googleapis.com/maps/api/geocode/json"
                f"?language={self._google_language}&region={self._google_region}&latlng={self._origin}&key={self._api_key}"
            )
        _LOGGER.debug("Google request sent: %s", url)
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to retrieve geocode from Google. Error: %s", err)
            return
        decoded = json.loads(response.text)
        street_number = ''
        street = 'Unnamed Road'
        alt_street = 'Unnamed Road'
        city = ''
        postal_town = ''
        formatted_address = ''
        state = ''
        county = ''
        country = ''
        postal_code = ''

        for result in decoded["results"]:
            for component in result["address_components"]:
                if 'street_number' in component["types"]:
                    if street_number == '':
                        street_number = component["long_name"]
                        self._street_number = street_number
                if 'route' in component["types"]:
                    if street == 'Unnamed Road':
                        street = component["long_name"]
                        self._street = street
                if 'sublocality_level_1' in component["types"]:
                    if alt_street == 'Unnamed Road':
                        alt_street = component["long_name"]
                if 'postal_town' in component["types"]:
                    if postal_town == '':
                        postal_town = component["long_name"]
                        self._postal_town = postal_town
                if 'locality' in component["types"]:
                    if city == '':
                        city = component["long_name"]
                        self._city = city
                if 'administrative_area_level_1' in component["types"]:
                    if state == '':
                        state = component["long_name"]
                        self._region = state
                if 'administrative_area_level_2' in component["types"]:
                    if county == '':
                        county = component["long_name"]
                        self._county = county
                if 'country' in component["types"]:
                    if country == '':
                        country = component["long_name"]
                        self._country = country
                if 'postal_code' in component["types"]:
                    if postal_code == '':
                        postal_code = component["long_name"]
                        self._postal_code = postal_code

        try:
            if 'formatted_address' in decoded['results'][0]:
                formatted_address = decoded['results'][0]['formatted_address']
                self._formatted_address = formatted_address
        except IndexError:
            pass

        if 'error_message' in decoded:
            self._state = decoded['error_message']
            _LOGGER.error(
                "You have exceeded your daily requests or entered an incorrect key. "
                "Please create or check the API key."
            )
        elif self._display_zone == 'hide' or zone_check == "not_home":
            if street == 'Unnamed Road':
                street = alt_street
                self._street = alt_street
            if city == '':
                city = postal_town
                if city == '':
                    city = county

            display_options = self._options
            user_display = []

            if "street_number" in display_options:
                user_display.append(street_number)
            if "street" in display_options:
                user_display.append(street)
            if "city" in display_options:
                self._append_to_user_display(user_display, city)
            if "county" in display_options:
                self._append_to_user_display(user_display, county)
            if "state" in display_options:
                self._append_to_user_display(user_display, state)
            if "postal_town" in display_options:
                self._append_to_user_display(user_display, postal_town)
            if "postal_code" in display_options:
                self._append_to_user_display(user_display, postal_code)
            if "country" in display_options:
                self._append_to_user_display(user_display, country)
            if "formatted_address" in display_options:
                self._append_to_user_display(user_display, formatted_address)

            user_display_str = ', '.join(x for x in user_display)

            if user_display_str == '':
                user_display_str = street
            self._state = user_display_str
        else:
            self._state = zone_check[0].upper() + zone_check[1:]

    def _get_location_from_entity(self, entity_id):
        """Get the origin from the entity state or attributes."""
        entity = self._hass.states.get(entity_id)

        if entity is None:
            _LOGGER.error("Unable to find entity %s", entity_id)
            return None

        # Check if the entity has origin attributes
        if location.has_location(entity):
            return self._get_location_from_attributes(entity)

        # When everything fails just return nothing
        return None

    def _reset_attributes(self):
        """Resets attributes."""
        self._street = None
        self._street_number = None
        self._city = None
        self._postal_town = None
        self._postal_code = None
        self._region = None
        self._country = None
        self._county = None
        self._formatted_address = None

    def _append_to_user_display(self, user_display, append_check):
        """Appends a value to the display list if the value is not empty."""
        if append_check:
            user_display.append(append_check)

    @staticmethod
    def _get_location_from_attributes(entity):
        """Get the lat/long string from an entities attributes."""
        attr = entity.attributes
        return "%s,%s" % (attr.get(ATTR_LATITUDE), attr.get(ATTR_LONGITUDE))

    def _get_gravatar_for_email(self, email: str):
        """Return an 80px Gravatar for the given email address. Async friendly."""
        url = 'https://www.gravatar.com/avatar/{}.jpg?s=80&d=wavatar'
        return url.format(hashlib.md5(email.encode('utf-8').lower()).hexdigest())

    @staticmethod
    def _get_image_from_url(url: str):
        """Return the image URL as-is. Async friendly."""
        return url
