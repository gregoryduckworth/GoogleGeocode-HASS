---
layout: page
title: "Google Geocode"
description: "Convert device tracker location into a human-readable address."
date: 2017-07-30 11:00
sidebar: true
comments: false
sharing: true
footer: true
logo: google_maps.png
ha_category: Sensor
ha_iot_class: "Cloud Polling"
ha_release: 0.6
---



The `google_geocode` sensor converts device tracker location into a human-readable address.

The sensor will update the address each time the device tracker location changes. If the device tracker is in a zone it will display the zone.

### Example Screenshot:
![alt text](https://github.com/gregoryduckworth/GoogleGeocode-HASS/blob/master/Google_Geocode_Screenshot.png "Screenshot")

### Example entry for configuration.yaml
```
sensor:
  - platform: google_geocode
    origin: device_tracker.mobile_phone
```
### Configuration variables:

**origin** (Required): Tracking can be setup to track entity type `device_tracker`. The component updates will use the latest location of that entity and update the sensor.

**name** (Optional): A name to display on the sensor. The default is `Google Geocode`.

**options** (Optional): Select what level of address information you want. Choices are `street_number`, `street`, `city`, `county`, `state` (alias for `region`), `region`, `postal_town`, `postal_code`, `country`, or `formatted_address`. Separate multiple fields with a comma. The default is `street, city`. Unknown tokens are logged as a warning and ignored — a typo will never crash the sensor.

**order** (Optional): Override the display order of the fields chosen in `options`. Accepts the same field names as `options`, comma-separated. When omitted the fields appear in the default order: `street_number`, `street`, `city`, `county`, `state`/`region`, `postal_town`, `postal_code`, `country`, `formatted_address`. The `order` key is a *partial override* — listed fields appear first in the sequence you choose, then any remaining `options`-enabled fields follow in the default order. Unknown tokens are ignored with a warning. Example: `city, street`.

**display_zone** (Optional): Choose whether to display a zone name when the device is in a zone. Use `display` (or its alias `show`) to show the zone, or `hide` to always show the address. The default is `display`. Any unrecognised value is treated as `display` with a warning.

**gravatar** (Optional): An email address for the device's owner. If provided, it overrides `picture`. The default is none.

**image** (Optional): A link to an image which, if provided, overrides `picture`. The default is none.

**api_key** (Optional): Your application's API key. Identifies your application for quota management. Most users will not need this unless multiple sensors are created.

**language** (Optional): The language in which to display results from [Google Maps](https://developers.google.com/maps/documentation/javascript/localization#Language).

**region** (Optional): The region bias to use for results from [Google Maps](https://developers.google.com/maps/documentation/javascript/localization#Region).

**scan_interval** (Optional): The frequency of updates in seconds. The default is `60`.

**paused_by** (Optional): A Home Assistant entity ID (e.g. `input_boolean.vacation_mode`). When that entity's state is `on`, all geocoding API calls are suspended and the sensor state stays at its last known value. Polling resumes automatically when the entity returns to `off`. The default is none.

### Example with optional entry for configuration.yaml
```yaml
- platform: google_geocode
  name: michael
  origin: device_tracker.mobile_phone
  options: street_number, street, city
  order: city, street
  display_zone: hide
  api_key: XXXX_XXXXX_XXXXX
  language: en-GB
  region: GB
```

Powered by [Google Maps](http://www.google.com/maps/)
