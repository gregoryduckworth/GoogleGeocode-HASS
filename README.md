# Google Geocode

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

This component has been created to be used with Home Assistant.

Google geocode is the process of converting device tracker location into a human-readable address.

The sensor will update the address each time the device tracker location changes. If the device tracker is in a zone it will display the zone.

### Credit

Full credit for this component lies with [michaelmcarthur](https://github.com/michaelmcarthur).

### Installation:

#### HACS

- Ensure that HACS is installed.
- Search for and install the "Google Geocode HASS" integration.
- Restart Home Assistant.

#### Manual installation

- Download the latest release.
- Unpack the release and copy the custom_components/google_geocode directory into the custom_components directory of your Home Assistant installation.
- Restart Home Assistant.

### Example Screenshot:

![alt text](https://github.com/gregoryduckworth/GoogleGeocode-HASS/blob/main/Google_Geocode_Screenshot.png "Screenshot")

### Example entry for configuration.yaml

```
sensor:

  - platform: google_geocode
    origin: device_tracker.mobile_phone
```

### Configuration variables:

| Name          | Required/Optional | Description                                                                                                                                                                                                                                                                                                                                                                     |
| ------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| origin        | Required          | Tracking can be setup to track entity type device_tracker. The component updates it will use the latest location of that entity and update the sensor.                                                                                                                                                                                                                          |
| name          | Optional          | A name to display on the sensor. The default is “Google Geocode"                                                                                                                                                                                                                                                                                                                |
| options       | Optional          | Select what level of address information you want. Choices are `street_number`, `street`, `city`, `postal_town`, `county`, `state`/`region`, `postal_code`, `country` or `formatted_address`. Separate multiple fields with a comma. The default is `street, city`                                                                                                              |
| order         | Optional          | Override the display order of the fields chosen in `options`. Accepts the same field names as `options`, comma-separated. When omitted the fields appear in the default order (`street_number`, `street`, `city`, `county`, `state`/`region`, `postal_town`, `postal_code`, `country`, `formatted_address`). Unknown tokens are ignored with a warning. Example: `city, street` |
| display_zone  | Optional          | Choose whether to display a zone name when the device is in a zone. Use `display` (or its alias `show`) to show the zone, or `hide` to always show the address. The default is `display`. Any unrecognised value is treated as `display` with a warning.                                                                                                                        |
| gravatar      | Optional          | An email address for the device’s owner. You can set up a Gravatar [here.](https://gravatar.com) If provided, it will override `picture` The default is 'none'                                                                                                                                                                                                                  |
| image         | Optional          | A link to an image which if provided, will override `picture` The default is 'none'                                                                                                                                                                                                                                                                                             |
| api_key       | Optional          | Your application’s API key (get one by following the instructions below). This key identifies your application for purposes of quota management. Most users will not need to use this unless multiple sensors are created.                                                                                                                                                      |
| language      | Optional          | The language with which you want to display the results from [Google Maps](https://developers.google.com/maps/documentation/javascript/localization#Language)                                                                                                                                                                                                                   |
| region        | Optional          | The region with which you want to display the results from [Google Maps](https://developers.google.com/maps/documentation/javascript/localization#Region)                                                                                                                                                                                                                       |
| scan_interval | Optional          | The frequency with which scans occur in seconds, the default is 60.                                                                                                                                                                                                                                                                                                             |
| paused_by     | Optional          | A Home Assistant entity (e.g. `input_boolean.vacation_mode`) whose state controls whether polling is active. When the entity state is `on`, all geocoding API calls are suspended and the sensor state is left unchanged. Polling resumes automatically as soon as the entity returns to `off`. The default is 'none'                                                           |

You need to register for an API key to use Google Geocode. This can be done by following these instructions

- Go to [Google Maps Platform API](https://cloud.google.com/maps-platform/#get-started)
- Click on 'Get Started'
- Select 'Maps' and 'Places' then click 'continue'
- Create a new project or select an existing one then click 'next'.
- Click 'Create Billing Account'
- Create a name for the account then click 'Continue'
- Confirm your Country then click 'Confirm'
- Fill in your detail the click 'Submit and enable billing'
- To Emable your API's Click 'Next'
- Copy your API key.

### Example with optional entry for configuration.yaml

```yaml
- platform: google_geocode
  name: michael
  origin: device_tracker.mobile_phone
  options: street_number, street, city
  display_zone: hide
  gravatar: youremail@address.com
  api_key: XXXX_XXXXX_XXXXX
  language: en-GB
  region: GB
```

### Controlling field display order

By default, address fields are displayed in the order: `street_number`, `street`, `city`, `county`, `state`/`region`, `postal_town`, `postal_code`, `country`, `formatted_address`. You can override this with the optional `order` key, using any subset of the same field names:

```yaml
sensor:
  - platform: google_geocode
    origin: device_tracker.mobile_phone
    options: street, city, country
    order: city, street, country
```

The `order` key is a **partial override**: the fields you list appear first in the sequence you choose, then any remaining `options`-enabled fields follow in the default order. Fields must still be listed in `options` to appear in the sensor state — `order` cannot enable a field on its own.

### Typo tolerance

All three text-based configuration keys (`options`, `order`, and `display_zone`) are tolerant of mistakes:

- **`options` and `order`** — each comma-separated token is checked against the list of known field names. Any unrecognised token is logged as a warning and skipped, so the sensor continues to work with the valid tokens. For example, `options: stret, city` would log a warning about `stret` and display only the city.
- **`display_zone`** — accepts `display` (or its alias `show`) and `hide`. Any other value is logged as a warning and defaults to `display`.

No misspelling will cause the sensor to crash or produce silent wrong output — you will always see a log warning pointing to the bad token.

### Pausing polling based on a Home Assistant entity

Sometimes you may want to stop the sensor from making Google Maps API calls entirely — for example, when the family is on vacation together and you already know everyone's location.

The optional `paused_by` configuration key accepts any Home Assistant entity ID. When that entity's state is `on`, all geocoding requests are suspended and the sensor state stays at its last known value. As soon as the entity flips back to `off`, polling resumes automatically on the next scan interval.

A common setup is to pair it with an `input_boolean` that you toggle via a switch or automation:

```yaml
input_boolean:
  vacation_mode:
    name: Vacation Mode
    icon: mdi:beach
```

Then reference it in your sensor configuration:

```yaml
sensor:
  - platform: google_geocode
    name: michael
    origin: device_tracker.mobile_phone
    api_key: XXXX_XXXXX_XXXXX
    paused_by: input_boolean.vacation_mode
```

Any entity that exposes an `on`/`off` state works — `input_boolean`, `switch`, `binary_sensor`, and so on.
