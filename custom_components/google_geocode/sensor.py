"""
Support for Google Geocode sensors.
For more details about this platform, please refer to the documentation at
https://github.com/gregoryduckworth/GoogleGeocode-HASS
"""
from datetime import datetime
from datetime import timedelta 
import logging
import json
import requests
from requests import get

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

ATTR_STREET_NUMBER = 'Street Number'
ATTR_STREET = 'Street'
ATTR_CITY = 'City'
ATTR_POSTAL_TOWN = 'Postal Town'
ATTR_POSTAL_CODE = 'Postal Code'
ATTR_REGION = 'State'
ATTR_COUNTRY = 'Country'
ATTR_COUNTY = 'County'
ATTR_FORMATTED_ADDRESS = 'Formatted Address'

DEFAULT_NAME = 'Google Geocode'
DEFAULT_OPTION = 'street, city'
DEFAULT_LANGUAGE = 'en-GB'
DEFAULT_REGION = 'GB'
DEFAULT_DISPLAY_ZONE = 'display'
DEFAULT_KEY = 'no key'
current = '0,0'
zone_check = 'a'
SCAN_INTERVAL = timedelta(seconds=60)

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
})

TRACKABLE_DOMAINS = ['device_tracker', 'sensor', 'person']

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""
    name = config.get(CONF_NAME)
    api_key = config.get(CONF_API_KEY)
    origin = config.get(CONF_ORIGIN)
    options = config.get(CONF_OPTIONS)
    google_language = config.get(CONF_GOOGLE_LANGUAGE)
    google_region = config.get(CONF_GOOGLE_REGION)
    display_zone = config.get(CONF_DISPLAY_ZONE)
    gravatar = config.get(CONF_GRAVATAR) 
    image = config.get(CONF_IMAGE) 

    add_devices([GoogleGeocode(hass, origin, name, api_key, options, google_language, google_region, display_zone, gravatar, image)])

class GoogleGeocode(Entity):
    """Representation of a Google Geocode Sensor."""

    def __init__(self, hass, origin, name, api_key, options, google_language, google_region, display_zone, gravatar, image):
        """Initialize the sensor."""
        self._hass = hass
        self._name = name
        self._api_key = api_key
        self._options = options.lower()
        self._google_language = google_language.lower()
        self._google_region = google_region.lower()
        self._display_zone = display_zone.lower()
        self._state = "Awaiting Update"
        self._gravatar = gravatar
        self._image = image

        self._street_number = None
        self._street = None
        self._city = None
        self._postal_town = None
        self._postal_code = None
        self._city = None
        self._region = None
        self._country = None
        self._county = None
        self._formatted_address = None
        self._zone_check_current = None

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
        """Return the state of the sensor."""
        return self._state

    @property
    def entity_picture(self):
        """Return the picture of the device."""
        return self._picture

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return{
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

        if hasattr(self, '_origin_entity_id'):
            self._origin = self._get_location_from_entity(
                self._origin_entity_id
            )

        """Update if location has changed."""

        global current
        global zone_check
        global user_display

        # Don't update anyting if no origin location
        if self._origin is None:
            return

        # If location is still same then do not update.
        if current == self._origin:
            return

        if self.hass.states.get(self._origin_entity_id) is not None:
            zone_check = self.hass.states.get(self._origin_entity_id).state
        else: 
            zone_check = 'not_home'

        # Do not update location if zone is still the same and defined (not not_home)
        if zone_check == self._zone_check_current and zone_check != 'not_home':    
            return

        self._zone_check_current = zone_check
        lat = self._origin
        current = lat
        self._reset_attributes()
        if self._api_key == 'no key':
            url = "https://maps.google.com/maps/api/geocode/json?language=" + self._google_language + "&region=" + self._google_region + "&latlng=" + lat
        else:
            url = "https://maps.googleapis.com/maps/api/geocode/json?language=" + self._google_language + "&region=" + self._google_region + "&latlng=" + lat + "&key=" + self._api_key
        _LOGGER.debug("Google request sent: " + url)
        try:
            response = get(url, timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to retrieve geocode from Google. Error: %s", err)
            return
        json_input = response.text
        decoded = json.loads(json_input)
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
            _LOGGER.error("You have exceeded your daily requests or entered a incorrect key please create or check the api key.")
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
                self._append_to_user_display(city)
            if "county" in display_options:
                self._append_to_user_display(county)
            if "state" in display_options:
                self._append_to_user_display(state)
            if "postal_town" in display_options:
                self._append_to_user_display(postal_town)
            if "postal_code" in display_options:
                self._append_to_user_display(postal_code)
            if "country" in display_options:
                self._append_to_user_display(country)
            if "formatted_address" in display_options:
                self._append_to_user_display(formatted_address)

            user_display = ', '.join(  x for x in user_display )

            if user_display == '':
                user_display = street
            self._state = user_display
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

    def _append_to_user_display(self, append_check):
        """Appends attribute to state if false."""
        if append_check == "":
            pass
        else:
            user_display.append(append_check)

    @staticmethod
    def _get_location_from_attributes(entity):
        """Get the lat/long string from an entities attributes."""
        attr = entity.attributes
        return "%s,%s" % (attr.get(ATTR_LATITUDE), attr.get(ATTR_LONGITUDE))

    def _get_gravatar_for_email(self, email: str):
        """Return an 80px Gravatar for the given email address. Async friendly."""
        import hashlib
        url = 'https://www.gravatar.com/avatar/{}.jpg?s=80&d=wavatar'
        return url.format(hashlib.md5(email.encode('utf-8').lower()).hexdigest())

    def _get_image_from_url(self, url: str):
        """Return an image from a given url. Async friendly."""
        import hashlib
        return url.format(hashlib.md5(url.encode('utf-8').lower()).hexdigest())
