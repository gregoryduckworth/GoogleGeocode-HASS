# Google Geocode

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![release](https://img.shields.io/badge/release-v0.1.5-brightgreen)

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

![alt text](https://github.com/gregoryduckworth/GoogleGeocode-HASS/blob/master/Google_Geocode_Screenshot.png 'Screenshot')

### Example entry for configuration.yaml

```
sensor:

  - platform: google_geocode
    origin: device_tracker.mobile_phone
```

### Configuration variables:

|Name|Required/Optional|Description|
|----|-----------------|-----------|
| origin | Required | Tracking can be setup to track entity type device_tracker. The component updates it will use the latest location of that entity and update the sensor. |
| name | Optional | A name to display on the sensor. The default is “Google Geocode" |
| options | Optional | Select what level of address information you want. Choices are 'street_number', 'street', 'city', 'county', 'state', 'postal_code', 'country' or 'formatted_address'. You can use any combination of these options, separate each option with a comma. The default is 'street, city' |
| display_zone | Optional | Choose to display a zone when in a zone. Choices are 'show' or 'hide'. The default is 'show' |
| gravatar | Optional | An email address for the device’s owner. You can set up a Gravatar [here.](https://gravatar.com) If provided, it will override `picture` The default is 'none' |
| image | Optional | A link to an image which if provided, will override `picture` The default is 'none' |
| api_key | Optional | Your application’s API key (get one by following the instructions below). This key identifies your application for purposes of quota management. Most users will not need to use this unless multiple sensors are created. |
| language | Optional | The language with which you want to display the results from [Google Maps](https://developers.google.com/maps/documentation/javascript/localization#Language) |
| region | Optional | The region with which you want to display the results from [Google Maps](https://developers.google.com/maps/documentation/javascript/localization#Region) |
| scan_interval | Optional | The frequency with which scans occur in seconds, the default is 60. |

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

```
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
